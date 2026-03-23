"""Tests for the FRED macroeconomic data collector."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.collectors.macro import MacroCollector
from src.models.macro import MacroSnapshot, MacroSeries


@pytest.fixture
def mock_fred_series() -> pd.Series:
    """A minimal pandas Series simulating FRED API response."""
    return pd.Series(
        [5.33],
        index=pd.DatetimeIndex([pd.Timestamp("2024-01-01")]),
    )


@patch("src.collectors.macro.Fred")
def test_fetch_series_returns_macro_series(
    mock_fred_cls: MagicMock, mock_fred_series: pd.Series
) -> None:
    """fetch_series() should return a MacroSeries with correct values."""
    mock_fred_cls.return_value.get_series.return_value = mock_fred_series
    mock_fred_cls.return_value.get_series_info.return_value = MagicMock(
        title="Federal Funds Rate", units="Percent"
    )

    collector = MacroCollector(api_key="test_key")
    result = collector.fetch_series("FEDFUNDS", "Federal Funds Rate", "Percent")

    assert isinstance(result, MacroSeries)
    assert result.series_id == "FEDFUNDS"
    assert result.value == 5.33
    assert result.unit == "Percent"
    assert isinstance(result.observation_date, date)


@patch("src.collectors.macro.Fred")
def test_collect_returns_macro_snapshot(
    mock_fred_cls: MagicMock, mock_fred_series: pd.Series
) -> None:
    """collect() should return a MacroSnapshot with all expected series."""
    mock_fred_cls.return_value.get_series.return_value = mock_fred_series
    mock_fred_cls.return_value.get_series_info.return_value = MagicMock(
        title="Test Series", units="Percent"
    )

    collector = MacroCollector(api_key="test_key")
    snapshot = collector.collect()

    assert isinstance(snapshot, MacroSnapshot)
    assert len(snapshot.series) > 0
    assert isinstance(snapshot.fetched_at, datetime)
    series_ids = [s.series_id for s in snapshot.series]
    # Core series must always be present
    assert "FEDFUNDS" in series_ids
    assert "CPIAUCSL" in series_ids
    assert "UNRATE" in series_ids


@patch("src.collectors.macro.Fred")
def test_fetch_series_raises_on_empty_data(mock_fred_cls: MagicMock) -> None:
    """fetch_series() should raise ValueError when FRED returns empty data."""
    mock_fred_cls.return_value.get_series.return_value = pd.Series([], dtype=float)

    collector = MacroCollector(api_key="test_key")
    with pytest.raises(ValueError, match="empty"):
        collector.fetch_series("FEDFUNDS", "Federal Funds Rate", "Percent")
