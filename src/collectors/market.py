"""Market data collector using yfinance.

Fetches VIX, major global indices, commodities, and FX rates.
All external yfinance calls are isolated here — no yfinance imports elsewhere.
"""

import logging
from datetime import datetime, timezone

import yfinance as yf

from src.models.market import IndexSnapshot, MarketSnapshot

logger = logging.getLogger(__name__)

# Symbols to collect, grouped by category.
# Extend these lists to add more instruments without changing collector logic.
INDEX_SYMBOLS: list[tuple[str, str]] = [
    # Americas
    ("^GSPC", "标普500"),
    ("^IXIC", "纳斯达克"),
    ("^DJI", "道琼斯"),
    # Europe
    ("^FTSE", "富时100"),
    ("^GDAXI", "DAX"),
    ("^FCHI", "CAC40"),
    # Asia-Pacific
    ("^HSI", "恒生指数"),
    ("000001.SS", "上证指数"),
    ("399001.SZ", "深证成指"),
    ("^N225", "日经225"),
    ("^KS11", "韩国KOSPI"),
    ("^AXJO", "澳洲ASX200"),
    # Emerging Markets
    ("^BSESN", "印度SENSEX"),
    ("^BVSP", "巴西BOVESPA"),
]

COMMODITY_SYMBOLS: list[tuple[str, str]] = [
    # Precious Metals
    ("GC=F", "黄金"),
    ("SI=F", "白银"),
    ("PL=F", "铂金"),
    ("PA=F", "钯金"),
    # Base Metals (LME 铝/锌无 yfinance 标准合约，只保留 COMEX 铜)
    ("HG=F", "铜"),
    # Energy - Crude Oil
    ("CL=F", "WTI原油"),
    ("BZ=F", "布伦特原油"),
    # Energy - Gas
    ("NG=F", "天然气"),
    # Agriculture
    ("ZC=F", "玉米"),
    ("ZS=F", "大豆"),
    ("KE=F", "小麦"),
]

FX_SYMBOLS: list[tuple[str, str]] = [
    ("USDCNY=X", "美元/人民币"),
    ("EURUSD=X", "欧元/美元"),
    ("USDJPY=X", "美元/日元"),
    ("GBPUSD=X", "英镑/美元"),
    ("DX-Y.NYB", "美元指数"),
]

VIX_SYMBOL: str = "^VIX"


class MarketCollector:
    """Collects a point-in-time snapshot of key market indicators via yfinance."""

    def fetch_vix(self) -> float:
        """Fetch the latest VIX (CBOE Volatility Index) value.

        Returns:
            Current VIX level as a float.

        Raises:
            ValueError: If the fetched VIX value is not positive.
        """
        ticker = yf.Ticker(VIX_SYMBOL)
        vix = float(ticker.fast_info.last_price)
        if vix <= 0:
            raise ValueError(f"Invalid VIX value: {vix}")
        logger.debug("VIX: %.2f", vix)
        return vix

    def fetch_index(self, symbol: str, name: str) -> IndexSnapshot:
        """Fetch the latest price and change for a single ticker symbol.

        Args:
            symbol: yfinance ticker symbol, e.g. '^GSPC'.
            name: Human-readable label, e.g. 'S&P 500'.

        Returns:
            IndexSnapshot with price and percentage change.

        Raises:
            ValueError: If previous_close is zero (prevents division by zero).
        """
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        price = float(info.last_price)
        prev_close = float(info.previous_close)

        if prev_close == 0:
            raise ValueError(
                f"previous_close is zero for {symbol}, cannot compute change_pct"
            )

        change_pct = (price - prev_close) / prev_close * 100
        logger.debug("%s (%s): %.2f (%.2f%%)", name, symbol, price, change_pct)

        return IndexSnapshot(
            symbol=symbol,
            name=name,
            price=price,
            change_pct=round(change_pct, 4),
            fetched_at=datetime.now(timezone.utc),
        )

    def collect(self) -> MarketSnapshot:
        """Collect a full market snapshot covering VIX, indices, commodities, and FX.

        Returns:
            MarketSnapshot with all configured instruments populated.
        """
        fetched_at = datetime.now(timezone.utc)
        logger.info("Collecting market snapshot at %s", fetched_at.isoformat())

        vix = self.fetch_vix()

        indices: list = []
        for sym, name in INDEX_SYMBOLS:
            try:
                indices.append(self.fetch_index(sym, name))
            except (ValueError, TypeError) as exc:
                logger.warning("Skipping index %s (%s): %s", sym, name, exc)

        commodities: list = []
        for sym, name in COMMODITY_SYMBOLS:
            try:
                commodities.append(self.fetch_index(sym, name))
            except (ValueError, TypeError) as exc:
                logger.warning("Skipping commodity %s (%s): %s", sym, name, exc)

        fx_rates: list = []
        for sym, name in FX_SYMBOLS:
            try:
                fx_rates.append(self.fetch_index(sym, name))
            except (ValueError, TypeError) as exc:
                logger.warning("Skipping fx %s (%s): %s", sym, name, exc)

        return MarketSnapshot(
            fetched_at=fetched_at,
            vix=vix,
            indices=indices,
            commodities=commodities,
            fx_rates=fx_rates,
        )
