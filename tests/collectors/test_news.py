"""Tests for the GDELT news collector."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.collectors.news import NewsCollector, EASTERN_DOMAINS, WESTERN_DOMAINS
from src.models.news import MediaBias, NewsSnapshot


MOCK_GDELT_RESPONSE = {
    "articles": [
        {
            "title": "Global tensions rise",
            "url": "https://reuters.com/article/1",
            "domain": "reuters.com",
            "seendate": "20240315T120000Z",
            "language": "English",
        },
        {
            "title": "经济形势分析",
            "url": "https://xinhuanet.com/article/2",
            "domain": "xinhuanet.com",
            "seendate": "20240315T130000Z",
            "language": "Chinese",
        },
    ]
}


@patch("src.collectors.news.requests.get")
def test_collect_returns_news_snapshot(mock_get: MagicMock) -> None:
    """collect() should return a NewsSnapshot with articles from GDELT."""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_GDELT_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    collector = NewsCollector()
    snapshot = collector.collect("geopolitical risk")

    assert isinstance(snapshot, NewsSnapshot)
    assert len(snapshot.articles) == 2
    assert snapshot.query == "geopolitical risk"
    assert isinstance(snapshot.fetched_at, datetime)


@patch("src.collectors.news.requests.get")
def test_collect_tags_media_bias_correctly(mock_get: MagicMock) -> None:
    """collect() should tag western and eastern sources with correct MediaBias."""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_GDELT_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    collector = NewsCollector()
    snapshot = collector.collect("test")

    biases = {a.source_domain: a.media_bias for a in snapshot.articles}
    assert biases["reuters.com"] == MediaBias.WESTERN
    assert biases["xinhuanet.com"] == MediaBias.EASTERN


@patch("src.collectors.news.requests.get")
def test_collect_counts_east_west_balance(mock_get: MagicMock) -> None:
    """collect() should correctly count western_count and eastern_count."""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_GDELT_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    collector = NewsCollector()
    snapshot = collector.collect("test")

    assert snapshot.western_count == 1
    assert snapshot.eastern_count == 1


@patch("src.collectors.news.requests.get")
def test_collect_raises_on_http_error(mock_get: MagicMock) -> None:
    """collect() should raise an exception when GDELT API returns an HTTP error."""
    mock_get.return_value.raise_for_status.side_effect = Exception("HTTP 500")

    collector = NewsCollector()
    with pytest.raises(Exception):
        collector.collect("test")
