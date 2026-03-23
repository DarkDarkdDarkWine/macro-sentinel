"""GDELT news collector.

Fetches recent global news articles via the GDELT DOC 2.0 API.
Applies East/West media bias tagging to support balanced perspective analysis.
All HTTP calls to GDELT are isolated here — no requests imports elsewhere for news.
"""

import logging
from datetime import datetime, timezone

import requests

from src.models.news import MediaBias, NewsArticle, NewsSnapshot

logger = logging.getLogger(__name__)

# Timeout for GDELT API requests in seconds
REQUEST_TIMEOUT: int = 30

GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Domains associated with a predominantly western editorial perspective.
# This list is intentionally not exhaustive — unknown domains default to UNKNOWN.
WESTERN_DOMAINS: frozenset[str] = frozenset({
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "theguardian.com",
    "nytimes.com",
    "washingtonpost.com",
    "ft.com",
    "bloomberg.com",
    "wsj.com",
    "cnn.com",
    "nbcnews.com",
    "abcnews.go.com",
    "politico.com",
    "foreignpolicy.com",
})

# Domains associated with a predominantly eastern editorial perspective.
EASTERN_DOMAINS: frozenset[str] = frozenset({
    "xinhuanet.com",
    "cgtn.com",
    "chinadaily.com.cn",
    "globaltimes.cn",
    "people.com.cn",
    "scmp.com",
    "nhk.or.jp",
    "rt.com",
    "tass.com",
    "aljazeera.com",
    "presstv.ir",
})


def _classify_bias(domain: str) -> MediaBias:
    """Classify the editorial perspective of a news domain.

    Args:
        domain: Publishing domain, e.g. 'reuters.com'.

    Returns:
        MediaBias enum value based on known domain lists.
    """
    if domain in WESTERN_DOMAINS:
        return MediaBias.WESTERN
    if domain in EASTERN_DOMAINS:
        return MediaBias.EASTERN
    return MediaBias.UNKNOWN


def _parse_gdelt_date(raw: str) -> datetime:
    """Parse GDELT's date format '20240315T120000Z' into a datetime.

    Args:
        raw: GDELT date string.

    Returns:
        UTC-aware datetime object.
    """
    # GDELT uses compact ISO 8601: YYYYMMDDTHHmmssZ
    return datetime.strptime(raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


class NewsCollector:
    """Collects global news articles from GDELT with East/West perspective tagging."""

    def collect(self, query: str, max_records: int = 50) -> NewsSnapshot:
        """Fetch news articles matching the query from GDELT DOC 2.0 API.

        Both western and eastern sources are fetched in a single request;
        bias tagging is applied post-fetch to ensure balanced coverage.

        Args:
            query: Free-text search query, e.g. 'geopolitical risk trade war'.
            max_records: Maximum number of articles to return (default 50).

        Returns:
            NewsSnapshot with articles tagged by media perspective.

        Raises:
            Exception: If the GDELT API returns an HTTP error.
        """
        logger.info("Fetching GDELT news for query: '%s'", query)

        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": max_records,
            "format": "json",
        }

        response = requests.get(GDELT_API_URL, params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        raw_articles: list[dict] = response.json().get("articles", [])

        articles: list[NewsArticle] = []
        for item in raw_articles:
            domain = item.get("domain", "")
            bias = _classify_bias(domain)
            articles.append(
                NewsArticle(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    source_domain=domain,
                    published_at=_parse_gdelt_date(item["seendate"]),
                    language=item.get("language", "unknown"),
                    media_bias=bias,
                )
            )

        western_count = sum(1 for a in articles if a.media_bias == MediaBias.WESTERN)
        eastern_count = sum(1 for a in articles if a.media_bias == MediaBias.EASTERN)

        logger.info(
            "Fetched %d articles (western=%d, eastern=%d)",
            len(articles), western_count, eastern_count,
        )

        return NewsSnapshot(
            fetched_at=datetime.now(timezone.utc),
            query=query,
            articles=articles,
            western_count=western_count,
            eastern_count=eastern_count,
        )
