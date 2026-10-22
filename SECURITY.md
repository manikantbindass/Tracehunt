# Security

## Reporting vulnerabilities

Report a vulnerability privately through this repository's GitHub security reporting feature if enabled. If it is unavailable, contact the repository owner privately before publishing exploit details. Do not attach real API keys, production logs, or customer information to a public issue. Include affected versions, a synthetic reproduction, impact, and any suggested fix. No response-time or supported-release guarantee is currently published.

## Access and deployment boundary

The default configuration is a **local demonstration**. `DEMO_MODE=true` disables application API-key authentication, including when `API_KEY` is set. Sample data is synthetic, and Compose publishes web/API ports only on `127.0.0.1`. Disabling demo mode does not remove existing sample data.

With `DEMO_MODE=false`, startup requires an `API_KEY` of at least 24 characters. Versioned application routes and metrics validate `X-API-Key` using a constant-time comparison. Health/readiness endpoints (including their versioned aliases), `/docs`, and `/openapi.json` remain readable without the key. Restrict those at a gateway if their metadata should not be public.

All API-key holders share the same workspace and read/write permissions. There are no individual accounts, scoped ingestion tokens, tenant isolation, RBAC, SSO, or user-level audit identities. Audit `operator`/`system` labels do not identify a person, and audit records are not tamper-proof. The dashboard is not a separate authorization boundary; its key is held in browser session storage and is accessible to scripts running on that origin.

Before a network-facing deployment:

- Disable demo/seeding, generate a strong random key, and supply it through the environment or a secret manager. Coordinate key rotation across API, worker configuration, clients, and browser sessions; there is no dual-key rotation period.
- Use HTTPS plus authenticated access or a private network. Configure exact allowed CORS origins; CORS is a browser control, not API authorization.
- Keep SQL and Redis private, replace local database credentials, protect backups, and test restoration. Compose's default Redis has no password and relies on its private network boundary.
- Restrict ingestion to trusted producers and impose gateway connection, rate, request-time, and body limits. The application bounds request bodies (1 MiB by default) and schemas but does not implement rate limiting or per-client quotas.
- Restrict outbound traffic and review every private-network exception. Set retention and disk limits and assign monitoring/incident-response ownership.

## Outbound request protection

Monitor and webhook requests accept only HTTP/HTTPS and ports 80, 443, 8000, 8080, or 8443. URLs containing credentials or fragments are rejected. When private monitoring is disabled, non-global IP addresses, including loopback/link-local/private/reserved destinations, are rejected; all DNS results are checked. The chosen address is pinned for the request while preserving the hostname for Host/TLS. Redirect following and environment proxy use are disabled, TLS verification remains enabled, and response bodies are not downloaded.

Disabled monitors can store unresolved hostnames; full DNS validation happens when enabled or checked. Sample monitors never make outbound requests. `MONITOR_ALLOW_PRIVATE_NETWORKS=true` permits non-global destinations for both monitors and alert webhooks. Only trusted administrators should enable it. Application validation reduces SSRF exposure but does not replace network egress restrictions or a monitored-host allowlist.

There is no authenticated-monitor header/body configuration or signed webhook support. Alert receivers should deduplicate `event_id` because delivery can repeat. Do not put credentials in URLs; stored monitor URLs are visible to workspace users.

## Sensitive data and analysis

Log messages/metadata, incident content, audit details, and external analysis payloads receive selected best-effort redaction. The implementation uses sensitive-key matching and text patterns; it does not recognize every credential format or confidential identifier. Not every stored field is redacted, and arbitrary service names, trace IDs, URLs, and release values can contain sensitive data. Remove secrets at the source, use synthetic data for tests, and treat telemetry and backups as sensitive.

When `OPENAI_API_KEY` is set, manual and automatic worker investigations can send incident context and correlated evidence to OpenAI. Requests use structured output and `store=False`; that flag does not establish a provider-wide data-retention policy. Review the provider/account data handling terms and your own policy before enabling the integration. No provider key is exposed by the settings endpoint. Without a provider key, analysis runs locally; provider failures fall back to labeled heuristics.

Telemetry is treated as untrusted model input. AI findings and local pattern matches are hypotheses, and confidence is not a calibrated probability. TraceHunt does not execute suggested commands, infrastructure changes, or remediation. Operators must validate the evidence before acting.

The [operator runbook](docs/modules/operations.md) documents backups, retention coverage, failed events, and deployment checks. This repository is a development foundation; it makes no claim of hardened multi-tenant operation, regulatory compliance, penetration-test coverage, or qualified production capacity.
