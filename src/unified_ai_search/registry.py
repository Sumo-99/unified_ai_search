from .enums import Provider
from .providers.base import HttpSearchProvider
from .providers.exa import ExaProvider
from .providers.tavily import TavilyProvider

# Typed to the HTTP base: the client constructs strategies with its signature.
PROVIDER_REGISTRY: dict[Provider, type[HttpSearchProvider]] = {
    Provider.TAVILY: TavilyProvider,
    Provider.EXA: ExaProvider,
}
