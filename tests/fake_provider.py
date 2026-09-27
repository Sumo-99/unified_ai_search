from unified_ai_search.enums import Provider
from unified_ai_search.models import (
    ExtractRequest,
    ExtractResponse,
    ExtractResult,
    FailedExtraction,
    SearchRequest,
    SearchResponse,
    SearchResult,
    Usage,
)
from unified_ai_search.providers.base import HttpSearchProvider


class FakeProvider(HttpSearchProvider):
    PROVIDER = Provider.EXA
    ENV_VAR = "UNIFIED_TEST_API_KEY"
    BASE_URL = "https://fake.test"
    AUTH_HEADER = "x-api-key"
    AUTH_SCHEME = ""

    def _parse_error_message(self, response):
        try:
            return response.json().get("message", "fake failure")
        except ValueError:
            return "fake failure"

    def _capture_headers(self, response):
        return {"request_id": response.headers.get("x-test-request-id")}

    def search(self, request: SearchRequest) -> SearchResponse:
        result = self._request_json(
            "POST", "/search", operation="search", json={"query": request.query}
        )
        items = [SearchResult(**item) for item in result.body.get("results", [])]
        response = SearchResponse(
            provider=self.PROVIDER,
            query=request.query,
            results=items,
            raw=result.body,
            extras=result.headers,
            usage=Usage(
                latency_s=result.latency_s,
                result_count=len(items),
                request_id=result.headers.get("request_id"),
            ),
        )
        self._log_response(response, status_code=result.status_code)
        return response

    def extract(self, request: ExtractRequest) -> ExtractResponse:
        result = self._request_json(
            "POST", "/extract", operation="extract", json={"urls": request.urls}
        )
        items = [ExtractResult(**item) for item in result.body.get("results", [])]
        failed = [FailedExtraction(**item) for item in result.body.get("failed", [])]
        response = ExtractResponse(
            provider=self.PROVIDER,
            results=items,
            failed=failed,
            raw=result.body,
            extras=result.headers,
            usage=Usage(latency_s=result.latency_s, result_count=len(items)),
        )
        self._log_response(response, status_code=result.status_code)
        return response


class BearerFakeProvider(FakeProvider):
    BASE_URL = "https://bearer-fake.test"
    AUTH_HEADER = "Authorization"
    AUTH_SCHEME = "Bearer"
