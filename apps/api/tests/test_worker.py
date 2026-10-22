from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app import services, worker
from app.models import Audit, Deployment, Event, Incident, Log, Monitor, MonitorCheck, RuleState, now
from app.schemas import AnalysisOutput, LogCreate
from app.seed import seed_demo
from app.services import analyze_incident, check_monitor, create_incident, evaluate_errors, ingest
from app.worker import Worker


def drain_events(database, processor):
    for _ in range(10):
        with database() as db:
            ids = list(
                db.scalars(select(Event.id).where(Event.processed.is_(False), Event.available_at <= now()))
            )
        if not ids:
            return
        for event_id in ids:
            assert processor.process(event_id)
    pytest.fail("Event queue did not drain")


def test_error_burst_becomes_one_analyzed_incident(database, db, settings):
    for _ in range(settings.error_threshold):
        ingest(db, LogCreate(service="checkout", level="ERROR", message="Connection pool exhausted"))
    db.commit()
    processor = Worker()
    drain_events(database, processor)
    db.expire_all()
    incidents = list(db.scalars(select(Incident)))
    assert len(incidents) == 1
    assert incidents[0].severity == "high"
    assert incidents[0].analysis["source"] == "heuristic"
    assert "connection" in incidents[0].analysis["probable_cause"].lower()
    assert db.scalar(select(Audit).where(Audit.action == "alert.in_app"))
    event = db.scalar(select(Event).where(Event.kind == "log.error"))
    assert processor.process(event.id)
    db.refresh(event)
    assert event.attempts == 1


def test_anomaly_cooldown_and_fresh_incident_after_expiry(db, settings):
    for _ in range(settings.error_threshold):
        ingest(db, LogCreate(service="api", level="ERROR", message="timeout"))
    db.flush()
    incident = evaluate_errors(db, "api")
    assert evaluate_errors(db, "api").id == incident.id
    incident.status = "resolved"
    db.flush()
    assert evaluate_errors(db, "api") is None
    rule = db.get(RuleState, "error-burst:api")
    rule.last_incident_at = now() - timedelta(seconds=settings.incident_cooldown_seconds + 1)
    db.flush()
    assert evaluate_errors(db, "api").id != incident.id


def test_concurrent_error_events_do_not_duplicate_incidents(database, db, settings):
    for _ in range(settings.error_threshold):
        ingest(db, LogCreate(service="race", level="ERROR", message="timeout"))
    db.commit()
    ids = list(db.scalars(select(Event.id)))
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda event_id: Worker().process(event_id), ids))
    assert all(results)
    assert db.scalar(select(func.count()).select_from(Incident)) == 1


def test_active_lease_and_retry_schedule_then_terminal_failure(database, db, monkeypatch):
    event = Event(kind="fail", payload={})
    db.add(event)
    db.commit()
    processor = Worker()

    def fail(*args):
        raise RuntimeError("do-not-persist-secret")

    monkeypatch.setattr(processor, "handle", fail)
    event.leased_until = now() + timedelta(minutes=1)
    db.commit()
    assert processor.process(event.id) is False
    db.refresh(event)
    assert event.attempts == 0
    event.leased_until = now() - timedelta(seconds=1)
    db.commit()
    for attempt in range(1, 6):
        before = now()
        assert processor.process(event.id) is False
        db.refresh(event)
        assert event.attempts == attempt and event.leased_until is None
        assert event.processed is (attempt == 5)
        if attempt < 5:
            assert event.available_at >= before + timedelta(seconds=5 * 2**attempt)
            event.available_at = now() - timedelta(seconds=1)
            db.commit()
    assert processor.process(event.id) is True
    entries = list(db.scalars(select(Audit)))
    assert [entry.action for entry in entries].count("event.retry") == 4
    assert [entry.action for entry in entries].count("event.failed") == 1
    assert "do-not-persist-secret" not in str([entry.detail for entry in entries])


def test_monitor_failure_degradation_recovery_and_demo_never_calls_network(db, monkeypatch):
    monitor = Monitor(name="payments", url="https://example.com", latency_threshold_ms=500)
    db.add(monitor)
    db.flush()
    monkeypatch.setattr(services, "safe_request", lambda *a, **k: (503, 900))
    assert check_monitor(db, monitor).success is False
    assert monitor.status == "down"
    monkeypatch.setattr(services, "safe_request", lambda *a, **k: (200, 900))
    assert check_monitor(db, monitor).success is True
    assert monitor.status == "degraded"
    monkeypatch.setattr(services, "safe_request", lambda *a, **k: (200, 100))
    check_monitor(db, monitor)
    assert monitor.status == "up" and monitor.next_check > now()

    def fail(*args, **kwargs):
        raise AssertionError("Demo monitors must never use the network")

    monkeypatch.setattr(services, "safe_request", fail)
    monitor.is_demo = True
    check_monitor(db, monitor)
    assert monitor.status == "up"


def test_monitor_scheduler_skips_paused_and_demo_and_sql_survives_redis_outage(db, monkeypatch):
    for name, enabled, demo in [("active", True, False), ("paused", False, False), ("demo", True, True)]:
        db.add(Monitor(name=name, url="https://example.com", enabled=enabled, is_demo=demo))
    db.commit()
    monkeypatch.setattr(services, "safe_request", lambda *a, **k: (503, 20))
    processor = Worker()

    def unavailable(*args, **kwargs):
        raise ConnectionError("Redis down")

    processor.redis = SimpleNamespace(xgroup_create=unavailable)
    processor.tick()
    assert db.scalar(select(func.count()).select_from(MonitorCheck)) == 1
    assert db.scalar(select(Incident)).service == "active"
    processor.tick()
    assert db.scalar(select(func.count()).select_from(MonitorCheck)) == 1


def test_webhook_failure_retries_with_stable_event_id(db, database, monkeypatch, settings):
    monkeypatch.setattr(settings, "alert_webhook_url", "https://hooks.example.com/incident")
    incident = create_incident(db, "Timeouts", "api", "high", "Errors observed")
    db.commit()
    processor = Worker()
    created = db.scalar(select(Event).where(Event.kind == "incident.created"))
    assert processor.process(created.id)
    alert = db.scalar(select(Event).where(Event.kind == "alert.deliver"))
    deliveries = []

    def deliver(*args, **kwargs):
        deliveries.append(kwargs["json_body"])
        return (503 if len(deliveries) == 1 else 204), 2

    monkeypatch.setattr(worker, "safe_request", deliver)
    assert processor.process(alert.id) is False
    db.refresh(alert)
    alert.available_at = now() - timedelta(seconds=1)
    db.commit()
    assert processor.process(alert.id) is True
    assert [payload["event_id"] for payload in deliveries] == [alert.id, alert.id]
    assert deliveries[0]["incident"]["id"] == incident.id
    assert db.scalar(select(Audit).where(Audit.action == "alert.delivered"))


def test_heuristic_correlates_only_preceding_deployments_and_scoped_logs(db):
    incident = create_incident(db, "Database timeout", "api", "high", "timeout")
    db.add_all(
        [
            Log(
                service="api",
                level="ERROR",
                message="connection pool exhausted",
                created_at=incident.created_at,
            ),
            Log(service="other", level="ERROR", message="unrelated failure", created_at=incident.created_at),
            Deployment(
                service="api",
                version="v1",
                environment="production",
                status="success",
                created_at=incident.created_at - timedelta(minutes=10),
            ),
            Deployment(
                service="api",
                version="v2",
                environment="production",
                status="success",
                created_at=incident.created_at + timedelta(minutes=10),
            ),
        ]
    )
    db.flush()
    result = analyze_incident(db, incident, use_ai=False)
    assert "1 error logs and 1 preceding deployments" in result["summary"]
    assert "unrelated" not in str(result) and "v2" not in str(result)


def test_openai_structured_analysis_and_failure_fallback(db, monkeypatch, settings):
    import openai

    monkeypatch.setattr(settings, "openai_api_key", "fake-provider-key")
    captured = {}
    output = AnalysisOutput(
        summary="Evidence summary",
        probable_cause="A hypothesis",
        confidence=0.4,
        evidence=["Observed timeout"],
        recommended_actions=["Inspect dependency"],
    )

    def parse(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_parsed=output)

    monkeypatch.setattr(
        openai, "OpenAI", lambda **kwargs: SimpleNamespace(responses=SimpleNamespace(parse=parse))
    )
    incident = create_incident(db, "Timeouts", "api", "high", "password=secret-value")
    result = analyze_incident(db, incident)
    assert result["source"] == "openai"
    assert captured["text_format"] is AnalysisOutput and captured["store"] is False
    assert "secret-value" not in captured["input"] and "fake-provider-key" not in captured["input"]

    def fail(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(openai, "OpenAI", fail)
    assert analyze_incident(db, incident)["source"] == "heuristic"
    assert db.scalar(select(Audit).where(Audit.action == "analysis.fallback"))


def test_retention_keeps_incidents_and_unprocessed_events(db, settings):
    expired = now() - timedelta(days=settings.retention_days + 1)
    incident = create_incident(db, "Old incident", "api", "high", "retain evidence summary")
    db.add_all(
        [
            Log(service="api", level="INFO", message="old", created_at=expired),
            Audit(action="old", resource="api", detail="old", created_at=expired),
            Event(kind="old-completed", payload={}, processed=True, created_at=expired),
            Event(kind="old-pending", payload={}, available_at=now() + timedelta(days=1), created_at=expired),
        ]
    )
    db.commit()
    Worker().tick()
    assert db.scalar(select(Log)) is None
    assert db.scalar(select(Audit).where(Audit.action == "old")) is None
    assert db.scalar(select(Event).where(Event.kind == "old-completed")) is None
    assert db.scalar(select(Event).where(Event.kind == "old-pending"))
    assert db.get(Incident, incident.id)


def test_demo_seed_is_idempotent_and_has_no_future_logs(db):
    seed_demo(db)
    count = db.scalar(select(func.count()).select_from(Log))
    seed_demo(db)
    assert db.scalar(select(func.count()).select_from(Log)) == count
    assert db.scalar(select(func.max(Log.created_at))) <= now()
