import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from unified_ai_search.client import SearchClient
from unified_ai_search.enums import Provider
from unified_ai_search.errors import (
    AuthenticationError,
    ProviderAPIError,
    RateLimitError,
)
from unified_ai_search.models import ExtractRequest, SearchRequest
from unified_ai_search.providers.exa import ExaProvider
from unified_ai_search.registry import PROVIDER_REGISTRY

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "exa-test-only-secret"
SEARCH_URL = "https://api.exa.ai/search"
CONTENTS_URL = "https://api.exa.ai/contents"
ARXIV = "https://arxiv.org/abs/2307.06435"
MISSING = "https://example.com/missing"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def sent_json(router):
    return json.loads(router.calls.last.request.content)


def mixed_contents():
    # Docs show only a success status; the error entry uses the documented
    # field examples (tag CRAWL_NOT_FOUND, httpStatusCode 404).
    body = fixture("contents.json")
    body["statuses"].append(
        {
            "id": MISSING,
            "status": "error",
            "error": {"tag": "CRAWL_NOT_FOUND", "httpStatusCode": 404},
        }
    )
    return body


@pytest.fixture
def provider():
    with ExaProvider(api_key=KEY) as instance:
        yield instance


def test_registered_with_documented_constants():
    assert PROVIDER_REGISTRY[Provider.EXA] is ExaProvider
    assert ExaProvider.PROVIDER is Provider.EXA
    assert ExaProvider.ENV_VAR == "EXA_API_KEY"
    assert ExaProvider.BASE_URL == "https://api.exa.ai"
    assert ExaProvider.MAX_RESULTS_CAP == 100


def test_bearer_auth(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(SearchRequest(query="q"))
    assert respx_mock.calls.last.request.headers["Authorization"] == f"Bearer {KEY}"


# Search request mapping


def test_minimal_search_payload(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(SearchRequest(query="LLM survey", max_results=7))
    assert sent_json(respx_mock) == {
        "query": "LLM survey",
        "numResults": 7,
        "contents": {"highlights": True},
    }


def test_domains_and_content_use_camel_case_and_nesting(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(
        SearchRequest(
            query="q",
            include_domains=["arxiv.org"],
            exclude_domains=["reddit.com"],
            include_content=True,
        )
    )
    body = sent_json(respx_mock)
    assert body["includeDomains"] == ["arxiv.org"]
    assert body["excludeDomains"] == ["reddit.com"]
    assert body["contents"] == {"highlights": True, "text": True}


def test_client_clamps_max_results_to_documented_cap(respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with SearchClient("exa", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search("q", max_results=250)
    assert sent_json(respx_mock)["numResults"] == 100
    assert "from 250 to 100" in caplog.text


# Search kwargs filtering


def test_curated_search_kwargs_forwarded_and_bad_ones_dropped(respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with SearchClient("exa", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search(
                "q",
                type="deep-lite",
                category="research paper",
                startPublishedDate="2023-01-01T00:00:00.000Z",
                userLocation="US",
                moderation=True,
                includeText=["llm"],
                stream=True,
                outputSchema={"type": "object"},
            )
    body = sent_json(respx_mock)
    assert body["type"] == "deep-lite"
    assert body["category"] == "research paper"
    assert body["startPublishedDate"] == "2023-01-01T00:00:00.000Z"
    assert body["userLocation"] == "US"
    assert body["moderation"] is True
    for dropped in ("includeText", "stream", "outputSchema"):
        assert dropped not in body
        assert dropped in caplog.text


def test_unknown_search_type_dropped(respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with SearchClient("exa", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search("q", type="keyword")
    assert "type" not in sent_json(respx_mock)
    assert "provider option type" in caplog.text


@pytest.mark.parametrize(
    "native", ["numResults", "includeDomains", "excludeDomains", "contents"]
)
def test_native_names_fed_by_normalized_inputs_are_dropped(respx_mock, caplog, native):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with SearchClient("exa", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search("q", max_results=5, **{native: ["x"]})
    body = sent_json(respx_mock)
    assert body["numResults"] == 5
    assert body["contents"] == {"highlights": True}
    assert "includeDomains" not in body
    assert "normalized parameter wins" in caplog.text


# Search response mapping


def test_search_response_mapping(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    response = provider.search(SearchRequest(query="LLM survey", include_content=True))
    assert response.provider is Provider.EXA
    assert response.query == "LLM survey"
    assert response.raw == fixture("search.json")
    [result] = response.results
    assert result.title == "A Comprehensive Overview of Large Language Models"
    assert result.url == "https://arxiv.org/pdf/2307.06435.pdf"
    assert result.snippet == "Such requirements have limited their adoption..."
    assert result.content.startswith("Abstract Large Language Models")
    assert result.score is None
    assert result.extras["id"] == ARXIV
    assert result.extras["author"].startswith("Humza  Naveed")
    assert result.extras["image"] == "https://arxiv.org/pdf/2307.06435.pdf/page_1.png"
    assert result.extras["favicon"] == "https://arxiv.org/favicon.ico"
    assert result.extras["summary"].startswith("This overview paper")


def test_highlights_joined_with_blank_line(provider, respx_mock):
    body = fixture("search.json")
    body["results"][0]["highlights"] = ["first", "second"]
    body["results"][0]["highlightScores"] = [0.9, 0.4]
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.snippet == "first\n\nsecond"
    assert result.extras["highlightScores"] == [0.9, 0.4]


def test_no_highlights_gives_no_snippet(provider, respx_mock):
    body = fixture("search.json")
    del body["results"][0]["highlights"]
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.snippet is None


def test_text_ignored_unless_content_requested(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.content is None


def test_null_title_becomes_empty_string(provider, respx_mock):
    body = fixture("search.json")
    body["results"][0]["title"] = None
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.title == ""


def test_iso_published_date_parsed_with_raw_kept(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.published_date == datetime(
        2023, 11, 16, 1, 36, 32, 547000, tzinfo=timezone.utc
    )
    assert result.extras["published_raw"] == "2023-11-16T01:36:32.547Z"


def test_unparseable_date_is_none_with_raw_kept(provider, respx_mock):
    body = fixture("search.json")
    body["results"][0]["publishedDate"] = "last Tuesday"
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.published_date is None
    assert result.extras["published_raw"] == "last Tuesday"


def test_search_response_extras_and_headers(provider, respx_mock):
    body = fixture("search.json")
    body["searchTime"] = 312.4
    respx_mock.post(SEARCH_URL).respond(
        200,
        json=body,
        headers={
            "x-request-id": "b5947044c4b78efa9552a7c89b306d95",
            "x-exa-queued": "true",
            "x-exa-queue-ms": "42",
            "x-undocumented": "nope",
        },
    )
    response = provider.search(SearchRequest(query="q"))
    assert response.extras["resolvedSearchType"] == "neural"
    assert response.extras["searchTime"] == 312.4
    assert response.extras["x-exa-queued"] == "true"
    assert response.extras["x-exa-queue-ms"] == "42"
    assert "x-undocumented" not in response.extras


def test_request_id_from_body_else_header(provider, respx_mock):
    body = fixture("search.json")
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    assert (
        provider.search(SearchRequest(query="q")).usage.request_id
        == "b5947044c4b78efa9552a7c89b306d95"
    )
    del body["requestId"]
    respx_mock.post(SEARCH_URL).respond(
        200, json=body, headers={"x-request-id": "from-header"}
    )
    assert provider.search(SearchRequest(query="q")).usage.request_id == "from-header"


def test_search_cost_in_dollars(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    usage = provider.search(SearchRequest(query="q")).usage
    assert usage.result_count == 1
    assert usage.reported is not None
    assert usage.reported.unit == "usd"
    assert usage.reported.amount == pytest.approx(0.007)
    assert usage.reported.exact is False
    assert usage.reported.detail == {"total": 0.007, "search": {"neural": 0.007}}


def test_missing_cost_reports_none(provider, respx_mock):
    body = fixture("search.json")
    del body["costDollars"]
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    assert provider.search(SearchRequest(query="q")).usage.reported is None


# Extract (/contents)


def test_extract_payload(provider, respx_mock):
    respx_mock.post(CONTENTS_URL).respond(200, json=fixture("contents.json"))
    provider.extract(ExtractRequest(urls=[ARXIV], provider_kwargs={"maxAgeHours": 24}))
    assert sent_json(respx_mock) == {"urls": [ARXIV], "text": True, "maxAgeHours": 24}


def test_extract_success_mapping(provider, respx_mock):
    respx_mock.post(CONTENTS_URL).respond(200, json=fixture("contents.json"))
    response = provider.extract(ExtractRequest(urls=[ARXIV]))
    [result] = response.results
    assert result.url == ARXIV
    assert result.title == "A Comprehensive Overview of Large Language Models"
    assert result.content.startswith("Abstract Large Language Models")
    assert result.extras["resolved_url"] == "https://arxiv.org/pdf/2307.06435.pdf"
    assert result.extras["source"] == "cached"
    assert result.extras["author"].startswith("Humza  Naveed")
    assert result.extras["published_raw"] == "2023-11-16T01:36:32.547Z"
    assert response.failed == []
    assert response.raw == fixture("contents.json")
    assert response.usage.request_id == "e492118ccdedcba5088bfc4357a8a125"
    assert response.usage.reported.amount == pytest.approx(0.003)
    assert response.usage.reported.exact is False


def test_extract_mixed_statuses_matched_by_id(provider, respx_mock, caplog):
    respx_mock.post(CONTENTS_URL).respond(200, json=mixed_contents())
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        response = provider.extract(ExtractRequest(urls=[MISSING, ARXIV]))
    assert [r.url for r in response.results] == [ARXIV]
    [failed] = response.failed
    assert failed.url == MISSING
    assert failed.error == "CRAWL_NOT_FOUND (HTTP 404)"
    assert response.usage.result_count == 1
    assert "partial_extract_failures=1" in caplog.text


def test_error_status_without_details(provider, respx_mock):
    body = fixture("contents.json")
    body["statuses"].append({"id": MISSING, "status": "error"})
    respx_mock.post(CONTENTS_URL).respond(200, json=body)
    [failed] = provider.extract(ExtractRequest(urls=[ARXIV, MISSING])).failed
    assert failed.error == "error"


def test_result_with_error_status_is_a_failure(provider, respx_mock):
    body = fixture("contents.json")
    body["statuses"][0] = {
        "id": ARXIV,
        "status": "error",
        "error": {"tag": "CRAWL_TIMEOUT", "httpStatusCode": None},
    }
    respx_mock.post(CONTENTS_URL).respond(200, json=body)
    response = provider.extract(ExtractRequest(urls=[ARXIV]))
    assert response.results == []
    assert response.failed[0].error == "CRAWL_TIMEOUT"


def test_empty_text_is_a_failure(provider, respx_mock):
    body = fixture("contents.json")
    body["results"][0]["text"] = ""
    respx_mock.post(CONTENTS_URL).respond(200, json=body)
    response = provider.extract(ExtractRequest(urls=[ARXIV]))
    assert response.results == []
    assert response.failed[0].url == ARXIV
    assert response.failed[0].error == "empty content"


def test_requested_url_absent_from_response_is_a_failure(provider, respx_mock):
    respx_mock.post(CONTENTS_URL).respond(200, json=fixture("contents.json"))
    response = provider.extract(ExtractRequest(urls=[ARXIV, MISSING]))
    assert [r.url for r in response.results] == [ARXIV]
    assert [(f.url, f.error) for f in response.failed] == [
        (MISSING, "not returned by provider")
    ]


def test_extract_kwargs_filtered(respx_mock, caplog):
    respx_mock.post(CONTENTS_URL).respond(200, json=fixture("contents.json"))
    with SearchClient("exa", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.extract(
                [ARXIV],
                maxAgeHours=0,
                livecrawlTimeout=5000,
                subpages=-1,
                text=False,
                ids=["x"],
                livecrawl="always",
            )
    body = sent_json(respx_mock)
    assert body == {
        "urls": [ARXIV],
        "text": True,
        "maxAgeHours": 0,
        "livecrawlTimeout": 5000,
    }
    assert "normalized parameter wins" in caplog.text
    for dropped in ("subpages", "livecrawl"):
        assert dropped in caplog.text


# Errors


@pytest.mark.parametrize(
    "status,name,expected,message",
    [
        (400, "error_400.json", ProviderAPIError, "INVALID_REQUEST_BODY"),
        (401, "error_401.json", AuthenticationError, "INVALID_API_KEY: Invalid API"),
        (429, "error_429.json", RateLimitError, "RATE_LIMIT_EXCEEDED"),
        (503, "error_503.json", ProviderAPIError, "over capacity"),
    ],
)
def test_error_envelopes(provider, respx_mock, status, name, expected, message):
    respx_mock.post(SEARCH_URL).respond(status, json=fixture(name))
    with pytest.raises(expected, match=message) as caught:
        provider.search(SearchRequest(query="q"))
    if isinstance(caught.value, ProviderAPIError):
        assert caught.value.status_code == status
        assert caught.value.body == fixture(name)
    if isinstance(caught.value, RateLimitError):
        assert caught.value.retry_after is None


def test_402_payment_required_is_provider_error(provider, respx_mock):
    body = {"requestId": "r", "error": "Out of credits", "tag": "NO_MORE_CREDITS"}
    respx_mock.post(CONTENTS_URL).respond(402, json=body)
    with pytest.raises(ProviderAPIError, match="Out of credits") as caught:
        provider.extract(ExtractRequest(urls=[ARXIV]))
    assert caught.value.status_code == 402


def test_non_json_error_body_falls_back(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(500, text="<html>oops</html>")
    with pytest.raises(ProviderAPIError, match="exa returned HTTP 500"):
        provider.search(SearchRequest(query="q"))
