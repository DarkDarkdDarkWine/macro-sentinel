"""RSS news collector.

Fetches recent global news articles from curated RSS feeds.
Applies East/West media bias tagging based on each feed's editorial perspective.
All HTTP calls are handled by feedparser — no requests imports here.
"""

import logging
from datetime import datetime, timezone, timedelta
from time import mktime

import feedparser

from src.models.news import MediaBias, NewsArticle, NewsSnapshot

logger = logging.getLogger(__name__)

# Timeout in seconds for each RSS feed fetch.
REQUEST_TIMEOUT: int = 15

# Tuples of (feed_url, media_bias, source_domain).
# Edit this list to add/remove sources; the collector logic does not change.
RSS_FEEDS: list[tuple[str, MediaBias, str]] = [
    # Western / neutral wire services
    ("https://feeds.bbci.co.uk/news/world/rss.xml",           MediaBias.WESTERN, "bbc.co.uk"),
    ("https://feeds.bbci.co.uk/news/business/rss.xml",        MediaBias.WESTERN, "bbc.co.uk"),
    ("https://apnews.com/world-news.rss",                      MediaBias.WESTERN, "apnews.com"),
    ("https://www.cnbc.com/id/20910258/device/rss/rss.html",  MediaBias.WESTERN, "cnbc.com"),
    ("https://www.aljazeera.com/xml/rss/all.xml",              MediaBias.NEUTRAL, "aljazeera.com"),
    # Eastern / Asia-Pacific sources
    ("https://www.scmp.com/rss/3/feed",                        MediaBias.EASTERN, "scmp.com"),
    ("http://www.xinhuanet.com/english/rss_eng.htm",           MediaBias.EASTERN, "xinhuanet.com"),
    ("https://www3.nhk.or.jp/nhkworld/data/en/news/backstory/rss.xml",
                                                               MediaBias.EASTERN, "nhk.or.jp"),
    # High-signal official sources (low volume, authoritative)
    ("https://www.federalreserve.gov/feeds/press_all.xml",     MediaBias.NEUTRAL, "federalreserve.gov"),
]

# Include articles published within this window; older ones are discarded.
RECENCY_HOURS: int = 24


class NewsCollector:
    """Collects global news articles from curated RSS feeds with East/West perspective tagging."""

    def _fetch_feed(self, url: str, bias: MediaBias, domain: str) -> list[NewsArticle]:
        """Fetch and parse one RSS feed, returning a list of NewsArticle objects.

        Args:
            url: RSS feed URL.
            bias: Editorial perspective to tag every article from this feed.
            domain: Canonical source domain to assign (overrides per-entry domain).

        Returns:
            List of parsed NewsArticle objects; empty list on any error.
        """
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "macro-sentinel/0.1"})
        except Exception as exc:
            logger.warning("Failed to fetch RSS feed %s: %s", url, exc)
            return []

        articles: list[NewsArticle] = []
        for entry in feed.entries:
            published_parsed = getattr(entry, "published_parsed", None)
            if published_parsed is None:
                logger.debug("Skipping entry without published date: %s", getattr(entry, "link", ""))
                continue

            try:
                published_at = datetime.fromtimestamp(mktime(published_parsed), tz=timezone.utc)
            except (OverflowError, OSError, ValueError) as exc:
                logger.debug("Skipping entry with unparseable date: %s", exc)
                continue

            articles.append(NewsArticle(
                title=getattr(entry, "title", ""),
                url=getattr(entry, "link", ""),
                source_domain=domain,
                published_at=published_at,
                language="en",
                media_bias=bias,
            ))

        return articles

    def collect(self, query: str = "", max_records: int = 50) -> NewsSnapshot:
        """Fetch articles from all configured RSS feeds.

        Fetches all feeds, deduplicates by URL, sorts by publication date
        (newest first), and returns the top max_records articles.

        Args:
            query: Label stored in the snapshot for display/logging purposes.
                   Not used for filtering — feed selection provides that signal.
            max_records: Maximum number of articles to return (default 50).

        Returns:
            NewsSnapshot with articles tagged by media perspective.
        """
        logger.info("Collecting RSS news from %d feeds", len(RSS_FEEDS))

        all_articles: list[NewsArticle] = []
        seen_urls: set[str] = set()

        for url, bias, domain in RSS_FEEDS:
            for article in self._fetch_feed(url, bias, domain):
                if article.url and article.url not in seen_urls:
                    seen_urls.add(article.url)
                    all_articles.append(article)

        # Sort newest-first
        all_articles.sort(key=lambda a: a.published_at, reverse=True)

        # Filter to recency window; fall back to all articles if window is empty
        cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENCY_HOURS)
        recent = [a for a in all_articles if a.published_at >= cutoff]
        if not recent:
            logger.warning(
                "No articles within %dh window — returning all %d collected",
                RECENCY_HOURS, len(all_articles),
            )
            recent = all_articles

        articles = recent[:max_records]

        western_count = sum(1 for a in articles if a.media_bias == MediaBias.WESTERN)
        eastern_count = sum(1 for a in articles if a.media_bias == MediaBias.EASTERN)

        logger.info(
            "Collected %d articles (western=%d, eastern=%d)",
            len(articles), western_count, eastern_count,
        )

        return NewsSnapshot(
            fetched_at=datetime.now(timezone.utc),
            query=query,
            articles=articles,
            western_count=western_count,
            eastern_count=eastern_count,
        )
