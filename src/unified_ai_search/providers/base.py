import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import perf_counter
from types import TracebackType
from typing import Any, ClassVar, Literal, TypeVar
from urllib.parse import urlsplit

import httpx

from ..enums import Provider
from ..errors import (
    AuthenticationError,
    MissingAPIKeyError,
    ProviderAPIError,
    ProviderTimeoutError,
    RateLimitError,
    SearchSDKError,
)
from ..logging import logger, redact
from ..models import ExtractRequest, ExtractResponse, SearchRequest, SearchResponse
from ..pricing import PricingTable

Operation = Literal["search", "extract"]
_ProviderT = TypeVar("_ProviderT", bound="HttpSearchProvider")


class Searcher(ABC):
    @abstractmethod
    def search(self, request: SearchRequest) -> SearchResponse:
        """Search using normalized input."""


class Extractor(ABC):
    @abstractmethod
    def extract(self, request: ExtractRequest) -> ExtractResponse:
        """Extract using normalized input."""


class SearchProvider(Searcher, Extractor, ABC):
    @abstractmethod
    def close(self) -> None:
        """Release owned resources."""


@dataclass(frozen=True)
class HttpResult:
    body: dict[str, Any]
    latency_s: float
    status_code: int
    headers: dict[str, Any]


class HttpSearchProvider(SearchProvider):
    PROVIDER: ClassVar[Provider]
    ENV_VAR: ClassVar[str]
    BASE_URL: ClassVar[str]
    AUTH_HEADER: ClassVar[str] = "Authorization"
    AUTH_SCHEME: ClassVar[str] = "Bearer"
    MAX_RESULTS_CAP: ClassVar[int | None] = None

    def __init__(
        self,
        api_key: str | None = None,
        timeout: float = 30.0,
        pricing: PricingTable | None = None,
    ) -> None:
        key = api_key if api_key is not None else os.getenv(self.ENV_VAR)
        if not key or not key.strip():
            raise MissingAPIKeyError(
                f"{self.PROVIDER.value}: supply api_key or set {self.ENV_VAR}"
            )
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be finite and positive")
        self._api_key = key
        self.pricing = pricing if pricing is not None else PricingTable()
        self._http = self._build_http_client(timeout)

    def _auth_headers(self) -> dict[str, str]:
        value = (
            f"{self.AUTH_SCHEME} {self._api_key}" if self.AUTH_SCHEME else self._api_key
        )
        return {self.AUTH_HEADER: value}

    def _build_http_client(self, timeout: float) -> httpx.Client:
        return httpx.Client(
            base_url=self.BASE_URL,
            headers=self._auth_headers(),
            timeout=httpx.Timeout(timeout, connect=5.0),
        )

    def _parse_error_message(self, response: httpx.Response) -> str:
        """Adapters override this for their documented error body shape."""
        return f"{self.PROVIDER.value} returned HTTP {response.status_code}"

    def _capture_headers(self, response: httpx.Response) -> dict[str, Any]:
        """Adapters opt in only to headers documented by their provider."""
        return {}

    def _retry_after(self, response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            seconds = float(value)
        except ValueError:
            try:
                deadline = parsedate_to_datetime(value)
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=timezone.utc)
                seconds = max(
                    0.0, (deadline - datetime.now(timezone.utc)).total_seconds()
                )
            except (TypeError, ValueError, OverflowError):
                return None
        return seconds if math.isfinite(seconds) and seconds >= 0 else None

    def _status_error(self, response: httpx.Response) -> SearchSDKError:
        status = response.status_code
        message = redact(self._parse_error_message(response), [self._api_key])
        if status in (401, 403):
            return AuthenticationError(message)
        if status == 429 or (self.PROVIDER == Provider.TAVILY and status in (432, 433)):
            return RateLimitError(message, retry_after=self._retry_after(response))
        try:
            body: object = response.json()
        except ValueError:
            body = response.text
        return ProviderAPIError(message, status_code=status, body=body)

    def _log_failure(
        self,
        operation: Operation,
        error: SearchSDKError,
        latency_s: float,
        status_code: int | None,
    ) -> None:
        # Only error type is logged: even a parsed message may echo a request body.
        logger.error(
            "provider=%s operation=%s error=%s",
            self.PROVIDER.value,
            operation,
            type(error).__name__,
        )
        logger.info(
            "provider=%s operation=%s status=%s latency_s=%.6f reported_cost=%s",
            self.PROVIDER.value,
            operation,
            status_code,
            latency_s,
            None,
        )

    def _request_json(
        self,
        method: str,
        endpoint: str,
        *,
        operation: Operation,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> HttpResult:
        """One HTTP call, no retries; adapters normalize the returned JSON.

        After normalization, call _log_response once with the public response.
        Composite operations may aggregate multiple HttpResults before logging.
        """
        fields = sorted(set(json or {}) | set(params or {}))
        urls = (json or {}).get("urls", [])
        logger.debug(
            "provider=%s operation=%s endpoint=%s parameter_names=%s url_count=%s",
            self.PROVIDER.value,
            operation,
            redact(urlsplit(endpoint).path, [self._api_key]),
            redact(",".join(fields), [self._api_key]),
            len(urls) if isinstance(urls, list) else 0,
        )
        start = perf_counter()
        try:
            response = self._http.request(method, endpoint, json=json, params=params)
        except httpx.TimeoutException as exc:
            error = ProviderTimeoutError(f"{self.PROVIDER.value} request timed out")
            self._log_failure(operation, error, perf_counter() - start, None)
            raise error from exc
        except httpx.HTTPError as exc:
            network_error = ProviderAPIError(f"{self.PROVIDER.value} transport failure")
            self._log_failure(operation, network_error, perf_counter() - start, None)
            raise network_error from exc
        latency = perf_counter() - start
        if not response.is_success:
            status_error = self._status_error(response)
            self._log_failure(operation, status_error, latency, response.status_code)
            raise status_error
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("expected a JSON object")
        except ValueError as exc:
            json_error = ProviderAPIError(
                f"{self.PROVIDER.value} returned invalid JSON",
                status_code=response.status_code,
                body=response.text,
            )
            self._log_failure(operation, json_error, latency, response.status_code)
            raise json_error from exc
        return HttpResult(
            body=body,
            latency_s=latency,
            status_code=response.status_code,
            headers=self._capture_headers(response),
        )

    def _log_response(
        self, response: SearchResponse | ExtractResponse, *, status_code: int = 200
    ) -> None:
        failures = len(response.failed) if isinstance(response, ExtractResponse) else 0
        logger.debug(
            "provider=%s operation=%s result_count=%s failure_count=%s",
            self.PROVIDER.value,
            response.operation,
            response.usage.result_count,
            failures,
        )
        if failures:
            logger.warning(
                "provider=%s operation=%s partial_extract_failures=%s",
                self.PROVIDER.value,
                response.operation,
                failures,
            )
        cost = response.usage.reported
        logger.info(
            "provider=%s operation=%s status=%s latency_s=%.6f reported_cost=%s",
            self.PROVIDER.value,
            response.operation,
            status_code,
            response.usage.latency_s,
            cost.amount if cost is not None else None,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self: _ProviderT) -> _ProviderT:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
