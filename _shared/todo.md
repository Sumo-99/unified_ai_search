# Recorded TODOs

## Before publishing to PyPI
- **Clean up the ICM build structure.** Delete `stages/`, `_templates/`, and per-run `output/` reports. The codebase at publish time should look like a normal Python package.
- **Fold `_shared/providers/*.md` into `docs/providers/`** — these are living reference docs useful for maintaining the SDK when APIs change. Keep them in the repo, just organized as docs, not as ICM factory files.
- Update `_shared/agent-tools.md` reference in CLAUDE.md if CLAUDE.md is kept as project docs (otherwise delete it too).

## Next after v1
- **Automate refresh of the provider option models and the pricing table from provider docs via the Context7 MCP.** v1 keeps both manual and configurable.
- Async siblings (`AsyncSearcher`, `AsyncExtractor`) beside the sync ABCs.
- Optional shared connection pool through the `HttpSearchProvider._build_http_client` seam.
- Optional `sources` parameter to promote news and images into normalized results.
- You.com account-balance reconciliation (`GET https://api.you.com/v1/billing/account_balance`) as an audit feature, not per-call.
- Dynamic provider switching by parameter.

## Open facts to settle with `live` tests
- Real response payloads and headers for all five providers (all facts so far come from docs and specs).
- You.com: failed-extract shape, whether failed pages are billed, request-ID header.
- Firecrawl: credit price in dollars, whether `/v2/scrape` returns `creditsUsed` or an ID, per-URL failure shape.
- Tavily: canonical env var name.
- Retry-After behavior on 429 for every provider except Tavily (documented header).
