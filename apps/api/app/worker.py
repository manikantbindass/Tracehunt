"""Durable event processor and monitor scheduler. Run: python -m app.worker."""

import logging
import signal
import threading
import time
from datetime import timedelta

from sqlalchemy import delete, or_, select, update

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Audit, Base, Event, Incident, Log, Monitor, MonitorCheck, now
from app.security import safe_request
from app.services import analyze_incident, audit, check_monitor, emit, open_anomaly

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self):
        self.stop = threading.Event()
        self.redis = None
        self.last_cleanup = 0.0
        self.consumer = __import__("uuid").uuid4().hex
        if get_settings().redis_url:
            import redis

            self.redis = redis.Redis.from_url(
                get_settings().redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
            )

    def handle(self, db, event):
        if event.kind == "log.error":
            from app.services import evaluate_errors

            evaluate_errors(db, event.payload["service"])
        elif event.kind == "monitor.failed":
            monitor = db.get(Monitor, event.payload["monitor_id"])
            if monitor and monitor.status in ("down", "degraded"):
                open_anomaly(
                    db,
                    f"monitor:{monitor.id}",
                    f"{monitor.name} is {monitor.status}",
                    monitor.name,
                    "critical" if monitor.status == "down" else "medium",
                    f"Monitor detected {monitor.status}. Latest latency: {monitor.last_latency:.0f} ms.",
                )
        elif event.kind == "incident.created":
            incident = db.get(Incident, event.payload["incident_id"])
            if incident:
                if not incident.analysis:
                    analyze_incident(db, incident)
                if get_settings().alert_webhook_url:
                    emit(db, "alert.deliver", {"incident_id": incident.id})
                else:
                    audit(db, "alert.in_app", incident.id, "Incident is visible in the incident inbox.")
        elif event.kind == "alert.deliver":
            incident = db.get(Incident, event.payload["incident_id"])
            if incident and get_settings().alert_webhook_url:
                status, _ = safe_request(
                    get_settings().alert_webhook_url,
                    method="POST",
                    timeout=10,
                    json_body={
                        "event": "incident.created",
                        "event_id": event.id,
                        "incident": {
                            "id": incident.id,
                            "title": incident.title,
                            "service": incident.service,
                            "severity": incident.severity,
                            "status": incident.status,
                            "summary": incident.summary,
                        },
                    },
                )
                if not 200 <= status < 300:
                    raise RuntimeError(f"Webhook returned HTTP {status}")
                audit(db, "alert.delivered", incident.id, f"Webhook accepted event {event.id}.")
        else:
            audit(db, "event.unknown", event.id, f"Unknown event kind: {event.kind}")

    def process(self, event_id):
        timestamp = now()
        with SessionLocal() as db:
            claimed = db.execute(
                update(Event)
                .where(
                    Event.id == event_id,
                    Event.processed.is_(False),
                    Event.available_at <= timestamp,
                    or_(Event.leased_until.is_(None), Event.leased_until < timestamp),
                )
                .values(leased_until=timestamp + timedelta(minutes=2), attempts=Event.attempts + 1)
            )
            db.commit()
            if not claimed.rowcount:
                existing = db.get(Event, event_id)
                return existing is None or existing.processed
        try:
            with SessionLocal() as db:
                event = db.get(Event, event_id)
                self.handle(db, event)
                event.processed = True
                event.leased_until = None
                db.commit()
            return True
        except Exception as exc:
            logger.warning("Event %s failed (%s)", event_id, type(exc).__name__)
            with SessionLocal() as db:
                event = db.get(Event, event_id)
                if event:
                    event.leased_until = None
                    event.available_at = now() + timedelta(seconds=min(300, 5 * 2**event.attempts))
                    if event.attempts >= 5:
                        event.processed = True
                        audit(
                            db,
                            "event.failed",
                            event.id,
                            f"{event.kind} exhausted 5 attempts. Failure: {type(exc).__name__}.",
                        )
                    else:
                        audit(
                            db,
                            "event.retry",
                            event.id,
                            f"{event.kind} scheduled for retry after attempt {event.attempts}.",
                        )
                    db.commit()
            return False

    def dispatch_redis(self, ids):
        """Redis stream delivery is optional; the SQL sweep repairs transport outages."""
        if not self.redis:
            return
        try:
            try:
                self.redis.xgroup_create("tracehunt:events", "workers", id="0", mkstream=True)
            except Exception as exc:
                if "BUSYGROUP" not in str(exc):
                    raise
            for event_id in ids:
                if self.redis.set(f"tracehunt:dispatched:{event_id}", "1", nx=True, ex=300):
                    self.redis.xadd("tracehunt:events", {"event_id": event_id}, maxlen=10000)
            claimed = self.redis.xautoclaim(
                "tracehunt:events", "workers", self.consumer, min_idle_time=120000, start_id="0-0", count=25
            )
            entries = list(claimed[1])
            for _, messages in self.redis.xreadgroup(
                "workers", self.consumer, {"tracehunt:events": ">"}, count=25
            ):
                entries.extend(messages)
            for message_id, payload in entries:
                if self.process(payload["event_id"]):
                    self.redis.xack("tracehunt:events", "workers", message_id)
        except Exception as exc:
            logger.warning("Redis unavailable (%s); using SQL outbox", type(exc).__name__)

    def tick(self):
        with SessionLocal() as db:
            due = list(
                db.scalars(
                    select(Monitor.id)
                    .where(Monitor.enabled.is_(True), Monitor.is_demo.is_(False), Monitor.next_check <= now())
                    .limit(20)
                )
            )
        for monitor_id in due:
            with SessionLocal() as db:
                claimed = db.execute(
                    update(Monitor)
                    .where(Monitor.id == monitor_id, Monitor.next_check <= now(), Monitor.enabled.is_(True))
                    .values(next_check=now() + timedelta(minutes=2))
                )
                db.commit()
                if claimed.rowcount:
                    monitor = db.get(Monitor, monitor_id)
                    if monitor:
                        check_monitor(db, monitor)
                        db.commit()
        with SessionLocal() as db:
            ids = list(
                db.scalars(
                    select(Event.id)
                    .where(
                        Event.processed.is_(False),
                        Event.available_at <= now(),
                        or_(Event.leased_until.is_(None), Event.leased_until < now()),
                    )
                    .order_by(Event.created_at)
                    .limit(50)
                )
            )
        self.dispatch_redis(ids)
        for event_id in ids:
            self.process(event_id)
        if time.monotonic() - self.last_cleanup > 3600:
            cutoff = now() - timedelta(days=get_settings().retention_days)
            with SessionLocal() as db:
                for model in (Log, MonitorCheck, Audit):
                    db.execute(delete(model).where(model.created_at < cutoff))
                db.execute(delete(Event).where(Event.created_at < cutoff, Event.processed.is_(True)))
                db.commit()
            self.last_cleanup = time.monotonic()

    def run(self):
        logger.info("TraceHunt worker started")
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Worker tick failed; retrying")
            self.stop.wait(2)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if get_settings().demo_mode:
        Base.metadata.create_all(engine)
    worker = Worker()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: worker.stop.set())
    worker.run()


if __name__ == "__main__":
    main()
