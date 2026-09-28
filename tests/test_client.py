import logging
from typing import Literal

import pytest
from pydantic import ValidationError

from tests.fake_provider import FakeProvider
from unified_ai_search.client import SearchClient
from unified_ai_search.enums import Provider
from unified_ai_search.errors import (
    InvalidRequestError,
    MissingAPIKeyError,
    UnsupportedOperationError,
)
from unified_ai_search.pricing import PricingTable
from unified_ai_search.providers.base import Searcher
from unified_ai_search.providers.options import ProviderOptions
from unified_ai_search.registry import PROVIDER_REGISTRY

KEY = "test-only-secret"
SEARCH_URL = "https://fake.test/search"
EXTRACT_URL = "https://fake.test/extract"


class FakeSearchOptions(ProviderOptions):
    depth: Literal["basic", "advanced"] | None = None
    limit: int | None = None


class FakeExtractOptions(ProviderOptions):
    render_js: bool | None = None


class RecordingProvider(FakeProvider):
    MAX_RESULTS_CAP = 20
    SEARCH_OPTIONS = FakeSearchOptions
    EXTRACT_OPTIONS = FakeExtractOptions
    SEARCH_NORMALIZED_NAMES = frozenset({"numResults"})
    EXTRACT_NORMALIZED_NAMES = frozenset({"targets"})

    def search(self, request):
        self.last_request = request
        return super().search(request)

    def extract(self, request):
        self.last_request = request
        return super().extract(request)


class SearchOnlyProvider(Searcher):
    MAX_RESULTS_CAP = None
    SEARCH_OPTIONS = ProviderOptions
    SEARCH_NORMALIZED_NAMES: frozenset[str] = frozenset()

    def __init__(self, api_key=None, timeout=30.0, pricing=None):
        self.closed = False

    def search(self, request):
        raise AssertionError("not called in these tests")

    def close(self):
        self.closed = True


@pytest.fixture
def register(monkeypatch):
    def _register(cls, provider=Provider.EXA):
        monkeypatch.setitem(PROVIDER_REGISTRY, provider, cls)

    _register(FakeProvider)
    return _register


@pytest.fixture
def recording(register):
    register(RecordingProvider)
    with SearchClient("exa", api_key=KEY) as client:
        yield client


def warnings_in(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


# Construction


@pytest.mark.parametrize("value", ["exa", Provider.EXA])
def test_string_and_enum_coercion(register, value):
    with SearchClient(value, api_key=KEY) as client:
        assert client.provider is Provider.EXA
        assert type(client._strategy) is FakeProvider


@pytest.mark.parametrize("value", ["bing", "EXA", "", 5, None])
def test_unknown_provider_raises_value_error(register, value):
    with pytest.raises(ValueError, match="exa"):
        SearchClient(value, api_key=KEY)


def test_known_but_unregistered_provider_raises_value_error(register, monkeypatch):
    monkeypatch.delitem(PROVIDER_REGISTRY, Provider.YOU, raising=False)
    with pytest.raises(ValueError, match="no registered adapter"):
        SearchClient(Provider.YOU, api_key=KEY)


def test_strategy_objects_are_never_accepted(register):
    strategy = FakeProvider(api_key=KEY)
    try:
        with pytest.raises(ValueError):
            SearchClient(strategy, api_key=KEY)
    finally:
        strategy.close()


def test_missing_key_fails_at_construction(register, monkeypatch):
    monkeypatch.delenv(FakeProvider.ENV_VAR, raising=False)
    with pytest.raises(MissingAPIKeyError) as info:
        SearchClient("exa")
    assert FakeProvider.ENV_VAR in str(info.value)
    assert "exa" in str(info.value)


def test_explicit_key_beats_env_var(register, monkeypatch):
    monkeypatch.setenv(FakeProvider.ENV_VAR, "env-test-key")
    with SearchClient("exa") as client:
        assert client._strategy._http.headers["x-api-key"] == "env-test-key"
    with SearchClient("exa", api_key="explicit-test-key") as client:
        assert client._strategy._http.headers["x-api-key"] == "explicit-test-key"


def test_timeout_and_pricing_reach_the_strategy(register):
    pricing = PricingTable()
    with SearchClient("exa", api_key=KEY, timeout=7, pricing=pricing) as client:
        assert client._strategy._http.timeout.read == 7
        assert client._strategy.pricing is pricing


# Validation


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"query": "   "},
        {"query": "q", "max_results": 0},
        {"query": "q", "max_results": "ten"},
        {"query": "q", "include_domains": ["a.com"], "exclude_domains": ["A.com"]},
    ],
)
def test_invalid_search_raises_before_network(register, respx_mock, kwargs):
    route = respx_mock.post(SEARCH_URL)
    with SearchClient("exa", api_key=KEY) as client:
        query = kwargs.pop("query")
        with pytest.raises(InvalidRequestError) as info:
            client.search(query, **kwargs)
    assert isinstance(info.value.__cause__, ValidationError)
    assert not route.called


@pytest.mark.parametrize("urls", [[], ["not a url"], ["ftp://x.test/file"], [""]])
def test_invalid_extract_raises_before_network(register, respx_mock, urls):
    route = respx_mock.post(EXTRACT_URL)
    with SearchClient("exa", api_key=KEY) as client:
        with pytest.raises(InvalidRequestError) as info:
            client.extract(urls)
    assert isinstance(info.value.__cause__, ValidationError)
    assert not route.called


def test_normalized_inputs_reach_the_strategy(recording, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json={})
    response = recording.search(
        "q",
        max_results=5,
        include_domains=["a.com"],
        exclude_domains=["b.com"],
        include_content=True,
    )
    request = recording._strategy.last_request
    assert (request.query, request.max_results) == ("q", 5)
    assert request.include_domains == ["a.com"]
    assert request.exclude_domains == ["b.com"]
    assert request.include_content is True
    assert response.provider is Provider.EXA


# Clamping


def test_max_results_clamped_to_cap_with_warning(recording, respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json={})
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        recording.search("q", max_results=50)
    assert recording._strategy.last_request.max_results == 20
    [message] = warnings_in(caplog)
    assert "max_results" in message and "50" in message and "20" in message


def test_max_results_at_cap_is_not_clamped(recording, respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json={})
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        recording.search("q", max_results=20)
    assert recording._strategy.last_request.max_results == 20
    assert warnings_in(caplog) == []


def test_no_clamp_without_declared_cap(register, respx_mock, caplog):
    route = respx_mock.post(SEARCH_URL).respond(200, json={})
    with SearchClient("exa", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search("q", max_results=500)
    assert FakeProvider.MAX_RESULTS_CAP is None
    assert route.called
    assert warnings_in(caplog) == []


# Provider kwargs


def test_matching_kwargs_are_forwarded(recording, respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json={})
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        recording.search("q", depth="advanced", limit=3)
    assert recording._strategy.last_request.provider_kwargs == {
        "depth": "advanced",
        "limit": 3,
    }
    assert warnings_in(caplog) == []


def test_unknown_and_mistyped_kwargs_dropped_call_proceeds(
    recording, respx_mock, caplog
):
    route = respx_mock.post(SEARCH_URL).respond(200, json={})
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        recording.search("q", depth="advanced", bogus=1, limit="3")
    assert route.called
    assert recording._strategy.last_request.provider_kwargs == {"depth": "advanced"}
    messages = warnings_in(caplog)
    assert any("unknown" in m and "bogus" in m for m in messages)
    assert any("mistyped" in m and "limit" in m for m in messages)


def test_normalized_param_wins_on_collision(recording, respx_mock, caplog):
    route = respx_mock.post(SEARCH_URL).respond(200, json={})
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        recording.search("q", max_results=5, numResults=99)
    assert route.called
    request = recording._strategy.last_request
    assert request.max_results == 5
    assert request.provider_kwargs == {}
    [message] = warnings_in(caplog)
    assert "numResults" in message and "normalized parameter wins" in message


def test_extract_kwargs_filtered(recording, respx_mock, caplog):
    route = respx_mock.post(EXTRACT_URL).respond(200, json={})
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        recording.extract(
            ["https://a.test"], render_js=True, targets=["x"], depth="advanced"
        )
    assert route.called
    request = recording._strategy.last_request
    assert request.urls == ["https://a.test"]
    assert request.provider_kwargs == {"render_js": True}
    messages = warnings_in(caplog)
    assert any("targets" in m and "normalized parameter wins" in m for m in messages)
    assert any("unknown" in m and "depth" in m for m in messages)


def test_invalid_request_logs_no_kwarg_warnings(recording, respx_mock, caplog):
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        with pytest.raises(InvalidRequestError):
            recording.search("", bogus=1, max_results=500)
    assert warnings_in(caplog) == []


# Capability check


def test_extract_requires_extractor_capability(register, respx_mock):
    register(SearchOnlyProvider)
    with SearchClient("exa", api_key=KEY) as client:
        with pytest.raises(UnsupportedOperationError, match="exa"):
            client.extract(["https://a.test"])
    assert not respx_mock.calls


# Lifecycle


def test_close_is_idempotent(register):
    client = SearchClient("exa", api_key=KEY)
    client.close()
    client.close()
    assert client._strategy._http.is_closed


def test_context_manager_returns_self_and_closes(register):
    with SearchClient("exa", api_key=KEY) as client:
        assert isinstance(client, SearchClient)
        assert not client._strategy._http.is_closed
    assert client._strategy._http.is_closed


def test_context_manager_closes_on_error(register):
    register(SearchOnlyProvider)
    with pytest.raises(RuntimeError):
        with SearchClient("exa", api_key=KEY) as client:
            raise RuntimeError("boom")
    assert client._strategy.closed


# Public API


def test_public_api_exports():
    import unified_ai_search as sdk

    expected = {
        "SearchClient",
        "Provider",
        "PricingTable",
        "UnitPrice",
        "SearchRequest",
        "ExtractRequest",
        "SearchResponse",
        "ExtractResponse",
        "SearchResult",
        "ExtractResult",
        "FailedExtraction",
        "Usage",
        "ReportedCost",
        "SearchSDKError",
        "MissingAPIKeyError",
        "InvalidRequestError",
        "AuthenticationError",
        "RateLimitError",
        "ProviderAPIError",
        "ProviderTimeoutError",
        "UnsupportedOperationError",
    }
    assert expected <= set(sdk.__all__)
    for name in expected:
        assert getattr(sdk, name) is not None
    assert sdk.SearchClient is SearchClient
