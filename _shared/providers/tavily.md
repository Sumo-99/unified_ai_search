# Tavily: API facts

- Enum: `tavily` | Env var: `TAVILY_API_KEY` (UNVERIFIED, SDK convention; docs use a literal `tvly-...` key) | Auth: `Authorization: Bearer <key>`
- Base URL: `https://api.tavily.com` | Search: `POST /search` | Extract: `POST /extract` ("Extract")

## Search: normalized to native
| Normalized | Native | Notes |
|---|---|---|
| `query` | `query` | |
| `max_results` | `max_results` | default 10, `MAX_RESULTS_CAP = 20` |
| `include_domains` / `exclude_domains` | same names | also `include_domains_mode` (`restrict` or `prefer`) |
| `include_content` | `include_raw_content: true` | also accepts `"markdown"` (same as `true`) or `"text"` |
| (always sent) | `include_usage: true` | usage is opt-in |

Curated kwargs: `search_depth` (`basic`/`advanced`/`fast`/`ultra-fast`), `topic` (`general`/`news`/`finance`), `time_range`, `start_date`, `end_date`, `country`, `include_answer` (bool, `basic` or `advanced`), `include_published_date`, `include_domains_mode`, `include_images`, `include_favicon`, `exact_match`, `chunks_per_source` (1-3).

## Search response
`{results[], response_time, auto_parameters, usage:{credits}, request_id, answer?, images?}`.
Per result: `title`, `url`, `content` (query-relevant snippet) -> `snippet`, `raw_content` -> `content`, `score` -> `score`, `published_date` (only when `include_published_date` is set or `topic` is `news`; RFC 2822 string such as `Tue, 11 Mar 2025 17:00:00 GMT`, or `null`) -> `published_date`, `favicon`, `images`, `id` -> extras.
`response_time` (seconds) is the provider latency (the SDK still measures its own). `request_id` -> `usage.request_id`. `answer`, `images`, `auto_parameters` and `response_time` (a string in the docs example) -> response extras.

## Extract
Request: `urls` (string or list, 1-20), `format` (`markdown` default or `text`), `extract_depth` (`basic`/`advanced`), `query`, `chunks_per_source` (1-5), `timeout` (1-60 seconds), `include_images`, `include_favicon`, `include_usage`.
Response: `{results:[{url, raw_content, images, favicon?}], failed_results:[{url, error}], response_time, request_id, usage?}`.
Map `raw_content` -> `content`, `failed_results` -> `failed`. Output order is not guaranteed. HTTP 200 can carry only failures: check both arrays. More than 20 URLs, or all URLs invalid, returns 400 with `failed_results`.

## Usage and cost
`usage.credits` on both operations when `include_usage` is set. Extract may report 0 until 5 successful extractions (credits bill in steps, so extract is approximate). Search: 1 credit for basic/fast/ultra-fast, 2 for advanced. Pay-as-you-go: **$0.008 per credit** (paid plans $0.0075 to $0.005). Sources: https://docs.tavily.com/documentation/api-credits

## Errors
Codes 400, 401, 422, 429, 432 (key or plan limit), 433 (pay-as-you-go limit), 500. Body `{"detail":{"error":"..."}}`; 422 uses FastAPI shape `{"detail":[{type,loc,msg,input}]}`. `Retry-After` declared on 429: integer seconds, `minimum: 0` (OpenAPI `components.headers.RetryAfter`).

## Quirks
Non-standard 432 and 433 map to `RateLimitError`. `urls` may be a string or a list (always send a list). Search `content` is a chunk, not a page summary.

## Fixtures
Docs examples for search (with `usage`), extract `partialSuccess`, extract 400 `allInvalidUrls`, and 422/429/432/433 errors. Stored in `tests/providers/tavily/fixtures/`.

## Sources
https://docs.tavily.com/documentation/api-reference/endpoint/search.md
https://docs.tavily.com/documentation/api-reference/endpoint/extract.md
https://docs.tavily.com/documentation/api-reference/endpoint/usage.md (account usage, not used in v1)
https://docs.tavily.com/documentation/api-credits (prices; $0.008 pay-as-you-go confirmed 2026-09-27)

Verified 2026-09-27 from the OpenAPI specs above: `Retry-After` format, string variants of `include_raw_content`.

UNVERIFIED: env var name (`TAVILY_API_KEY` is the SDK convention; the docs never name one).
