# 04_adapters: one provider adapter per run

One job: implement a single provider adapter from its fact sheet, register it, and pass the contract suite. Run once per provider, in this order: `tavily`, `exa`, `parallel`, `you`, `firecrawl`.

## Inputs
- Working (this run): ../03_client/output/report.md
- Working (this run): the previous provider's `output/<provider>.md`, for pattern only (skip on the first run)
- Reference (every run): ../../_shared/providers/<provider>.md (only the current provider's file)
- Reference (every run): ../../_shared/response-schema.md
- Reference (every run): ../../_shared/errors-and-logging.md
- Reference (every run): ../../_shared/design.md (Request handling section)

Do NOT load: other providers' fact sheets, or the design sections on layout and the client.

## Process
1. Check the fact sheet for `UNVERIFIED` items that block this adapter. Resolve what docs can settle (for Firecrawl: the credit price, from the billing page); leave the rest marked and note them in the report.
2. Record fixtures under `tests/providers/<provider>/fixtures/` from the docs examples listed in the fact sheet.
3. Tests first, per adapter: request payload mapping (`query`, `max_results` including native naming and nesting, domains, `include_content`), response mapping (snippet join, content, date parse to `datetime` with original in `extras["published_raw"]`, extras), extract with partial failures, header capture, error-body parsing, cost (`reported`, `exact`, `detail`), kwargs filtering against its option models.
4. Implement `providers/<provider>.py` and its typed option models (curated set from the fact sheet). Set `MAX_RESULTS_CAP` only where the fact sheet documents one. Register in `registry.py`.
5. Confirm the shared contract suite now includes this provider and passes; `mypy --strict`, `ruff`, full suite green.
6. Add the static prices used to `pricing.py` with source URL and date.

Provider notes: Firecrawl extract uses a bounded thread pool over `/v2/scrape`; Parallel sets `full_content` for extract when content is wanted; You.com extract treats null content as a failure and reports the `blend` upper bound.

## Outputs
- `<provider>.md` -> output/: what was mapped, fixtures used, `UNVERIFIED` items still open, price values added, deviations from the fact sheet.

## Human check
Read the adapter's mapping table in the report, then open its fixtures and confirm one search and one extract response map to the fields you expect in `_shared/response-schema.md`. Edit the report in place; the next provider run reads it for pattern.
