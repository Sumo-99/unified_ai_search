# Conventions

## Tooling
- `uv` project, `hatchling` build, `src/` layout, Python `>=3.10`.
- Runtime deps: `httpx`, `pydantic>=2`. Dev deps: `pytest`, `respx`, `ruff`, `mypy`.
- `mypy --strict`, `ruff check` and `ruff format --check` must pass at the end of every stage.
- Package ships `py.typed`.

## Testing
- TDD: write the failing test, watch it fail, then write the code.
- `tests/contract/`: one suite parametrized over `PROVIDER_REGISTRY`. Asserts ABC conformance, normalized response shape, error mapping, missing-key failure, `usage` always populated.
- `tests/providers/<name>/`: adapter unit tests using fixtures under `fixtures/`, mocked with `respx`. Fixtures start from the docs' example payloads listed in `_shared/providers/<name>.md`.
- `tests/live/`: marker `live`, skipped by default, needs real keys (`-m live`).
- No test makes a real network call unless marked `live`.

## Style
- Match the surrounding code's comment density. Comments only for the non-obvious why.
- One class per concern. Adapters translate only; validation, clamping and kwargs filtering live in the client and base classes.
- Provider-specific constants (`MAX_RESULTS_CAP`, endpoints, env var name) are class attributes on the adapter.
- Names: modules `snake_case`, classes `PascalCase`, provider files named by `Provider` enum value.

## Docs and provenance
- Every provider fact in `_shared/providers/` carries a source URL. Anything not verified is marked `UNVERIFIED`.
- Static prices carry source URL and collection date, in `pricing.py` and in the provider file.
