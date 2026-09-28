from datetime import datetime
from typing import Any, ClassVar, Literal

import httpx
from pydantic import Field

from ..enums import Provider
from ..logging import logger
from ..models import (
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    FailedExtraction,
    ReportedCost,
    SearchRequest,
    SearchResponse,
    SearchResult,
    Usage,
)
from .base import HttpSearchProvider
from .options import ProviderOptions

# Flat caller kwargs that Parallel nests under `advanced_settings`.
_ADVANCED = ("location", "fetch_policy", "excerpt_settings")
_INCLUDED_RESULTS = 10
_FAST_MODES = ("turbo", "fast")


class ParallelFetchPolicy(ProviderOptions):
    max_age_seconds: int | None = Field(default=None, ge=600)
    timeout_seconds: float | None = Field(default=None, gt=0)
    disable_cache_fallback: bool | None = None


class ParallelExcerptSettings(ProviderOptions):
    max_chars_per_result: int | None = Field(default=None, ge=1)


class ParallelSearchOptions(ProviderOptions):
    objective: str | None = None
    mode: Literal["turbo", "fast", "basic", "advanced"] | None = None
    max_chars_total: int | None = Field(default=None, ge=1)
    session_id: str | None = None
    client_model: str | None = None
    after_date: str | None = None
    location: str | None = None
    fetch_policy: ParallelFetchPolicy | None = None
    excerpt_settings: ParallelExcerptSettings | None = None


class ParallelExtractOptions(ProviderOptions):
    objective: str | None = None
    search_queries: list[str] | None = None
    max_chars_total: int | None = Field(default=None, ge=1)
    session_id: str | None = None
    client_model: str | None = None
    fetch_policy: ParallelFetchPolicy | None = None
    excerpt_settings: ParallelExcerptSettings | None = None
    full_content_max_chars: int | None = Field(default=None, ge=1)


class ParallelProvider(HttpSearchProvider):
    PROVIDER = Provider.PARALLEL
    ENV_VAR = "PARALLEL_API_KEY"
    BASE_URL = "https://api.parallel.ai"
    AUTH_HEADER = "x-api-key"
    AUTH_SCHEME = ""
    SEARCH_OPTIONS = ParallelSearchOptions
    EXTRACT_OPTIONS = ParallelExtractOptions
    SEARCH_NORMALIZED_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"search_queries", "advanced_settings", "source_policy"}
    )
    EXTRACT_NORMALIZED_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"advanced_settings", "full_content"}
    )

    def search(self, request: SearchRequest) -> SearchResponse:
        kwargs = dict(request.provider_kwargs)
        advanced = _pop_advanced(kwargs)
        advanced["max_results"] = request.max_results
        source_policy: dict[str, Any] = {}
        if request.include_domains:
            source_policy["include_domains"] = request.include_domains
        if request.exclude_domains:
            source_policy["exclude_domains"] = request.exclude_domains
        if "after_date" in kwargs:
            source_policy["after_date"] = kwargs.pop("after_date")
        if source_policy:
            advanced["source_policy"] = source_policy
        if request.include_content:
            logger.warning(
                "provider=%s ignored include_content: search returns excerpts only",
                self.PROVIDER.value,
            )
        payload = {
            **kwargs,
            "search_queries": [request.query],
            "advanced_settings": advanced,
        }
        result = self._request_json(
            "POST", "/v1/search", operation="search", json=payload
        )
        body = result.body
        items = [_search_result(item) for item in body.get("results") or []]
        mode = str(request.provider_kwargs.get("mode") or "advanced")
        response = SearchResponse(
            provider=self.PROVIDER,
            query=request.query,
            results=items,
            usage=Usage(
                request_id=body.get("search_id"),
                latency_s=result.latency_s,
                result_count=len(items),
                reported=self._search_cost(body, mode, len(items)),
            ),
            extras=_extras(body),
            raw=body,
        )
        self._log_response(response, status_code=result.status_code)
        return response

    def extract(self, request: ExtractRequest) -> ExtractResponse:
        kwargs = dict(request.provider_kwargs)
        advanced = _pop_advanced(kwargs)
        max_chars = kwargs.pop("full_content_max_chars", None)
        # Extract always wants page text, so full content is always requested.
        advanced["full_content"] = (
            {"max_chars_per_result": max_chars} if max_chars is not None else True
        )
        payload = {**kwargs, "urls": request.urls, "advanced_settings": advanced}
        result = self._request_json(
            "POST", "/v1/extract", operation="extract", json=payload
        )
        body = result.body
        by_url = {item["url"]: item for item in body.get("results") or []}
        errors = {
            error["url"]: error
            for error in body.get("errors") or []
            if isinstance(error, dict) and "url" in error
        }
        items: list[ExtractResult] = []
        failed: list[FailedExtraction] = []
        # A returned result wins over an error for the same URL (the docs
        # example lists one URL in both arrays).
        for url in request.urls:
            item = by_url.get(url)
            if item is not None:
                extracted = _extract_result(url, item)
                if extracted is None:
                    failed.append(FailedExtraction(url=url, error="empty content"))
                else:
                    items.append(extracted)
            elif url in errors:
                failed.append(FailedExtraction(url=url, error=_error(errors[url])))
            else:
                failed.append(
                    FailedExtraction(url=url, error="not returned by provider")
                )
        response = ExtractResponse(
            provider=self.PROVIDER,
            results=items,
            failed=failed,
            usage=Usage(
                request_id=body.get("extract_id"),
                latency_s=result.latency_s,
                result_count=len(items),
                reported=self._extract_cost(body),
            ),
            extras=_extras(body),
            raw=body,
        )
        self._log_response(response, status_code=result.status_code)
        return response

    def _search_cost(
        self, body: dict[str, Any], mode: str, result_count: int
    ) -> ReportedCost | None:
        usage = _usage(body)
        searches = sum(sku["count"] for sku in usage if sku["name"] == "sku_search")
        if not searches:
            return None
        base = (
            self.pricing.parallel_search_fast
            if mode in _FAST_MODES
            else self.pricing.parallel_search_basic
        )
        extra_price = self.pricing.parallel_additional_result
        if base.amount is None or extra_price.amount is None:
            return None
        additional = max(0, result_count - _INCLUDED_RESULTS)
        detail = {
            "usage": usage,
            "mode": mode,
            "additional_results": additional,
            "usd_per_request": base.amount,
            "usd_per_additional_result": extra_price.amount,
            "price_source": base.source_url,
        }
        unpriced = [sku for sku in usage if sku["name"] != "sku_search"]
        if unpriced:
            detail["unpriced_skus"] = unpriced
        return ReportedCost(
            amount=searches * base.amount + additional * extra_price.amount,
            exact=False,
            detail=detail,
        )

    def _extract_cost(self, body: dict[str, Any]) -> ReportedCost | None:
        usage = _usage(body)
        extract_skus = [sku for sku in usage if sku["name"].startswith("sku_extract")]
        price = self.pricing.parallel_extract
        if not extract_skus or price.amount is None:
            return None
        # Extract is priced per URL; each extract SKU counts URLs, so a URL billed
        # for excerpts and full content is still one URL.
        urls = max(sku["count"] for sku in extract_skus)
        detail: dict[str, Any] = {
            "usage": usage,
            "urls_billed": urls,
            "usd_per_url": price.amount,
            "price_source": price.source_url,
        }
        unpriced = [sku for sku in usage if sku not in extract_skus]
        if unpriced:
            detail["unpriced_skus"] = unpriced
        return ReportedCost(amount=urls * price.amount, exact=False, detail=detail)

    def _parse_error_message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = None
        error = body.get("error") if isinstance(body, dict) else None
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return f"parallel: {error['message']}"
        return super()._parse_error_message(response)


def _pop_advanced(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {name: kwargs.pop(name) for name in _ADVANCED if name in kwargs}


def _usage(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        sku
        for sku in body.get("usage") or []
        if isinstance(sku, dict)
        and isinstance(sku.get("name"), str)
        and isinstance(sku.get("count"), int)
    ]


def _extras(body: dict[str, Any]) -> dict[str, Any]:
    extras: dict[str, Any] = {}
    if body.get("warnings"):
        extras["warnings"] = body["warnings"]
    if "session_id" in body:
        extras["session_id"] = body["session_id"]
    return extras


def _joined_excerpts(item: dict[str, Any]) -> str | None:
    excerpts = [e for e in item.get("excerpts") or [] if isinstance(e, str)]
    return "\n\n".join(excerpts) or None


def _published(item: dict[str, Any], extras: dict[str, Any]) -> datetime | None:
    raw = item.get("publish_date")
    if not isinstance(raw, str):
        return None
    extras["published_raw"] = raw
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _search_result(item: dict[str, Any]) -> SearchResult:
    extras: dict[str, Any] = {}
    published = _published(item, extras)
    return SearchResult(
        title=item.get("title") or "",
        url=item["url"],
        snippet=_joined_excerpts(item),
        published_date=published,
        extras=extras,
    )


def _extract_result(url: str, item: dict[str, Any]) -> ExtractResult | None:
    extras: dict[str, Any] = {}
    _published(item, extras)
    content = item.get("full_content")
    extras["content_source"] = "full_content"
    if not content:
        content = _joined_excerpts(item)
        extras["content_source"] = "excerpts"
    if not content:
        return None
    return ExtractResult(
        url=url, title=item.get("title"), content=content, extras=extras
    )


def _error(error: dict[str, Any]) -> str:
    kind = str(error.get("error_type") or "error")
    code = error.get("http_status_code")
    return f"{kind} (HTTP {code})" if code else kind
