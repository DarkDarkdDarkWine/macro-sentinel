"""Tests for the RSS news collector."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.collectors.news import NewsCollector, RSS_FEEDS
from src.models.news import MediaBias, NewsSnapshot


def _make_entry(title: str, link: str, published_parsed=None) -> SimpleNamespace:
    """Build a minimal feedparser entry namespace."""
    if published_parsed is None:
        # Default: 2024-03-15 12:00 UTC as time.struct_time tuple
        published_parsed = (2024, 3, 15, 12, 0, 0, 4, 75, 0)
    return SimpleNamespace(
        title=title,
        link=link,
        published_parsed=published_parsed,
        get=lambda key, default=None: getattr(
            SimpleNamespace(title=title, link=link), key, default
        ),
    )


def _make_feed(entries: list, bozo: bool = False) -> SimpleNamespace:
    """Build a minimal feedparser feed namespace."""
    return SimpleNamespace(entries=entries, bozo=bozo, bozo_exception=None)


@patch("src.collectors.news.feedparser.parse")
def test_collect_returns_news_snapshot(mock_parse: MagicMock) -> None:
    """collect() should return a NewsSnapshot aggregating entries from all RSS feeds."""
    mock_parse.return_value = _make_feed([
        _make_entry("Global tensions rise", "https://bbc.co.uk/1"),
    ])

    snapshot = NewsCollector().collect("test query")

    assert isinstance(snapshot, NewsSnapshot)
    assert snapshot.query == "test query"
    assert isinstance(snapshot.fetched_at, datetime)
    assert len(snapshot.articles) > 0


@patch("src.collectors.news.feedparser.parse")
def test_collect_assigns_media_bias_from_feed_definition(mock_parse: MagicMock) -> None:
    """collect() should assign MediaBias from each feed's defined perspective, not domain lookup."""
    # Return one entry per feed call; the bias comes from the feed definition in RSS_FEEDS
    mock_parse.return_value = _make_feed([
        _make_entry("Article", "https://example.com/1"),
    ])

    snapshot = NewsCollector().collect("test")

    # All entries should have a known bias (not UNKNOWN) since feeds define it
    for article in snapshot.articles:
        assert article.media_bias != MediaBias.UNKNOWN


@patch("src.collectors.news.feedparser.parse")
def test_collect_counts_east_west_correctly(mock_parse: MagicMock) -> None:
    """collect() western_count and eastern_count must match article bias tags."""
    mock_parse.return_value = _make_feed([
        _make_entry("Article", "https://example.com/1"),
    ])

    snapshot = NewsCollector().collect("test")

    computed_western = sum(1 for a in snapshot.articles if a.media_bias == MediaBias.WESTERN)
    computed_eastern = sum(1 for a in snapshot.articles if a.media_bias == MediaBias.EASTERN)
    assert snapshot.western_count == computed_western
    assert snapshot.eastern_count == computed_eastern


@patch("src.collectors.news.feedparser.parse")
def test_collect_skips_entries_without_published_date(mock_parse: MagicMock) -> None:
    """collect() should skip feed entries that have no parseable published date."""
    good = _make_entry("Has date", "https://bbc.co.uk/1")
    bad = SimpleNamespace(
        title="No date",
        link="https://bbc.co.uk/2",
        published_parsed=None,
        get=lambda k, d=None: d,
    )
    mock_parse.return_value = _make_feed([good, bad])

    snapshot = NewsCollector().collect("test")

    titles = [a.title for a in snapshot.articles]
    assert "No date" not in titles
    # Should not crash; good articles still collected from other feeds too
    assert any(a.title == "Has date" for a in snapshot.articles)


@patch("src.collectors.news.feedparser.parse")
def test_collect_continues_when_one_feed_raises(mock_parse: MagicMock) -> None:
    """collect() should not abort if one feed raises an exception; others still collected."""
    call_count = 0

    def side_effect(url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("feed unreachable")
        return _make_feed([_make_entry("Article from other feed", "https://example.com/1")])

    mock_parse.side_effect = side_effect

    snapshot = NewsCollector().collect("test")

    # Should still have articles from the remaining feeds
    assert isinstance(snapshot, NewsSnapshot)
    assert len(snapshot.articles) > 0


@patch("src.collectors.news.feedparser.parse")
def test_collect_respects_max_records(mock_parse: MagicMock) -> None:
    """collect() should return at most max_records articles."""
    mock_parse.return_value = _make_feed([
        _make_entry(f"Article {i}", f"https://bbc.co.uk/{i}")
        for i in range(20)
    ])

    snapshot = NewsCollector().collect("test", max_records=5)

    assert len(snapshot.articles) <= 5


@patch("src.collectors.news.feedparser.parse")
def test_collect_deduplicates_by_url(mock_parse: MagicMock) -> None:
    """collect() should not return duplicate articles (same URL from multiple feeds)."""
    same_url = "https://example.com/shared-article"
    mock_parse.return_value = _make_feed([
        _make_entry("Duplicate article", same_url),
    ])

    snapshot = NewsCollector().collect("test")

    urls = [a.url for a in snapshot.articles]
    assert len(urls) == len(set(urls))


def test_rss_feeds_constant_has_required_bias_coverage() -> None:
    """RSS_FEEDS must include both WESTERN and EASTERN sources for balanced coverage."""
    biases = {bias for _, bias, _ in RSS_FEEDS}
    assert MediaBias.WESTERN in biases
    assert MediaBias.EASTERN in biases
