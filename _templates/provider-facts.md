# {Provider}: API facts

Copy to `_shared/providers/{provider}.md`. Every claim carries a source URL. Mark anything unchecked `UNVERIFIED`.

- Enum value: `{provider}` | Env var: `{PROVIDER}_API_KEY` | Auth header: `{header}`
- Base URL: {url} | Search: `{METHOD path}` | Extract ("{provider's name for it}"): `{METHOD path}`

## Search: normalized to native
| Normalized | Native param | Notes (default, cap, nesting) |
|---|---|---|
| `query` | | |
| `max_results` | | cap: {n or none documented} |
| `include_domains` / `exclude_domains` | | |
| `include_content` | | {how, or "not supported"} |

## Search response: native to normalized
Result list path, then per result: title, url, snippet, content, score, published_date (format), extras. Response level: request id, latency, usage/cost, extras.

## Extract
Request params, max URLs per call, response shape, how per-URL failures are reported.

## Usage and cost
Body fields, headers, opt-in flags, units, exact vs estimate. Static prices with source URL and date.

## Errors
Status codes used, body shape per code, Retry-After behavior.

## Quirks
Anything that complicates the normalized interface.

## Fixtures
Docs example payloads to record under `tests/providers/{provider}/fixtures/`.

## Sources and UNVERIFIED
