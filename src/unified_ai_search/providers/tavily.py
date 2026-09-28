from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar, Literal

import httpx
from pydantic import Field

from ..enums import Provider
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

_SEARCH_EXTRAS = ("answer", "images", "auto_parameters", "response_time")


class TavilySearchOptions(ProviderOptions):
    search_depth: Literal["basic", "advanced", "fast", "ultra-fast"] | None = None
    topic: Literal["general", "news", "finance"] | None = None
    time_range: Literal["day", "week", "month", "year", "d", "w", "m", "y"] | None = (
        None
    )
    start_date: str | None = None
    end_date: str | None = None
    country: str | None = None
    include_answer: bool | Literal["basic", "advanced"] | None = None
    include_published_date: bool | None = None
    include_domains_mode: Literal["restrict", "prefer"] | None = None
    include_images: bool | None = None
    include_favicon: bool | None = None
    exact_match: bool | None = None
    chunks_per_source: int | None = Field(default=None, ge=1, le=3)


class TavilyExtractOptions(ProviderOptions):
    format: Literal["markdown", "text"] | None = None
    extract_depth: Literal["basic", "advanced"] | None = None
    query: str | None = None
    chunks_per_source: int | None = Field(default=None, ge=1, le=5)
    timeout: float | None = Field(default=None, ge=1, le=60)
    include_images: bool | None = None
    include_favicon: bool | None = None


class TavilyProvider(HttpSearchProvider):
    PROVIDER = Provider.TAVILY
    ENV_VAR = "TAVILY_API_KEY"
    BASE_URL = "https://api.tavily.com"
    MAX_RESULTS_CAP = 20
    SEARCH_OPTIONS = TavilySearchOptions
    EXTRACT_OPTIONS = TavilyExtractOptions
    SEARCH_NORMALIZED_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"include_raw_content", "include_usage"}
    )
    EXTRACT_NORMALIZED_NAMES: ClassVar[frozenset[str]] = frozenset({"include_usage"})

    def search(self, request: SearchRequest) -> SearchResponse:
        payload: dict[str, Any] = {
            **request.provider_kwargs,
            "query": request.query,
            "max_results": request.max_results,
            "include_usage": True,
        }
        if request.include_domains:
            payload["include_domains"] = request.include_domains
        if request.exclude_domains:
            payload["exclude_domains"] = request.exclude_domains
        if request.include_content:
            payload["include_raw_content"] = True
        result = self._request_json("POST", "/search", operation="search", json=payload)
        body = result.body
        items = [_search_result(item) for item in body.get("results") or []]
        response = SearchResponse(
            provider=self.PROVIDER,
            query=request.query,
            results=items,
            usage=Usage(
                request_id=body.get("request_id"),
                latency_s=result.latency_s,
                result_count=len(items),
                reported=self._cost(body),
            ),
            extras={key: body[key] for key in _SEARCH_EXTRAS if key in body},
            raw=body,
        )
        self._log_response(response, status_code=result.status_code)
        return response

    def extract(self, request: ExtractRequest) -> ExtractResponse:
        payload: dict[str, Any] = {
            "urls": request.urls,
            "include_usage": True,
            **request.provider_kwargs,
        }
        result = self._request_json(
            "POST", "/extract", operation="extract", json=payload
        )
        body = result.body
        items: list[ExtractResult] = []
        failed = [
            FailedExtraction(url=item["url"], error=str(item.get("error", "")))
            for item in body.get("failed_results") or []
        ]
        for item in body.get("results") or []:
            content = item.get("raw_content")
            if not content:
                failed.append(FailedExtraction(url=item["url"], error="empty content"))
                continue
            extras = {k: item[k] for k in ("images", "favicon") if k in item}
            items.append(ExtractResult(url=item["url"], content=content, extras=extras))
        response = ExtractResponse(
            provider=self.PROVIDER,
            results=items,
            failed=failed,
            usage=Usage(
                request_id=body.get("request_id"),
                latency_s=result.latency_s,
                result_count=len(items),
                reported=self._cost(body),
            ),
            extras={"response_time": body["response_time"]}
            if "response_time" in body
            else {},
            raw=body,
        )
        self._log_response(response, status_code=result.status_code)
        return response

    def _cost(self, body: dict[str, Any]) -> ReportedCost | None:
        usage = body.get("usage")
        credits = usage.get("credits") if isinstance(usage, dict) else None
        price = self.pricing.tavily_credit
        if not isinstance(credits, (int, float)) or price.amount is None:
            return None
        # Credits bill in steps (extract may report 0), so dollars are approximate.
        return ReportedCost(
            amount=credits * price.amount,
            exact=False,
            detail={
                "credits": credits,
                "usd_per_credit": price.amount,
                "price_source": price.source_url,
            },
        )

    def _parse_error_message(self, response: httpx.Response) -> str:
        fallback = super()._parse_error_message(response)
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            return fallback
        if isinstance(detail, dict) and isinstance(detail.get("error"), str):
            return f"tavily: {detail['error']}"
        if isinstance(detail, list):
            # FastAPI 422 items also carry `input`, which echoes caller data.
            parts = [
                ".".join(str(p) for p in item.get("loc", [])) + f": {item.get('msg')}"
                for item in detail
                if isinstance(item, dict)
            ]
            if parts:
                return "tavily: " + "; ".join(parts)
        if isinstance(detail, str):
            return f"tavily: {detail}"
        return fallback


def _search_result(item: dict[str, Any]) -> SearchResult:
    extras: dict[str, Any] = {
        k: item[k] for k in ("favicon", "images", "id") if k in item
    }
    published: datetime | None = None
    raw_date = item.get("published_date")
    if isinstance(raw_date, str):
        extras["published_raw"] = raw_date
        published = _parse_date(raw_date)
    return SearchResult(
        title=item.get("title") or "",
        url=item["url"],
        snippet=item.get("content"),
        content=item.get("raw_content"),
        score=item.get("score"),
        published_date=published,
        extras=extras,
    )


def _parse_date(value: str) -> datetime | None:
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
