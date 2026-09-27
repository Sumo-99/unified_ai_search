import pytest
from pydantic import ValidationError


def test_search_request_defaults_and_preservation():
    from unified_ai_search.models import SearchRequest

    request = SearchRequest(query="  original query  ")
    assert request.query == "  original query  "
    assert request.max_results == 10
    assert request.include_content is False
    assert request.include_domains is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"query": ""},
        {"query": " \n "},
        {"query": "q", "max_results": 0},
        {
            "query": "q",
            "include_domains": ["example.com"],
            "exclude_domains": ["EXAMPLE.COM"],
        },
    ],
)
def test_search_validation_translates_pydantic(kwargs):
    from unified_ai_search.errors import InvalidRequestError
    from unified_ai_search.models import SearchRequest

    with pytest.raises(InvalidRequestError) as caught:
        SearchRequest(**kwargs)
    assert isinstance(caught.value.__cause__, ValidationError)


@pytest.mark.parametrize(
    "urls", [[], [""], ["bad"], ["ftp://example.com"], ["https://"]]
)
def test_extract_requires_http_urls(urls):
    from unified_ai_search.errors import InvalidRequestError
    from unified_ai_search.models import ExtractRequest

    with pytest.raises(InvalidRequestError) as caught:
        ExtractRequest(urls=urls)
    assert isinstance(caught.value.__cause__, ValidationError)


def test_extract_preserves_urls():
    from unified_ai_search.models import ExtractRequest

    urls = ["https://example.com", "http://example.org/a?q=1"]
    assert ExtractRequest(urls=urls).urls == urls


def test_response_schema_and_frozen_models():
    from unified_ai_search.enums import Provider
    from unified_ai_search.models import (
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

    cost = ReportedCost(amount=0.008, exact=False, detail={"credits": 1})
    usage = Usage(latency_s=0.1, result_count=1, reported=cost)
    result = SearchResult(title="Title", url="https://example.com")
    raw = {"items": [{"title": "Title"}]}
    search = SearchResponse(
        provider=Provider.EXA, query="q", results=[result], usage=usage, raw=raw
    )
    extract_result = ExtractResult(url="https://example.com", content="text")
    failed = FailedExtraction(url="https://bad.example", error="not found")
    extract = ExtractResponse(
        provider=Provider.EXA, results=[extract_result], failed=[failed], usage=usage
    )
    assert search.operation == "search"
    assert extract.operation == "extract"
    assert search.raw == raw
    assert cost.unit == "usd"
    assert usage.request_id is None
    assert (
        result.snippet
        is result.content
        is result.score
        is result.published_date
        is None
    )
    assert extract_result.title is None
    models = [
        cost,
        usage,
        result,
        search,
        extract_result,
        failed,
        extract,
        SearchRequest(query="q"),
        ExtractRequest(urls=["https://example.com"]),
    ]
    for model in models:
        field = next(iter(type(model).model_fields))
        with pytest.raises(ValidationError, match="frozen_instance"):
            setattr(model, field, getattr(model, field))
    with pytest.raises(ValidationError):
        SearchResponse(provider=Provider.EXA, query="q", results=[])
    other = SearchResult(title="other", url="https://example.org")
    result.extras["local"] = True
    assert other.extras == {}


@pytest.mark.parametrize(
    "kwargs",
    [{"latency_s": -1, "result_count": 0}, {"latency_s": 0, "result_count": -1}],
)
def test_usage_rejects_negative_measurements(kwargs):
    from unified_ai_search.models import Usage

    with pytest.raises(ValidationError):
        Usage(**kwargs)
