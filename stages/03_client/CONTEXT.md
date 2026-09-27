# 03_client: SearchClient (the strategy context)

One job: the public facade that selects a strategy and applies request-level rules.

## Inputs
- Working (this run): ../02_core/output/report.md
- Reference (every run): ../../_shared/design.md (Pattern and Request handling sections)
- Reference (every run): ../../_shared/errors-and-logging.md

Do NOT load: `_shared/providers/`, `response-schema.md` (already built in 02).

## Process
1. Tests first against `FakeProvider` registered in the registry: string and enum coercion, unknown provider `ValueError`, missing key raises `MissingAPIKeyError` at construction (explicit key beats env var), `InvalidRequestError` wrapping pydantic errors before any network call, `max_results` clamping to `MAX_RESULTS_CAP` with a WARNING (no clamp when the adapter declares none), kwargs filtering (drop unknown or mistyped, WARNING, call proceeds, normalized param wins on collision), `Extractor` capability check, `close()` and context-manager behavior.
2. Implement `client.py` per the design. The client builds its strategy itself from the registry; no strategy object is ever accepted from outside.
3. Export the public API from `__init__.py`: `SearchClient`, `Provider`, the models, the errors, `PricingTable`.
4. `mypy --strict`, `ruff`, full suite green.

## Outputs
- `report.md` -> output/: public API listing, behavior table of every rule with the test that proves it.

## Human check
Use the client from a Python REPL against the fake provider: construct with a missing key, a bad string, a clamped `max_results`, a bogus kwarg. Confirm each behaves as the design says.
