# You.com: API facts

- Enum: `you` | Env var: `YDC_API_KEY` (named in the docs header) | Auth: `X-API-Key: <key>`
- Base URL: `https://ydc-index.io` | Search: `POST /v1/search` | Extract: `POST /v1/contents` ("Contents")

## Search: normalized to native
| Normalized | Native | Notes |
|---|---|---|
| `query` | `query` | |
| `max_results` | `count` | default 10, applies per section (`web` and `news`), no cap in the API reference: pass through |
| `include_domains` / `exclude_domains` | same names | up to 500 each; passing both returns 422, so the SDK sends only `include_domains` (WARNING) |
| `include_content` | `extraction: {extraction_mode: "full_page", full_page: {extraction_formats: ["markdown"]}}` | POST only; identical to the docs' Full Page example request |

Curated kwargs: `freshness` (`day`/`week`/`month`/`year` or `YYYY-MM-DDtoYYYY-MM-DD`), `country`, `language`, `safesearch` (`off`/`moderate`/`strict`), `offset` (0-9), `knowledge` (`core`), `boost_domains` (not combinable with `include_domains`), `crawl_timeout` (1-60, default 10), `extraction_source` (`blend`/`cache`/`fetch`; nested into `extraction`, full page only), `highlights` (SDK flag -> `extraction: {extraction_mode: "highlights"}`; full page wins when both are set). `livecrawl` and `livecrawl_formats` are deprecated: not curated.

## Search response
`{results:{web[], news[], knowledge[]?}, metadata:{search_uuid, query, latency}}`. Flatten `web` only into `results`; `news` and `knowledge` go to response extras. `knowledge` is omitted when none are relevant.
Per web result: `url`, `title`, `description` -> `snippet` (else joined `snippets[]`, else joined `contents.highlights`), `snippets[]` -> extras, `contents.markdown` -> `content`, `page_age` (ISO without timezone in the examples, for example `2024-12-18T00:00:00`, but typed as a free string) -> `published_date`, `thumbnail_url` and `favicon_url` -> extras. No score.
With `extraction_mode: "highlights"`, `description` and `snippets` are omitted and `contents.highlights[]` is returned instead.
`metadata.search_uuid` -> `usage.request_id`; `metadata.latency` (seconds) -> extras.

## Extract
Request: `urls[]`, `formats[]` (`html`/`markdown`/`metadata`), `crawl_timeout` (1-60), `max_age` (≥0 seconds, nullable). No URL limit documented. The SDK always sends `formats: ["markdown", "metadata"]`.
Response: a **bare JSON array** `[{url, title, html?, markdown?, metadata?{site_name, favicon_url}}]`, no envelope, so no request ID or latency in the body. The SDK wraps it as `raw = {"results": [...]}`. Per-URL failures are not documented: pages that fail come back with null `markdown` and `html`, and are mapped to `failed` ("no content returned"). Requested URLs absent from the array also go to `failed`.

## Usage and cost
No cost, credit or usage field in any body. Rate-limit headers `X-RateLimit-Limit/Remaining/Reset` (request counts; Reset is a Unix timestamp) on every response -> extras.
Static estimate (https://you.com/docs/administration/billing.md, confirmed 2026-09-27):
- Search: $0.005 per call ("up to 100 results per call"). `count` does not change it. Knowledge, snippets and highlights are included.
- Full-page extraction: +$0.001 per page crawled live, counted over **web and news** results (the billing example counts both). `cache` = $0 extra; `fetch` = every returned page live; `blend` (default) is unknowable, so the SDK reports the **upper bound** (`0.005 + pages x 0.001`) with lower and upper bounds in `reported.detail`. Pages = web plus news results with non-null `contents` (an inference).
- Contents: $0.001 per page. The SDK bills every entry in the returned array (UNVERIFIED whether failed pages are billed).
All `exact=false`.

## Errors
401 and 403 `{detail}`; 402 `{error, message, upgrade_url, limit?, used?, period?, reset_at?}`; 422 `{error}`; 500 `{detail}`. The field names are documented, but no example values are. 429 is not in the API reference, but https://you.com/docs/rate-limits.md documents it and says to honor `Retry-After` "when present".

## Quirks
Three different error shapes. Results grouped by section. Highlights and snippets are mutually exclusive. "Up to 100 results per call" on the billing page is the only hint of a `count` limit; the API reference gives none, so the SDK passes it through.

## Fixtures
Four search examples from the API reference (snippets with web and news, highlights, knowledge, full page with web and news markdown), the contents example (html and metadata only), and 401/402/422 bodies built from the documented field names. Stored in `tests/providers/you/fixtures/`.

## Sources
https://docs.you.com/api-reference/search/v1-search.md (redirects to you.com/docs; read 2026-09-27)
https://docs.you.com/api-reference/contents.md
https://you.com/docs/rate-limits.md
https://you.com/docs/administration/billing.md

Verified 2026-09-27: env var, the full-page request shape, highlights pricing (included), Retry-After on 429, and that news pages count toward full-page billing.

UNVERIFIED: failed-extract shape, whether failed pages are billed, request-ID header, price of deprecated `livecrawl`, a hard `count` limit, account usage beyond `GET https://api.you.com/v1/billing/account_balance` (not used in v1).
