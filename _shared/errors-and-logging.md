# Errors and logging: signed-off

## Errors
All inherit `SearchSDKError`. Callers never see `httpx` exceptions. No automatic retries in v1.

| Exception | Trigger |
|---|---|
| `MissingAPIKeyError` | no key at construction; names the provider and env var |
| `InvalidRequestError` | failed input validation (before any network call) |
| `AuthenticationError` | 401 or 403 |
| `RateLimitError` | 429 (Tavily 432 and 433 too); `retry_after` is `float | None`, present only when the header is |
| `ProviderAPIError` | other 4xx and 5xx; carries `status_code` and `body`. Includes You.com 402 |
| `ProviderTimeoutError` | httpx timeout |
| `UnsupportedOperationError` | provider lacks a capability |

Each adapter owns its error-body parser because the five providers use different shapes (see `providers/<name>.md`). `HttpSearchProvider` maps status codes; the subclass supplies message extraction.

## Logging
Standard library `logging`, logger `unified_ai_search` with a `NullHandler`, silent unless configured.

| Level | What |
|---|---|
| INFO | one line per call: provider, operation, status, latency, reported cost |
| DEBUG | request metadata (endpoint, parameter names, URL count), response metadata (result count, per-URL failures) |
| WARNING | clamped `max_results`, dropped kwargs, ignored flags (`include_content` on Parallel search), partial extract failures |
| ERROR | translated failures |

Never log API keys, request bodies or response bodies.
