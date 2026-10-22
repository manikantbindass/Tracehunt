import json
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import main, services
from app.models import Audit, Event, Log, Monitor, MonitorCheck, now


def test_ingestion_redaction_filters_and_transactional_outbox(client, db):
    response = client.post(
        "/api/v1/logs",
        json={
            "service": "checkout",
            "level": "error",
            "message": "payment failed password=sample-secret",
            "trace_id": "trace-42",
            "metadata": {"token": "top-secret", "nested": [{"api_key": "hidden"}]},
        },
    )
    assert response.status_code == 201
    log = response.json()
    assert log["level"] == "ERROR"
    assert log["message"] == "payment failed password=[REDACTED]"
    assert log["metadata"] == {"token": "[REDACTED]", "nested": [{"api_key": "[REDACTED]"}]}
    event = db.scalar(select(Event))
    assert event.kind == "log.error" and event.payload["log_id"] == log["id"]
    result = client.get(
        "/api/v1/logs", params={"service": "checkout", "level": "ERROR", "search": "trace-42"}
    )
    assert [row["id"] for row in result.json()] == [log["id"]]
    assert client.get("/api/v1/logs", params={"search": "%"}).json() == []
    assert client.get("/api/v1/logs", params={"search": "_"}).json() == []


def test_batch_is_all_or_nothing(client, db):
    response = client.post(
        "/api/v1/logs/batch",
        json={
            "logs": [
                {"service": "checkout", "message": "valid"},
                {"service": "checkout", "message": ""},
            ]
        },
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(Log)) == 0
    result = client.post(
        "/api/v1/logs/batch",
        json={
            "logs": [
                {"service": "checkout", "message": "one", "level": "warning"},
                {"service": "checkout", "message": "two"},
            ]
        },
    )
    assert result.json()["accepted"] == 2
    assert len(result.json()["ids"]) == 2
    assert client.get("/api/v1/logs", params={"level": "warning"}).json()[0]["level"] == "WARN"


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_metadata_is_rejected_without_echoing_input(client, value):
    response = client.post(
        "/api/v1/logs",
        content=('{"service":"a","message":"secret=never-echo","metadata":{"latency_ms":' + value + "}}"),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert "never-echo" not in response.text


def test_body_and_metadata_limits(client):
    assert client.post("/api/v1/logs", content=b"x" * (main.settings.max_body_bytes + 1)).status_code == 413
    result = client.post(
        "/api/v1/logs", json={"service": "a", "message": "a", "metadata": {"text": "a" * 16001}}
    )
    assert result.status_code == 422


def test_incident_lifecycle_and_redacted_timeline(client):
    row = client.post(
        "/api/v1/incidents",
        json={
            "title": "Payment timeout",
            "service": "payment",
            "severity": "high",
            "summary": "password=never-save connection pool exhausted",
        },
    ).json()
    detail = client.get(f"/api/v1/incidents/{row['id']}").json()
    assert "never-save" not in json.dumps(detail)
    assert detail["timeline"][0]["kind"] == "created"
    for status in ["investigating", "resolved", "open"]:
        response = client.patch(f"/api/v1/incidents/{row['id']}", json={"status": status})
        assert response.json()["status"] == status
        assert bool(response.json()["resolved_at"]) == (status == "resolved")
    client.patch(f"/api/v1/incidents/{row['id']}", json={"status": "open"})
    detail = client.get(f"/api/v1/incidents/{row['id']}").json()
    assert len(detail["timeline"]) == 4
    assert client.patch(f"/api/v1/incidents/{row['id']}", json={"status": "invalid"}).status_code == 422
    analysis = client.post(f"/api/v1/incidents/{row['id']}/analyze").json()
    assert analysis["source"] == "heuristic" and analysis["evidence"] and analysis["recommended_actions"]
    assert client.get("/api/v1/incidents/missing").status_code == 404


def test_monitor_crud_and_check(client, monkeypatch, db):
    monkeypatch.setattr(main, "validate_target", lambda *a, **k: ("example.com", 443, "93.184.216.34"))
    monkeypatch.setattr(services, "safe_request", lambda *a, **k: (200, 125.0))
    result = client.post("/api/v1/monitors", json={"name": "checkout", "url": "https://example.com/health"})
    assert result.status_code == 201
    monitor_id = result.json()["id"]
    result = client.post(f"/api/v1/monitors/{monitor_id}/check")
    assert result.json()["status"] == "up" and result.json()["uptime"] == 100
    assert client.patch(f"/api/v1/monitors/{monitor_id}", json={"enabled": False}).json()["enabled"] is False
    assert db.scalar(select(func.count()).select_from(MonitorCheck)) == 1
    assert client.delete(f"/api/v1/monitors/{monitor_id}").status_code == 204
    assert db.scalar(select(func.count()).select_from(MonitorCheck)) == 0
    assert client.post(f"/api/v1/monitors/{monitor_id}/check").status_code == 404


def test_disabled_monitor_still_blocks_literal_private_targets(client):
    response = client.post(
        "/api/v1/monitors", json={"name": "private", "url": "http://127.0.0.1", "enabled": False}
    )
    assert response.status_code == 422
    response = client.post(
        "/api/v1/monitors", json={"name": "offline", "url": "https://example.invalid", "enabled": False}
    )
    assert response.status_code == 201


def test_production_authentication_and_safe_settings(client, monkeypatch, settings):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "api_key", "testing-secret-key-at-least-24-characters")
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/logs").status_code == 401
    assert client.get("/metrics").status_code == 401
    assert client.get("/api/v1/logs", headers={"X-API-Key": "wrong"}).status_code == 401
    response = client.get("/api/v1/settings", headers={"X-API-Key": settings.api_key})
    assert response.status_code == 200 and settings.api_key not in response.text
    with pytest.raises(main.HTTPException) as exc:
        main.authenticate("\u00e9")
    assert exc.value.status_code == 401


def test_overview_calculates_real_telemetry_and_ignores_invalid_latencies(client):
    for index, latency in enumerate([10, 20, 100, -1, True, 10**500]):
        assert (
            client.post(
                "/api/v1/logs",
                json={
                    "service": "api",
                    "message": "request",
                    "level": "ERROR" if index == 0 else "INFO",
                    "metadata": {"latency_ms": latency},
                },
            ).status_code
            == 201
        )
    result = client.get("/api/v1/overview")
    assert result.status_code == 200
    overview = result.json()
    assert overview["stats"]["requests_24h"] == 6
    assert overview["stats"]["p95_latency"] == 100
    assert overview["stats"]["error_rate"] == 16.67
    assert overview["services"][0]["latency"] == 43.3
    assert sum(point["requests"] for point in overview["traffic"]) == 6


def test_overview_average_does_not_overflow_for_finite_values(client):
    for _ in range(2):
        assert (
            client.post(
                "/api/v1/logs",
                json={
                    "service": "api",
                    "message": "request",
                    "metadata": {"latency_ms": 1e308},
                },
            ).status_code
            == 201
        )
    response = client.get("/api/v1/overview")
    assert response.status_code == 200
    assert response.json()["services"][0]["latency"] == 1e308


def test_overview_service_uptime_follows_selected_window(client, db):
    monitor = Monitor(name="checkout", url="https://example.com/health")
    db.add(monitor)
    db.flush()
    timestamp = now()
    db.add_all(
        [
            MonitorCheck(
                monitor_id=monitor.id,
                success=success,
                latency=100,
                created_at=timestamp - age,
            )
            for age, success in [
                (timedelta(minutes=30), True),
                (timedelta(hours=2), False),
                (timedelta(days=2), False),
            ]
        ]
    )
    db.commit()
    for hours, expected in [(1, 100), (24, 50), (168, 33.33)]:
        overview = client.get("/api/v1/overview", params={"hours": hours}).json()
        assert overview["stats"]["uptime"] == expected
        assert overview["services"][0]["uptime"] == expected
    assert client.get("/api/v1/monitors").json()[0]["uptime"] == 50


def test_activity_cursor_handles_equal_timestamps_and_microseconds(database, db):
    timestamp = now().replace(microsecond=123456)
    db.add_all(
        [
            Audit(id=f"event-{index:03}", action="test", resource="test", detail="ok", created_at=timestamp)
            for index in range(105)
        ]
    )
    db.commit()
    rows, cursor = main.fetch_activity((timestamp - timedelta(seconds=1), ""))
    assert len(rows) == 100
    more, cursor = main.fetch_activity(cursor)
    assert len(more) == 5
    assert len({row["id"] for row in rows + more}) == 105
    assert main.fetch_activity(cursor)[0] == []


def test_deployments_audit_and_metrics(client):
    response = client.post(
        "/api/v1/deployments", json={"service": "api", "version": "v1", "commit_sha": "abcdef1"}
    )
    assert response.status_code == 201
    assert client.get("/api/v1/deployments").json()[0]["id"] == response.json()["id"]
    assert client.get("/api/v1/audit").json()[0]["action"] == "deployment.created"
    assert "tracehunt_events_pending 0" in client.get("/metrics").text
    assert client.get("/ready").json()["status"] == "ready"
