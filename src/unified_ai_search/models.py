from datetime import datetime
from typing import Any, Literal, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    ModelWrapValidatorHandler,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)

from .enums import Provider
from .errors import InvalidRequestError

_RequestT = TypeVar("_RequestT", bound="RequestModel")
_URL = TypeAdapter(HttpUrl)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class RequestModel(FrozenModel):
    @model_validator(mode="wrap")
    @classmethod
    def translate_validation(
        cls: type[_RequestT], data: Any, handler: ModelWrapValidatorHandler[_RequestT]
    ) -> _RequestT:
        try:
            return handler(data)
        except ValidationError as exc:
            # Pydantic errors include user inputs; keep the public message safe.
            raise InvalidRequestError(f"Invalid {cls.__name__}") from exc


class SearchRequest(RequestModel):
    query: str
    max_results: int = Field(default=10, ge=1)
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    include_content: bool = False
    provider_kwargs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query must not be empty")
        return value

    @field_validator("exclude_domains")
    @classmethod
    def disjoint_domains(
        cls, values: list[str] | None, info: ValidationInfo
    ) -> list[str] | None:
        included = {
            domain.strip().lower() for domain in info.data.get("include_domains") or []
        }
        excluded = {domain.strip().lower() for domain in values or []}
        if included & excluded:
            raise ValueError("include_domains and exclude_domains overlap")
        return values


class ExtractRequest(RequestModel):
    urls: list[str] = Field(min_length=1)
    provider_kwargs: dict[str, Any] = Field(default_factory=dict)

    @field_validator("urls")
    @classmethod
    def valid_urls(cls, values: list[str]) -> list[str]:
        for value in values:
            _URL.validate_python(value)
        return values


class ReportedCost(FrozenModel):
    unit: Literal["usd"] = "usd"
    amount: float = Field(ge=0, allow_inf_nan=False)
    exact: bool
    detail: dict[str, Any] = Field(default_factory=dict)


class Usage(FrozenModel):
    request_id: str | None = None
    latency_s: float = Field(ge=0, allow_inf_nan=False)
    result_count: int = Field(ge=0)
    reported: ReportedCost | None = None


class SearchResult(FrozenModel):
    title: str
    url: str
    snippet: str | None = None
    content: str | None = None
    score: float | None = None
    published_date: datetime | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class ExtractResult(FrozenModel):
    url: str
    title: str | None = None
    content: str
    extras: dict[str, Any] = Field(default_factory=dict)


class FailedExtraction(FrozenModel):
    url: str
    error: str


class SearchResponse(FrozenModel):
    provider: Provider
    operation: Literal["search"] = "search"
    query: str
    results: list[SearchResult] = Field(default_factory=list)
    usage: Usage
    extras: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class ExtractResponse(FrozenModel):
    provider: Provider
    operation: Literal["extract"] = "extract"
    results: list[ExtractResult] = Field(default_factory=list)
    failed: list[FailedExtraction] = Field(default_factory=list)
    usage: Usage
    extras: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
