from enum import Enum


class Provider(str, Enum):
    YOU = "you"
    EXA = "exa"
    PARALLEL = "parallel"
    TAVILY = "tavily"
    FIRECRAWL = "firecrawl"
