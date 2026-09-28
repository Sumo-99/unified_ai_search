"""Unified AI search SDK."""

from .client import SearchClient
from .enums import Provider
from .errors import (
    AuthenticationError,
    InvalidRequestError,
    MissingAPIKeyError,
    ProviderAPIError,
    ProviderTimeoutError,
    RateLimitError,
    SearchSDKError,
    UnsupportedOperationError,
)
from .models import (
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
from .pricing import PricingTable, UnitPrice

__version__ = "0.1.0"

__all__ = [
    "AuthenticationError",
    "ExtractRequest",
    "ExtractResponse",
    "ExtractResult",
    "FailedExtraction",
    "InvalidRequestError",
    "MissingAPIKeyError",
    "PricingTable",
    "Provider",
    "ProviderAPIError",
    "ProviderTimeoutError",
    "RateLimitError",
    "ReportedCost",
    "SearchClient",
    "SearchRequest",
    "SearchResponse",
    "SearchResult",
    "SearchSDKError",
    "UnitPrice",
    "UnsupportedOperationError",
    "Usage",
    "__version__",
]
