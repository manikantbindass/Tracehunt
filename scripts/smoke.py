#!/usr/bin/env python3
"""Exercise a running TraceHunt API using only the Python standard library.

Run against a disposable local/demo database; the test retains clearly marked
logs, resolved incidents, a deployment, and associated audit entries. Temporary
monitors are deleted in finally blocks. Network checks run only with --monitor-url.

    python scripts/smoke.py
    python scripts/smoke.py --base-url http://127.0.0.1:8000

TRACEHUNT_API_URL and TRACEHUNT_API_KEY supply the default connection settings.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class Api:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def request(self, method: str, path: str, payload: dict | None = None) -> object:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:800]
            raise RuntimeError(f"{method} {path}: HTTP {error.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError) as error:
            raise RuntimeError(f"{method} {path}: {error}") from None

    def get(self, path: str) -> object:
        return self.request("GET", path)

    def post(self, path: str, payload: dict | None = None) -> object:
        return self.request("POST", path, payload)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def object_with_id(value: object, label: str) -> dict:
    require(isinstance(value, dict) and bool(value.get("id")), f"{label}: expected object with id")
    return value


def pass_check(message: str) -> None:
    print(f"PASS {message}", flush=True)


def run(api: Api, check_worker: bool = False, monitor_url: str | None = None) -> None:
    suffix = uuid.uuid4().hex[:10]
    marker = f"tracehunt-smoke-{suffix}"
    service = marker
    monitor_id = None
    started = time.monotonic()

    health = api.get("/health")
    require(isinstance(health, dict), "health: expected JSON object")
    require(health.get("status") in {"ok", "healthy"}, f"health: unhealthy response {health}")
    pass_check("health")
    ready = api.get("/ready")
    require(isinstance(ready, dict) and ready.get("status") == "ready", "readiness: database unavailable")
    pass_check("database readiness")

    overview = api.get("/api/v1/overview")
    require(isinstance(overview, dict) and bool(overview), "overview: expected a nonempty object")
    pass_check("overview")

    first_log = object_with_id(
        api.post("/api/v1/logs", {
            "service": service,
            "level": "error",
            "message": f"{marker} database connection timeout",
            "trace_id": f"smoke-{suffix}",
            "metadata": {"synthetic": True, "smoke_test": marker, "latency_ms": 1200},
        }),
        "single log ingestion",
    )
    batch = api.post("/api/v1/logs/batch", {
        "logs": [
            {"service": service, "level": "info", "message": f"{marker} request completed", "metadata": {"synthetic": True}},
            {"service": service, "level": "warn", "message": f"{marker} connection pool saturation", "metadata": {"synthetic": True}},
        ]
    })
    require(
        isinstance(batch, dict) and batch.get("accepted") == 2 and len(batch.get("ids", [])) == 2,
        "batch ingestion: expected two accepted records and two ids",
    )
    search = urllib.parse.urlencode({"service": service, "search": marker})
    logs = api.get(f"/api/v1/logs?{search}")
    require(isinstance(logs, list), "log search: expected array")
    require(len(logs) == 3, f"log search: expected 3 records, received {len(logs)}")
    require(all(log.get("service") == service and marker in log.get("message", "") for log in logs), "log search: filters not applied")
    require(any(log.get("id") == first_log["id"] for log in logs), "log search: created record missing")
    errors = api.get(f"/api/v1/logs?{search}&level=error")
    require(
        isinstance(errors, list) and len(errors) == 1 and errors[0].get("id") == first_log["id"],
        "log search: case-insensitive level filter not applied",
    )
    pass_check("log ingestion, batch, and search")

    incident = object_with_id(
        api.post("/api/v1/incidents", {
            "title": f"{marker} database connectivity",
            "service": service,
            "severity": "high",
            "summary": "Synthetic smoke test: connection timeout after deployment.",
        }),
        "incident creation",
    )
    incident_id = urllib.parse.quote(str(incident["id"]), safe="")
    investigated = api.request("PATCH", f"/api/v1/incidents/{incident_id}", {"status": "investigating"})
    require(isinstance(investigated, dict) and investigated.get("status") == "investigating", "incident update: status not persisted")
    analysis = api.post(f"/api/v1/incidents/{incident_id}/analyze")
    require(isinstance(analysis, dict) and bool(analysis.get("summary")), "incident analysis: summary missing")
    require(analysis.get("source") in {"heuristic", "openai"}, "incident analysis: source missing")
    require(bool(analysis.get("evidence")) and bool(analysis.get("recommended_actions")), "incident analysis: evidence or actions missing")
    resolved = api.request("PATCH", f"/api/v1/incidents/{incident_id}", {"status": "resolved"})
    require(isinstance(resolved, dict) and resolved.get("status") == "resolved", "incident resolution: status not persisted")
    incidents = api.get("/api/v1/incidents")
    require(isinstance(incidents, list) and any(row.get("id") == incident["id"] for row in incidents), "incident list: created incident missing")
    pass_check("incident creation, investigation, analysis, and resolution")
    detail = api.get(f"/api/v1/incidents/{incident_id}")
    require(isinstance(detail, dict) and len(detail.get("timeline", [])) >= 4, "incident timeline: lifecycle events missing")
    reopened = api.request("PATCH", f"/api/v1/incidents/{incident_id}", {"status": "open"})
    require(isinstance(reopened, dict) and reopened.get("resolved_at") is None, "incident reopening: stale resolution time")
    api.request("PATCH", f"/api/v1/incidents/{incident_id}", {"status": "resolved"})
    pass_check("incident timeline and reopening")

    try:
        monitor = object_with_id(
            api.post("/api/v1/monitors", {
                "name": marker,
                "url": "https://example.invalid/tracehunt-smoke",
                "method": "GET",
                "interval_seconds": 300,
                "timeout_seconds": 5,
                "expected_status": 200,
                "latency_threshold_ms": 1000,
                "enabled": False,
            }),
            "monitor creation",
        )
        monitor_id = urllib.parse.quote(str(monitor["id"]), safe="")
        require(monitor.get("enabled") is False, "monitor creation: expected disabled monitor")
        paused = api.request("PATCH", f"/api/v1/monitors/{monitor_id}", {"enabled": False})
        require(isinstance(paused, dict) and paused.get("enabled") is False, "monitor pause: enabled was not false")
        monitors = api.get("/api/v1/monitors")
        require(isinstance(monitors, list) and any(row.get("id") == monitor["id"] for row in monitors), "monitor list: created monitor missing")
    finally:
        if monitor_id is not None:
            api.request("DELETE", f"/api/v1/monitors/{monitor_id}")
    monitors_after_delete = api.get("/api/v1/monitors")
    require(isinstance(monitors_after_delete, list) and not any(str(row.get("id")) == monitor_id for row in monitors_after_delete), "monitor deletion: record still present")
    pass_check("disabled monitor creation, pause, list, and deletion")
    if monitor_url:
        checked_monitor_id = None
        try:
            live_monitor = object_with_id(api.post("/api/v1/monitors", {
                "name": f"{marker}-http", "url": monitor_url,
                "interval_seconds": 300, "latency_threshold_ms": 60000,
            }), "HTTP monitor creation")
            checked_monitor_id = live_monitor["id"]
            checked = api.post(f"/api/v1/monitors/{checked_monitor_id}/check")
            require(isinstance(checked, dict) and checked.get("status") == "up", "HTTP monitor: expected healthy response")
            require(bool(checked.get("last_checked")) and checked.get("last_latency") is not None, "HTTP monitor: check not persisted")
        finally:
            if checked_monitor_id:
                api.request("DELETE", f"/api/v1/monitors/{checked_monitor_id}")
        pass_check("real HTTP monitor probe and persistence")

    deployment = object_with_id(
        api.post("/api/v1/deployments", {
            "service": service,
            "version": f"smoke-{suffix}",
            "environment": "demo",
            "status": "success",
            "commit_sha": suffix,
        }),
        "deployment creation",
    )
    deployments = api.get("/api/v1/deployments")
    require(isinstance(deployments, list) and any(row.get("id") == deployment["id"] for row in deployments), "deployment list: created deployment missing")
    pass_check("deployment creation and list")

    audit = api.get("/api/v1/audit")
    require(isinstance(audit, list) and bool(audit), "audit: expected a nonempty array")
    settings = api.get("/api/v1/settings")
    require(isinstance(settings, dict) and bool(settings), "settings: expected a nonempty object")
    if api.api_key:
        require(api.api_key not in json.dumps(settings), "settings: API key leaked")
    pass_check("audit and safe settings")
    if check_worker:
        worker_service = f"{marker}-worker"
        threshold = settings.get("error_threshold", 5)
        require(isinstance(threshold, int) and 2 <= threshold <= 500, "worker smoke requires ERROR_THRESHOLD between 2 and 500")
        api.post("/api/v1/logs/batch", {"logs": [
            {"service": worker_service, "level": "error",
             "message": f"Synthetic connection timeout {index}", "metadata": {"synthetic": True, "smoke_test": marker}}
            for index in range(threshold)
        ]})
        deadline = time.monotonic() + 60
        detected = None
        while time.monotonic() < deadline:
            rows = api.get("/api/v1/incidents?" + urllib.parse.urlencode({"search": worker_service}))
            matching = [row for row in rows if row.get("service") == worker_service]
            require(len(matching) <= 1, "worker: duplicate anomaly incidents")
            if matching and matching[0].get("analysis"):
                detected = matching[0]
                break
            time.sleep(1)
        require(detected is not None, "worker: no automatically analyzed error-burst incident within 60s")
        api.request("PATCH", f"/api/v1/incidents/{detected['id']}", {"status": "resolved"})
        pass_check("worker error-burst detection, deduplication, and automatic analysis")
    print(f"All smoke checks passed in {time.monotonic() - started:.1f}s; marker={marker}.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.getenv("TRACEHUNT_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.getenv("TRACEHUNT_API_KEY", ""), help="API key (default: TRACEHUNT_API_KEY)")
    parser.add_argument("--worker", action="store_true", help="Also require background anomaly detection and automatic analysis")
    parser.add_argument("--monitor-url", help="Also probe this controlled HTTP endpoint; it must return 200")
    args = parser.parse_args()
    if not args.base_url.startswith(("http://", "https://")):
        parser.error("--base-url must be an http:// or https:// URL")
    try:
        run(Api(args.base_url, args.api_key), check_worker=args.worker, monitor_url=args.monitor_url)
    except (AssertionError, RuntimeError, ValueError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
