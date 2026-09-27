import logging
from collections.abc import Iterable

logger = logging.getLogger("unified_ai_search")
logger.addHandler(logging.NullHandler())


def redact(text: str, secrets: Iterable[str]) -> str:
    for secret in sorted(set(secrets) - {""}, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    return text
