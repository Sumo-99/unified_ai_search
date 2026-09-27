# unified-ai-search: the build pipeline

The flow in one line: scaffold it, lay the core contracts, build the client, add one adapter at a time, harden and verify.

| Stage | Job | Input | Output | Human check |
|---|---|---|---|---|
| `01_scaffold` | uv project, tooling, empty package | `_shared/conventions.md` | `output/report.md` | run `uv run pytest`, `ruff check`, `mypy` (all green) |
| `02_core` | enums, errors, models, ABCs, base provider | 01's report, `_shared/design.md`, `_shared/response-schema.md`, `_shared/errors-and-logging.md` | `output/report.md` | read the public models and ABC signatures |
| `03_client` | `SearchClient`, validation, clamping, kwargs filter | 02's report, `_shared/design.md` | `output/report.md` | try the client against the fake provider |
| `04_adapters` | one adapter per provider, via the template | 03's report, `_shared/providers/<name>.md` | `output/<provider>.md` per provider | read each adapter report, then its fixtures |
| `05_hardening` | live-test marker, README, final walk test | all reports | `output/report.md` | run the contract suite, skim the README |

Factory (stable, every run): `_shared/`
Product (new each run): `src/`, `tests/`, and each stage's `output/report.md`

Status is whatever exists: a stage is COMPLETE when its `output/` holds a report. Stage 04 is complete per provider: `output/tavily.md`, `output/exa.md`, `output/parallel.md`, `output/you.md`, `output/firecrawl.md`.

Adapter order in 04 is Tavily, Exa, Parallel, You.com, Firecrawl: simplest response shapes first, the Firecrawl exception (no batch extract) last.
