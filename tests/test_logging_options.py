import logging
from typing import Literal

import pytest
from pydantic import Field


def test_logger_and_redaction():
    from unified_ai_search.logging import logger, redact

    assert logger.name == "unified_ai_search"
    assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)
    assert (
        redact("token abc and abcdef", ["abc", "abcdef", ""])
        == "token [REDACTED] and [REDACTED]"
    )


def test_options_keep_valid_fields_drop_bad_ones(caplog):
    from unified_ai_search.providers.options import ProviderOptions, filter_options

    class Options(ProviderOptions):
        depth: Literal["basic", "advanced"] = "basic"
        count: int = Field(default=1, ge=1)
        enabled: bool = False
        domains: list[str] = Field(default_factory=list)

    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        result = filter_options(
            Options,
            {
                "depth": "advanced",
                "count": "3",
                "enabled": 1,
                "domains": ["example.com"],
                "unknown": "SECRET",
            },
        )
    assert result == {"depth": "advanced", "domains": ["example.com"]}
    assert len(caplog.records) == 3
    assert "SECRET" not in caplog.text
    assert filter_options(Options, {"count": 0}) == {}
    assert filter_options(Options, {"depth": "wrong"}) == {}
    assert filter_options(Options, {"count": True}) == {}
    assert filter_options(Options, {}) == {}


def test_normalized_parameter_wins(caplog):
    from unified_ai_search.providers.options import ProviderOptions, filter_options

    class Options(ProviderOptions):
        count: int = 1

    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        assert filter_options(Options, {"count": 99}, normalized_names={"count"}) == {}
    assert "count" in caplog.text


def test_options_are_frozen():
    from pydantic import ValidationError

    from unified_ai_search.providers.options import ProviderOptions

    class Options(ProviderOptions):
        enabled: bool = False

    with pytest.raises(ValidationError):
        Options().enabled = True


def test_options_honor_custom_validators():
    from pydantic import field_validator

    from unified_ai_search.providers.options import ProviderOptions, filter_options

    class Options(ProviderOptions):
        count: int = 1
        enabled: bool = False

        @field_validator("count")
        @classmethod
        def positive(cls, value):
            if value < 1:
                raise ValueError("must be positive")
            return value

    assert filter_options(Options, {"count": -1, "enabled": True}) == {"enabled": True}


def test_options_honor_model_validators(caplog):
    from pydantic import model_validator

    from unified_ai_search.providers.options import ProviderOptions, filter_options

    class Options(ProviderOptions):
        lower: int = 0
        upper: int = 10

        @model_validator(mode="after")
        def ordered(self):
            if self.lower > self.upper:
                raise ValueError("invalid range")
            return self

    with caplog.at_level(logging.WARNING, logger="unified_ai_search"):
        assert filter_options(Options, {"lower": 20, "upper": 10}) == {}
    assert "Dropped" in caplog.text
