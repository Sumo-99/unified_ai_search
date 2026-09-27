# Firecrawl: API facts

- Enum: `firecrawl` | Env var: `FIRECRAWL_API_KEY` | Auth: `Authorization: Bearer fc-...` (env var name from SDK docs, unconfirmed on the API pages)
- Base URL: `https://api.firecrawl.dev` | Search: `POST /v2/search` | Extract: **no multi-URL sync endpoint**. `POST /v2/scrape` takes one URL; `/v2/batch/scrape` is async with polling.

## Search: normalized to native
| Normalized | Native | Notes |
|---|---|---|
| `query` | `query` | max 500 characters |
| `max_results` | `limit` | default 10, `MAX_RESULTS_CAP = 100`, per source type |
| `include_domains` / `exclude_domains` | `includeDomains` / `excludeDomains` | mutually exclusive, bare hostnames |
| `include_content` | `scrapeOptions: {formats: [{"type": "markdown"}]}` | string forms of `formats` UNVERIFIED |

Curated kwargs: `sources`, `categories`, `tbs`, `location`, `country`, `timeout`. The `research` category behavior changes on 2026-11-16.

## Search response
`{success, data:{web[], news[], images[]}, warning, id, creditsUsed}`. Flatten `web` only; `news` and `images` go to response extras; `warning` -> extras.
Per web result: `title`, `url`, `description` -> `snippet`, `markdown` -> `content`, `metadata{...}` -> extras. No score, no published date (`published_date = None`). `id` -> `usage.request_id`. No latency.

## Extract (v1 approach)
Concurrent single-URL `POST /v2/scrape` calls through a bounded pool (about 5 workers). Scrape request: `url`, `formats`, `onlyMainContent` (default true), `maxAge`, `timeout` (ms, default 60000), `waitFor`. Response: `{success, data:{markdown, html, ..., metadata{sourceURL, statusCode, contentType, error, ...}, warning}}`.
Per-URL failure = a raised error or `metadata.error` set: -> `failed`. Aggregate `usage`: `latency_s` = total wall clock, `request_id = None`, per-URL scrape details in extras.

## Usage and cost
- Search: `creditsUsed` (integer, exact credits) x price table. Billing: 2 credits per 10 results, rounded up; each scraped result adds scrape credits.
- Extract: scrape returns no cost. Estimate = 1 credit per successfully scraped page x price table, `exact=false`. Optional features add credits (for example +1 for zero data retention); the estimate ignores them unless a caller kwarg enables them.
- Credit price in dollars: **UNVERIFIED, look up in stage 04** (https://docs.firecrawl.dev/billing.md, plan-dependent; use the pay-as-you-go reference).
- Account usage `GET /v2/team/credit-usage` exists (not used in v1).

## Errors
Codes 400, 402, 403, 404, 408, 409, 429, 500. Bodies `{"error": "..."}`; some 5xx `{success:false, code, error}`. `Retry-After` on 429 per https://docs.firecrawl.dev/api-reference/errors.md; error bodies for 402/429/5xx may carry `chargeId`.

## Quirks
Sync search, async batch: v1 deliberately avoids batch. `limit` applies per source. Team-wide concurrency limit.

## Fixtures
Docs examples for search (with and without `scrapeOptions`), scrape success, scrape with `metadata.error`, 402 and 429.

## Sources
https://docs.firecrawl.dev/api-reference/endpoint/search.md
https://docs.firecrawl.dev/api-reference/endpoint/scrape.md
https://docs.firecrawl.dev/billing.md
https://docs.firecrawl.dev/api-reference/errors.md

UNVERIFIED: credit dollar price, `creditsUsed` or ID on scrape in practice, failed-page appearance, string `formats`.
