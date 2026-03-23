"""Tests for the yfinance market data collector."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.collectors.market import MarketCollector
from src.models.market import MarketSnapshot


@pytest.fixture
def mock_ticker_data() -> dict:
    """Minimal yfinance Ticker.fast_info mock payload."""
    return {
        "lastPrice": 5200.0,
        "previousClose": 5100.0,
    }


@patch("src.collectors.market.yf.Ticker")
def test_fetch_vix_returns_float(mock_ticker_cls: MagicMock) -> None:
    """fetch_vix() should return a positive float representing the VIX level."""
    mock_info = MagicMock()
    mock_info.last_price = 18.5
    mock_ticker_cls.return_value.fast_info = mock_info

    collector = MarketCollector()
    vix = collector.fetch_vix()

    assert isinstance(vix, float)
    assert vix > 0


@patch("src.collectors.market.yf.Ticker")
def test_fetch_index_returns_snapshot(mock_ticker_cls: MagicMock) -> None:
    """fetch_index() should return an IndexSnapshot with correct symbol and price."""
    mock_info = MagicMock()
    mock_info.last_price = 5200.0
    mock_info.previous_close = 5100.0
    mock_ticker_cls.return_value.fast_info = mock_info

    collector = MarketCollector()
    snapshot = collector.fetch_index("^GSPC", "S&P 500")

    assert snapshot.symbol == "^GSPC"
    assert snapshot.name == "S&P 500"
    assert snapshot.price == 5200.0
    assert round(snapshot.change_pct, 2) == round((5200.0 - 5100.0) / 5100.0 * 100, 2)


@patch("src.collectors.market.yf.Ticker")
def test_collect_returns_market_snapshot(mock_ticker_cls: MagicMock) -> None:
    """collect() should return a fully populated MarketSnapshot."""
    mock_info = MagicMock()
    mock_info.last_price = 100.0
    mock_info.previous_close = 95.0
    mock_ticker_cls.return_value.fast_info = mock_info

    collector = MarketCollector()
    snapshot = collector.collect()

    assert isinstance(snapshot, MarketSnapshot)
    assert snapshot.vix > 0
    assert len(snapshot.indices) > 0
    assert len(snapshot.commodities) > 0
    assert len(snapshot.fx_rates) > 0
    assert isinstance(snapshot.fetched_at, datetime)


@patch("src.collectors.market.yf.Ticker")
def test_fetch_index_raises_on_zero_previous_close(mock_ticker_cls: MagicMock) -> None:
    """fetch_index() should raise ValueError when previous_close is zero (bad data)."""
    mock_info = MagicMock()
    mock_info.last_price = 100.0
    mock_info.previous_close = 0.0
    mock_ticker_cls.return_value.fast_info = mock_info

    collector = MarketCollector()
    with pytest.raises(ValueError, match="previous_close"):
        collector.fetch_index("^GSPC", "S&P 500")
