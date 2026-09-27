import logging

import pytest

from tests.contract.cases import CONTRACT_CASES
from tests.fake_provider import BearerFakeProvider, FakeProvider
from unified_ai_search.errors import (
    AuthenticationError,
    MissingAPIKeyError,
    ProviderAPIError,
    ProviderTimeoutError,
    RateLimitError,
)
from unified_ai_search.models import (
    ExtractRequest,
    ExtractResponse,
    SearchRequest,
    SearchResponse,
    Usage,
)
from unified_ai_search.providers.base import Extractor, Searcher, SearchProvider
from unified_ai_search.registry import PROVIDER_REGISTRY


@pytest.fixture(
    params=[FakeProvider, BearerFakeProvider, *PROVIDER_REGISTRY.values()],
    ids=lambda cls: cls.__name__,
)
def provider_type(request):
    return request.param


@pytest.fixture
def case(provider_type):
    assert provider_type in CONTRACT_CASES, (
        "Add wire fixtures in tests/contract/cases.py"
    )
    return CONTRACT_CASES[provider_type]


@pytest.fixture
def provider(provider_type):
    with provider_type(api_key="contract-test-key") as instance:
        yield instance


def test_interfaces(provider):
    assert all(
        isinstance(provider, base) for base in (Searcher, Extractor, SearchProvider)
    )


def test_missing_key(provider_type, monkeypatch):
    monkeypatch.delenv(provider_type.ENV_VAR, raising=False)
    with pytest.raises(MissingAPIKeyError, match=provider_type.ENV_VAR):
        provider_type()


@pytest.mark.parametrize("explicit", [None, "explicit-contract-key"])
def test_key_resolution(provider_type, case, respx_mock, monkeypatch, explicit):
    monkeypatch.setenv(provider_type.ENV_VAR, "env-contract-key")
    case.success(respx_mock, "search")
    with provider_type(api_key=explicit) as instance:
        instance.search(SearchRequest(query="q"))
    case.assert_auth(respx_mock, explicit or "env-contract-key")


@pytest.mark.parametrize("operation", ["search", "extract"])
def test_normalized_response(provider, case, respx_mock, caplog, operation):
    case.success(respx_mock, operation)
    request = (
        SearchRequest(query="private query")
        if operation == "search"
        else ExtractRequest(urls=["https://example.com", "https://bad.example"])
    )
    with caplog.at_level(logging.DEBUG, logger="unified_ai_search"):
        response = getattr(provider, operation)(request)
    assert isinstance(
        response, SearchResponse if operation == "search" else ExtractResponse
    )
    assert response.operation == operation
    assert response.provider == provider.PROVIDER
    assert len(response.results) == 1
    assert isinstance(response.raw, dict)
    assert isinstance(response.extras, dict)
    assert isinstance(response.usage, Usage)
    assert response.usage.result_count == len(response.results)
    assert response.usage.latency_s >= 0
    if operation == "extract":
        assert len(response.failed) == 1
        assert response.results[0].content
    if response.usage.reported is not None:
        assert response.usage.reported.unit == "usd"
        assert response.usage.reported.amount >= 0
    assert "contract-test-key" not in caplog.text
    assert "private query" not in caplog.text


@pytest.mark.parametrize(
    "status,expected",
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (429, RateLimitError),
        (500, ProviderAPIError),
    ],
)
@pytest.mark.parametrize("headers", [{}, {"Retry-After": "3"}])
def test_error_mapping(provider, case, respx_mock, caplog, status, expected, headers):
    case.failure(respx_mock, status, headers)
    with caplog.at_level(logging.DEBUG, logger="unified_ai_search"):
        with pytest.raises(expected) as caught:
            provider.search(SearchRequest(query="q"))
    if isinstance(caught.value, RateLimitError):
        assert caught.value.retry_after == (3 if headers else None)
    if isinstance(caught.value, ProviderAPIError):
        assert caught.value.status_code == status
    assert "contract-test-key" not in caplog.text
    assert "private error body" not in caplog.text


def test_timeout_mapping(provider, case, respx_mock):
    case.timeout(respx_mock)
    with pytest.raises(ProviderTimeoutError):
        provider.search(SearchRequest(query="q"))
