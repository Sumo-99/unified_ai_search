# Design: signed-off architecture

Source of truth for how the SDK is structured. Stage contracts link here; they do not restate it.

## Scope
- Package `unified_ai_search`, Python 3.10+, sync only. Operations: `search` and `extract`. No dynamic provider switching in v1.
- Runtime deps: `httpx` (direct REST, no provider SDKs) and `pydantic` v2.

## Pattern: Strategy + Adapter, no dependency injection

```
SearchClient (context) --delegates--> SearchProvider (strategy interface)
                                        |- Searcher  (ABC: search)
                                        `- Extractor (ABC: extract)
HttpSearchProvider(SearchProvider)   shared base, owns its httpx.Client
  |- YouProvider  ExaProvider  ParallelProvider  TavilyProvider  FirecrawlProvider
registry.py: PROVIDER_REGISTRY = {Provider.EXA: ExaProvider, ...}
```

```python
class Provider(str, Enum): YOU="you"; EXA="exa"; PARALLEL="parallel"; TAVILY="tavily"; FIRECRAWL="firecrawl"

class Searcher(ABC):
    @abstractmethod
    def search(self, request: SearchRequest) -> SearchResponse: ...
class Extractor(ABC):
    @abstractmethod
    def extract(self, request: ExtractRequest) -> ExtractResponse: ...
class SearchProvider(Searcher, Extractor, ABC): ...

class SearchClient:
    def __init__(self, provider: Provider | str, api_key: str | None = None,
                 timeout: float = 30.0, pricing: PricingTable | None = None): ...
    def search(self, query: str, *, max_results: int = 10, include_domains=None,
               exclude_domains=None, include_content: bool = False, **provider_kwargs) -> SearchResponse: ...
    def extract(self, urls: list[str], **provider_kwargs) -> ExtractResponse: ...
    def close(self) -> None   # plus __enter__ / __exit__
```

- The client coerces string or enum (unknown value: `ValueError`), looks the class up in the registry and builds the strategy itself. Nothing is injected.
- **Key resolution, fail fast at construction:** explicit `api_key=` wins over the env var, else `MissingAPIKeyError` naming the provider and the env var. Env vars: `YDC_API_KEY`, `EXA_API_KEY`, `PARALLEL_API_KEY`, `TAVILY_API_KEY` (SDK convention, not confirmed in Tavily's docs), `FIRECRAWL_API_KEY`.
- `HttpSearchProvider` builds one `httpx.Client` per provider: `Timeout(30.0, connect=5.0)`, `base_url`, auth header. It owns closing it. `_build_http_client` is the seam for a shared pool later.
- `SearchClient.extract()` checks `isinstance(strategy, Extractor)`, else `UnsupportedOperationError`. All five support extract today; the check is future-proofing.

## Request handling
- **Normalized inputs:** `query`, `max_results` (default 10), `include_domains`, `exclude_domains`, `include_content`; `urls` for extract.
- **Validation** (pydantic): non-empty query, `max_results >= 1`, valid non-empty URLs, no include/exclude overlap. Failure raises `InvalidRequestError` (pydantic error as `__cause__`) before any network call.
- **Clamping:** `max_results` is clamped to a documented cap only. Tavily 20, Exa 100, Firecrawl 100, each a class constant `MAX_RESULTS_CAP`. Every clamp logs a WARNING. You.com and Parallel pass through.
- **Provider kwargs:** each provider has static, typed pydantic option models for search and extract (a curated set from its docs, maintained by hand in v1). Matching kwargs are forwarded; unknown names or mismatched types are dropped with a WARNING and the call proceeds. A normalized parameter wins over a colliding native one (WARNING).
- **Adapter specifics:** Parallel sends `search_queries=[query]`, no `objective` unless the caller passes it. Tavily always sends `include_usage=true`. Firecrawl extract runs concurrent single-URL `/v2/scrape` calls (bounded pool, about 5 workers). You.com and Firecrawl search put only the `web` section in `results`; other sections go to response `extras`.

## Layout
```
src/unified_ai_search/
  __init__.py  client.py  enums.py  registry.py  errors.py  models.py  pricing.py  logging.py
  providers/
    base.py  options.py  you.py  exa.py  parallel.py  tavily.py  firecrawl.py
tests/
  contract/   one suite, parametrized over PROVIDER_REGISTRY
  providers/  per-adapter unit tests + recorded fixtures
  live/       opt-in, marker `live`, real keys
```
`models.py` becomes a `models/` package if it grows.

## Recorded TODOs
See `_shared/todo.md`.
