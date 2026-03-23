"""FastAPI dashboard server for Macro Sentinel.

Serves the HTML dashboard and exposes /api/collect to trigger data collectors.
Collectors are instantiated per-request so they can be easily mocked in tests.
"""

import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from src.collectors.macro import MacroCollector
from src.collectors.market import MarketCollector
from src.collectors.news import NewsCollector

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="Macro Sentinel", version="0.1.0")

# Default news query — covers geopolitical and macro themes
DEFAULT_NEWS_QUERY = "geopolitical risk economy inflation trade war"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serve the single-page dashboard."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path, encoding="utf-8") as f:
        return f.read()


@app.get("/api/collect")
def collect(
    sources: str = Query(
        default="market,macro,news",
        description="Comma-separated list of sources to collect: market, macro, news",
    ),
) -> dict[str, Any]:
    """Trigger data collection for the requested sources and return results as JSON.

    Args:
        sources: Comma-separated source names. Defaults to all three sources.

    Returns:
        Dict with keys matching requested sources ('market', 'macro', 'news').

    Raises:
        HTTPException 500: If any collector raises an unexpected error.
    """
    requested = {s.strip() for s in sources.split(",")}
    result: dict[str, Any] = {}

    try:
        if "market" in requested:
            logger.info("Collecting market data")
            result["market"] = MarketCollector().collect().model_dump(mode="json")

        if "macro" in requested:
            api_key = os.environ.get("FRED_API_KEY", "")
            logger.info("Collecting macro data")
            result["macro"] = MacroCollector(api_key=api_key).collect().model_dump(mode="json")

        if "news" in requested:
            logger.info("Collecting news data")
            result["news"] = NewsCollector().collect(DEFAULT_NEWS_QUERY).model_dump(mode="json")

    except Exception as exc:
        logger.exception("Collector failed: %s", exc)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc

    return result
