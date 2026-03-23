"""News event models collected via GDELT API."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MediaBias(str, Enum):
    """Approximate geopolitical perspective of the news source."""

    WESTERN = "western"
    EASTERN = "eastern"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class NewsArticle(BaseModel):
    """A single news article from GDELT."""

    title: str = Field(description="Article headline")
    url: str = Field(description="Source URL")
    source_domain: str = Field(description="Publishing domain, e.g. 'reuters.com'")
    published_at: datetime = Field(description="Article publication timestamp")
    language: str = Field(description="ISO 639-1 language code, e.g. 'en'")
    # Perspective tag applied during collection to ensure balanced East/West coverage
    media_bias: MediaBias = Field(
        default=MediaBias.UNKNOWN,
        description="Approximate geopolitical perspective of the source",
    )


class NewsSnapshot(BaseModel):
    """A batch of news articles fetched from GDELT for a given query and time window."""

    fetched_at: datetime = Field(description="UTC timestamp when snapshot was taken")
    query: str = Field(description="Search query used to fetch articles")
    articles: list[NewsArticle] = Field(description="List of fetched articles")
    western_count: int = Field(
        description="Number of articles from western-perspective sources"
    )
    eastern_count: int = Field(
        description="Number of articles from eastern-perspective sources"
    )
