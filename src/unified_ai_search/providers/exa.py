from datetime import datetime
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

_CAPTURED_HEADERS = ("x-exa-queued", "x-exa-queue-ms")
_SEARCH_EXTRAS = ("resolvedSearchType", "searchType", "searchTime")
_RESULT_EXTRAS = ("id", "author", "image", "favicon", "summary", "highlightScores")


class ExaSearchOptions(ProviderOptions):
    type: (
        Literal["instant", "fast", "auto", "deep-lite", "deep", "deep-reasoning"] | None
    ) = None
    category: str | None = None
    userLocation: str | None = None
    startPublishedDate: str | None = None
    endPublishedDate: str | None = None
    startCrawlDate: str | None = None
    endCrawlDate: str | None = None
    moderation: bool | None = None


class ExaExtractOptions(ProviderOptions):
    maxAgeHours: int | None = None
    livecrawlTimeout: int | None = Field(default=None, ge=0)
    subpages: int | None = Field(default=None, ge=0)
    subpageTarget: str | list[str] | None = None


class ExaProvider(HttpSearchProvider):
    PROVIDER = Provider.EXA
    ENV_VAR = "EXA_API_KEY"
    BASE_URL = "https://api.exa.ai"
    MAX_RESULTS_CAP = 100
    SEARCH_OPTIONS = ExaSearchOptions
    EXTRACT_OPTIONS = ExaExtractOptions
    SEARCH_NORMALIZED_NAMES: ClassVar[frozenset[str]] = frozenset(
        {"numResults", "includeDomains", "excludeDomains", "contents"}
    )
    EXTRACT_NORMALIZED_NAMES: ClassVar[frozenset[str]] = frozenset({"ids", "text"})

    def search(self, request: SearchRequest) -> SearchResponse:
        # Highlights are always requested: they are Exa's only snippet source.
        contents: dict[str, Any] = {"highlights": True}
        if request.include_content:
            contents["text"] = True
        payload: dict[str, Any] = {
            **request.provider_kwargs,
            "query": request.query,
            "numResults": request.max_results,
            "contents": contents,
        }
        if request.include_domains:
            payload["includeDomains"] = request.include_domains
        if request.exclude_domains:
            payload["excludeDomains"] = request.exclude_domains
        result = self._request_json("POST", "/search", operation="search", json=payload)
        body = result.body
        items = [
            _search_result(item, request.include_content)
            for item in body.get("results") or []
        ]
        extras = {key: body[key] for key in _SEARCH_EXTRAS if key in body}
        extras.update(_queue_headers(result.headers))
        response = SearchResponse(
            provider=self.PROVIDER,
            query=request.query,
            results=items,
            usage=self._usage(body, result.headers, result.latency_s, len(items)),
            extras=extras,
            raw=body,
        )
        self._log_response(response, status_code=result.status_code)
        return response

    def extract(self, request: ExtractRequest) -> ExtractResponse:
        payload: dict[str, Any] = {
            **request.provider_kwargs,
            "urls": request.urls,
            "text": True,
        }
        result = self._request_json(
            "POST", "/contents", operation="extract", json=payload
        )
        body = result.body
        statuses = {
            status["id"]: status
            for status in body.get("statuses") or []
            if isinstance(status, dict) and "id" in status
        }
        by_id = {
            item.get("id") or item.get("url"): item
            for item in body.get("results") or []
        }
        items: list[ExtractResult] = []
        failed: list[FailedExtraction] = []
        # Match by requested id, never by position (Exa does not promise order).
        for url in request.urls:
            status = statuses.get(url, {})
            item = by_id.get(url)
            if status.get("status") == "error":
                failed.append(FailedExtraction(url=url, error=_status_error(status)))
            elif item is None:
                failed.append(
                    FailedExtraction(url=url, error="not returned by provider")
                )
            elif not item.get("text"):
                failed.append(FailedExtraction(url=url, error="empty content"))
            else:
                items.append(_extract_result(url, item, status))
        response = ExtractResponse(
            provider=self.PROVIDER,
            results=items,
            failed=failed,
            usage=self._usage(body, result.headers, result.latency_s, len(items)),
            extras=_queue_headers(result.headers),
            raw=body,
        )
        self._log_response(response, status_code=result.status_code)
        return response

    def _usage(
        self,
        body: dict[str, Any],
        headers: dict[str, Any],
        latency_s: float,
        count: int,
    ) -> Usage:
        return Usage(
            request_id=body.get("requestId") or headers.get("x-request-id"),
            latency_s=latency_s,
            result_count=count,
            reported=_cost(body),
        )

    def _capture_headers(self, response: httpx.Response) -> dict[str, Any]:
        names = ("x-request-id", *_CAPTURED_HEADERS)
        return {
            name: response.headers[name] for name in names if name in response.headers
        }

    def _parse_error_message(self, response: httpx.Response) -> str:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("error"), str):
            tag = body.get("tag")
            prefix = f"{tag}: " if isinstance(tag, str) else ""
            return f"exa: {prefix}{body['error']}"
        return super()._parse_error_message(response)


def _cost(body: dict[str, Any]) -> ReportedCost | None:
    cost = body.get("costDollars")
    if not isinstance(cost, dict):
        return None
    total = cost.get("total")
    if not isinstance(total, (int, float)):
        return None
    # Exa documents `total` as an estimate, "not an invoice record".
    return ReportedCost(amount=total, exact=False, detail=cost)


def _queue_headers(headers: dict[str, Any]) -> dict[str, Any]:
    return {name: headers[name] for name in _CAPTURED_HEADERS if name in headers}


def _search_result(item: dict[str, Any], include_content: bool) -> SearchResult:
    extras: dict[str, Any] = {k: item[k] for k in _RESULT_EXTRAS if k in item}
    published = _published(item, extras)
    highlights = [h for h in item.get("highlights") or [] if isinstance(h, str)]
    return SearchResult(
        title=item.get("title") or "",
        url=item["url"],
        snippet="\n\n".join(highlights) or None,
        content=item.get("text") if include_content else None,
        published_date=published,
        extras=extras,
    )


def _extract_result(
    url: str, item: dict[str, Any], status: dict[str, Any]
) -> ExtractResult:
    extras: dict[str, Any] = {
        k: item[k] for k in ("author", "image", "favicon", "summary") if k in item
    }
    _published(item, extras)
    if item.get("url") and item["url"] != url:
        extras["resolved_url"] = item["url"]
    if "source" in status:
        extras["source"] = status["source"]
    return ExtractResult(
        url=url, title=item.get("title"), content=item["text"], extras=extras
    )


def _status_error(status: dict[str, Any]) -> str:
    error = status.get("error")
    if not isinstance(error, dict) or not error.get("tag"):
        return "error"
    code = error.get("httpStatusCode")
    return f"{error['tag']} (HTTP {code})" if code else str(error["tag"])


def _published(item: dict[str, Any], extras: dict[str, Any]) -> datetime | None:
    raw = item.get("publishedDate")
    if not isinstance(raw, str):
        return None
    extras["published_raw"] = raw
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
