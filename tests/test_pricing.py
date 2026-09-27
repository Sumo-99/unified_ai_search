from datetime import date

import pytest
from pydantic import ValidationError


def test_pricing_defaults_and_provenance():
    from unified_ai_search.pricing import PricingTable

    table = PricingTable()
    assert table.tavily_credit.amount == 0.008
    assert table.you_search.amount == 0.005
    assert table.you_contents_page.amount == 0.001
    assert table.parallel_extract.amount == 0.001
    assert table.firecrawl_credit.amount is None
    assert table.firecrawl_credit.verified is False
    for name in type(table).model_fields:
        rate = getattr(table, name)
        assert rate.source_url.startswith("https://")
        assert isinstance(rate.collected_on, date)


def test_pricing_override_isolated_and_validated():
    from unified_ai_search.pricing import PricingTable, UnitPrice

    override = UnitPrice(
        amount=0.004,
        unit="credit",
        source_url="https://example.com/rate",
        collected_on=date(2026, 9, 27),
        verified=True,
    )
    custom = PricingTable(tavily_credit=override)
    assert custom.tavily_credit.amount == 0.004
    assert PricingTable().tavily_credit.amount == 0.008
    with pytest.raises(ValidationError):
        UnitPrice(
            amount=-1,
            unit="credit",
            source_url="https://example.com/rate",
            collected_on=date(2026, 9, 27),
        )
