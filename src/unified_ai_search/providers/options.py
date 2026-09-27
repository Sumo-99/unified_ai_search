from collections.abc import Mapping, Set
from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from ..logging import logger


class ProviderOptions(BaseModel):
    """Optional native kwargs; subclasses give every field a default."""

    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")


def filter_options(
    options_type: type[ProviderOptions],
    kwargs: Mapping[str, Any],
    *,
    normalized_names: Set[str] = frozenset(),
) -> dict[str, Any]:
    accepted: dict[str, Any] = {}
    for name, value in kwargs.items():
        if name in normalized_names:
            logger.warning(
                "Dropped provider option %s: normalized parameter wins", name
            )
            continue
        field = options_type.model_fields.get(name)
        if field is None:
            logger.warning("Dropped unknown provider option %s", name)
            continue
        try:
            accepted[name] = TypeAdapter(field.rebuild_annotation()).validate_python(
                value, strict=True
            )
        except ValidationError:
            logger.warning("Dropped mistyped provider option %s", name)
    while accepted:
        try:
            validated = options_type.model_validate(accepted, strict=True)
            return validated.model_dump(exclude_unset=True)
        except ValidationError as exc:
            invalid = {
                error["loc"][0]
                for error in exc.errors()
                if error["loc"] and error["loc"][0] in accepted
            }
            if not invalid:
                logger.warning(
                    "Dropped provider options: incompatible option combination"
                )
                return {}
            for name in invalid:
                accepted.pop(str(name))
                logger.warning("Dropped invalid provider option %s", name)
    return {}
