from .enums import Provider
from .providers.base import SearchProvider

PROVIDER_REGISTRY: dict[Provider, type[SearchProvider]] = {}
