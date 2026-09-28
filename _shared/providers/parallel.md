# Parallel: API facts

- Enum: `parallel` | Env var: `PARALLEL_API_KEY` (used throughout the docs' code samples) | Auth: `x-api-key` (the only documented security scheme; Bearer UNVERIFIED)
- Base URL: `https://api.parallel.ai` | Search: `POST /v1/search` | Extract: `POST /v1/extract` ("Extract"). The `/v1beta/*` paths are legacy.

## Search: normalized to native
| Normalized | Native | Notes |
|---|---|---|
| `query` | `search_queries: [query]` | no `objective` unless the caller passes it |
| `max_results` | `advanced_settings.max_results` | default 10, no cap documented: pass through |
| `include_domains` / `exclude_domains` | `advanced_settings.source_policy.include_domains` / `exclude_domains` | excludes apply only when includes are empty |
| `include_content` | not supported on search | `content = None` plus WARNING |

Curated kwargs (flat for the caller; the adapter nests them): `objective`, `mode` (`turbo`/`fast`/`basic`/`advanced`, default `advanced`), `max_chars_total`, `session_id`, `client_model`, `after_date` -> `advanced_settings.source_policy.after_date`, `location` / `fetch_policy` / `excerpt_settings` -> `advanced_settings.*`.
`fetch_policy` = `{max_age_seconds (min 600), timeout_seconds, disable_cache_fallback}`; `excerpt_settings` = `{max_chars_per_result}`.

## Search response
`{search_id, results[], warnings (nullable), usage[], session_id}`. `session_id` is always returned (echoed or server-generated). Per result: `url`, `title`, `publish_date` (`YYYY-MM-DD`, often null) -> `published_date`, `excerpts[]` (markdown strings) -> `snippet` (join with `"\n\n"`). No score, no full content.

## Extract
Request: `urls[]` (up to 20), `objective`, `search_queries[]`, `max_chars_total`, `session_id`, `client_model`, `advanced_settings.{fetch_policy, excerpt_settings, full_content}`. **`full_content` sits under `advanced_settings`** (boolean, or `{max_chars_per_result}`; default false).
Response: `{extract_id, results[], errors[], warnings, usage[], session_id}`. Per result: `url`, `title`, `publish_date`, `excerpts[]`, `full_content` -> `content`. Errors: `{url, error_type, http_status_code?, content?}` -> `failed`; documented as "requested URLs not in the results", yet the OpenAPI example lists the same URL in both arrays (the adapter lets the result win). Output is always markdown. The SDK always sets `full_content` (extract always wants page text) and falls back to joined excerpts.

## Usage and cost
`usage[]` = `[{name, count}]` SKU counts, returned by default. Documented SKU names: `sku_search`, `sku_extract_excerpts` (only these two appear anywhere in the docs). `search_id` / `extract_id` -> `usage.request_id`. No latency, no usage headers documented.
Prices (https://docs.parallel.ai/getting-started/pricing.md, confirmed 2026-09-27): search `turbo`/`fast` = $0.001 per request, `basic`/`advanced` = $0.005, each including 10 results, plus $0.001 per additional result; extract = $0.001 per URL (no separate price for full content).
SDK conversion: search = `sku_search` count x mode price + (returned results beyond 10) x $0.001; extract = the largest `sku_extract_*` count x $0.001. Other SKUs are listed in `reported.detail["unpriced_skus"]`.

## Errors
422 `{type:"error", error:{ref_id, message}}` is the only documented error. Rate limit 600 req/min each for search and extract; the 429 body and Retry-After are not documented.

## Quirks
Domain filters, `max_results`, `location`, `fetch_policy` and `excerpt_settings` are nested under `advanced_settings`. Search is objective and query driven. `warnings` and `session_id` -> response extras.

## Fixtures
Search sample response from the Search quickstart (10 results, `usage`), extract sample from the Extract quickstart (`usage`, empty `errors`), the OpenAPI extract example (URL in both `results` and `errors`), and the 422 example. Stored in `tests/providers/parallel/fixtures/`.

## Sources
https://docs.parallel.ai/api-reference/search-api/search.md (embedded OpenAPI read 2026-09-27)
https://docs.parallel.ai/api-reference/extract/extract.md (same)
https://docs.parallel.ai/getting-started/pricing.md
https://docs.parallel.ai/getting-started/rate-limits.md
https://docs.parallel.ai/llms-full.txt (quickstart sample responses, SKU names, `mode` default)

Verified 2026-09-27: env var, `mode` default `advanced`, `full_content` location, prices.

UNVERIFIED: Bearer auth, 429 body and Retry-After, request-ID header, account usage endpoint, max `max_results`, full SKU list (for example a full-content SKU), whether additional results are billed on returned or requested count.
