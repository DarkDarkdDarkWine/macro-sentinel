"""Macroeconomic data collector using the FRED API.

Fetches key economic series: interest rates, inflation, unemployment, etc.
All FRED API calls are isolated here — no fredapi imports elsewhere.
"""

import logging
from datetime import datetime, timezone

from fredapi import Fred

# Timeout in seconds for all FRED HTTP requests.
REQUEST_TIMEOUT: int = 30

from src.models.macro import MacroSeries, MacroSnapshot

logger = logging.getLogger(__name__)

# Core FRED series to collect: (series_id, human_readable_name, unit)
# Add entries here to expand macro coverage without changing collector logic.
FRED_SERIES: list[tuple[str, str, str]] = [
    ("FEDFUNDS", "联邦基金利率", "%"),
    ("CPIAUCSL", "消费者价格指数(CPI)", "指数"),
    ("UNRATE", "失业率", "%"),
    ("T10Y2Y", "10年-2年美债利差", "%"),
    ("DGS10", "10年期美债收益率", "%"),
]


class MacroCollector:
    """Collects a point-in-time snapshot of key macroeconomic indicators via FRED."""

    def __init__(self, api_key: str) -> None:
        """Initialise the collector with a FRED API key.

        Args:
            api_key: FRED API key obtained from fredaccount.stlouisfed.org.
        """
        # request_params is forwarded to every underlying requests call by fredapi.
        self._fred = Fred(api_key=api_key, request_params={"timeout": REQUEST_TIMEOUT})

    def fetch_series(self, series_id: str, name: str, unit: str) -> MacroSeries:
        """Fetch the latest observation for a single FRED series.

        Args:
            series_id: FRED series identifier, e.g. 'FEDFUNDS'.
            name: Human-readable label, e.g. 'Federal Funds Rate'.
            unit: Unit of measurement, e.g. 'Percent'.

        Returns:
            MacroSeries with the latest value and observation date.

        Raises:
            ValueError: If FRED returns an empty series.
        """
        data = self._fred.get_series(series_id)

        if data.empty:
            raise ValueError(
                f"FRED returned empty data for series '{series_id}'"
            )

        # Drop NaN entries and take the most recent valid observation
        data = data.dropna()
        latest_date = data.index[-1]
        latest_value = float(data.iloc[-1])

        logger.debug("%s (%s): %.4f as of %s", name, series_id, latest_value, latest_date)

        return MacroSeries(
            series_id=series_id,
            name=name,
            value=latest_value,
            unit=unit,
            observation_date=latest_date.date(),
            fetched_at=datetime.now(timezone.utc),
        )

    def collect(self) -> MacroSnapshot:
        """Collect a full macro snapshot covering all configured FRED series.

        Returns:
            MacroSnapshot with all configured series populated.
        """
        fetched_at = datetime.now(timezone.utc)
        logger.info("Collecting macro snapshot at %s", fetched_at.isoformat())

        series = [
            self.fetch_series(sid, name, unit)
            for sid, name, unit in FRED_SERIES
        ]

        return MacroSnapshot(fetched_at=fetched_at, series=series)
