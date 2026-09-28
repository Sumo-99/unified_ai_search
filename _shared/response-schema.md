# Response schema: signed-off

Frozen pydantic v2 models (`ConfigDict(frozen=True)`). Anything a provider cannot supply is `None`.

```
SearchResponse:   provider, operation="search", query, results[SearchResult], usage: Usage, extras: dict, raw: dict
SearchResult:     title, url, snippet|None, content|None, score|None, published_date: datetime|None, extras: dict
ExtractResponse:  provider, operation="extract", results[ExtractResult], failed[FailedExtraction], usage: Usage, extras: dict, raw: dict
ExtractResult:    url, title|None, content, extras: dict
FailedExtraction: url, error
Usage:            request_id|None, latency_s, result_count, reported: ReportedCost|None
ReportedCost:     unit="usd", amount, exact: bool, detail: dict
```

## Field rules
- `snippet` is one string. Exa `highlights` and Parallel `excerpts` are joined with `"\n\n"`. You.com, Tavily and Firecrawl supply a single short string.
- `content` holds only real full-page text (markdown or text). It is `None` when the provider cannot return it (Parallel search) or `include_content=False`. Requesting content from a provider that cannot supply it logs a WARNING.
- `published_date` is a real `datetime` when parseable, else `None`. The original string goes in the result's `extras["published_raw"]`.
- `score` is passed through as reported. Only Tavily supplies it. Values are not comparable across providers.
- `results` holds the common web results only. Provider-specific data goes in `extras` (response level: news, images, answer, warnings, rate-limit headers; result level: author, favicon, thumbnail).
- `raw` is the untouched provider JSON, on responses only.
- Partial extract failures land in `failed` and never raise. If the whole call fails (auth, network), raise.

## Usage
- `latency_s` and `result_count` are always measured by the SDK around the HTTP call (Firecrawl extract: total wall-clock over all scrapes).
- `request_id` comes from the body or a documented header, else `None` (Firecrawl extract: `None`, per-URL details in `extras`).
- Headers captured, documented ones only: Exa `x-request-id`, `x-exa-queued` and `x-exa-queue-ms`, You.com `X-RateLimit-*`.

## Cost: always dollars
Native units are converted with the static table in `src/unified_ai_search/pricing.py`, reference price = **pay-as-you-go**, each value carrying its source URL and collection date. Callers can override via `SearchClient(pricing=...)`. Native amounts (credits, SKU counts) always stay in `reported.detail`.

| Provider | Source | `exact` |
|---|---|---|
| Exa | `costDollars.total` (documented as an estimate, not an invoice record) | false |
| Tavily | `usage.credits` x price table | false |
| Firecrawl search | `creditsUsed` x price table | false |
| Firecrawl extract | 1 credit per successfully scraped page x price table | false |
| Parallel | `usage[]` SKU counts x price table | false |
| You.com | published prices x request parameters (see `providers/you.md`) | false |

You.com `blend` full-page extraction reports the upper bound, with both bounds in `detail`. Refreshing the table is manual in v1 (see `todo.md`).
