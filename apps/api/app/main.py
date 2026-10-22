import asyncio
import hmac
import json
import math
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from statistics import mean
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, engine, get_db
from app.models import Audit, Base, Deployment, Event, Incident, Log, Monitor, MonitorCheck, Timeline, now
from app.schemas import (
    DeploymentCreate,
    IncidentCreate,
    IncidentUpdate,
    LogBatch,
    LogCreate,
    MonitorCreate,
    MonitorUpdate,
)
from app.security import validate_target
from app.seed import seed_demo
from app.services import (
    analyze_incident,
    audit,
    check_monitor,
    create_incident,
    ingest,
    iso,
    monitor_data,
    serialize,
)

settings = get_settings()
Db = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(_app):
    if settings.demo_mode:
        Base.metadata.create_all(engine)
        if settings.seed_demo:
            with SessionLocal() as db:
                seed_demo(db)
    worker = thread = None
    if settings.run_worker:
        from app.worker import Worker

        worker = Worker()
        thread = threading.Thread(target=worker.run, daemon=True, name="tracehunt-worker")
        thread.start()
    yield
    if worker:
        worker.stop.set()
        thread.join(timeout=5)


app = FastAPI(
    title="TraceHunt AI",
    version="1.0.0",
    description="Observability, durable incident detection, and evidence-based incident intelligence.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)


class BodyLimitMiddleware:
    """Bound actual request bytes even when Content-Length is omitted or dishonest."""

    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        size = 0
        chunks = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.maximum:
                response = JSONResponse({"detail": "Request body exceeds limit"}, status_code=413)
                return await response(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if chunks:
                return chunks.pop(0)
            return await receive()

        await self.app(scope, replay, send)


app.add_middleware(BodyLimitMiddleware, maximum=settings.max_body_bytes)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # Do not echo submitted secrets or non-JSON float values in validation errors.
    return JSONResponse(
        status_code=422,
        content={"detail": [{key: error[key] for key in ("type", "loc", "msg")} for error in exc.errors()]},
    )


def authenticate(x_api_key: Annotated[str | None, Header()] = None):
    if not settings.demo_mode and (
        not x_api_key or not hmac.compare_digest(x_api_key.encode("utf-8"), settings.api_key.encode("utf-8"))
    ):
        raise HTTPException(401, "A valid X-API-Key header is required")


router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])


@app.get("/health", tags=["Health"])
@app.get("/api/v1/health", tags=["Health"])
def health():
    return {"status": "ok", "version": "1.0.0", "demo_mode": settings.demo_mode}


@app.get("/ready", tags=["Health"])
@app.get("/api/v1/ready", tags=["Health"])
def ready():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db.execute(select(Monitor.id).limit(1))
    except Exception:
        return JSONResponse({"status": "not_ready", "database": "unavailable"}, status_code=503)
    return {
        "status": "ready",
        "database": "connected",
        "queue": "redis_with_sql_fallback" if settings.redis_url else "sql_outbox",
    }


def require(db, model, row_id):
    row = db.get(model, row_id)
    if row is None:
        raise HTTPException(404, "Resource not found")
    return row


def latency_value(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except OverflowError:
        return None


@router.get("/overview")
def overview(db: Db, hours: int = Query(default=24, ge=1, le=168)):
    timestamp = now()
    since = timestamp - timedelta(hours=hours)
    logs = list(
        db.scalars(select(Log).where(Log.created_at >= since).order_by(Log.created_at.desc()).limit(50000))
    )
    checks = list(db.scalars(select(MonitorCheck).where(MonitorCheck.created_at >= since).limit(50000)))
    total = db.scalar(select(func.count()).select_from(Log).where(Log.created_at >= since)) or 0
    error_count = (
        db.scalar(
            select(func.count())
            .select_from(Log)
            .where(Log.created_at >= since, Log.level.in_(["ERROR", "FATAL"]))
        )
        or 0
    )
    latencies = sorted(
        value for row in logs if (value := latency_value(row.attributes.get("latency_ms"))) is not None
    )
    if not latencies:
        latencies = sorted(row.latency for row in checks)
    p95 = latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)] if latencies else 0
    monitors = list(db.scalars(select(Monitor).order_by(Monitor.name)))
    active = db.scalar(select(func.count()).select_from(Incident).where(Incident.status != "resolved"))
    bucket_seconds = hours * 3600 / 24
    buckets = [
        {
            "time": iso(since + timedelta(seconds=index * bucket_seconds)),
            "requests": 0,
            "errors": 0,
            "latency": 0,
            "_latencies": [],
        }
        for index in range(24)
    ]
    grouped = defaultdict(list)
    for row in logs:
        grouped[row.service].append(row)
        index = min(23, max(0, int((row.created_at - since).total_seconds() / bucket_seconds)))
        bucket = buckets[index]
        bucket["requests"] += 1
        bucket["errors"] += row.level in ("ERROR", "FATAL")
        value = latency_value(row.attributes.get("latency_ms"))
        if value is not None:
            bucket["_latencies"].append(value)
    for bucket in buckets:
        values = bucket.pop("_latencies")
        bucket["latency"] = round(mean(values), 1) if values else 0
    services = []
    service_names = sorted(set(grouped) | {monitor.name for monitor in monitors})
    for name in service_names:
        records = grouped[name]
        errors = sum(row.level in ("ERROR", "FATAL") for row in records)
        monitor = next((item for item in monitors if item.name == name), None)
        values = [
            value for row in records if (value := latency_value(row.attributes.get("latency_ms"))) is not None
        ]
        monitor_stats = monitor_data(db, monitor, since=since) if monitor else {}
        services.append(
            {
                "id": monitor.id if monitor else name,
                "name": name,
                "status": monitor.status if monitor else "degraded" if errors else "up",
                "uptime": monitor_stats.get(
                    "uptime", round((1 - errors / len(records)) * 100, 2) if records else 100
                ),
                "latency": round(mean(values), 1) if values else monitor.last_latency if monitor else 0,
                "error_rate": round(errors / len(records) * 100, 2) if records else 0,
                "requests": len(records),
            }
        )
    return {
        "stats": {
            "requests_24h": total,
            "error_rate": round(error_count / total * 100, 2) if total else 0,
            "p95_latency": round(p95, 1),
            "uptime": round(sum(item.success for item in checks) / len(checks) * 100, 2) if checks else 100,
            "active_incidents": active,
            "monitors_up": sum(item.status == "up" for item in monitors),
            "monitors_total": len(monitors),
        },
        "traffic": buckets,
        "services": services,
        "hours": hours,
        "sampled": total > 50000,
        "sample_limit": 50000,
        "recent_incidents": [
            serialize(row)
            for row in db.scalars(select(Incident).order_by(Incident.created_at.desc()).limit(5))
        ],
        "recent_deployments": [
            serialize(row)
            for row in db.scalars(select(Deployment).order_by(Deployment.created_at.desc()).limit(5))
        ],
        "activity": [
            serialize(row) for row in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(8))
        ],
    }


@router.get("/monitors")
def list_monitors(db: Db):
    return [monitor_data(db, row) for row in db.scalars(select(Monitor).order_by(Monitor.created_at.desc()))]


@router.post("/monitors", status_code=201)
def add_monitor(data: MonitorCreate, db: Db):
    try:
        validate_target(data.url, resolve=data.enabled)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = Monitor(**data.model_dump())
    db.add(row)
    db.flush()
    audit(db, "monitor.created", row.id, f"Created monitor {row.name}.", actor="operator")
    db.commit()
    return monitor_data(db, row)


@router.patch("/monitors/{monitor_id}")
def update_monitor(monitor_id: str, data: MonitorUpdate, db: Db):
    row = require(db, Monitor, monitor_id)
    if data.enabled and not row.is_demo:
        try:
            validate_target(row.url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    row.enabled = data.enabled
    row.next_check = now()
    audit(
        db, "monitor.updated", row.id, f"Monitor {'enabled' if row.enabled else 'paused'}.", actor="operator"
    )
    db.commit()
    return monitor_data(db, row)


@router.post("/monitors/{monitor_id}/check")
def run_check(monitor_id: str, db: Db):
    row = require(db, Monitor, monitor_id)
    check_monitor(db, row)
    db.commit()
    return monitor_data(db, row)


@router.delete("/monitors/{monitor_id}", status_code=204)
def remove_monitor(monitor_id: str, db: Db):
    row = require(db, Monitor, monitor_id)
    db.execute(delete(MonitorCheck).where(MonitorCheck.monitor_id == row.id))
    audit(db, "monitor.deleted", row.id, f"Deleted monitor {row.name}.", actor="operator")
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/logs")
def list_logs(
    db: Db,
    search: str = Query(default="", max_length=200),
    level: str = Query(default="", max_length=10),
    service: str = Query(default="", max_length=120),
    limit: int = Query(default=100, ge=1, le=1000),
):
    query = select(Log)
    if search:
        query = query.where(
            Log.message.icontains(search, autoescape=True) | Log.trace_id.icontains(search, autoescape=True)
        )
    if level and level.lower() != "all":
        query = query.where(Log.level == ("WARN" if level.upper() == "WARNING" else level.upper()))
    if service and service.lower() != "all":
        query = query.where(Log.service == service)
    return [serialize(row) for row in db.scalars(query.order_by(Log.created_at.desc()).limit(limit))]


@router.post("/logs", status_code=201)
def add_log(data: LogCreate, db: Db):
    row = ingest(db, data)
    db.commit()
    return serialize(row)


@router.post("/logs/batch", status_code=201)
def add_logs(data: LogBatch, db: Db):
    ids = [ingest(db, item).id for item in data.logs]
    db.commit()
    return {"accepted": len(ids), "ids": ids}


@router.get("/incidents")
def list_incidents(
    db: Db,
    status: str = Query(default="", max_length=20),
    severity: str = Query(default="", max_length=10),
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
):
    query = select(Incident)
    if status and status != "all":
        query = query.where(Incident.status == status)
    if severity and severity != "all":
        query = query.where(Incident.severity == severity)
    if search:
        query = query.where(
            Incident.title.icontains(search, autoescape=True)
            | Incident.service.icontains(search, autoescape=True)
        )
    return [serialize(row) for row in db.scalars(query.order_by(Incident.created_at.desc()).limit(limit))]


@router.post("/incidents", status_code=201)
def add_incident(data: IncidentCreate, db: Db):
    row = create_incident(db, **data.model_dump())
    db.commit()
    return serialize(row)


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str, db: Db):
    row = serialize(require(db, Incident, incident_id))
    row["timeline"] = [
        serialize(item)
        for item in db.scalars(
            select(Timeline).where(Timeline.incident_id == incident_id).order_by(Timeline.created_at)
        )
    ]
    return row


@router.patch("/incidents/{incident_id}")
def update_incident(incident_id: str, data: IncidentUpdate, db: Db):
    row = require(db, Incident, incident_id)
    if row.status != data.status:
        row.status, row.updated_at = data.status, now()
        row.resolved_at = now() if data.status == "resolved" else None
        db.add(Timeline(incident_id=row.id, kind="status", message=f"Status changed to {data.status}."))
        audit(db, "incident.updated", row.id, f"Incident marked {data.status}.", actor="operator")
        db.commit()
    return serialize(row)


@router.post("/incidents/{incident_id}/analyze")
def analyze(incident_id: str, db: Db):
    result = analyze_incident(db, require(db, Incident, incident_id))
    db.commit()
    return result


@router.get("/deployments")
def list_deployments(db: Db, limit: int = Query(default=100, ge=1, le=500)):
    return [
        serialize(row)
        for row in db.scalars(select(Deployment).order_by(Deployment.created_at.desc()).limit(limit))
    ]


@router.post("/deployments", status_code=201)
def add_deployment(data: DeploymentCreate, db: Db):
    row = Deployment(**data.model_dump())
    db.add(row)
    db.flush()
    audit(db, "deployment.created", row.id, f"{row.service} {row.version}: {row.status}.", actor="operator")
    db.commit()
    return serialize(row)


@router.get("/audit")
def list_audit(db: Db, limit: int = Query(default=100, ge=1, le=500)):
    return [
        serialize(row) for row in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(limit))
    ]


@router.get("/settings")
def safe_settings():
    return {
        "version": "1.0.0",
        "demo_mode": settings.demo_mode,
        "ai_enabled": bool(settings.openai_api_key),
        "ai_provider": "openai" if settings.openai_api_key else "heuristic",
        "redis_configured": bool(settings.redis_url),
        "alerts_enabled": bool(settings.alert_webhook_url),
        "monitor_allow_private_networks": settings.monitor_allow_private_networks,
        "retention_days": settings.retention_days,
        "error_threshold": settings.error_threshold,
        "error_window_seconds": settings.error_window_seconds,
    }


def fetch_activity(cursor: tuple[datetime, str]):
    """Keep full timestamp precision and a tie-breaker across paginated SSE polls."""
    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(Audit)
                .where(
                    or_(
                        Audit.created_at > cursor[0],
                        and_(Audit.created_at == cursor[0], Audit.id > cursor[1]),
                    )
                )
                .order_by(Audit.created_at, Audit.id)
                .limit(100)
            )
        )
        next_cursor = (rows[-1].created_at, rows[-1].id) if rows else cursor
        return [serialize(row) for row in rows], next_cursor


@router.get("/events")
async def events(request: Request):
    async def stream():
        cursor = (now(), "")
        yield "event: connected\ndata: {}\n\n"
        while not await request.is_disconnected():
            # Short-lived synchronous sessions run in a thread; never retain them across SSE waits.
            rows, cursor = await asyncio.to_thread(fetch_activity, cursor)
            for row in rows:
                yield f"id: {row['id']}\nevent: activity\ndata: {json.dumps(row)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(3)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/metrics", dependencies=[Depends(authenticate)], include_in_schema=False)
@router.get("/metrics")
def metrics(db: Db):
    lines = []
    for name, model, condition, description in [
        ("tracehunt_logs_total", Log, None, "Persisted log events."),
        (
            "tracehunt_incidents_active",
            Incident,
            Incident.status != "resolved",
            "Open or investigating incidents.",
        ),
        ("tracehunt_monitors_total", Monitor, None, "Configured monitors."),
        ("tracehunt_events_pending", Event, Event.processed.is_(False), "Unprocessed durable events."),
    ]:
        query = select(func.count()).select_from(model)
        if condition is not None:
            query = query.where(condition)
        lines.extend([f"# HELP {name} {description}", f"# TYPE {name} gauge", f"{name} {db.scalar(query)}"])
    return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")


app.include_router(router)
