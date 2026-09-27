# 01_scaffold: uv project and tooling

One job: create a green, empty, typed package with all tooling wired.

## Inputs
- Reference (every run): ../../_shared/conventions.md
- Reference (every run): ../../_shared/design.md (Layout section only)

Do NOT load: `_shared/providers/`, `response-schema.md`, `errors-and-logging.md`.

## Process
1. Write a failing smoke test first: `tests/test_smoke.py` imports `unified_ai_search` and asserts it exposes `__version__`.
2. `uv init --lib` in the repo root, then set `pyproject.toml`: `hatchling`, `requires-python >=3.10`, deps `httpx` and `pydantic>=2`, dev deps `pytest`, `respx`, `ruff`, `mypy`.
3. Create the `src/unified_ai_search/` package with `__init__.py` (`__version__`) and `py.typed`. Do not create the other modules yet.
4. Configure `ruff`, `mypy --strict` and `pytest` in `pyproject.toml`, including the `live` marker (skipped unless `-m live`).
5. `.gitignore` is already in the repo root — verify it covers Python caches, venvs, and `stages/*/output/`.
6. Create an empty-but-honest `README.md` stub.
7. Run the three checks until green.

## Outputs
- `report.md` -> output/: files created, exact commands run, their results.

## Human check
Run `uv run pytest`, `uv run ruff check`, `uv run mypy src` yourself and confirm all three pass. Edit the report if anything is misdescribed; the next stage reads it.
