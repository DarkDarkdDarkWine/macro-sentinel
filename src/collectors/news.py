"""GDELT news collector.

Fetches recent global news articles via the GDELT DOC 2.0 API.
Applies East/West media bias tagging to support balanced perspective analysis.
All HTTP calls to GDELT are isolated here — no requests imports elsewhere for news.
"""

import logging
import time
from datetime import datetime, timezone

import requests

from src.models.news import MediaBias, NewsArticle, NewsSnapshot

logger = logging.getLogger(__name__)

# Timeout for GDELT API requests in seconds
REQUEST_TIMEOUT: int = 30

# Retry settings for 429 Too Many Requests
MAX_RETRIES: int = 3
RETRY_BACKOFF_SECONDS: float = 5.0  # wait time doubles each retry

GDELT_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Primary timespan: return only articles from the last 24 hours.
# GDELT's default searches its entire multi-year archive sorted by relevance,
# which causes stale articles to surface ahead of breaking news.
GDELT_TIMESPAN: str = "1d"

# Fallback timespan used when the primary window returns zero articles
# (e.g., low news volume, weekend, or API indexing lag).
GDELT_FALLBACK_TIMESPAN: str = "7d"

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

    def _get_with_retry(self, url: str, params: dict) -> requests.Response:
        """GET with exponential backoff on HTTP 429.

        Args:
            url: Target URL.
            params: Query parameters.

        Returns:
            Successful Response object.

        Raises:
            requests.exceptions.HTTPError: After MAX_RETRIES exhausted on 429,
                or immediately on any other HTTP error.
        """
        wait = RETRY_BACKOFF_SECONDS
        for attempt in range(MAX_RETRIES + 1):
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            try:
                response.raise_for_status()
                return response
            except requests.exceptions.HTTPError as exc:
                # Only retry on 429; surface all other errors immediately
                if response.status_code != 429 or attempt == MAX_RETRIES:
                    raise
                logger.warning(
                    "GDELT returned 429, retrying in %.0fs (attempt %d/%d)",
                    wait, attempt + 1, MAX_RETRIES,
                )
                time.sleep(wait)
                wait *= 2  # exponential backoff

        # Unreachable, but satisfies type checker
        raise RuntimeError("Retry loop exited unexpectedly")

    def _fetch_raw_articles(self, query: str, max_records: int, timespan: str) -> list[dict]:
        """Fetch raw article dicts from GDELT for the given timespan.

        Args:
            query: Free-text search query.
            max_records: Maximum number of results to request.
            timespan: GDELT timespan string, e.g. '1d' or '7d'.

        Returns:
            List of raw article dicts; empty list on parse failure or no results.

        Raises:
            requests.exceptions.HTTPError: On non-429 HTTP errors after retries exhausted.
        """
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": max_records,
            "format": "json",
            "sort": "DateDesc",
            "timespan": timespan,
        }

        response = self._get_with_retry(GDELT_API_URL, params=params)

        # GDELT occasionally returns HTTP 200 with an empty body when no articles
        # match the query or the service is under load.
        try:
            return response.json().get("articles", [])
        except ValueError:
            # Log first 200 chars of body to aid future diagnosis of the root cause.
            body_preview = response.text[:200] if response.text else "<empty>"
            logger.warning(
                "GDELT returned non-JSON body for query '%s' timespan=%s: %s",
                query, timespan, body_preview,
            )
            return []

    def collect(self, query: str, max_records: int = 50) -> NewsSnapshot:
        """Fetch news articles matching the query from GDELT DOC 2.0 API.

        Tries the primary timespan (GDELT_TIMESPAN) first. If zero articles are
        returned — which happens when there is a low news volume or indexing lag —
        retries with the fallback timespan (GDELT_FALLBACK_TIMESPAN) before giving up.

        Args:
            query: Free-text search query, e.g. 'geopolitical risk trade war'.
            max_records: Maximum number of articles to return (default 50).

        Returns:
            NewsSnapshot with articles tagged by media perspective.

        Raises:
            requests.exceptions.HTTPError: If the GDELT API returns an HTTP error.
        """
        logger.info("Fetching GDELT news for query: '%s'", query)

        raw_articles = self._fetch_raw_articles(query, max_records, GDELT_TIMESPAN)

        if not raw_articles:
            logger.warning(
                "No articles from GDELT with timespan=%s, retrying with timespan=%s",
                GDELT_TIMESPAN, GDELT_FALLBACK_TIMESPAN,
            )
            raw_articles = self._fetch_raw_articles(query, max_records, GDELT_FALLBACK_TIMESPAN)

        articles: list[NewsArticle] = []
        for item in raw_articles:
            # Skip articles with missing or malformed date — one bad record must not
            # abort the entire batch; log and continue instead of raising.
            raw_date = item.get("seendate", "")
            if not raw_date:
                logger.warning("Skipping article with missing seendate: %s", item.get("url"))
                continue
            try:
                published_at = _parse_gdelt_date(raw_date)
            except ValueError:
                logger.warning(
                    "Skipping article with unparseable seendate '%s': %s",
                    raw_date, item.get("url"),
                )
                continue

            domain = item.get("domain", "")
            articles.append(
                NewsArticle(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    source_domain=domain,
                    published_at=published_at,
                    language=item.get("language", "unknown"),
                    media_bias=_classify_bias(domain),
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
