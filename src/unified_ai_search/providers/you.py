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

_RATE_LIMIT_HEADERS = (
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
)
_FULL_PAGE: dict[str, Any] = {
    "extraction_mode": "full_page",
    "full_page": {"extraction_formats": ["markdown"]},
}


class YouSearchOptions(ProviderOptions):
    freshness: str | None = None
    country: str | None = None
    language: str | None = None
    safesearch: Literal["off", "moderate", "strict"] | None = None
    offset: int | None = Field(default=None, ge=0, le=9)
    knowledge: Literal["core"] | None = None
    boost_domains: list[str] | None = None
    crawl_timeout: int | None = Field(default=None, ge=1, le=60)
    extraction_source: Literal["blend", "cache", "fetch"] | None = None
    highlights: bool | None = None


class YouExtractOptions(ProviderOptions):
    crawl_timeout: int | None = Field(default=None, ge=1, le=60)
    max_age: int | None = Field(default=None, ge=0)


class YouProvider(HttpSearchProvider):
    PROVIDER = Provider.YOU
    ENV_VAR = "YDC_API_KEY"
    BASE_URL = "https://ydc-index.io"
    AUTH_HEADER = "X-API-Key"
    AUTH_SCHEME = ""
    SEARCH_OPTIONS = YouSearchOptions
    EXTRACT_OPTIONS = YouExtractOptions
    SEARCH_NORMALIZED_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"count", "extraction"}
    )
    EXTRACT_NORMALIZED_NAMES: ClassVar[frozenset[str]] = frozenset({"formats"})

    def search(self, request: SearchRequest) -> SearchResponse:
        kwargs = dict(request.provider_kwargs)
        source = kwargs.pop("extraction_source", None)
        highlights = kwargs.pop("highlights", None)
        payload: dict[str, Any] = {
            **kwargs,
            "query": request.query,
            "count": request.max_results,
        }
        if request.include_domains:
            payload["include_domains"] = request.include_domains
            if request.exclude_domains:
                # You.com rejects both lists together with a 422.
                self._warn("ignored exclude_domains: include_domains is set")
        elif request.exclude_domains:
            payload["exclude_domains"] = request.exclude_domains
        if request.include_content:
            payload["extraction"] = dict(_FULL_PAGE)
            if source:
                payload["extraction"]["extraction_source"] = source
            if highlights:
                self._warn("ignored highlights: include_content requests full pages")
        else:
            if highlights:
                payload["extraction"] = {"extraction_mode": "highlights"}
            if source:
                self._warn("ignored extraction_source: only applies to full pages")
        result = self._request_json(
            "POST", "/v1/search", operation="search", json=payload
        )
        body = result.body
        sections = body.get("results") or {}
        web = sections.get("web") or []
        items = [_search_result(item, request.include_content) for item in web]
        metadata = body.get("metadata") or {}
        extras: dict[str, Any] = {
            key: sections[key] for key in ("news", "knowledge") if key in sections
        }
        if "latency" in metadata:
            extras["latency"] = metadata["latency"]
        extras.update(result.headers)
        pages = _pages_with_content(web + (sections.get("news") or []))
        response = SearchResponse(
            provider=self.PROVIDER,
            query=request.query,
            results=items,
            usage=Usage(
                request_id=metadata.get("search_uuid"),
                latency_s=result.latency_s,
                result_count=len(items),
                reported=self._search_cost(
                    request.include_content, source or "blend", pages
                ),
            ),
            extras=extras,
            raw=body,
        )
        self._log_response(response, status_code=result.status_code)
        return response

    def extract(self, request: ExtractRequest) -> ExtractResponse:
        payload = {
            **request.provider_kwargs,
            "urls": request.urls,
            "formats": ["markdown", "metadata"],
        }
        result = self._request_json(
            "POST",
            "/v1/contents",
            operation="extract",
            json=payload,
            list_key="results",
        )
        body = result.body
        returned = [
            item for item in body.get("results") or [] if isinstance(item, dict)
        ]
        items: list[ExtractResult] = []
        failed: list[FailedExtraction] = []
        seen: set[str] = set()
        # Failed crawls come back as entries with null content, not as errors.
        for item in returned:
            url = item.get("url")
            if not isinstance(url, str):
                continue
            seen.add(url)
            if item.get("markdown"):
                items.append(_extract_result(url, item))
            else:
                failed.append(FailedExtraction(url=url, error="no content returned"))
        failed.extend(
            FailedExtraction(url=url, error="not returned by provider")
            for url in request.urls
            if url not in seen
        )
        response = ExtractResponse(
            provider=self.PROVIDER,
            results=items,
            failed=failed,
            usage=Usage(
                latency_s=result.latency_s,
                result_count=len(items),
                reported=self._extract_cost(len(returned), len(items)),
            ),
            extras=dict(result.headers),
            raw=body,
        )
        self._log_response(response, status_code=result.status_code)
        return response

    def _search_cost(
        self, full_page: bool, source: str, pages: int
    ) -> ReportedCost | None:
        call = self.pricing.you_search
        live = self.pricing.you_live_page
        if call.amount is None or live.amount is None:
            return None
        detail: dict[str, Any] = {
            "calls": 1,
            "usd_per_call": call.amount,
            "price_source": call.source_url,
        }
        if not full_page:
            return ReportedCost(amount=call.amount, exact=False, detail=detail)
        # Only live crawls are billed: `cache` never, `fetch` always, `blend`
        # unknowable, so the upper bound is reported.
        live_cost = pages * live.amount
        lower = call.amount + (live_cost if source == "fetch" else 0.0)
        upper = call.amount + (0.0 if source == "cache" else live_cost)
        detail.update(
            extraction_source=source,
            pages_with_content=pages,
            usd_per_live_page=live.amount,
            lower_bound_usd=lower,
            upper_bound_usd=upper,
        )
        return ReportedCost(amount=upper, exact=False, detail=detail)

    def _extract_cost(self, returned: int, succeeded: int) -> ReportedCost | None:
        price = self.pricing.you_contents_page
        if price.amount is None:
            return None
        return ReportedCost(
            amount=returned * price.amount,
            exact=False,
            detail={
                "pages_billed": returned,
                "pages_with_content": succeeded,
                "usd_per_page": price.amount,
                "price_source": price.source_url,
            },
        )

    def _capture_headers(self, response: httpx.Response) -> dict[str, Any]:
        return {
            name: response.headers[name]
            for name in _RATE_LIMIT_HEADERS
            if name in response.headers
        }

    def _parse_error_message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            if isinstance(body.get("detail"), str):
                return f"you: {body['detail']}"
            error, message = body.get("error"), body.get("message")
            if isinstance(error, str) and isinstance(message, str):
                return f"you: {error}: {message}"
            if isinstance(error, str):
                return f"you: {error}"
        return super()._parse_error_message(response)

    def _warn(self, message: str) -> None:
        logger.warning("provider=%s %s", self.PROVIDER.value, message)


def _pages_with_content(results: list[Any]) -> int:
    return sum(
        1
        for item in results
        if isinstance(item, dict)
        and (
            (item.get("contents") or {}).get("markdown")
            or (item.get("contents") or {}).get("html")
        )
    )


def _joined(values: Any) -> str | None:
    strings = [v for v in values or [] if isinstance(v, str)]
    return "\n\n".join(strings) or None


def _search_result(item: dict[str, Any], include_content: bool) -> SearchResult:
    contents = item.get("contents") or {}
    extras: dict[str, Any] = {
        k: item[k] for k in ("snippets", "thumbnail_url", "favicon_url") if k in item
    }
    published: datetime | None = None
    raw_date = item.get("page_age")
    if isinstance(raw_date, str):
        extras["published_raw"] = raw_date
        try:
            published = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            published = None
    return SearchResult(
        title=item.get("title") or "",
        url=item["url"],
        snippet=item.get("description")
        or _joined(item.get("snippets"))
        or _joined(contents.get("highlights")),
        content=contents.get("markdown") if include_content else None,
        published_date=published,
        extras=extras,
    )


def _extract_result(url: str, item: dict[str, Any]) -> ExtractResult:
    metadata = item.get("metadata") or {}
    extras = {
        k: metadata[k]
        for k in ("site_name", "favicon_url")
        if metadata.get(k) is not None
    }
    return ExtractResult(
        url=url, title=item.get("title"), content=item["markdown"], extras=extras
    )
