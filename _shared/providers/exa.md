# Exa: API facts

- Enum: `exa` | Env var: `EXA_API_KEY` (named in the docs' agent instructions; the official SDKs read it) | Auth: `Authorization: Bearer <key>` (or `x-api-key`)
- Base URL: `https://api.exa.ai` | Search: `POST /search` | Extract: `POST /contents` ("Contents")

## Search: normalized to native
| Normalized | Native | Notes |
|---|---|---|
| `query` | `query` | |
| `max_results` | `numResults` | default 10, 1-100 public limit, `MAX_RESULTS_CAP = 100` |
| `include_domains` / `exclude_domains` | `includeDomains` / `excludeDomains` | camelCase |
| `include_content` | `contents: {text: true}` | content fields are opt-in |
| (always sent) | `contents: {highlights: true}` | highlights are opt-in and are the only snippet source |

Curated kwargs: `type` (`instant`/`fast`/`auto`/`deep-lite`/`deep`/`deep-reasoning`, default `auto`), `category` (known: `company`, `publication`, `news`, `personal site`, `financial report`, `people`; typed as a string), `userLocation`, `startPublishedDate`, `endPublishedDate`, `startCrawlDate`, `endCrawlDate`, `moderation`.
Deprecated and not curated: `includeText`, `excludeText`, `contents.livecrawl` (use `maxAgeHours`), `crawledBeforeDate` (use `snapshotAsOf`).

## Search response
`{requestId, results[], costDollars, searchTime?, resolvedSearchType? (deprecated), output?}`.
Per result: `id`, `title` (nullable), `url`, `publishedDate` (ISO 8601 with `Z`) -> `published_date`, `author`, `image`, `favicon`, `summary` and `highlightScores` -> extras, `highlights[]` -> `snippet` (join with `"\n\n"`), `text` -> `content`. There is no per-result `score` in the schema, so `score = None`.
`searchTime` is server-side processing in milliseconds (it can be lower than end-to-end latency) -> response extras.

## Extract
Request: `urls[]` (1-100; `ids` is the deprecated alias), plus `text`, `highlights`, `summary`, `maxAgeHours`, `livecrawlTimeout`, `subpages`, `subpageTarget`, `snapshotAsOf`. `text` takes a boolean or `{maxCharacters, includeHtmlTags, verbosity, includeSections, excludeSections}`. There is no markdown option: output is text, optionally with HTML tags.
Response: `{requestId, results[], statuses[], costDollars}`. `statuses[]` = `{id, status: "success"|"error", source?: "cached"|"crawled", error?: {tag, httpStatusCode|null}}` (field examples: `CRAWL_NOT_FOUND`, `404`). A result's `id` is the requested URL; its `url` can differ (a resolved or PDF URL). HTTP 200 even when URLs fail; match by `id`, not position. Failed -> `failed`.

## Usage and cost
`costDollars.total` is in dollars and returned on both operations (e.g. 0.007 for a search, 0.003 for a contents call) -> `reported`. The docs call it an "**estimated** total dollar cost ... not an invoice record", so `exact=false`. Breakdown (`search.{neural,keyword}`, `contents.{text,highlights,summary}`, `summary`) -> `reported.detail`. `requestId` -> `usage.request_id`.
Headers: `x-request-id` on every response (matches `requestId`); `x-exa-queued` and `x-exa-queue-ms` on 200 -> extras.

## Errors
`{requestId, error, tag}` on 400 (`INVALID_REQUEST_BODY`), 401 (`INVALID_API_KEY`), 402 (out of credits or budget; x402 challenge without a key), 429 (`RATE_LIMIT_EXCEEDED`), 500 (`DEFAULT_ERROR`), 503 (`SERVICE_OVERLOADED`). 402 and 503 map to `ProviderAPIError`. `Retry-After` is not among the documented 429 headers.

## Quirks
Extra request fields (`outputSchema`, `systemPrompt`, `stream`, `additionalQueries`) belong to the deep and answer modes and are not in the curated set. Some options are beta (`x-exa-lifecycle: beta`). The GitHub OpenAPI spec is older than the docs' embedded spec (it lacks `deep-lite` and still lists `neural`), so the docs win.

## Fixtures
Docs examples for search (with contents), contents (success status only; tests add an error status from the documented field examples), and 400/401/429/503 errors. Stored in `tests/providers/exa/fixtures/`.

## Sources
https://docs.exa.ai/reference/search.md (redirects; embedded OpenAPI read 2026-09-27)
https://docs.exa.ai/reference/get-contents.md (same)
https://raw.githubusercontent.com/exa-labs/openapi-spec/master/exa-openapi-spec.yaml (older)

Verified 2026-09-27: env var, default `type`, contents text options (no markdown or html names), `costDollars` is an estimate.

UNVERIFIED: `Retry-After` on 429 (undocumented; the base parses it if present), account usage path (not used in v1).
