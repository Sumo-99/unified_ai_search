# Exa: API facts

- Enum: `exa` | Env var: `EXA_API_KEY` | Auth: `Authorization: Bearer <key>` (or `x-api-key`)
- Base URL: `https://api.exa.ai` | Search: `POST /search` | Extract: `POST /contents` ("Contents")

## Search: normalized to native
| Normalized | Native | Notes |
|---|---|---|
| `query` | `query` | |
| `max_results` | `numResults` | default 10, `MAX_RESULTS_CAP = 100` |
| `include_domains` / `exclude_domains` | `includeDomains` / `excludeDomains` | camelCase |
| `include_content` | `contents: {text: true}` | content fields are opt-in |

Curated kwargs: `type` (`instant`/`fast`/`auto`/`deep-lite`/`deep`/`deep-reasoning`), `category`, `startPublishedDate`, `endPublishedDate`, `includeText`, `excludeText`, `userLocation`.

## Search response
`{requestId, results[], costDollars}` (also `resolvedSearchType` or `searchType`).
Per result: `id`, `title`, `url`, `publishedDate` (ISO) -> `published_date`, `author` and `image` and `favicon` -> extras, `highlights[]` (+`highlightScores`) -> `snippet` (join with `"\n\n"`), `text` -> `content`, `summary` -> extras. No per-result `score` in the schema read: `score = None`.

## Extract
Request: `urls[]` or `ids[]` (1-100), plus `text`, `highlights`, `summary`, `maxAgeHours`, `subpages`. `text` takes a boolean or options object; markdown/html option names unchecked.
Response: `{requestId, results[], statuses[], costDollars}`. `statuses[]` = `{id: url, status: "success"|"error", source: "cached"|"crawled", error:{tag, httpStatusCode}}`. HTTP 200 even when URLs fail; match by `id` (a URL), not position. Failed -> `failed`.

## Usage and cost
`costDollars.total` (dollars, always returned, e.g. 0.007 for a search) -> `reported` with `exact=true`. Breakdown (`search`, `contents`, nested `breakdown`, `perRequestPrices`) -> `reported.detail`. `requestId` -> `usage.request_id`. No latency in body.
Headers: `x-request-id` (matches `requestId`), `x-exa-queued`, `x-exa-queue-ms` -> extras.

## Errors
`{requestId, error, tag}` throughout: 401 `INVALID_API_KEY`, 429 `RATE_LIMIT_EXCEEDED`. Retry-After not documented.

## Quirks
Extra request fields (`outputSchema`, `systemPrompt`, `stream`) look like answer/deep modes: not in the curated set. Some options are beta.

## Fixtures
Docs examples for search with contents, contents with mixed `statuses`, and 401/429 errors.

## Sources
https://docs.exa.ai/reference/search.md
https://docs.exa.ai/reference/get-contents.md
https://raw.githubusercontent.com/exa-labs/openapi-spec/master/exa-openapi-spec.yaml

UNVERIFIED: default `type`, contents markdown/html option names, whether `costDollars` is exact, Retry-After, account usage path.
