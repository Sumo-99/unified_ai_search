# 02_core: contracts and base classes

One job: build every type the adapters and client depend on, and nothing that talks to a real provider.

## Inputs
- Working (this run): ../01_scaffold/output/report.md
- Reference (every run): ../../_shared/design.md
- Reference (every run): ../../_shared/response-schema.md
- Reference (every run): ../../_shared/errors-and-logging.md
- Reference (every run): ../../_shared/conventions.md

Do NOT load: `_shared/providers/` (adapters are stage 04), other stages' reports.

## Process
1. Tests first, module by module: `enums.py` (`Provider`), `errors.py` (the full tree, `RateLimitError.retry_after`, `ProviderAPIError.status_code/body`), `models.py` (requests with validation, responses, `Usage`, `ReportedCost`, all frozen), `pricing.py` (`PricingTable` with pay-as-you-go defaults, overridable; values carry source URL and date; Firecrawl credit price left as a marked placeholder until stage 04).
2. `providers/base.py`: `Searcher`, `Extractor`, `SearchProvider` ABCs, then `HttpSearchProvider`: builds the `httpx.Client`, measures latency, translates status codes and `httpx` exceptions into the error tree, logs per `errors-and-logging.md`, exposes hooks for error-message parsing and header capture, owns `close()`.
3. `providers/options.py`: base class and filter helper for typed provider kwargs (drop unknown or mistyped names with a WARNING).
4. `logging.py`: logger with `NullHandler`, and a redaction helper for secrets.
5. `registry.py` with an empty-safe `PROVIDER_REGISTRY`.
6. A test-only `FakeProvider(HttpSearchProvider)` under `tests/` plus `tests/contract/` harness parametrized over the registry (the fake first, real adapters join in stage 04). Contract cases: ABC conformance, response shape, error mapping (401, 403, 429 with and without Retry-After, 5xx, timeout), `usage` always populated, no secret in logs.
7. `mypy --strict`, `ruff`, and the full suite green.

## Outputs
- `report.md` -> output/: public models and ABC signatures as built, deviations from `_shared/design.md` (each with a reason), test counts.

## Human check
Read `models.py` and `providers/base.py` against `_shared/response-schema.md` and `_shared/design.md`. Any deviation in the report must be one you accept; edit the report in place, or revert it before stage 03.
