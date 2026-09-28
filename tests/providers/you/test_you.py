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
from unified_ai_search.providers.you import YouProvider
from unified_ai_search.registry import PROVIDER_REGISTRY

FIXTURES = Path(__file__).parent / "fixtures"
KEY = "ydc-test-only-secret"
SEARCH_URL = "https://ydc-index.io/v1/search"
CONTENTS_URL = "https://ydc-index.io/v1/contents"
WIKI = "https://en.wikipedia.org/wiki/Main_Page"
MISSING = "https://example.com/missing"
FULL_PAGE = {
    "extraction_mode": "full_page",
    "full_page": {"extraction_formats": ["markdown"]},
}
RATE_HEADERS = {
    "X-RateLimit-Limit": "10",
    "X-RateLimit-Remaining": "9",
    "X-RateLimit-Reset": "1790000000",
}


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def sent_json(router):
    return json.loads(router.calls.last.request.content)


def contents_with_markdown():
    items = fixture("contents.json")
    items[0]["markdown"] = "# Wikipedia\n\nWelcome."
    return items


@pytest.fixture
def provider():
    with YouProvider(api_key=KEY) as instance:
        yield instance


def test_registered_with_documented_constants():
    assert PROVIDER_REGISTRY[Provider.YOU] is YouProvider
    assert YouProvider.PROVIDER is Provider.YOU
    assert YouProvider.ENV_VAR == "YDC_API_KEY"
    assert YouProvider.BASE_URL == "https://ydc-index.io"
    assert YouProvider.MAX_RESULTS_CAP is None


def test_x_api_key_auth(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(SearchRequest(query="q"))
    headers = respx_mock.calls.last.request.headers
    assert headers["X-API-Key"] == KEY
    assert "Authorization" not in headers


# Search request mapping


def test_docs_snippets_request_payload(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(
        SearchRequest(
            query="What are the latest geopolitical updates from India",
            include_domains=["timesofindia.indiatimes.com", "ndtv.com", "thehindu.com"],
        )
    )
    assert sent_json(respx_mock) == {
        "query": "What are the latest geopolitical updates from India",
        "count": 10,
        "include_domains": ["timesofindia.indiatimes.com", "ndtv.com", "thehindu.com"],
    }


def test_include_content_matches_docs_full_page_request(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search_full_page.json"))
    provider.search(SearchRequest(query="q", max_results=2, include_content=True))
    assert sent_json(respx_mock) == {"query": "q", "count": 2, "extraction": FULL_PAGE}


def test_extraction_source_nests_only_with_full_page(provider, respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search_full_page.json"))
    provider.search(
        SearchRequest(
            query="q",
            include_content=True,
            provider_kwargs={"extraction_source": "fetch"},
        )
    )
    assert sent_json(respx_mock)["extraction"] == {
        **FULL_PAGE,
        "extraction_source": "fetch",
    }
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        provider.search(
            SearchRequest(query="q", provider_kwargs={"extraction_source": "fetch"})
        )
    assert "extraction" not in sent_json(respx_mock)
    assert "extraction_source" in caplog.text


def test_highlights_kwarg_requests_highlights(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search_highlights.json"))
    provider.search(SearchRequest(query="q", provider_kwargs={"highlights": True}))
    assert sent_json(respx_mock)["extraction"] == {"extraction_mode": "highlights"}


def test_full_page_wins_over_highlights(provider, respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search_full_page.json"))
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        provider.search(
            SearchRequest(
                query="q", include_content=True, provider_kwargs={"highlights": True}
            )
        )
    assert sent_json(respx_mock)["extraction"] == FULL_PAGE
    assert "highlights" in caplog.text


def test_both_domain_lists_send_include_only(provider, respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        provider.search(
            SearchRequest(
                query="q", include_domains=["a.com"], exclude_domains=["b.com"]
            )
        )
    body = sent_json(respx_mock)
    assert body["include_domains"] == ["a.com"]
    assert "exclude_domains" not in body
    assert "exclude_domains" in caplog.text


def test_exclude_domains_alone(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    provider.search(SearchRequest(query="q", exclude_domains=["b.com"]))
    assert sent_json(respx_mock)["exclude_domains"] == ["b.com"]


def test_large_count_passes_through(respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with SearchClient("you", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search("q", max_results=250)
    assert sent_json(respx_mock)["count"] == 250
    assert "clamped" not in caplog.text


# Search kwargs filtering


def test_curated_search_kwargs(respx_mock, caplog):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    with SearchClient("you", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.search(
                "q",
                freshness="2025-01-01to2025-06-30",
                country="IN",
                language="EN-GB",
                safesearch="strict",
                offset=2,
                knowledge="core",
                boost_domains=["ndtv.com"],
                crawl_timeout=61,
                livecrawl="web",
                count=3,
                extraction={"extraction_mode": "full_page"},
            )
    body = sent_json(respx_mock)
    assert body["freshness"] == "2025-01-01to2025-06-30"
    assert body["country"] == "IN"
    assert body["language"] == "EN-GB"
    assert body["safesearch"] == "strict"
    assert body["offset"] == 2
    assert body["knowledge"] == "core"
    assert body["boost_domains"] == ["ndtv.com"]
    assert body["count"] == 10
    for dropped in ("crawl_timeout", "livecrawl", "extraction"):
        assert dropped not in body
        assert dropped in caplog.text
    assert caplog.text.count("normalized parameter wins") == 2


# Search response mapping


def test_snippets_response_mapping(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(
        200, json=fixture("search.json"), headers=RATE_HEADERS
    )
    response = provider.search(SearchRequest(query="india"))
    web = fixture("search.json")["results"]["web"]
    assert response.provider is Provider.YOU
    assert response.raw == fixture("search.json")
    assert [r.url for r in response.results] == [w["url"] for w in web]
    first = response.results[0]
    assert first.title == web[0]["title"]
    assert first.snippet == web[0]["description"]
    assert first.content is None
    assert first.score is None
    assert first.published_date is None
    assert first.extras["snippets"] == web[0]["snippets"]
    assert first.extras["thumbnail_url"] == web[0]["thumbnail_url"]
    assert first.extras["favicon_url"] == web[0]["favicon_url"]
    assert response.usage.request_id == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    assert response.usage.result_count == 2


def test_news_and_metadata_go_to_response_extras(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(
        200, json=fixture("search.json"), headers=RATE_HEADERS
    )
    extras = provider.search(SearchRequest(query="q")).extras
    assert extras["news"] == fixture("search.json")["results"]["news"]
    assert extras["latency"] == 0.6842031478881836
    assert extras["X-RateLimit-Limit"] == "10"
    assert extras["X-RateLimit-Remaining"] == "9"
    assert extras["X-RateLimit-Reset"] == "1790000000"
    assert "knowledge" not in extras


def test_knowledge_goes_to_extras(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search_knowledge.json"))
    response = provider.search(SearchRequest(query="q"))
    assert response.extras["knowledge"][0]["type"] == "answer"
    assert len(response.results) == 1


def test_full_page_markdown_and_page_age(provider, respx_mock):
    body = fixture("search_full_page.json")
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    [result] = provider.search(SearchRequest(query="q", include_content=True)).results
    assert result.content == body["results"]["web"][0]["contents"]["markdown"]
    assert result.published_date == datetime(2024, 12, 18)
    assert result.extras["published_raw"] == "2024-12-18T00:00:00"


def test_free_form_page_age_kept_raw(provider, respx_mock):
    body = fixture("search.json")
    body["results"]["web"][0]["page_age"] = "3 days ago"
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    first = provider.search(SearchRequest(query="q")).results[0]
    assert first.published_date is None
    assert first.extras["published_raw"] == "3 days ago"


def test_highlights_become_the_snippet(provider, respx_mock):
    body = fixture("search_highlights.json")
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    first = provider.search(SearchRequest(query="q")).results[0]
    highlights = body["results"]["web"][0]["contents"]["highlights"]
    assert first.snippet == "\n\n".join(highlights)
    assert first.content is None


def test_snippets_used_when_description_missing(provider, respx_mock):
    body = fixture("search.json")
    del body["results"]["web"][0]["description"]
    body["results"]["web"][0]["snippets"] = ["one", "two"]
    respx_mock.post(SEARCH_URL).respond(200, json=body)
    assert provider.search(SearchRequest(query="q")).results[0].snippet == "one\n\ntwo"


def test_empty_body_is_an_empty_response(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json={})
    response = provider.search(SearchRequest(query="q"))
    assert response.results == []
    assert response.usage.request_id is None


# Search cost


def test_plain_search_cost(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search.json"))
    reported = provider.search(SearchRequest(query="q")).usage.reported
    assert reported.unit == "usd"
    assert reported.amount == pytest.approx(0.005)
    assert reported.exact is False
    assert reported.detail["calls"] == 1
    assert "extraction_source" not in reported.detail


def test_full_page_blend_reports_upper_bound(provider, respx_mock):
    # Docs full-page example: one web and one news page with markdown.
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search_full_page.json"))
    reported = provider.search(
        SearchRequest(query="q", include_content=True)
    ).usage.reported
    assert reported.amount == pytest.approx(0.005 + 2 * 0.001)
    assert reported.detail["extraction_source"] == "blend"
    assert reported.detail["pages_with_content"] == 2
    assert reported.detail["lower_bound_usd"] == pytest.approx(0.005)
    assert reported.detail["upper_bound_usd"] == pytest.approx(0.007)


@pytest.mark.parametrize("source,expected", [("cache", 0.005), ("fetch", 0.007)])
def test_full_page_cache_and_fetch(provider, respx_mock, source, expected):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search_full_page.json"))
    reported = provider.search(
        SearchRequest(
            query="q",
            include_content=True,
            provider_kwargs={"extraction_source": source},
        )
    ).usage.reported
    assert reported.amount == pytest.approx(expected)
    assert reported.detail["lower_bound_usd"] == pytest.approx(expected)
    assert reported.detail["upper_bound_usd"] == pytest.approx(expected)


def test_highlights_cost_nothing_extra(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(200, json=fixture("search_highlights.json"))
    reported = provider.search(
        SearchRequest(query="q", provider_kwargs={"highlights": True})
    ).usage.reported
    assert reported.amount == pytest.approx(0.005)


# Extract (/v1/contents)


def test_extract_payload(provider, respx_mock):
    respx_mock.post(CONTENTS_URL).respond(200, json=contents_with_markdown())
    provider.extract(ExtractRequest(urls=[WIKI], provider_kwargs={"max_age": 3600}))
    assert sent_json(respx_mock) == {
        "urls": [WIKI],
        "formats": ["markdown", "metadata"],
        "max_age": 3600,
    }


def test_extract_mapping(provider, respx_mock):
    items = contents_with_markdown()
    respx_mock.post(CONTENTS_URL).respond(200, json=items, headers=RATE_HEADERS)
    response = provider.extract(ExtractRequest(urls=[WIKI]))
    [result] = response.results
    assert result.url == WIKI
    assert result.title == "Wikipedia, the free encyclopedia"
    assert result.content == "# Wikipedia\n\nWelcome."
    assert result.extras == {
        "site_name": "Wikipedia",
        "favicon_url": "https://api.ydc-index.io/favicon?domain=en.wikipedia.org&size=128",
    }
    assert response.raw == {"results": items}
    assert response.usage.request_id is None
    assert response.extras["X-RateLimit-Remaining"] == "9"


def test_docs_contents_example_has_no_markdown_so_it_fails(provider, respx_mock):
    # The docs example asks for html only; the adapter needs markdown.
    respx_mock.post(CONTENTS_URL).respond(200, json=fixture("contents.json"))
    response = provider.extract(ExtractRequest(urls=[WIKI]))
    assert response.results == []
    assert [(f.url, f.error) for f in response.failed] == [
        (WIKI, "no content returned")
    ]


def test_null_content_and_missing_urls_fail(provider, respx_mock, caplog):
    items = contents_with_markdown() + [
        {
            "url": "https://example.com/blocked",
            "title": None,
            "markdown": None,
            "html": None,
        }
    ]
    respx_mock.post(CONTENTS_URL).respond(200, json=items)
    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        response = provider.extract(
            ExtractRequest(urls=[WIKI, "https://example.com/blocked", MISSING])
        )
    assert [r.url for r in response.results] == [WIKI]
    assert [(f.url, f.error) for f in response.failed] == [
        ("https://example.com/blocked", "no content returned"),
        (MISSING, "not returned by provider"),
    ]
    assert "partial_extract_failures=2" in caplog.text


def test_extract_cost_per_returned_page(provider, respx_mock):
    items = contents_with_markdown() + [{"url": MISSING, "markdown": None}]
    respx_mock.post(CONTENTS_URL).respond(200, json=items)
    reported = provider.extract(ExtractRequest(urls=[WIKI, MISSING])).usage.reported
    assert reported.amount == pytest.approx(0.002)
    assert reported.exact is False
    assert reported.detail["pages_billed"] == 2
    assert reported.detail["pages_with_content"] == 1


def test_extract_kwargs(respx_mock, caplog):
    respx_mock.post(CONTENTS_URL).respond(200, json=contents_with_markdown())
    with SearchClient("you", api_key=KEY) as client:
        with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
            client.extract([WIKI], crawl_timeout=30, max_age=-1, formats=["html"])
    assert sent_json(respx_mock) == {
        "urls": [WIKI],
        "formats": ["markdown", "metadata"],
        "crawl_timeout": 30,
    }
    assert "max_age" in caplog.text
    assert "normalized parameter wins" in caplog.text


# Errors


@pytest.mark.parametrize(
    "status,name,expected,message",
    [
        (401, "error_401.json", AuthenticationError, "you: Invalid or missing API key"),
        (
            402,
            "error_402.json",
            ProviderAPIError,
            "you: insufficient_credits: Your account",
        ),
        (422, "error_422.json", ProviderAPIError, "you: include_domains and exclude"),
    ],
)
def test_three_error_shapes(provider, respx_mock, status, name, expected, message):
    respx_mock.post(SEARCH_URL).respond(status, json=fixture(name))
    with pytest.raises(expected, match=message) as caught:
        provider.search(SearchRequest(query="q"))
    if isinstance(caught.value, ProviderAPIError):
        assert caught.value.status_code == status
        assert caught.value.body == fixture(name)


def test_429_with_retry_after(provider, respx_mock):
    respx_mock.post(SEARCH_URL).respond(429, json={}, headers={"Retry-After": "2"})
    with pytest.raises(RateLimitError) as caught:
        provider.search(SearchRequest(query="q"))
    assert caught.value.retry_after == 2


def test_unexpected_error_body_falls_back(provider, respx_mock):
    respx_mock.post(CONTENTS_URL).respond(500, text="boom")
    with pytest.raises(ProviderAPIError, match="you returned HTTP 500"):
        provider.extract(ExtractRequest(urls=[WIKI]))
