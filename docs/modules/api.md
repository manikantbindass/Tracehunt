# API guide

The application API lives at `/api/v1`. Run the backend and use `/docs` or `/openapi.json` for its generated schema. Examples below use a local demo with `curl`; in Windows PowerShell use `curl.exe` to avoid older shell aliases, or send the same JSON with `Invoke-RestMethod`.

## Authentication and errors

When `DEMO_MODE=false`, send the shared workspace key in `X-API-Key` on every application request. All holders have the same read/write permissions. Demo mode ignores API-key authentication even if a key is configured.

```bash
curl http://localhost:8000/api/v1/settings \
  -H "X-API-Key: YOUR_WORKSPACE_KEY"
```

Health and readiness routes, their `/api/v1` aliases, and generated documentation are publicly readable. Both metrics routes require the key outside demo mode. The frontend can proxy the versioned API; unversioned operational endpoints are served directly by the backend.

Requests use JSON. Unknown input fields are rejected; strings are trimmed. Common error statuses are `401` for a missing/incorrect key, `404` for an absent resource, `413` for a body above `MAX_BODY_BYTES` (default 1 MiB), and `422` for validation failures. Validation errors can return a `detail` array; other handled errors typically return a `detail` string.

IDs are strings and timestamps are server-assigned UTC values. Create routes return `201`. Delete monitor returns `204` without a body. There are no idempotency keys, general update routes, bulk deletion routes, or cursor-based pagination. Retrying a successful create request can duplicate its records.

## Structured logs

```bash
curl -X POST http://localhost:8000/api/v1/logs \
  -H "Content-Type: application/json" \
  -d '{"service":"checkout-api","level":"ERROR","message":"Database connection timeout","trace_id":"trace-001","metadata":{"latency_ms":1250,"status_code":503,"synthetic":true}}'
```

| Field | Contract |
| --- | --- |
| `service` | Required; 1–120 characters, letters/digits/underscore plus `.`, `/`, `-` |
| `level` | `DEBUG`, `INFO`, `WARN`, `ERROR`, `FATAL`; default `INFO`; case-insensitive input and `WARNING` normalizes to `WARN` |
| `message` | Required; 1–10,000 characters |
| `trace_id` | Optional string, at most 128 characters |
| `metadata` | JSON object, default `{}`; serialized size at most 16,000 UTF-8 bytes; non-finite numeric values are rejected |

The stored response includes an ID and `created_at`. Message and metadata redaction is best effort. Avoid secrets in every field, including service and trace identifiers. There is no client-provided timestamp field. Numeric `metadata.latency_ms` contributes to overview latency calculations.

Batch ingestion accepts one to 500 records in a single transaction; the total request body limit still applies:

```bash
curl -X POST http://localhost:8000/api/v1/logs/batch \
  -H "Content-Type: application/json" \
  -d '{"logs":[{"service":"checkout-api","message":"Synthetic request completed"},{"service":"checkout-api","level":"WARN","message":"Synthetic latency warning"}]}'
```

Response shape: `{"accepted":2,"ids":["...","..."]}`. Invalid batch input rejects the whole request.

`GET /logs` returns newest records first. Parameters: `service` (exact match), `level`, `search` (literal case-insensitive substring of message or trace ID), and `limit` (1–1000, default 100). Empty filters and `all` service/level values disable those filters. Search is not a full-text or regular-expression engine; SQL wildcard characters are escaped.

## HTTP monitors

```bash
curl -X POST http://localhost:8000/api/v1/monitors \
  -H "Content-Type: application/json" \
  -d '{"name":"public-api","url":"https://example.com/health","method":"GET","interval_seconds":60,"timeout_seconds":10,"expected_status":200,"latency_threshold_ms":1000,"enabled":true}'
```

| Field | Default and bounds |
| --- | --- |
| `name` | Required, 1–120 characters; letters/digits/underscore, spaces, `.`, `:`, `/`, `-` |
| `url` | Required, 8–2048 characters; HTTP or HTTPS; no credentials or fragments |
| `method` | `GET` or `HEAD`, default `GET` |
| `interval_seconds` | 60; range 30–86,400 |
| `timeout_seconds` | 10; range 1–30 |
| `expected_status` | 200; range 100–599 |
| `latency_threshold_ms` | 1000; range 10–60,000 |
| `enabled` | `true` |

Allowed target ports are 80, 443, 8000, 8080, and 8443. Private/non-global addresses are blocked by default. Enabled monitor creation resolves and validates DNS; disabled creation can store an unresolved hostname, which is validated when enabled or checked. See [SECURITY.md](../../SECURITY.md).

| Route | Behavior |
| --- | --- |
| `GET /monitors` | All monitors, newest first; includes status, last latency/check, `is_demo`, and 24-hour uptime |
| `PATCH /monitors/{id}` | Accepts only `{"enabled":false}` or `{"enabled":true}` |
| `POST /monitors/{id}/check` | Synchronous immediate check; returns updated monitor; also works when paused |
| `DELETE /monitors/{id}` | Removes the monitor and its stored check rows |

There is no public check-history route or target/threshold edit route. Create a replacement monitor to change those fields. `down` means a request error or unexpected status; `degraded` means expected status with latency above threshold. Scheduled checks need the worker. Demo monitors never contact their target URLs.

## Incidents and investigations

```bash
curl -X POST http://localhost:8000/api/v1/incidents \
  -H "Content-Type: application/json" \
  -d '{"title":"Checkout errors after release","service":"checkout-api","severity":"high","summary":"Synthetic investigation of repeated connection timeouts."}'
```

Create requires `title` (3–240 characters) and `service` (1–120); `severity` is `critical`, `high`, `medium`, or `low` (default `medium`), and `summary` defaults to empty with a 10,000-character maximum.

`GET /incidents` supports `status`, `severity`, `search` (literal case-insensitive substring of title or service), and `limit` (1–500, default 100). Empty/`all` status and severity filters are ignored. `GET /incidents/{id}` adds a chronological `timeline` to the incident response.

```bash
curl -X PATCH http://localhost:8000/api/v1/incidents/INCIDENT_ID \
  -H "Content-Type: application/json" -d '{"status":"investigating"}'

curl -X POST http://localhost:8000/api/v1/incidents/INCIDENT_ID/analyze

curl -X PATCH http://localhost:8000/api/v1/incidents/INCIDENT_ID \
  -H "Content-Type: application/json" -d '{"status":"resolved"}'
```

Allowed statuses are `open`, `investigating`, and `resolved`. Any can transition to another; changing a resolved incident to `open` reopens it and clears `resolved_at`. Repeating the same status does not append another status timeline entry.

Analysis returns `summary`, `probable_cause`, `confidence`, `evidence`, `recommended_actions`, `source` (`heuristic` or `openai`), and `generated_at`. It stores the latest result and appends timeline activity. It can also run automatically when the worker handles a newly created incident. Model suggestions never execute actions. See [analysis windows and limitations](../architecture/system-design.md#evidence-and-analysis).

## Deployments and activity

```bash
curl -X POST http://localhost:8000/api/v1/deployments \
  -H "Content-Type: application/json" \
  -d '{"service":"checkout-api","version":"v1.2.0","environment":"production","status":"success","commit_sha":"a1b2c3d"}'
```

`service` and `version` are required (1–120 characters). `environment` defaults to `production` (1–32 characters). Status is `success` (default), `failed`, `in_progress`, or `rolled_back`. Optional `commit_sha` is 7–64 hexadecimal characters. Records describe a release; they do not deploy software.

`GET /deployments` and `GET /audit` accept `limit` from 1–500 (default 100), newest first. Audit actors are `operator` or `system` labels and do not identify individual API-key holders. `GET /settings` returns non-secret flags and selected runtime settings; it cannot change server configuration.

## Overview and update stream

`GET /overview?hours=24` accepts 1–168 hours and returns `stats`, 24 `traffic` buckets, `services`, recent incidents/releases, and audit activity. `requests_24h` retains its name for compatibility even when a different `hours` window is requested. It counts log records. `sampled` and `sample_limit` indicate the log aggregation bound; use the [system design](../architecture/system-design.md#read-views-and-operational-limits) for metric semantics.

`GET /events` returns `text/event-stream`, beginning with a `connected` event and then `activity` events with serialized audit rows. Comment heartbeats are emitted while connected. It polls SQL about every three seconds and starts at connection time; there is no `Last-Event-ID` replay or durable subscription, and log ingestions do not each produce an audit event.

```bash
curl -N http://localhost:8000/api/v1/events \
  -H "X-API-Key: YOUR_WORKSPACE_KEY"
```

Browser native `EventSource` cannot set the required custom header. Authenticated clients should use a fetch-based SSE reader or a trusted same-origin gateway. Never place the key in a query string. Use ordinary API reads to refresh complete current state after a disconnect.

## Operational routes

| Route | Meaning |
| --- | --- |
| `GET /health` or `/api/v1/health` | Process liveness, version, and demo flag; no dependency checks |
| `GET /ready` or `/api/v1/ready` | SQL connectivity and monitor-table query; `503` when unavailable |
| `GET /metrics` or `/api/v1/metrics` | Prometheus text gauges; authentication required outside demo mode |

Metrics are `tracehunt_logs_total` (currently stored logs), `tracehunt_incidents_active`, `tracehunt_monitors_total`, and `tracehunt_events_pending`. Despite `_total` names, these are gauges and may decrease after deletion/retention. Readiness does not check worker or Redis health. See the [operator runbook](operations.md) for diagnosis and recovery.
