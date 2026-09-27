import pytest


def test_provider_values():
    from unified_ai_search.enums import Provider

    assert {p.value for p in Provider} == {
        "you",
        "exa",
        "parallel",
        "tavily",
        "firecrawl",
    }
    assert Provider("exa") is Provider.EXA
    assert isinstance(Provider.EXA, str)
    with pytest.raises(ValueError):
        Provider("unknown")


def test_error_tree_and_attributes():
    from unified_ai_search import errors

    for name in (
        "MissingAPIKeyError",
        "InvalidRequestError",
        "AuthenticationError",
        "RateLimitError",
        "ProviderAPIError",
        "ProviderTimeoutError",
        "UnsupportedOperationError",
    ):
        assert issubclass(getattr(errors, name), errors.SearchSDKError)
    assert errors.RateLimitError("limited").retry_after is None
    assert errors.RateLimitError("limited", retry_after=2.5).retry_after == 2.5
    error = errors.ProviderAPIError("bad", status_code=500, body={"error": "bad"})
    assert error.status_code == 500
    assert error.body == {"error": "bad"}
    assert errors.ProviderAPIError("network").status_code is None
