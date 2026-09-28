import json
import logging
from datetime import datetime
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
from unified_ai_search.providers.parallel import ParallelProvider
from unified_ai_search.registry import PROVIDER_REGISTRY

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "parallel-test-only-secret"
SEARCH_URL = "https://api.parallel.ai/v1/search"
EXTRACT_URL = "https://api.parallel.ai/v1/extract"
UN = "https://www.un.org/en/about-us/history-of-the-un"
MISSING = "https://example.com/missing"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def sent_json(router):
    return json.loads(router.calls.last.request.content)


def search_body(results=1, usage=None):
    body = fixture("search.json")
    body["results"] = body["results"][:results]
    if usage is not None:
        body["usage"] = usage
    return body


@pytest.fixture
def provider():
    with ParallelProvider(api_key=KEY) as instance:
        yield instance


def test_registered_with_documented_constants():
    assert PROVIDER_REGISTRY[Provider.PARALLEL] is ParallelProvider
    assert ParallelProvider.PROVIDER is Provider.PARALLEL
    assert ParallelProvider.ENV_VAR == "PARALLEL_API_KEY"
    assert ParallelProvider.BASE_URL == "https://api.parallel.ai"
    assert ParallelProvider.MAX_RESULTS_CAP is None


def test_x_api_key_auth(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body())
    provider.search(SearchRequest(query="q"))
    headers = respx_mock.calls.last.request.headers
    assert headers["x-api-key"] == KEY
    assert "Authorization" not in headers


# Search request mapping


def test_minimal_search_payload(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body())
    provider.search(SearchRequest(query="parallel web systems", max_results=7))
    assert sent_json(respx_mock) == {
        "search_queries": ["parallel web systems"],
        "advanced_settings": {"max_results": 7},
    }


def test_domains_nest_under_source_policy(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body())
    provider.search(
        SearchRequest(
            query="q", include_domains=["reuters.com"], exclude_domains=["x.com"]
        )
    )
    assert sent_json(respx_mock)["advanced_settings"] == {
        "max_results": 10,
        "source_policy": {
            "include_domains": ["reuters.com"],
            "exclude_domains": ["x.com"],
        },
    }


def test_large_max_results_passes_through(respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body())
    with SearchClient("parallel", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search("q", max_results=250)
    assert sent_json(respx_mock)["advanced_settings"]["max_results"] == 250
    assert "clamped" not in caplog.text


def test_include_content_is_ignored_with_warning(provider, respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body())
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        response = provider.search(SearchRequest(query="q", include_content=True))
    assert "full_content" not in json.dumps(sent_json(respx_mock))
    assert response.results[0].content is None
    assert "include_content" in caplog.text


# Search kwargs filtering and nesting


def test_top_level_and_nested_kwargs(respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body())
    with SearchClient("parallel", api_key=KEY) as client:
        client.search(
            "q",
            include_domains=["reuters.com"],
            objective="Latest Parallel product news",
            mode="fast",
            max_chars_total=5000,
            session_id="session_abc",
            after_date="2025-01-01",
            location="us",
            fetch_policy={"max_age_seconds": 3600},
            excerpt_settings={"max_chars_per_result": 800},
        )
    body = sent_json(respx_mock)
    assert body["objective"] == "Latest Parallel product news"
    assert body["mode"] == "fast"
    assert body["max_chars_total"] == 5000
    assert body["session_id"] == "session_abc"
    assert body["advanced_settings"] == {
        "max_results": 10,
        "source_policy": {
            "include_domains": ["reuters.com"],
            "after_date": "2025-01-01",
        },
        "location": "us",
        "fetch_policy": {"max_age_seconds": 3600},
        "excerpt_settings": {"max_chars_per_result": 800},
    }


def test_no_objective_unless_passed(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body())
    provider.search(SearchRequest(query="q"))
    assert "objective" not in sent_json(respx_mock)


def test_bad_search_kwargs_dropped(respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body())
    with SearchClient("parallel", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search(
                "q",
                mode="agentic",
                fetch_policy={"max_age_seconds": 60},
                processor="pro",
            )
    body = sent_json(respx_mock)
    assert "mode" not in body
    assert "fetch_policy" not in body["advanced_settings"]
    assert "processor" not in body
    for dropped in ("mode", "fetch_policy", "processor"):
        assert dropped in caplog.text


@pytest.mark.parametrize(
    "native", ["search_queries", "advanced_settings", "source_policy"]
)
def test_native_names_fed_by_normalized_inputs_are_dropped(respx_mock, caplog, native):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body())
    with SearchClient("parallel", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search("q", **{native: {"x": 1}})
    assert sent_json(respx_mock) == {
        "search_queries": ["q"],
        "advanced_settings": {"max_results": 10},
    }
    assert "normalized parameter wins" in caplog.text


# Search response mapping


def test_search_response_mapping(provider, respx_mock):
    body = search_body(results=10)
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    response = provider.search(SearchRequest(query="parallel"))
    assert response.provider is Provider.PARALLEL
    assert response.raw == body
    assert len(response.results) == 10
    first = response.results[0]
    assert first.url == body["results"][0]["url"]
    assert first.title == body["results"][0]["title"]
    assert first.snippet == body["results"][0]["excerpts"][0]
    assert first.content is None
    assert first.score is None
    assert first.published_date is None
    assert "published_raw" not in first.extras
    assert response.usage.request_id == "search_8a911eb27c7a4afaa20d0d9dc98d07c0"
    assert response.extras == {"session_id": "session_8a911eb27c7a4afaa20d0d9dc98d07c0"}


def test_publish_date_parsed_with_raw_kept(provider, respx_mock):
    body = search_body(results=10)
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    last = provider.search(SearchRequest(query="q")).results[-1]
    assert last.published_date == datetime(2025, 11, 19)
    assert last.extras["published_raw"] == "2025-11-19"


def test_unparseable_publish_date(provider, respx_mock):
    body = search_body()
    body["results"][0]["publish_date"] = "Nov 2025"
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.published_date is None
    assert result.extras["published_raw"] == "Nov 2025"


def test_excerpts_joined_and_missing_title(provider, respx_mock):
    body = search_body()
    body["results"][0]["excerpts"] = ["## One", "## Two"]
    body["results"][0]["title"] = None
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q")).results
    assert result.snippet == "## One\n\n## Two"
    assert result.title == ""


def test_warnings_go_to_extras(provider, respx_mock):
    body = search_body()
    body["warnings"] = [{"type": "warning", "message": "objective ignored"}]
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    extras = provider.search(SearchRequest(query="q")).extras
    assert extras["warnings"] == [{"type": "warning", "message": "objective ignored"}]


# Search cost


@pytest.mark.parametrize(
    "mode,expected",
    [
        (None, 0.005),
        ("advanced", 0.005),
        ("basic", 0.005),
        ("fast", 0.001),
        ("turbo", 0.001),
    ],
)
def test_search_cost_by_mode(provider, respx_mock, mode, expected):
    respx_mock.post(SEARCH_URL).respond(200, json=search_body(results=10))
    kwargs = {"mode": mode} if mode else {}
    reported = provider.search(
        SearchRequest(query="q", provider_kwargs=kwargs)
    ).usage.reported
    assert reported.unit == "usd"
    assert reported.amount == pytest.approx(expected)
    assert reported.exact is False
    assert reported.detail["usage"] == [{"name": "sku_search", "count": 1}]
    assert reported.detail["mode"] == (mode or "advanced")
    assert reported.detail["additional_results"] == 0


def test_search_cost_adds_results_beyond_ten(provider, respx_mock):
    body = search_body(results=10)
    body["results"] = body["results"] + body["results"][:3]
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    reported = provider.search(SearchRequest(query="q", max_results=13)).usage.reported
    assert reported.amount == pytest.approx(0.005 + 3 * 0.001)
    assert reported.detail["additional_results"] == 3


def test_unknown_skus_are_listed_not_priced(provider, respx_mock):
    usage = [{"name": "sku_search", "count": 1}, {"name": "sku_mystery", "count": 4}]
    respx_mock.post(SEARCH_URL).respond(200, json=search_body(usage=usage))
    reported = provider.search(SearchRequest(query="q")).usage.reported
    assert reported.amount == pytest.approx(0.005)
    assert reported.detail["unpriced_skus"] == [{"name": "sku_mystery", "count": 4}]


def test_no_usage_or_no_known_sku_reports_none(provider, respx_mock):
    body = search_body()
    del body["usage"]
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    assert provider.search(SearchRequest(query="q")).usage.reported is None
    respx_mock.post(SEARCH_URL).respond(
        200, json=search_body(usage=[{"name": "sku_mystery", "count": 1}])
    )
    assert provider.search(SearchRequest(query="q")).usage.reported is None


# Extract


def test_extract_payload_always_requests_full_content(provider, respx_mock):
    respx_mock.post(EXTRACT_URL).respond(200, json=fixture("extract.json"))
    provider.extract(ExtractRequest(urls=[UN]))
    assert sent_json(respx_mock) == {
        "urls": [UN],
        "advanced_settings": {"full_content": True},
    }


def test_extract_kwargs(respx_mock, caplog):
    respx_mock.post(EXTRACT_URL).respond(200, json=fixture("extract.json"))
    with SearchClient("parallel", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.extract(
                [UN],
                objective="When was the United Nations established?",
                search_queries=["UN founded"],
                max_chars_total=10000,
                fetch_policy={"timeout_seconds": 30},
                full_content_max_chars=20000,
                full_content=False,
                advanced_settings={},
            )
    assert sent_json(respx_mock) == {
        "urls": [UN],
        "objective": "When was the United Nations established?",
        "search_queries": ["UN founded"],
        "max_chars_total": 10000,
        "advanced_settings": {
            "full_content": {"max_chars_per_result": 20000},
            "fetch_policy": {"timeout_seconds": 30},
        },
    }
    assert caplog.text.count("normalized parameter wins") == 2


def test_extract_falls_back_to_excerpts(provider, respx_mock):
    respx_mock.post(EXTRACT_URL).respond(200, json=fixture("extract.json"))
    response = provider.extract(ExtractRequest(urls=[UN]))
    [result] = response.results
    assert result.url == UN
    assert result.title == "History of the United Nations | United Nations"
    assert result.content == "\n\n".join(
        fixture("extract.json")["results"][0]["excerpts"]
    )
    assert result.extras["content_source"] == "excerpts"
    assert result.extras["published_raw"] == "2001-01-01"
    assert response.failed == []
    assert response.usage.request_id == "extract_470002358ec147e8a40cb70d0d82627e"
    assert response.extras == {"session_id": "session_8a911eb27c7a4afaa20d0d9dc98d07c0"}


def test_extract_prefers_full_content(provider, respx_mock):
    body = fixture("extract.json")
    body["results"][0]["full_content"] = "# History of the United Nations\n\nFull."
    respx_mock.post(EXTRACT_URL).respond(200, json=body)
    [result] = provider.extract(ExtractRequest(urls=[UN])).results
    assert result.content == "# History of the United Nations\n\nFull."
    assert result.extras["content_source"] == "full_content"


def test_extract_errors_map_to_failed(provider, respx_mock, caplog):
    body = fixture("extract.json")
    body["errors"] = [
        {
            "url": MISSING,
            "error_type": "fetch_error",
            "http_status_code": 404,
            "content": "Not Found",
        }
    ]
    respx_mock.post(EXTRACT_URL).respond(200, json=body)
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        response = provider.extract(ExtractRequest(urls=[UN, MISSING]))
    assert [r.url for r in response.results] == [UN]
    [failed] = response.failed
    assert failed.url == MISSING
    assert failed.error == "fetch_error (HTTP 404)"
    assert "partial_extract_failures=1" in caplog.text


def test_docs_example_with_url_in_both_arrays(provider, respx_mock):
    # The docs example lists the same URL as a result and an error; the result wins.
    respx_mock.post(EXTRACT_URL).respond(200, json=fixture("extract_with_errors.json"))
    response = provider.extract(ExtractRequest(urls=["https://www.example.com"]))
    [result] = response.results
    assert result.content == "Full content ..."
    assert response.failed == []


def test_result_with_no_text_is_a_failure(provider, respx_mock):
    body = fixture("extract.json")
    body["results"][0]["excerpts"] = []
    respx_mock.post(EXTRACT_URL).respond(200, json=body)
    response = provider.extract(ExtractRequest(urls=[UN]))
    assert response.results == []
    assert [(f.url, f.error) for f in response.failed] == [(UN, "empty content")]


def test_requested_url_absent_from_response_is_a_failure(provider, respx_mock):
    respx_mock.post(EXTRACT_URL).respond(200, json=fixture("extract.json"))
    response = provider.extract(ExtractRequest(urls=[UN, MISSING]))
    assert [(f.url, f.error) for f in response.failed] == [
        (MISSING, "not returned by provider")
    ]


def test_extract_cost_per_url(provider, respx_mock):
    body = fixture("extract.json")
    body["usage"] = [
        {"name": "sku_extract_excerpts", "count": 3},
        {"name": "sku_extract_full_content", "count": 3},
    ]
    respx_mock.post(EXTRACT_URL).respond(200, json=body)
    reported = provider.extract(ExtractRequest(urls=[UN])).usage.reported
    assert reported.amount == pytest.approx(0.003)
    assert reported.exact is False
    assert reported.detail["urls_billed"] == 3
    assert reported.detail["usage"] == body["usage"]


def test_extract_docs_usage_costs_one_url(provider, respx_mock):
    respx_mock.post(EXTRACT_URL).respond(200, json=fixture("extract.json"))
    reported = provider.extract(ExtractRequest(urls=[UN])).usage.reported
    assert reported.amount == pytest.approx(0.001)


# Errors


def test_422_envelope(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(422, json=fixture("error_422.json"))
    with pytest.raises(ProviderAPIError) as caught:
        provider.search(SearchRequest(query="q"))
    assert str(caught.value) == "parallel: Request validation error"
    assert caught.value.status_code == 422
    assert caught.value.body == fixture("error_422.json")


@pytest.mark.parametrize(
    "status,expected", [(401, AuthenticationError), (429, RateLimitError)]
)
def test_same_envelope_on_other_statuses(provider, respx_mock, status, expected):
    body = {"type": "error", "error": {"ref_id": "r", "message": "Nope"}}
    respx_mock.post(SEARCH_URL).respond(status, json=body)
    with pytest.raises(expected, match="parallel: Nope"):
        provider.search(SearchRequest(query="q"))


def test_unexpected_error_body_falls_back(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(500, text="upstream failure")
    with pytest.raises(ProviderAPIError, match="parallel returned HTTP 500"):
        provider.search(SearchRequest(query="q"))
