"""Tests for the GDELT news collector."""

from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest

from src.collectors.news import (
    EASTERN_DOMAINS,
    GDELT_FALLBACK_TIMESPAN,
    GDELT_TIMESPAN,
    WESTERN_DOMAINS,
    NewsCollector,
)
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
def test_collect_requests_date_desc_sort_and_timespan(mock_get: MagicMock) -> None:
    """collect() must request sort=DateDesc and a timespan so results are recent."""
    mock_response = MagicMock()
    mock_response.json.return_value = MOCK_GDELT_RESPONSE
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    collector = NewsCollector()
    collector.collect("test")

    _, kwargs = mock_get.call_args
    params = kwargs.get("params", {})
    assert params.get("sort") == "DateDesc"
    assert "timespan" in params


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
def test_collect_returns_empty_snapshot_on_empty_response_body(mock_get: MagicMock) -> None:
    """collect() should return an empty snapshot when GDELT returns HTTP 200 with empty body."""
    import json as json_module

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = json_module.JSONDecodeError("Expecting value", "", 0)
    mock_get.return_value = mock_response

    collector = NewsCollector()
    snapshot = collector.collect("test")

    assert isinstance(snapshot, NewsSnapshot)
    assert snapshot.articles == []
    assert snapshot.western_count == 0
    assert snapshot.eastern_count == 0


@patch("src.collectors.news.requests.get")
def test_collect_skips_articles_with_malformed_date(mock_get: MagicMock) -> None:
    """collect() should skip articles with unparseable seendate, not crash."""
    bad_response = {
        "articles": [
            {
                "title": "Good article",
                "url": "https://reuters.com/1",
                "domain": "reuters.com",
                "seendate": "20240315T120000Z",
                "language": "English",
            },
            {
                "title": "Bad date article",
                "url": "https://apnews.com/2",
                "domain": "apnews.com",
                "seendate": "NOT_A_DATE",
                "language": "English",
            },
        ]
    }
    mock_response = MagicMock()
    mock_response.json.return_value = bad_response
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    collector = NewsCollector()
    snapshot = collector.collect("test")

    assert len(snapshot.articles) == 1
    assert snapshot.articles[0].title == "Good article"


@patch("src.collectors.news.requests.get")
def test_collect_skips_articles_with_missing_seendate(mock_get: MagicMock) -> None:
    """collect() should skip articles where seendate key is absent."""
    bad_response = {
        "articles": [
            {
                "title": "No date",
                "url": "https://bbc.com/1",
                "domain": "bbc.com",
                "language": "English",
                # seendate intentionally missing
            },
            {
                "title": "Has date",
                "url": "https://reuters.com/2",
                "domain": "reuters.com",
                "seendate": "20240315T120000Z",
                "language": "English",
            },
        ]
    }
    mock_response = MagicMock()
    mock_response.json.return_value = bad_response
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    collector = NewsCollector()
    snapshot = collector.collect("test")

    assert len(snapshot.articles) == 1
    assert snapshot.articles[0].title == "Has date"


@patch("src.collectors.news.requests.get")
def test_collect_falls_back_to_longer_timespan_when_no_results(mock_get: MagicMock) -> None:
    """collect() should retry with GDELT_FALLBACK_TIMESPAN when primary returns 0 articles."""
    empty_response = {"articles": []}
    full_response = MOCK_GDELT_RESPONSE

    # First call (1d) → empty; second call (fallback) → articles
    mock_response_empty = MagicMock()
    mock_response_empty.json.return_value = empty_response
    mock_response_empty.raise_for_status.return_value = None

    mock_response_full = MagicMock()
    mock_response_full.json.return_value = full_response
    mock_response_full.raise_for_status.return_value = None

    mock_get.side_effect = [mock_response_empty, mock_response_full]

    collector = NewsCollector()
    snapshot = collector.collect("test")

    assert len(snapshot.articles) == 2
    assert mock_get.call_count == 2

    # Verify the second call used the fallback timespan
    second_call_params = mock_get.call_args_list[1][1]["params"]
    assert second_call_params["timespan"] == GDELT_FALLBACK_TIMESPAN


@patch("src.collectors.news.requests.get")
def test_collect_raises_on_http_error(mock_get: MagicMock) -> None:
    """collect() should raise an exception when GDELT API returns an HTTP error."""
    mock_get.return_value.raise_for_status.side_effect = Exception("HTTP 500")

    collector = NewsCollector()
    with pytest.raises(Exception):
        collector.collect("test")


@patch("src.collectors.news.time.sleep")
@patch("src.collectors.news.requests.get")
def test_collect_retries_on_429(mock_get: MagicMock, mock_sleep: MagicMock) -> None:
    """collect() should retry on HTTP 429 then succeed; verifies retry count and backoff."""
    import requests as req

    rate_limit_response = MagicMock()
    rate_limit_response.status_code = 429
    rate_limit_response.raise_for_status.side_effect = req.exceptions.HTTPError(
        response=MagicMock(status_code=429)
    )

    ok_response = MagicMock()
    ok_response.status_code = 200
    ok_response.raise_for_status.return_value = None
    ok_response.json.return_value = MOCK_GDELT_RESPONSE

    # First call → 429, second call → success
    mock_get.side_effect = [rate_limit_response, ok_response]

    collector = NewsCollector()
    snapshot = collector.collect("test")

    assert len(snapshot.articles) == 2
    assert mock_get.call_count == 2  # exactly one retry
    assert mock_sleep.called
    # Backoff should start at RETRY_BACKOFF_SECONDS
    from src.collectors.news import RETRY_BACKOFF_SECONDS
    assert mock_sleep.call_args_list[0] == call(RETRY_BACKOFF_SECONDS)


@patch("src.collectors.news.time.sleep")
@patch("src.collectors.news.requests.get")
def test_collect_raises_after_max_retries(mock_get: MagicMock, mock_sleep: MagicMock) -> None:
    """collect() should raise after exhausting all retries on persistent 429."""
    import requests as req

    rate_limit_response = MagicMock()
    rate_limit_response.status_code = 429
    rate_limit_response.raise_for_status.side_effect = req.exceptions.HTTPError(
        response=MagicMock(status_code=429)
    )
    mock_get.return_value = rate_limit_response

    collector = NewsCollector()
    with pytest.raises(req.exceptions.HTTPError):
        collector.collect("test")
