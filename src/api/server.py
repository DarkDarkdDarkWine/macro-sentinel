"""FastAPI dashboard server for Macro Sentinel.

Serves the HTML dashboard and exposes /api/collect to trigger data collectors.
Collectors are instantiated per-request so they can be easily mocked in tests.
"""

import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from src.analyzers.llm import LLMClient, translate_titles
from src.collectors.macro import MacroCollector
from src.collectors.market import MarketCollector
from src.collectors.news import NewsCollector

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="Macro Sentinel", version="0.1.0")

# Default news query — broad macro + geopolitical coverage.
# GDELT treats space-separated terms as implicit OR, which is more reliable
# than explicit Boolean syntax across API versions.
DEFAULT_NEWS_QUERY = (
    "war conflict sanctions geopolitical inflation recession"
    " interest rate central bank trade tariff economy"
)

# Cache TTL in seconds — GDELT rate-limits aggressively; reuse results within this window.
# 10 minutes is long enough to survive repeated clicks while staying reasonably fresh.
CACHE_TTL_SECONDS: float = 600.0

# In-memory cache: maps cache key → (fetched_at_timestamp, serialised_data)
_cache: dict[str, tuple[float, Any]] = {}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serve the single-page dashboard."""
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    with open(html_path, encoding="utf-8") as f:
        return f.read()


def _cached_collect(key: str, collect_fn: Any) -> Any:
    """Return cached data for *key* if still within TTL, otherwise call *collect_fn*.

    Args:
        key: Cache key string identifying this data source.
        collect_fn: Zero-argument callable that fetches fresh data and returns
            a serialisable dict.

    Returns:
        Serialised data dict, either from cache or freshly collected.
    """
    now = time.time()
    if key in _cache:
        cached_at, cached_data = _cache[key]
        if now - cached_at < CACHE_TTL_SECONDS:
            logger.info("Cache hit for '%s' (age %.0fs)", key, now - cached_at)
            return cached_data

    logger.info("Cache miss for '%s', fetching fresh data", key)
    data = collect_fn()
    _cache[key] = (now, data)
    return data


@app.get("/api/collect")
def collect(
    sources: str = Query(
        default="market,macro,news",
        description="Comma-separated list of sources to collect: market, macro, news",
    ),
) -> dict[str, Any]:
    """Trigger data collection for the requested sources and return results as JSON.

    Results are cached per source for CACHE_TTL_SECONDS to avoid hitting
    rate-limited external APIs (especially GDELT) on every page refresh.

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
            result["market"] = _cached_collect(
                "market",
                lambda: MarketCollector().collect().model_dump(mode="json"),
            )

        if "macro" in requested:
            api_key = os.environ.get("FRED_API_KEY", "")
            if not api_key:
                raise HTTPException(
                    status_code=503,
                    detail={"error": "FRED_API_KEY environment variable not set"},
                )
            result["macro"] = _cached_collect(
                "macro",
                lambda: MacroCollector(api_key=api_key).collect().model_dump(mode="json"),
            )

        if "news" in requested:
            deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")

            def _collect_and_translate_news() -> dict:
                snapshot = NewsCollector().collect(DEFAULT_NEWS_QUERY)
                if deepseek_key:
                    llm = LLMClient(api_key=deepseek_key)
                    titles = [a.title for a in snapshot.articles]
                    translated = translate_titles(llm, titles)
                    # Build an immutable copy with translated titles instead of mutating
                    # live model objects — preserves Pydantic model integrity.
                    snapshot = snapshot.model_copy(update={
                        "articles": [
                            article.model_copy(update={"title": zh})
                            for article, zh in zip(snapshot.articles, translated)
                        ]
                    })
                return snapshot.model_dump(mode="json")

            result["news"] = _cached_collect("news", _collect_and_translate_news)

    except HTTPException:
        raise  # propagate 503 / other HTTP errors from key-missing checks
    except Exception as exc:
        logger.exception("Collector failed: %s", exc)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc

    return result
