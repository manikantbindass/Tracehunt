# TraceHunt AI project documents

| Document | Format | Contents |
| --- | --- | --- |
| [Complete project guide](TraceHunt-AI-Project-Guide.pdf) | PDF, 24 pages | Detailed explanations, architecture and workflow diagrams, example graphs, setup, operations, and limitations |
| [Project presentation](TraceHunt-AI-Project-Presentation.pptx) | PowerPoint, 24 slides | Presentation-ready overview with detailed speaker notes, editable diagrams, and two native charts with embedded data |

## Topic index

Page and slide numbers match.

| Pages/slides | Topics |
| --- | --- |
| 1-4 | What the project is, the problem, users, and operating loop |
| 5-9 | Architecture, stack, log ingestion, HTTP monitoring, and detection rules |
| 10-11 | Illustrative error and latency graphs |
| 12-16 | Incident lifecycle, evidence, optional AI, data model, and reliable delivery |
| 17-21 | Metrics, local setup, API integration, security, and operations |
| 22-24 | Validation limits, a worked example, roadmap, and source map |

## Scope and sources

Prepared 23 October 2026 against implementation revision [`0f148d6`](https://github.com/manikantbindass/Tracehunt/tree/0f148d696d546a78c850bdffa3a55eb52c56ce6b). PDF references and slide notes link to source files at that revision. Graphs are invented educational scenarios, not telemetry, benchmarks, or measured downtime improvements. Proposed extensions are labeled as roadmap ideas. Validation results are identified as the recorded implementation baseline, not a new test run.

For live configuration and current commands, use the [repository README](../../README.md), [system design](../architecture/system-design.md), [API guide](../modules/api.md), [operator runbook](../modules/operations.md), and [security guidance](../../SECURITY.md).

## Editable authoring sources

The shared narrative is in [`scripts/docs/content.py`](../../scripts/docs/content.py). [`build_pdf.py`](../../scripts/docs/build_pdf.py) uses ReportLab; run it from the repository root with a Python environment containing ReportLab. It also exports the shared JSON content into ignored `.tmp/project-docs/`.

[`build_deck.mjs`](../../scripts/docs/build_deck.mjs) uses the Codex bundled `@oai/artifact-tool` presentation runtime and its validation helpers. It is an authoring script, not an application dependency. Configure `RUNTIME_NODE_MODULES`, `TRACEHUNT_PRESENTATION_SKILL`, and `TRACEHUNT_DOCS_PYTHON` for that environment, and run a copy from `.tmp/project-docs/` with the runtime modules available there. Preserve earlier outputs and the private validation receipt before rebuilding because the finalizer intentionally refuses to overwrite them. Review all rendered pages/slides after changing content.
