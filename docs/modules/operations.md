# Operator runbook

The default deployment is a local demo with synthetic data and unauthenticated application access. Use the [README quick start](../../README.md#quick-start) to start it. This runbook covers the repository's single-workspace Compose stack and local Python mode; it does not provide a managed production service or Kubernetes deployment.

## Start and inspect the stack

Docker must be running its Linux container engine. From the repository root, copy `.env.example` to `.env`, review it, and start:

```bash
docker compose up --build -d --wait
docker compose ps
docker compose logs --tail=100 api worker
```

The dashboard binds to `127.0.0.1:3000` and the API to `127.0.0.1:8000`. PostgreSQL and Redis are only reachable on the Compose network. The API applies `alembic upgrade head` before Uvicorn starts, and the worker starts after API readiness succeeds.

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
python scripts/smoke.py --worker
```

On Windows PowerShell, use `Copy-Item .env.example .env` and `curl.exe`. Smoke writes uniquely named synthetic logs, deployments, audit rows, and resolved incidents. Its temporary monitor is deleted. Run it only against a disposable workspace. `--worker` additionally waits for error-burst detection and automatic analysis; the default smoke run alone does not prove the worker is running.

Compose is configured with restart policies for the main services. The worker has no dedicated health endpoint or container health check. Confirm recent monitor check times, error-burst processing, audit activity, and worker logs separately from API readiness.

## Configuration and deployment changes

Compose reads root `.env` and passes explicit variables to its services. Local Python processes instead read `.env` from their working directory, normally `apps/api`; process environment values override that file. The API and worker need identical database, detection, retention, private-network, and provider settings. Restart both after changing those settings.

For a private deployment, set `DEMO_MODE=false`, `SEED_DEMO=false`, and a random `API_KEY` of at least 24 characters. Supply unique PostgreSQL credentials, HTTPS, external authentication or a private network, backups, and gateway request/rate limits. See [SECURITY.md](../../SECURITY.md). Turning demo mode off does not delete existing synthetic records; start with a separate database when a clean workspace is required.

`API_INTERNAL_URL` is a frontend build argument. Rebuild the web image when changing it; a runtime environment change alone does not replace the compiled Next.js rewrite. Browser connection settings can instead target an absolute API base URL ending in `/api/v1`; allow that dashboard origin in `CORS_ORIGINS`. The workspace key is stored in browser session storage.

For local Python operation, select the database configuration and run migrations before the first API or worker start, including demo mode:

```bash
cd apps/api
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If the API was previously started directly in demo mode, it may have created tables without an Alembic revision. Applying the initial migration to that database then fails with an existing-table error. Stop both processes and preserve the old database and its backup. For a disposable demo, point both processes at a new `DATABASE_URL`, apply migrations there, and start them again. Do not delete the original database automatically or blindly run `alembic stamp head`: stamping records a revision without checking or changing the schema. Keeping existing data requires a separately reviewed adoption/migration plan that compares its actual schema with the migration target.

Run `python -m app.worker` in another terminal using the same environment and working directory. SQLite's relative URL is relative to that directory; starting one process elsewhere can create an unintended second database. `RUN_WORKER=true` is an alternative single-process development mode. Avoid running it alongside a separate worker unless intentionally testing concurrency.

## Back up and recover data

The named `postgres-data` and `redis-data` volumes survive `docker compose down`. SQL contains the authoritative telemetry, incident state, audit, and event outbox. Redis data is useful for transport continuity but is not a substitute for a database backup.

Take a PostgreSQL logical backup with the service's configured database user. Writing the dump inside the container and copying it avoids binary output redirection issues in older PowerShell versions:

```bash
mkdir backups
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/tracehunt.dump'
docker compose cp postgres:/tmp/tracehunt.dump ./backups/tracehunt.dump
```

Use a unique dated backup filename in normal operations. Protect backups as sensitive data, keep copies outside the application host, and record the application revision and migration revision. Do not commit dumps. Back up environment configuration and provider/key references separately in a secure location.

Test restoration into a separate database before relying on a backup. Copy the dump into that database's container and use `pg_restore --no-owner` with the target database credentials; confirm migration revision, readiness, row counts, and representative incidents. Keep the validation environment's worker stopped and external providers/webhooks disabled until reviewed: restored pending events may deliver notifications or send evidence when processing resumes.

For SQLite, stop API and worker before making a filesystem backup, or use SQLite's online backup API. Copying only the main database file while WAL writers are active is not a reliable backup. Restore to a separate path and verify with the same application revision before resuming traffic.

Before an upgrade: make and verify a backup, inspect migration changes, then start the new application. `create_all` in demo mode creates missing tables but does not migrate an old schema. Do not assume an old binary remains compatible with a newer migration; a rollback may require restoring a compatible backup and accepting loss of later writes.

## Health, metrics, and queue diagnosis

| Signal | Interpretation and next action |
| --- | --- |
| `/health` fails | API process or route is unavailable; inspect service state and startup logs |
| `/ready` returns `503` | Database connectivity or monitor-table query failed; inspect PostgreSQL, credentials, and migration logs |
| `/ready` succeeds but no new incidents/checks | Confirm worker is running against the same database and check its logs; readiness does not inspect it |
| `tracehunt_events_pending` grows | Processing is delayed or failing; inspect worker throughput and `event.retry`/`event.failed` audit records |
| Redis errors | Worker falls back to SQL; inspect Redis availability, but do not delete SQL events to clear the queue |
| Provider errors | Analysis falls back to heuristics; inspect `analysis.fallback`, provider configuration, and network access |
| Monitor is `down` | Inspect target status, DNS, TLS, allowed destination/port, and timeout; unexpected HTTP status counts as failure |
| Monitor is `degraded` | Expected status matched, but header latency exceeded the configured threshold |

Read metrics with `X-API-Key` outside demo mode:

```bash
curl http://localhost:8000/metrics -H "X-API-Key: YOUR_WORKSPACE_KEY"
```

These four metrics are database gauges. `tracehunt_logs_total` counts retained rows rather than a monotonic ingestion counter. The endpoint does not report worker liveness, Redis connectivity, delivery latency, retry count, or failed-event count. Add external process checks, gateway instrumentation, storage alerts, and notification checks appropriate to the deployment.

Inspect newest activity through `GET /api/v1/audit?limit=500`. Retry failures are recorded without raw exception messages, to reduce accidental secret exposure. An event is attempted at most five times, then marked processed with `event.failed`; it no longer contributes to pending count. There is no replay endpoint or dead-letter UI. After correcting a cause, a trusted operator must inspect the event and decide whether a controlled requeue is safe. Blind retries can duplicate external webhook effects.

## Alert and analysis configuration

`ALERT_WEBHOOK_URL` receives a JSON POST for newly created incidents, including `event`, `event_id`, and an incident object. A 2xx response acknowledges delivery. Redirects are not followed. The receiver must tolerate duplicate `event_id` values; delivery is at least once. There are no configured custom headers, signatures, per-route policies, escalation schedules, or email/Slack integrations.

The webhook uses the same URL/port validation and `MONITOR_ALLOW_PRIVATE_NETWORKS` policy as monitors. Enabling private networks widens both destinations. Use an egress policy and trusted administration. Avoid secrets in the webhook URL and do not place a real public receiver in test configuration without intentionally enabling delivery.

If `OPENAI_API_KEY` is configured, manual investigations and automatic worker analysis may send incident evidence to OpenAI. If no key is configured, analysis stays local. Set the key only after reviewing data handling; `store=False` is a request setting, not a promise about provider-wide retention. Provider errors produce heuristic results. Review the `source` field when assessing an analysis.

## Retention and cleanup

`RETENTION_DAYS` defaults to 30 and is applied by the worker on startup and approximately hourly. It removes expired logs, monitor checks, audit rows, and processed events. It does not delete incidents, timelines, deployments, rule states, or unprocessed events. Retention stops when the worker stops. Historical incident evidence can disappear even though the saved incident analysis remains.

There is no archival export service or per-record delete API for logs/incidents/deployments. Define storage budgets and retention obligations outside this demo. Monitor disk usage and back up before any manual maintenance.

```bash
docker compose down
```

This stops the stack and preserves volumes. `docker compose down --volumes` erases the local PostgreSQL and Redis volumes; use that only for an intentional reset after preserving required data.

## Controlled integration checks

The optional `test` Compose profile adds an internal nginx probe with no host port. CI enables private-network requests only for its disposable test stack, then runs:

```bash
python scripts/smoke.py --worker --monitor-url http://probe
```

To reproduce locally, use an isolated, disposable Compose project and configure `MONITOR_ALLOW_PRIVATE_NETWORKS=true` for that test run before starting `docker compose --profile test up --build -d --wait`. The URL is resolved and fetched from the API container. Restore the default private-network block afterward; it should remain false for normal demo/private deployments unless deliberately needed.

The probe option verifies an actual HTTP check against a controlled endpoint returning 200. It does not qualify arbitrary Internet egress, TLS certificates, provider access, signed alerts, concurrent workers, or sustained capacity. The API unit tests, migration check, frontend type/build checks, and this smoke workflow cover different failure modes; a passing readiness check is not a replacement for them.
