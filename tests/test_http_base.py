import logging
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest

from tests.fake_provider import FakeProvider
from unified_ai_search.enums import Provider
from unified_ai_search.errors import (
    AuthenticationError,
    MissingAPIKeyError,
    ProviderAPIError,
    ProviderTimeoutError,
    RateLimitError,
)
from unified_ai_search.models import ExtractRequest, SearchRequest
from unified_ai_search.providers.base import (
    Extractor,
    HttpSearchProvider,
    Searcher,
    SearchProvider,
)
from unified_ai_search.registry import PROVIDER_REGISTRY


@pytest.fixture(params=[FakeProvider], ids=lambda cls: cls.__name__)
def provider_type(request):
    return request.param


@pytest.fixture
def provider(provider_type):
    instance = provider_type(api_key="test-only-secret")
    yield instance
    instance.close()


def test_abc_conformance(provider):
    assert isinstance(
        provider, (Searcher, Extractor, SearchProvider, HttpSearchProvider)
    )
    for base in (Searcher, Extractor, SearchProvider, HttpSearchProvider):
        with pytest.raises(TypeError):
            base()


def test_missing_key_and_explicit_precedence(provider_type, monkeypatch):
    monkeypatch.delenv(provider_type.ENV_VAR, raising=False)
    with pytest.raises(MissingAPIKeyError, match=provider_type.ENV_VAR):
        provider_type()
    monkeypatch.setenv(provider_type.ENV_VAR, "env-test-key")
    with provider_type() as instance:
        assert instance._http.headers["x-api-key"] == "env-test-key"
    with provider_type(api_key="explicit-test-key", timeout=12) as instance:
        assert instance._http.headers["x-api-key"] == "explicit-test-key"
        assert instance._http.timeout.read == 12
        assert instance._http.timeout.connect == 5
    assert instance._http.is_closed
    instance.close()
    with pytest.raises(MissingAPIKeyError):
        provider_type(api_key="")


def test_search_shape_usage_and_safe_logs(provider, respx_mock, caplog, monkeypatch):
    body = {
        "results": [
            {
                "title": "Title",
                "url": "https://example.com",
                "snippet": "private response text",
            }
        ],
        "opaque": {"keep": True},
    }
    route = respx_mock.post("https://fake.test/search").mock(
        return_value=httpx.Response(
            200,
            json=body,
            headers={"x-test-request-id": "request-123", "authorization": "secret"},
        )
    )
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr(
        "unified_ai_search.providers.base.perf_counter", lambda: next(ticks)
    )
    with caplog.at_level(logging.DEBUG, logger="unified_ai_search"):
        response = provider.search(SearchRequest(query="private request text"))
    assert route.call_count == 1
    assert response.raw == body
    assert response.operation == "search"
    assert response.results[0].content is None
    assert response.usage.latency_s == 0.25
    assert response.usage.result_count == 1
    assert response.usage.request_id == "request-123"
    assert response.usage.reported is None
    assert "authorization" not in response.extras
    assert sum(r.levelno == logging.INFO for r in caplog.records) == 1
    assert "private request text" not in caplog.text
    assert "private response text" not in caplog.text
    assert "test-only-secret" not in caplog.text


def test_partial_extract(provider, respx_mock, caplog):
    respx_mock.post("https://fake.test/extract").respond(
        200,
        json={
            "results": [{"url": "https://example.com", "content": "page"}],
            "failed": [{"url": "https://bad.example", "error": "private body"}],
        },
    )
    with caplog.at_level(logging.DEBUG, logger="unified_ai_search"):
        response = provider.extract(
            ExtractRequest(urls=["https://example.com", "https://bad.example"])
        )
    assert len(response.failed) == 1
    assert response.usage.result_count == 1
    assert response.usage.latency_s >= 0
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert "private body" not in caplog.text


@pytest.mark.parametrize(
    "status,error_type",
    [
        (401, AuthenticationError),
        (403, AuthenticationError),
        (429, RateLimitError),
        (400, ProviderAPIError),
        (402, ProviderAPIError),
        (500, ProviderAPIError),
        (503, ProviderAPIError),
    ],
)
def test_status_translation_and_no_retries(
    provider, respx_mock, caplog, status, error_type
):
    body = {"message": "server echoed test-only-secret", "private": "body-only"}
    route = respx_mock.post("https://fake.test/search").respond(status, json=body)
    with caplog.at_level(logging.DEBUG, logger="unified_ai_search"):
        with pytest.raises(error_type) as caught:
            provider.search(SearchRequest(query="q"))
    assert route.call_count == 1
    assert "test-only-secret" not in str(caught.value)
    assert "test-only-secret" not in caplog.text
    assert "body-only" not in caplog.text
    assert sum(r.levelno == logging.INFO for r in caplog.records) == 1
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    if isinstance(caught.value, ProviderAPIError):
        assert caught.value.status_code == status
        assert caught.value.body == body
    if isinstance(caught.value, RateLimitError):
        assert caught.value.retry_after is None


@pytest.mark.parametrize(
    "header,expected", [("2.5", 2.5), ("bad", None), ("-2", None), ("nan", None)]
)
def test_retry_after(provider, respx_mock, header, expected):
    respx_mock.post("https://fake.test/search").respond(
        429, headers={"Retry-After": header}
    )
    with pytest.raises(RateLimitError) as caught:
        provider.search(SearchRequest(query="q"))
    assert caught.value.retry_after == expected


def test_retry_after_http_date(provider, respx_mock):
    date = format_datetime(
        datetime.now(timezone.utc) + timedelta(seconds=60), usegmt=True
    )
    respx_mock.post("https://fake.test/search").respond(
        429, headers={"Retry-After": date}
    )
    with pytest.raises(RateLimitError) as caught:
        provider.search(SearchRequest(query="q"))
    assert 0 < caught.value.retry_after <= 60


@pytest.mark.parametrize(
    "exc,expected",
    [
        (httpx.ReadTimeout, ProviderTimeoutError),
        (httpx.ConnectTimeout, ProviderTimeoutError),
        (httpx.ConnectError, ProviderAPIError),
        (httpx.RemoteProtocolError, ProviderAPIError),
    ],
)
def test_transport_errors(provider, respx_mock, caplog, exc, expected):
    route = respx_mock.post("https://fake.test/search").mock(
        side_effect=exc("test-only-secret")
    )
    with caplog.at_level(logging.DEBUG, logger="unified_ai_search"):
        with pytest.raises(expected):
            provider.search(SearchRequest(query="q"))
    assert route.call_count == 1
    assert "test-only-secret" not in caplog.text


@pytest.mark.parametrize("payload", ["not json", "[]", "null"])
def test_invalid_json_response(provider, respx_mock, payload):
    respx_mock.post("https://fake.test/search").respond(200, text=payload)
    with pytest.raises(ProviderAPIError) as caught:
        provider.search(SearchRequest(query="q"))
    assert caught.value.status_code == 200


def test_list_body_wrapped_only_when_opted_in(provider, respx_mock):
    respx_mock.post("https://fake.test/contents").respond(200, json=[{"url": "u"}])
    result = provider._request_json(
        "POST", "/contents", operation="extract", json={}, list_key="results"
    )
    assert result.body == {"results": [{"url": "u"}]}
    respx_mock.post("https://fake.test/contents").respond(200, json={"a": 1})
    result = provider._request_json(
        "POST", "/contents", operation="extract", json={}, list_key="results"
    )
    assert result.body == {"a": 1}
    respx_mock.post("https://fake.test/contents").respond(200, text="null")
    with pytest.raises(ProviderAPIError):
        provider._request_json(
            "POST", "/contents", operation="extract", json={}, list_key="results"
        )


@pytest.mark.parametrize("status", [432, 433])
def test_tavily_specific_rate_limits(respx_mock, status):
    class TavilyFake(FakeProvider):
        PROVIDER = Provider.TAVILY

    respx_mock.post("https://fake.test/search").respond(status)
    with TavilyFake(api_key="test") as provider:
        with pytest.raises(RateLimitError):
            provider.search(SearchRequest(query="q"))


@pytest.mark.parametrize("operation", ["search", "extract"])
def test_empty_results_still_have_usage(provider, respx_mock, operation):
    respx_mock.post(f"https://fake.test/{operation}").respond(200, json={})
    request = (
        SearchRequest(query="q")
        if operation == "search"
        else ExtractRequest(urls=["https://example.com"])
    )
    response = getattr(provider, operation)(request)
    assert response.results == []
    assert response.usage.result_count == 0
    assert response.usage.latency_s >= 0


def test_default_headers_capture_nothing(provider, respx_mock):
    response = httpx.Response(200, headers={"Authorization": "private"})
    assert HttpSearchProvider._capture_headers(provider, response) == {}


def test_registry_has_no_fake_adapter():
    assert FakeProvider not in PROVIDER_REGISTRY.values()
    assert all(isinstance(key, Provider) for key in PROVIDER_REGISTRY)
