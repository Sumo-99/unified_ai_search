# 05_hardening: live tests, docs, final walk

One job: make the finished SDK trustworthy to a stranger.

## Inputs
- Working (this run): ../04_adapters/output/ (all five provider reports)
- Reference (every run): ../../_shared/todo.md
- Reference (every run): ../../_shared/conventions.md

Do NOT load: the provider fact sheets (their open items are already in the reports).

## Process
1. Live tests: one `tests/live/test_<provider>.py` per provider (search and extract), marker `live`, skipped without the provider's key. They print, never store, key material. Use them to settle the open facts in `_shared/todo.md` and update the fact sheets.
2. README: install, quick start (`SearchClient(Provider.EXA)`), the response shape, cost semantics (dollars, `exact`, plan-dependent prices, override via `pricing=`), per-provider caveats (clamping, `include_content` on Parallel, You.com `blend` upper bound), how to run tests (`-m live`), how to add a provider (copy `_templates/provider-facts.md`, implement the adapter, register it).
3. Audit: no `httpx` exception escapes; no secret in any log level (test with `caplog` at DEBUG); every WARNING case in `errors-and-logging.md` is tested.
4. Run the ICM walk test: entry file plus one contract routes a cold reader; `CLAUDE.md` under 60 lines; no fact stored in two places; status readable from `stages/*/output/`.
5. Full suite, `mypy --strict` and `ruff` green. Update `_shared/todo.md` with anything learned.

## Outputs
- `report.md` -> output/: live-test results per provider (or "skipped, no key"), open facts settled and still open, walk-test result.

## Human check
Run the contract suite (`uv run pytest tests/contract`), then read the README quick start aloud as a new user would and follow it once against a provider you have a key for.
