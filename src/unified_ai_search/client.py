from types import TracebackType
from typing import Any

from .enums import Provider
from .errors import UnsupportedOperationError
from .logging import logger
from .models import ExtractRequest, ExtractResponse, SearchRequest, SearchResponse
from .pricing import PricingTable
from .providers.base import Extractor, HttpSearchProvider
from .providers.options import filter_options
from .registry import PROVIDER_REGISTRY


class SearchClient:
    """Public facade: builds one provider strategy and applies request rules."""

    def __init__(
        self,
        provider: Provider | str,
        api_key: str | None = None,
        timeout: float = 30.0,
        pricing: PricingTable | None = None,
    ) -> None:
        self.provider = _coerce_provider(provider)
        strategy_type = PROVIDER_REGISTRY.get(self.provider)
        if strategy_type is None:
            raise ValueError(f"{self.provider.value}: no registered adapter")
        self._strategy: HttpSearchProvider = strategy_type(
            api_key=api_key, timeout=timeout, pricing=pricing
        )

    def search(
        self,
        query: str,
        *,
        max_results: int = 10,
        include_domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        include_content: bool = False,
        **provider_kwargs: Any,
    ) -> SearchResponse:
        request = SearchRequest(
            query=query,
            max_results=max_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            include_content=include_content,
        )
        strategy = self._strategy
        updates: dict[str, Any] = {
            "provider_kwargs": filter_options(
                strategy.SEARCH_OPTIONS,
                provider_kwargs,
                normalized_names=strategy.SEARCH_NORMALIZED_NAMES,
            )
        }
        cap = strategy.MAX_RESULTS_CAP
        if cap is not None and request.max_results > cap:
            logger.warning(
                "provider=%s clamped max_results from %s to %s",
                self.provider.value,
                request.max_results,
                cap,
            )
            updates["max_results"] = cap
        return strategy.search(request.model_copy(update=updates))

    def extract(self, urls: list[str], **provider_kwargs: Any) -> ExtractResponse:
        strategy = self._strategy
        if not isinstance(strategy, Extractor):
            raise UnsupportedOperationError(
                f"{self.provider.value} does not support extract"
            )
        request = ExtractRequest(urls=urls)
        filtered = filter_options(
            strategy.EXTRACT_OPTIONS,
            provider_kwargs,
            normalized_names=strategy.EXTRACT_NORMALIZED_NAMES,
        )
        return strategy.extract(
            request.model_copy(update={"provider_kwargs": filtered})
        )

    def close(self) -> None:
        self._strategy.close()

    def __enter__(self) -> "SearchClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _coerce_provider(value: Provider | str) -> Provider:
    try:
        return Provider(value)
    except ValueError:
        valid = ", ".join(member.value for member in Provider)
        raise ValueError(
            f"Unknown provider {value!r}; expected one of: {valid}"
        ) from None
