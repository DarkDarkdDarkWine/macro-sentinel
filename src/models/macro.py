"""Macroeconomic indicator models collected via FRED API."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class MacroSeries(BaseModel):
    """A single FRED data series with its latest value."""

    series_id: str = Field(description="FRED series ID, e.g. 'FEDFUNDS'")
    name: str = Field(description="Human-readable name, e.g. 'Federal Funds Rate'")
    value: float = Field(description="Latest available value")
    unit: str = Field(description="Unit of measurement, e.g. 'Percent'")
    observation_date: date = Field(description="Date of the latest observation")
    fetched_at: datetime = Field(description="UTC timestamp when data was fetched")


class MacroSnapshot(BaseModel):
    """Aggregated snapshot of key macroeconomic indicators at a point in time."""

    fetched_at: datetime = Field(description="UTC timestamp when snapshot was taken")
    series: list[MacroSeries] = Field(
        description="Key FRED series: interest rates, CPI, unemployment, etc."
    )
