import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from unified_ai_search.client import SearchClient
from unified_ai_search.enums import Provider
from unified_ai_search.errors import (
    AuthenticationError,
    ProviderAPIError,
    RateLimitError,
)
from unified_ai_search.models import ExtractRequest, SearchRequest
from unified_ai_search.pricing import PricingTable, UnitPrice
from unified_ai_search.providers.tavily import TavilyProvider
from unified_ai_search.registry import PROVIDER_REGISTRY

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "tvly-test-only-secret"
SEARCH_URL = "https://api.tavily.com/search"
EXTRACT_URL = "https://api.tavily.com/extract"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def sent_json(router):
    return json.loads(router.calls.last.request.content)


@pytest.fixture
def provider():
    with TavilyProvider(api_key=KEY) as instance:
        yield instance


def test_registered_with_documented_constants():
    assert PROVIDER_REGISTRY[Provider.TAVILY] is TavilyProvider
    assert TavilyProvider.PROVIDER is Provider.TAVILY
    assert TavilyProvider.ENV_VAR == "TAVILY_API_KEY"
    assert TavilyProvider.BASE_URL == "https://api.tavily.com"
    assert TavilyProvider.MAX_RESULTS_CAP == 20


def test_bearer_auth(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(SearchRequest(query="q"))
    assert respx_mock.calls.last.request.headers["Authorization"] == f"Bearer {KEY}"


# Search request mapping


def test_minimal_search_payload(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(SearchRequest(query="Who is Leo Messi?", max_results=7))
    assert sent_json(respx_mock) == {
        "query": "Who is Leo Messi?",
        "max_results": 7,
        "include_usage": True,
    }


def test_domains_and_content_map_to_native_names(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(
        SearchRequest(
            query="q",
            include_domains=["britannica.com"],
            exclude_domains=["reddit.com"],
            include_content=True,
        )
    )
    body = sent_json(respx_mock)
    assert body["include_domains"] == ["britannica.com"]
    assert body["exclude_domains"] == ["reddit.com"]
    assert body["include_raw_content"] is True


def test_provider_kwargs_are_merged_into_search_payload(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(
        SearchRequest(
            query="q",
            provider_kwargs={"search_depth": "advanced", "topic": "news"},
        )
    )
    body = sent_json(respx_mock)
    assert body["search_depth"] == "advanced"
    assert body["topic"] == "news"
    assert body["include_usage"] is True


def test_client_clamps_max_results_to_documented_cap(respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with SearchClient("tavily", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search("q", max_results=50)
    assert sent_json(respx_mock)["max_results"] == 20
    assert "from 50 to 20" in caplog.text


# Search kwargs filtering


def test_curated_search_kwargs_forwarded_and_bad_ones_dropped(respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with SearchClient("tavily", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search(
                "q",
                search_depth="advanced",
                topic="finance",
                time_range="week",
                include_answer="basic",
                include_published_date=True,
                chunks_per_source=9,
                country=5,
                bogus=1,
            )
    body = sent_json(respx_mock)
    assert body["search_depth"] == "advanced"
    assert body["topic"] == "finance"
    assert body["time_range"] == "week"
    assert body["include_answer"] == "basic"
    assert body["include_published_date"] is True
    for dropped in ("chunks_per_source", "country", "bogus"):
        assert dropped not in body
        assert dropped in caplog.text


@pytest.mark.parametrize("native", ["include_raw_content", "include_usage"])
def test_native_names_fed_by_the_sdk_cannot_be_overridden(respx_mock, caplog, native):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with SearchClient("tavily", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search("q", **{native: False})
    body = sent_json(respx_mock)
    assert body["include_usage"] is True
    assert "include_raw_content" not in body
    assert "normalized parameter wins" in caplog.text


# Search response mapping


def test_search_response_mapping(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    response = provider.search(SearchRequest(query="Who is Leo Messi?"))
    assert response.provider is Provider.TAVILY
    assert response.query == "Who is Leo Messi?"
    assert response.raw == fixture("search.json")
    [result] = response.results
    assert result.title == "Lionel Messi Facts | Britannica"
    assert result.url == "https://www.britannica.com/facts/Lionel-Messi"
    assert result.snippet.startswith("Lionel Messi, an Argentine footballer")
    assert result.content is None
    assert result.score == 0.81025416
    assert result.extras["favicon"] == "https://britannica.com/favicon.png"
    assert result.extras["id"] == "a3f9c2-04"


def test_rfc_2822_published_date_parsed_with_raw_kept(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.published_date == datetime(2025, 3, 11, 17, tzinfo=timezone.utc)
    assert result.extras["published_raw"] == "Tue, 11 Mar 2025 17:00:00 GMT"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2025-03-11", datetime(2025, 3, 11)),
        ("2025-03-11T17:00:00Z", datetime(2025, 3, 11, 17, tzinfo=timezone.utc)),
        ("sometime last spring", None),
    ],
)
def test_other_date_shapes(provider, respx_mock, raw, expected):
    body = fixture("search.json")
    body["results"][0]["published_date"] = raw
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.published_date == expected
    assert result.extras["published_raw"] == raw


def test_missing_published_date_leaves_no_raw(provider, respx_mock):
    body = fixture("search.json")
    del body["results"][0]["published_date"]
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.published_date is None
    assert "published_raw" not in result.extras


def test_raw_content_maps_to_content(provider, respx_mock):
    body = fixture("search.json")
    body["results"][0]["raw_content"] = "# Lionel Messi\n\nFull page."
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q", include_content=True)).results
    assert result.content == "# Lionel Messi\n\nFull page."


def test_search_response_extras(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    response = provider.search(SearchRequest(query="q"))
    assert response.extras["answer"].startswith("Lionel Messi, born in 1987")
    assert response.extras["images"] == []
    assert response.extras["auto_parameters"] == {
        "topic": "general",
        "search_depth": "basic",
    }
    assert response.extras["response_time"] == "1.67"


def test_search_usage_and_cost(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    usage = provider.search(SearchRequest(query="q")).usage
    assert usage.request_id == "123e4567-e89b-12d3-a456-426614174111"
    assert usage.result_count == 1
    assert usage.latency_s >= 0
    assert usage.reported is not None
    assert usage.reported.amount == pytest.approx(0.008)
    assert usage.reported.exact is False
    assert usage.reported.detail == {
        "credits": 1,
        "usd_per_credit": 0.008,
        "price_source": "https://docs.tavily.com/documentation/api-credits",
    }


def test_cost_uses_caller_pricing_override(respx_mock):
    body = fixture("search.json")
    body["usage"] = {"credits": 2}
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    pricing = PricingTable(
        tavily_credit=UnitPrice(
            amount=0.005,
            unit="credit",
            source_url="https://example.com/contract",
            collected_on="2026-09-27",
        )
    )
    with TavilyProvider(api_key=KEY, pricing=pricing) as instance:
        reported = instance.search(SearchRequest(query="q")).usage.reported
    assert reported.amount == pytest.approx(0.01)
    assert reported.detail["credits"] == 2


def test_no_usage_or_unknown_price_reports_no_cost(respx_mock):
    body = fixture("search.json")
    del body["usage"]
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    with TavilyProvider(api_key=KEY) as instance:
        assert instance.search(SearchRequest(query="q")).usage.reported is None
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    unpriced = PricingTable(
        tavily_credit=UnitPrice(
            amount=None, unit="credit", source_url="x", collected_on="2026-09-27"
        )
    )
    with TavilyProvider(api_key=KEY, pricing=unpriced) as instance:
        assert instance.search(SearchRequest(query="q")).usage.reported is None


def test_no_documented_headers_captured(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(
        200, json=fixture("search.json"), headers={"x-request-id": "hdr"}
    )
    response = provider.search(SearchRequest(query="q"))
    assert response.usage.request_id == "123e4567-e89b-12d3-a456-426614174111"
    assert "x-request-id" not in response.extras


# Extract


def test_extract_payload(provider, respx_mock):
    respx_mock.post(EXTRACT_URL).respond(200, json=fixture("extract_partial.json"))
    provider.extract(
        ExtractRequest(
            urls=["https://example.com/article", "https://example.com/unavailable"],
            provider_kwargs={"extract_depth": "advanced", "format": "text"},
        )
    )
    assert sent_json(respx_mock) == {
        "urls": ["https://example.com/article", "https://example.com/unavailable"],
        "include_usage": True,
        "extract_depth": "advanced",
        "format": "text",
    }


def test_extract_partial_failure_mapping(provider, respx_mock, caplog):
    respx_mock.post(EXTRACT_URL).respond(200, json=fixture("extract_partial.json"))
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        response = provider.extract(
            ExtractRequest(
                urls=["https://example.com/article", "https://example.com/unavailable"]
            )
        )
    [result] = response.results
    assert result.url == "https://example.com/article"
    assert result.content == "Example extracted article content."
    assert result.title is None
    assert result.extras == {"images": []}
    [failed] = response.failed
    assert failed.url == "https://example.com/unavailable"
    assert failed.error == "Failed to retrieve content"
    assert response.raw == fixture("extract_partial.json")
    assert response.extras["response_time"] == 0.5
    assert response.usage.request_id == "123e4567-e89b-12d3-a456-426614174111"
    assert response.usage.result_count == 1
    assert response.usage.reported is None
    assert "partial_extract_failures=1" in caplog.text


def test_extract_all_failures_on_http_200_does_not_raise(provider, respx_mock):
    body = fixture("extract_partial.json")
    body["results"] = []
    respx_mock.post(EXTRACT_URL).respond(200, json=body)
    response = provider.extract(ExtractRequest(urls=["https://example.com/a"]))
    assert response.results == []
    assert len(response.failed) == 1


def test_extract_empty_content_is_a_failure(provider, respx_mock):
    body = fixture("extract_partial.json")
    body["results"][0]["raw_content"] = None
    respx_mock.post(EXTRACT_URL).respond(200, json=body)
    response = provider.extract(ExtractRequest(urls=["https://example.com/a"]))
    assert response.results == []
    assert [f.url for f in response.failed] == [
        "https://example.com/unavailable",
        "https://example.com/article",
    ]


def test_extract_cost_is_approximate(provider, respx_mock):
    body = fixture("extract_partial.json")
    body["usage"] = {"credits": 1}
    respx_mock.post(EXTRACT_URL).respond(200, json=body)
    reported = provider.extract(
        ExtractRequest(urls=["https://example.com/a"])
    ).usage.reported
    assert reported.amount == pytest.approx(0.008)
    assert reported.exact is False
    assert reported.detail["credits"] == 1


def test_extract_kwargs_filtered(respx_mock, caplog):
    respx_mock.post(EXTRACT_URL).respond(200, json=fixture("extract_partial.json"))
    with SearchClient("tavily", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.extract(
                ["https://example.com/a"],
                query="messi",
                chunks_per_source=5,
                timeout=61,
                format="html",
                include_usage=False,
            )
    body = sent_json(respx_mock)
    assert body["urls"] == ["https://example.com/a"]
    assert body["include_usage"] is True
    assert body["query"] == "messi"
    assert body["chunks_per_source"] == 5
    assert "timeout" not in body
    assert "format" not in body
    assert "normalized parameter wins" in caplog.text


# Errors


@pytest.mark.parametrize(
    "status,name,expected,message",
    [
        (429, "error_429.json", RateLimitError, "excessive requests"),
        (432, "error_432.json", RateLimitError, "plan's set usage limit"),
        (433, "error_433.json", RateLimitError, "pay-as-you-go limit"),
    ],
)
def test_rate_limit_errors(provider, respx_mock, status, name, expected, message):
    respx_mock.post(SEARCH_URL).respond(
        status, json=fixture(name), headers={"Retry-After": "60"}
    )
    with pytest.raises(expected, match=message) as caught:
        provider.search(SearchRequest(query="q"))
    assert caught.value.retry_after == 60


def test_401_message_parsed(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(
        401, json={"detail": {"error": "Unauthorized: missing or invalid API key."}}
    )
    with pytest.raises(AuthenticationError, match="missing or invalid API key"):
        provider.search(SearchRequest(query="q"))


def test_422_message_uses_loc_and_msg_but_never_input(provider, respx_mock):
    body = fixture("error_422.json")
    body["detail"][0]["input"] = "private user input"
    respx_mock.post(SEARCH_URL).respond(422, json=body)
    with pytest.raises(ProviderAPIError) as caught:
        provider.search(SearchRequest(query="q"))
    assert str(caught.value) == "tavily: body.query: Input should be a valid string"
    assert caught.value.status_code == 422
    assert caught.value.body == body


def test_extract_400_all_invalid_raises_with_body(provider, respx_mock):
    respx_mock.post(EXTRACT_URL).respond(
        400, json=fixture("extract_400_all_invalid.json")
    )
    with pytest.raises(ProviderAPIError, match="All URLs failed validation") as caught:
        provider.extract(ExtractRequest(urls=["https://example.com/a"]))
    assert caught.value.status_code == 400
    assert caught.value.body == fixture("extract_400_all_invalid.json")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="<html>oops</html>"),
        httpx.Response(500, json={"detail": "plain string"}),
        httpx.Response(500, json={"unexpected": True}),
    ],
)
def test_unexpected_error_bodies_fall_back(provider, respx_mock, response):
    respx_mock.post(SEARCH_URL).mock(return_value=response)
    with pytest.raises(ProviderAPIError) as caught:
        provider.search(SearchRequest(query="q"))
    assert caught.value.status_code == 500
    assert str(caught.value).startswith("tavily")
