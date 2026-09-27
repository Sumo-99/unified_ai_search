# Parallel: API facts

- Enum: `parallel` | Env var: `PARALLEL_API_KEY` | Auth: `x-api-key` (Bearer acceptance UNVERIFIED)
- Base URL: `https://api.parallel.ai` | Search: `POST /v1/search` | Extract: `POST /v1/extract` ("Extract"). The `/v1beta/*` paths are legacy.

## Search: normalized to native
| Normalized | Native | Notes |
|---|---|---|
| `query` | `search_queries: [query]` | no `objective` unless the caller passes it |
| `max_results` | `advanced_settings.max_results` | default 10, no cap documented: pass through |
| `include_domains` / `exclude_domains` | `advanced_settings.source_policy.include_domains` / `exclude_domains` | up to 200 combined; excludes ignored when includes are set |
| `include_content` | not supported on search | `content = None` plus WARNING |

Curated kwargs: `objective`, `mode` (`turbo`/`fast`/`basic`/`advanced`, default `advanced`), `max_chars_total`, `source_policy.after_date`, `fetch_policy`, `excerpt_settings`, `location`.

## Search response
`{search_id, results[], warnings, usage[]}` (plus `session_id` when sent). Per result: `url`, `title`, `publish_date` (`YYYY-MM-DD`, often null) -> `published_date`, `excerpts[]` (markdown strings) -> `snippet` (join with `"\n\n"`). No score, no full content.

## Extract
Request: `urls[]` (up to 20), `objective`, `search_queries[]`, `max_chars_total`, `fetch_policy`, `full_content` (boolean or settings, default false).
Response: `{extract_id, results[], errors[], warnings, usage[], session_id}`. Per result: `url`, `title`, `publish_date`, `excerpts[]`, `full_content` -> `content`. Errors: `{url, error_type, http_status_code, content}` -> `failed`. Output is always markdown. Extract sets `full_content: true` when the caller wants `content`; otherwise fall back to joined excerpts.

## Usage and cost
`usage[]` = `[{name, count}]` SKU counts, returned by default (e.g. `sku_search`, `sku_extract_excerpts`). `search_id` / `extract_id` -> `usage.request_id`. Convert to dollars with the price table; SKU list stays in `reported.detail`. No latency, no usage headers documented.
Prices (https://docs.parallel.ai/getting-started/pricing.md): search `turbo`/`fast` = 0.001 + 0.001 x extra results; `basic`/`advanced` = 0.005 + 0.001 x extra results; extract = $0.001 per URL.

## Errors
422 `{type:"error", error:{ref_id, message}}`. Rate limit 600 req/min each for search and extract; exact 429 body and Retry-After not documented.

## Quirks
Domain filters and `max_results` are nested under `advanced_settings`. Search is objective and query driven. `warnings` -> response extras.

## Fixtures
Docs examples for search, extract with `errors`, and 422.

## Sources
https://docs.parallel.ai/api-reference/search-api/search
https://docs.parallel.ai/api-reference/extract/extract.md
https://docs.parallel.ai/getting-started/rate-limits.md

UNVERIFIED: Bearer auth, 429 body and Retry-After, request-ID header, account usage endpoint, max `max_results`.
