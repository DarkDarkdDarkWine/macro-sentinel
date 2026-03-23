"""Market data models for financial indicators collected via yfinance."""

from datetime import datetime

from pydantic import BaseModel, Field


class IndexSnapshot(BaseModel):
    """A single market index price snapshot."""

    symbol: str = Field(description="Ticker symbol, e.g. '^GSPC'")
    name: str = Field(description="Human-readable name, e.g. 'S&P 500'")
    price: float = Field(description="Latest closing price")
    change_pct: float = Field(description="Percentage change from previous close")
    fetched_at: datetime = Field(description="UTC timestamp when data was fetched")


class MarketSnapshot(BaseModel):
    """Aggregated snapshot of key market indicators at a point in time."""

    fetched_at: datetime = Field(description="UTC timestamp when snapshot was taken")
    vix: float = Field(description="CBOE Volatility Index (fear gauge)")
    indices: list[IndexSnapshot] = Field(
        description="Major global indices: S&P 500, NASDAQ, HSI, SSE, etc."
    )
    commodities: list[IndexSnapshot] = Field(
        description="Key commodities: gold, crude oil, etc."
    )
    fx_rates: list[IndexSnapshot] = Field(
        description="Key FX pairs: USD/CNY, EUR/USD, etc."
    )
