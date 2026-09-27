from datetime import date

from pydantic import Field

from .models import FrozenModel

_COLLECTED = date(2026, 9, 27)
_TAVILY = "https://docs.tavily.com/documentation/api-credits"
_YOU = "https://you.com/docs/administration/billing"
_PARALLEL = "https://docs.parallel.ai/getting-started/pricing"


class UnitPrice(FrozenModel):
    amount: float | None = Field(ge=0, allow_inf_nan=False)
    unit: str
    source_url: str
    collected_on: date
    verified: bool = False


def _rate(amount: float, unit: str, source: str) -> UnitPrice:
    return UnitPrice(
        amount=amount,
        unit=unit,
        source_url=source,
        collected_on=_COLLECTED,
        verified=True,
    )


class PricingTable(FrozenModel):
    """USD per native unit; adapters retain native amounts in cost detail.

    Sources and collection dates travel with each rate. Exa reports USD directly
    and needs no conversion rate. Parallel wire SKU mapping belongs to its adapter.
    """

    tavily_credit: UnitPrice = _rate(0.008, "credit", _TAVILY)
    you_search: UnitPrice = _rate(0.005, "request", _YOU)
    you_contents_page: UnitPrice = _rate(0.001, "page", _YOU)
    you_live_page: UnitPrice = _rate(0.001, "page", _YOU)
    parallel_search_fast: UnitPrice = _rate(0.001, "request", _PARALLEL)
    parallel_search_basic: UnitPrice = _rate(0.005, "request", _PARALLEL)
    parallel_additional_result: UnitPrice = _rate(0.001, "result", _PARALLEL)
    parallel_extract: UnitPrice = _rate(0.001, "url", _PARALLEL)
    # UNVERIFIED: stage 04 must determine the applicable Firecrawl credit price.
    firecrawl_credit: UnitPrice = UnitPrice(
        amount=None,
        unit="credit",
        source_url="https://www.firecrawl.dev/pricing",
        collected_on=_COLLECTED,
        verified=False,
    )
