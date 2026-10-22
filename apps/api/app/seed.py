import math
import random
from datetime import timedelta

from sqlalchemy import select

from app.models import Audit, Deployment, Incident, Log, Monitor, MonitorCheck, Timeline, now

SERVICES = ["api-gateway", "payment-service", "auth-service", "notification-service", "user-service"]


def seed_demo(db):
    """Deterministic, explicitly labeled sample data. Never overwrite an existing workspace."""
    if db.scalar(select(Monitor.id).limit(1)) or db.scalar(select(Log.id).limit(1)):
        return
    randomizer = random.Random(42)
    current = now()
    monitors = []
    for index, name in enumerate(SERVICES):
        monitor = Monitor(
            name=name,
            url=f"https://example.com/health/{name}",
            is_demo=True,
            status="degraded" if index == 1 else "up",
            interval_seconds=60,
            timeout_seconds=10,
            expected_status=200,
            latency_threshold_ms=500 if index == 1 else 1000,
            last_latency=842 if index == 1 else [128, 74, 56, 92, 104][index],
            last_checked=current - timedelta(seconds=12 + index * 5),
        )
        db.add(monitor)
        db.flush()
        monitors.append(monitor)
    for hour in range(24):
        timestamp = current - timedelta(hours=24 - hour)
        volume = int(28 + 18 * (math.sin(hour / 4) + 1) + randomizer.randint(0, 16))
        for index in range(volume):
            service = SERVICES[index % len(SERVICES)]
            failure = service == "payment-service" and hour >= 21 and index % 3 == 0
            slow = service == "payment-service" and hour >= 20
            latency = randomizer.randint(650, 1400) if slow else randomizer.randint(30, 200)
            db.add(
                Log(
                    service=service,
                    level="ERROR" if failure else "WARN" if slow else "INFO",
                    message=(
                        "Connection pool exhausted: timed out waiting for available database connection"
                        if failure
                        else "Upstream request latency above normal baseline"
                        if slow
                        else randomizer.choice(
                            [
                                "Request completed successfully",
                                "Health check passed",
                                "Background job processed",
                                "Request authenticated and routed",
                            ]
                        )
                    ),
                    trace_id=f"demo-{hour:02d}-{index:04d}",
                    attributes={
                        "demo": True,
                        "latency_ms": latency,
                        "status_code": 503 if failure else 200,
                        "method": "GET",
                        "path": "/v1/payments" if service == "payment-service" else "/v1/requests",
                    },
                    created_at=timestamp + timedelta(seconds=index * 20),
                )
            )
        for index, monitor in enumerate(monitors):
            db.add(
                MonitorCheck(
                    monitor_id=monitor.id,
                    success=not (index == 1 and hour == 22),
                    latency=842 if index == 1 and hour >= 21 else randomizer.randint(40, 160),
                    status_code=503 if index == 1 and hour == 22 else 200,
                    created_at=timestamp,
                )
            )
    incident = Incident(
        title="Elevated payment latency and connection timeouts",
        service="payment-service",
        severity="high",
        status="investigating",
        summary="Demo incident: payment requests are experiencing increased latency after the v2.4.1 rollout. "
        "Connection pool exhaustion is visible in correlated error logs.",
        fingerprint="demo:payment",
        created_at=current - timedelta(minutes=32),
        updated_at=current - timedelta(minutes=8),
        analysis={
            "summary": "Demo analysis: payment-service latency increased after the v2.4.1 deployment.",
            "probable_cause": "Database connection pool exhaustion is a plausible cause; deployment timing is correlated, not proof.",
            "confidence": 0.78,
            "evidence": [
                "Sample payment logs contain database connection pool timeouts.",
                "Sample v2.4.1 deployment preceded the incident by 10 minutes.",
                "Sample monitor latency increased from approximately 120 ms to 842 ms.",
            ],
            "recommended_actions": [
                "Inspect active database connections and slow queries.",
                "Compare the v2.4.1 pool configuration with the previous version.",
                "Consider a rollback if the deployment regression is confirmed.",
            ],
            "source": "heuristic",
            "generated_at": (current - timedelta(minutes=8)).isoformat() + "Z",
        },
    )
    db.add(incident)
    db.flush()
    for minutes, kind, message in [
        (32, "created", "Demo: error threshold exceeded in payment-service."),
        (24, "status", "Incident moved to investigating."),
        (8, "analysis", "Evidence-based analysis generated from sample telemetry."),
    ]:
        db.add(
            Timeline(
                incident_id=incident.id,
                kind=kind,
                message=message,
                created_at=current - timedelta(minutes=minutes),
            )
        )
    db.add(
        Incident(
            title="Notification delivery queue backlog",
            service="notification-service",
            severity="medium",
            status="open",
            summary="Demo incident: delivery queue depth exceeded the sample threshold.",
            created_at=current - timedelta(hours=2),
            updated_at=current - timedelta(minutes=50),
        )
    )
    db.add(
        Incident(
            title="Authentication token validation errors",
            service="auth-service",
            severity="low",
            status="resolved",
            summary="Demo incident: stale signing key cache refreshed successfully.",
            created_at=current - timedelta(hours=7),
            updated_at=current - timedelta(hours=6),
            resolved_at=current - timedelta(hours=6),
        )
    )
    for name, version, minutes in [
        ("payment-service", "v2.4.1", 42),
        ("api-gateway", "v3.8.0", 115),
        ("auth-service", "v1.12.3", 390),
        ("notification-service", "v2.1.0", 580),
    ]:
        db.add(
            Deployment(
                service=name,
                version=version,
                environment="production",
                status="success",
                commit_sha=f"{randomizer.getrandbits(28):07x}",
                created_at=current - timedelta(minutes=minutes),
            )
        )
    for minutes, action, detail in [
        (8, "incident.analyzed", "Demo analysis completed for payment-service."),
        (24, "incident.updated", "Demo payment incident assigned to investigation."),
        (32, "incident.created", "Demo high-severity incident opened."),
        (42, "deployment.created", "Demo payment-service v2.4.1 deployed."),
        (115, "deployment.created", "Demo api-gateway v3.8.0 deployed."),
    ]:
        db.add(
            Audit(
                action=action,
                actor="demo",
                resource="payment-service",
                detail=detail,
                created_at=current - timedelta(minutes=minutes),
            )
        )
    db.commit()
