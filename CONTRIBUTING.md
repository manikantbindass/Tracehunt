# Contributing to TraceHunt AI

Open an issue for a bug or proposal, and keep pull requests focused on one behavior. Read the [system design](docs/architecture/system-design.md) and [API guide](docs/modules/api.md) before changing persistence, worker processing, or public contracts.

## Development

Follow the local setup in [README.md](README.md). The API can use SQLite with no external services; use Docker Compose when changing PostgreSQL, Redis, or worker behavior.

Apply `alembic upgrade head` before starting the API/worker for the first time. A database created by direct demo startup may have tables without an Alembic revision; preserve it and use a fresh disposable `DATABASE_URL` for tests, or follow a reviewed adoption plan. Do not delete a developer database or blindly stamp its migration revision. See the [runbook](docs/modules/operations.md#configuration-and-deployment-changes) for the existing-table case.

1. Create a branch from `main`.
2. Make your change and add tests for observable behavior when appropriate.
3. Run `python -m pytest -q` in `apps/api`; run `alembic upgrade head` against a disposable database when changing the schema.
4. Run `npm run typecheck` and `npm run build` in `apps/web`.
5. Run `python scripts/smoke.py` against a disposable development API when changing the API contract. Add `--worker` when changing detection or background processing. The [operator runbook](docs/modules/operations.md#controlled-integration-checks) describes the optional controlled monitor probe.
6. Update relevant documentation and open a pull request.

Never commit `.env` files, API keys, database files, private logs, or customer incident data. Synthetic fixtures should be clearly identified. Treat log text and AI-generated analysis as untrusted input.

## Project conventions

- Python: type annotations, Pydantic request validation, SQLAlchemy persistence.
- Frontend: strict TypeScript, accessible controls, explicit loading/error/empty states.
- API: `/api/v1` routes, stable response shapes, and bounded ingestion/results. List endpoints currently provide limits rather than cursor pagination; do not imply full historical retrieval.
- Database changes: add an Alembic migration; do not rely on demo-mode table creation in production.
- Worker changes: preserve the atomic SQL outbox, lease recovery, persistent incident deduplication, and documented retry limits. External side effects can repeat after a crash; test receiver idempotency where relevant.
- Security changes: exercise demo and authenticated modes, input limits, redaction, and outbound destination validation. Do not weaken the private-network default to make a test pass; use the isolated test profile when appropriate.
- Commits: concise Conventional Commits, for example `fix(api): preserve incident recovery history`.

Record the commands actually run, their results, and anything that could not be verified in the pull request. CI configuration is not evidence that a run passed. Avoid tests that contact real customer services or consume provider credentials; mock external calls and use synthetic records. Documentation should distinguish implemented behavior from planned work, especially for root-cause confidence, traffic metrics, alert delivery, and production readiness.

## Reporting issues

Include the command or screen, expected and actual behavior, relevant sanitized logs, operating system, and the commit SHA. For security issues, follow [SECURITY.md](SECURITY.md).
