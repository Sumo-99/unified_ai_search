import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx
import respx

from tests.fake_provider import BearerFakeProvider, FakeProvider
from unified_ai_search.providers.base import SearchProvider
from unified_ai_search.providers.exa import ExaProvider
from unified_ai_search.providers.tavily import TavilyProvider


class ContractCase(ABC):
    """Provider-specific wire fixtures for the shared behavioral contract."""

    @abstractmethod
    def success(self, router: respx.MockRouter, operation: str) -> None:
        """Mock one result; extract additionally has one per-URL failure."""

    @abstractmethod
    def failure(
        self, router: respx.MockRouter, status: int, headers: dict[str, str]
    ) -> None:
        """Mock an HTTP failure for search."""

    @abstractmethod
    def timeout(self, router: respx.MockRouter) -> None:
        """Mock an HTTPX timeout for search."""

    @abstractmethod
    def assert_auth(self, router: respx.MockRouter, key: str) -> None:
        """Check auth in captured requests according to the provider's wire format."""


class FakeCase(ContractCase):
    def __init__(self, provider_type: type[FakeProvider]) -> None:
        self.provider_type = provider_type

    def success(self, router: respx.MockRouter, operation: str) -> None:
        item = {"url": "https://example.com", "title": "Title"}
        if operation == "extract":
            item["content"] = "page text"
        body = {"results": [item]}
        if operation == "extract":
            body["failed"] = [{"url": "https://bad.example", "error": "not found"}]
        router.post(f"{self.provider_type.BASE_URL}/{operation}").respond(
            200, json=body
        )

    def failure(
        self, router: respx.MockRouter, status: int, headers: dict[str, str]
    ) -> None:
        router.post(f"{self.provider_type.BASE_URL}/search").respond(
            status, json={"message": "private error body"}, headers=headers
        )

    def timeout(self, router: respx.MockRouter) -> None:
        router.post(f"{self.provider_type.BASE_URL}/search").mock(
            side_effect=httpx.ReadTimeout("private transport detail")
        )

    def assert_auth(self, router: respx.MockRouter, key: str) -> None:
        prefix = self.provider_type.AUTH_SCHEME
        value = f"{prefix} {key}" if prefix else key
        assert (
            router.calls.last.request.headers[self.provider_type.AUTH_HEADER] == value
        )


class TavilyCase(ContractCase):
    BASE_URL = "https://api.tavily.com"

    def success(self, router: respx.MockRouter, operation: str) -> None:
        name = "search.json" if operation == "search" else "extract_partial.json"
        router.post(f"{self.BASE_URL}/{operation}").respond(
            200, json=_fixture("tavily", name)
        )

    def failure(
        self, router: respx.MockRouter, status: int, headers: dict[str, str]
    ) -> None:
        router.post(f"{self.BASE_URL}/search").respond(
            status, json={"detail": {"error": "private error body"}}, headers=headers
        )

    def timeout(self, router: respx.MockRouter) -> None:
        router.post(f"{self.BASE_URL}/search").mock(
            side_effect=httpx.ReadTimeout("private transport detail")
        )

    def assert_auth(self, router: respx.MockRouter, key: str) -> None:
        assert router.calls.last.request.headers["Authorization"] == f"Bearer {key}"


class ExaCase(ContractCase):
    BASE_URL = "https://api.exa.ai"

    def success(self, router: respx.MockRouter, operation: str) -> None:
        if operation == "search":
            router.post(f"{self.BASE_URL}/search").respond(
                200, json=_fixture("exa", "search.json")
            )
            return
        body = _fixture("exa", "contents.json")
        body["results"][0]["id"] = "https://example.com"
        body["statuses"] = [
            {"id": "https://example.com", "status": "success", "source": "crawled"},
            {
                "id": "https://bad.example",
                "status": "error",
                "error": {"tag": "CRAWL_NOT_FOUND", "httpStatusCode": 404},
            },
        ]
        router.post(f"{self.BASE_URL}/contents").respond(200, json=body)

    def failure(
        self, router: respx.MockRouter, status: int, headers: dict[str, str]
    ) -> None:
        router.post(f"{self.BASE_URL}/search").respond(
            status,
            json={"requestId": "r", "error": "private error body", "tag": "T"},
            headers=headers,
        )

    def timeout(self, router: respx.MockRouter) -> None:
        router.post(f"{self.BASE_URL}/search").mock(
            side_effect=httpx.ReadTimeout("private transport detail")
        )

    def assert_auth(self, router: respx.MockRouter, key: str) -> None:
        assert router.calls.last.request.headers["Authorization"] == f"Bearer {key}"


def _fixture(provider: str, name: str) -> dict[str, Any]:
    path = Path(__file__).parent.parent / "providers" / provider / "fixtures" / name
    body: dict[str, Any] = json.loads(path.read_text())
    return body


CONTRACT_CASES: dict[type[SearchProvider], ContractCase] = {
    FakeProvider: FakeCase(FakeProvider),
    BearerFakeProvider: FakeCase(BearerFakeProvider),
    TavilyProvider: TavilyCase(),
    ExaProvider: ExaCase(),
}
