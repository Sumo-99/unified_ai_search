# You.com: API facts

- Enum: `you` | Env var: `YDC_API_KEY` | Auth: `X-API-Key: <key>`
- Base URL: `https://ydc-index.io` | Search: `POST /v1/search` | Extract: `POST /v1/contents` ("Contents")

## Search: normalized to native
| Normalized | Native | Notes |
|---|---|---|
| `query` | `query` | |
| `max_results` | `count` | default 10, applies per section (`web` and `news`), no cap documented: pass through |
| `include_domains` / `exclude_domains` | same names | up to 500 each; passing both returns 422 |
| `include_content` | `extraction: {extraction_mode: "full_page", full_page: {extraction_formats: ["markdown"]}}` | POST only |

Curated kwargs: `freshness`, `country`, `language`, `safesearch`, `offset`, `extraction_source` (`blend`/`cache`/`fetch`), `crawl_timeout` (1-60, default 10), `boost_domains`. `livecrawl` is deprecated: not in the curated set.

## Search response
`{results:{web[], news[], knowledge[]}, metadata:{search_uuid, query, latency}}`. Flatten `web` only into `results`; `news` and `knowledge` go to response extras.
Per web result: `url`, `title`, `description` and `snippets[]` -> `snippet`, `contents.markdown` -> `content`, `page_age` (free-form string, parse if possible) -> `published_date`, `thumbnail_url` and `favicon_url` -> extras. No score.
`metadata.search_uuid` -> `usage.request_id`; `metadata.latency` (seconds) is the provider latency.

## Extract
Request: `urls[]`, `formats[]` (`html`/`markdown`/`metadata`), `crawl_timeout`, `max_age`. No URL limit documented.
Response: a **bare JSON array** `[{url, title, html, markdown, metadata{site_name, favicon_url}}]`, no envelope, so no request ID or latency in the body. Per-URL failures are not documented: pages that fail to crawl come back with null `markdown` and `html`. Treat null content as a failure: -> `failed` with a generic error.

## Usage and cost
No cost, credit or usage field in any body. Rate-limit headers `X-RateLimit-Limit/Remaining/Reset` (request counts) on every response -> extras.
Static estimate (https://you.com/docs/administration/billing.md, collected 2026-09-27):
- Search: $0.005 per call. `count` does not change it.
- Full-page extraction: +$0.001 per page crawled live. `cache` = $0 extra; `fetch` = every returned page live; `blend` (default) unknowable: report the **upper bound** (`0.005 + pages x 0.001`) with lower and upper bounds in `reported.detail`. Pages = results with non-null `contents` (an inference).
- Highlights extraction: appears free (UNVERIFIED).
- Contents: $0.001 per URL.
All `exact=false`.

## Errors
401 and 403 `{detail}`; 402 `{error, message, upgrade_url, limit, used, period}`; 422 `{error}`; 500 `{detail}`. 429 and Retry-After not documented, but `Retry-After` is listed at https://you.com/docs/rate-limits.md for 429.

## Quirks
Three different error shapes. Results grouped by section. Highlights and snippets are mutually exclusive.

## Fixtures
Docs examples for search (web and news), contents array with a null-content page, 402 and 422.

## Sources
https://docs.you.com/api-reference/search/v1-search.md
https://docs.you.com/api-reference/contents.md
https://you.com/docs/rate-limits.md
https://you.com/docs/administration/billing.md

UNVERIFIED: failed-extract shape, whether failed pages are billed, request-ID header, price of deprecated `livecrawl`, highlights pricing, account usage beyond `GET https://api.you.com/v1/billing/account_balance` (not used in v1).
