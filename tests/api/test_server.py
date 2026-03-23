"""Tests for the FastAPI dashboard server."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.server import app
from src.models.macro import MacroSeries, MacroSnapshot
from src.models.market import IndexSnapshot, MarketSnapshot
from src.models.news import MediaBias, NewsArticle, NewsSnapshot

NOW = datetime.now(timezone.utc)


def _make_index(symbol: str, name: str) -> IndexSnapshot:
    return IndexSnapshot(symbol=symbol, name=name, price=100.0, change_pct=1.0, fetched_at=NOW)


MOCK_MARKET = MarketSnapshot(
    fetched_at=NOW,
    vix=18.5,
    indices=[_make_index("^GSPC", "S&P 500"), _make_index("000001.SS", "Shanghai")],
    commodities=[_make_index("GC=F", "Gold")],
    fx_rates=[_make_index("USDCNY=X", "USD/CNY")],
)

MOCK_MACRO = MacroSnapshot(
    fetched_at=NOW,
    series=[
        MacroSeries(
            series_id="FEDFUNDS",
            name="Federal Funds Rate",
            value=5.33,
            unit="Percent",
            observation_date=NOW.date(),
            fetched_at=NOW,
        )
    ],
)

MOCK_NEWS = NewsSnapshot(
    fetched_at=NOW,
    query="geopolitical risk",
    articles=[
        NewsArticle(
            title="Global tensions rise",
            url="https://reuters.com/1",
            source_domain="reuters.com",
            published_at=NOW,
            language="en",
            media_bias=MediaBias.WESTERN,
        ),
        NewsArticle(
            title="经济分析",
            url="https://xinhuanet.com/1",
            source_domain="xinhuanet.com",
            published_at=NOW,
            language="zh",
            media_bias=MediaBias.EASTERN,
        ),
    ],
    western_count=1,
    eastern_count=1,
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_index_returns_html(client: TestClient) -> None:
    """GET / should return the HTML dashboard page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@patch("src.api.server.LLMClient")
@patch("src.api.server.translate_titles")
@patch("src.api.server.MarketCollector")
@patch("src.api.server.MacroCollector")
@patch("src.api.server.NewsCollector")
def test_collect_all_returns_combined_data(
    mock_news_cls: MagicMock,
    mock_macro_cls: MagicMock,
    mock_market_cls: MagicMock,
    mock_translate: MagicMock,
    mock_llm_cls: MagicMock,
    client: TestClient,
) -> None:
    """GET /api/collect should return market, macro, and news data combined."""
    import src.api.server as server_module

    server_module._cache.clear()
    mock_market_cls.return_value.collect.return_value = MOCK_MARKET
    mock_macro_cls.return_value.collect.return_value = MOCK_MACRO
    mock_news_cls.return_value.collect.return_value = MOCK_NEWS
    mock_translate.return_value = [a.title for a in MOCK_NEWS.articles]

    response = client.get("/api/collect")
    assert response.status_code == 200

    data = response.json()
    assert "market" in data
    assert "macro" in data
    assert "news" in data
    assert data["market"]["vix"] == 18.5
    assert len(data["macro"]["series"]) == 1
    assert len(data["news"]["articles"]) == 2


@patch("src.api.server.MarketCollector")
@patch("src.api.server.MacroCollector")
@patch("src.api.server.NewsCollector")
def test_collect_market_only(
    mock_news_cls: MagicMock,
    mock_macro_cls: MagicMock,
    mock_market_cls: MagicMock,
    client: TestClient,
) -> None:
    """GET /api/collect?sources=market should return only market data."""
    import src.api.server as server_module

    server_module._cache.clear()
    mock_market_cls.return_value.collect.return_value = MOCK_MARKET

    response = client.get("/api/collect?sources=market")
    assert response.status_code == 200

    data = response.json()
    assert "market" in data
    assert "macro" not in data
    assert "news" not in data


@patch("src.api.server.LLMClient")
@patch("src.api.server.translate_titles")
@patch("src.api.server.NewsCollector")
def test_collect_news_returns_cached_result_within_ttl(
    mock_news_cls: MagicMock,
    mock_translate: MagicMock,
    mock_llm_cls: MagicMock,
    client: TestClient,
) -> None:
    """Second /api/collect?sources=news call within TTL should return cached data."""
    import src.api.server as server_module

    server_module._cache.clear()
    mock_news_cls.return_value.collect.return_value = MOCK_NEWS
    mock_translate.return_value = [a.title for a in MOCK_NEWS.articles]

    r1 = client.get("/api/collect?sources=news")
    assert r1.status_code == 200

    r2 = client.get("/api/collect?sources=news")
    assert r2.status_code == 200
    assert r2.json() == r1.json()
    assert mock_news_cls.return_value.collect.call_count == 1  # only fetched once


@patch("src.api.server.LLMClient")
@patch("src.api.server.translate_titles")
@patch("src.api.server.time")
@patch("src.api.server.NewsCollector")
def test_collect_news_refetches_after_ttl_expires(
    mock_news_cls: MagicMock,
    mock_time: MagicMock,
    mock_translate: MagicMock,
    mock_llm_cls: MagicMock,
    client: TestClient,
) -> None:
    """After TTL expires, /api/collect?sources=news should call the collector again."""
    import src.api.server as server_module

    server_module._cache.clear()
    mock_news_cls.return_value.collect.return_value = MOCK_NEWS
    mock_translate.return_value = [a.title for a in MOCK_NEWS.articles]
    mock_time.time.return_value = 0.0

    client.get("/api/collect?sources=news")
    assert mock_news_cls.return_value.collect.call_count == 1

    mock_time.time.return_value = server_module.CACHE_TTL_SECONDS + 1
    client.get("/api/collect?sources=news")
    assert mock_news_cls.return_value.collect.call_count == 2


@patch("src.api.server.MarketCollector")
def test_collect_returns_500_on_collector_error(
    mock_market_cls: MagicMock,
    client: TestClient,
) -> None:
    """GET /api/collect should return 500 when a collector raises an exception."""
    mock_market_cls.return_value.collect.side_effect = RuntimeError("yfinance timeout")

    response = client.get("/api/collect?sources=market")
    assert response.status_code == 500
    assert "error" in response.json()["detail"]
