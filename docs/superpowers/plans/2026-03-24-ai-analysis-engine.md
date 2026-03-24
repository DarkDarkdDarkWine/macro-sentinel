# AI Analysis Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/api/brief` endpoint that calls DeepSeek to synthesise all collected data (market + macro + news) into a structured Chinese-language macro briefing (宏观简报), then display it as the top card in the dashboard.

**Architecture:** A new `MacroBriefing` Pydantic model (with `str, Enum` sentiment type, matching existing `MediaBias` pattern) captures the briefing structure. A `generate_briefing()` function in `src/analyzers/briefing.py` formats collected data into a prompt, calls DeepSeek for a JSON response, and parses it — falling back to a placeholder on `openai.OpenAIError` or parse failure. The `/api/brief` endpoint re-uses the existing per-source cache by calling `_cached_collect` for each source, then calls `generate_briefing()` and caches the resulting briefing under key `"brief"`. The frontend adds a top-level card.

**Tech Stack:** Python 3.10+ / Pydantic v2 / `openai` SDK (DeepSeek-compatible) / FastAPI / vanilla JS + CSS (no new dependencies)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/models/briefing.py` | **Create** | `MarketSentiment` enum + `MacroBriefing` Pydantic model |
| `src/analyzers/briefing.py` | **Create** | Prompt builder, JSON parser, `generate_briefing()` |
| `src/api/server.py` | **Modify** | Add `/api/brief` endpoint; import `generate_briefing` at module level so patch works in tests |
| `src/api/static/index.html` | **Modify** | Add 宏观简报 card at page top |
| `tests/models/test_briefing.py` | **Create** | Model validation tests |
| `tests/analyzers/test_briefing.py` | **Create** | Analyzer unit tests (LLM mocked) |
| `tests/api/test_server.py` | **Modify** | Tests for `/api/brief` endpoint |

**Note:** `tests/models/__init__.py` must be created (empty); `tests/analyzers/__init__.py` already exists.

---

## Task 1: MacroBriefing Pydantic Model

**Files:**
- Create: `src/models/briefing.py`
- Create: `tests/models/__init__.py` (empty)
- Create: `tests/models/test_briefing.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/models/test_briefing.py
"""Tests for MacroBriefing Pydantic model."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models.briefing import MacroBriefing, MarketSentiment


def test_macro_briefing_valid_construction():
    briefing = MacroBriefing(
        generated_at=datetime.now(timezone.utc),
        summary="全球市场情绪偏谨慎，美联储维持高利率。",
        key_risks=["通胀持续高企", "地缘政治紧张"],
        market_sentiment=MarketSentiment.BEARISH,
        articles_analysed=10,
        macro_series_count=5,
        is_fallback=False,
    )
    assert briefing.summary == "全球市场情绪偏谨慎，美联储维持高利率。"
    assert briefing.market_sentiment == MarketSentiment.BEARISH
    assert len(briefing.key_risks) == 2
    assert briefing.is_fallback is False


def test_macro_briefing_sentiment_enum_values():
    for val in MarketSentiment:
        b = MacroBriefing(
            generated_at=datetime.now(timezone.utc),
            summary="test",
            key_risks=[],
            market_sentiment=val,
            articles_analysed=0,
            macro_series_count=0,
        )
        assert b.market_sentiment == val


def test_macro_briefing_rejects_invalid_sentiment():
    with pytest.raises(ValidationError):
        MacroBriefing(
            generated_at=datetime.now(timezone.utc),
            summary="test",
            key_risks=[],
            market_sentiment="unknown_value",  # type: ignore[arg-type]
            articles_analysed=0,
            macro_series_count=0,
        )


def test_macro_briefing_is_fallback_defaults_to_false():
    b = MacroBriefing(
        generated_at=datetime.now(timezone.utc),
        summary="test",
        key_risks=[],
        market_sentiment=MarketSentiment.NEUTRAL,
        articles_analysed=0,
        macro_series_count=0,
    )
    assert b.is_fallback is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/darkwine/WorkSpace/macro-sentinel
python3 -m pytest tests/models/test_briefing.py -v
```
Expected: `ModuleNotFoundError: No module named 'src.models.briefing'`

- [ ] **Step 3: Create `tests/models/__init__.py`** (empty file)

- [ ] **Step 4: Create `src/models/briefing.py`**

```python
"""Macro briefing model produced by the AI analysis engine."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class MarketSentiment(str, Enum):
    """Overall market sentiment classification for a briefing."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    VOLATILE = "volatile"


class MacroBriefing(BaseModel):
    """Structured AI-generated macro briefing synthesising all collected data."""

    generated_at: datetime = Field(description="UTC timestamp when briefing was generated")
    summary: str = Field(description="3-5 sentence macro overview in Simplified Chinese")
    key_risks: list[str] = Field(
        description="Top risk factors in Simplified Chinese (3-5 items)"
    )
    market_sentiment: MarketSentiment = Field(
        description="Overall market sentiment"
    )
    articles_analysed: int = Field(description="Number of news articles included in analysis")
    macro_series_count: int = Field(description="Number of FRED macro series included")
    is_fallback: bool = Field(
        default=False,
        description="True when briefing is a placeholder due to LLM/parse failure",
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/models/test_briefing.py -v
```
Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add src/models/briefing.py tests/models/__init__.py tests/models/test_briefing.py
git commit -m "feat: add MacroBriefing Pydantic model with MarketSentiment enum"
```

---

## Task 2: Prompt Builder

**Files:**
- Create: `src/analyzers/briefing.py` (initial — prompt builder only)
- Create: `tests/analyzers/test_briefing.py` (initial — prompt builder tests)

The prompt builder formats raw snapshot data into a compact, structured string for DeepSeek. Keeping it pure (no I/O) makes it easy to test deterministically.

- [ ] **Step 1: Write the failing tests**

```python
# tests/analyzers/test_briefing.py
"""Tests for AI briefing analyzer."""
import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from src.analyzers.briefing import _build_prompt
from src.models.macro import MacroSeries, MacroSnapshot
from src.models.market import IndexSnapshot, MarketSnapshot
from src.models.news import MediaBias, NewsArticle, NewsSnapshot


def _make_market() -> MarketSnapshot:
    now = datetime.now(timezone.utc)
    idx = IndexSnapshot(symbol="^GSPC", name="标普500", price=5000.0, change_pct=-0.5, fetched_at=now)
    return MarketSnapshot(
        fetched_at=now,
        vix=22.5,
        indices=[idx],
        commodities=[
            IndexSnapshot(symbol="GC=F", name="黄金", price=2300.0, change_pct=0.3, fetched_at=now)
        ],
        fx_rates=[
            IndexSnapshot(symbol="USDCNY=X", name="美元/人民币", price=7.25, change_pct=0.1, fetched_at=now)
        ],
    )


def _make_macro() -> MacroSnapshot:
    now = datetime.now(timezone.utc)
    s = MacroSeries(
        series_id="FEDFUNDS", name="联邦基金利率", value=5.33, unit="%",
        observation_date=date(2024, 1, 1), fetched_at=now,
    )
    return MacroSnapshot(fetched_at=now, series=[s])


def _make_news() -> NewsSnapshot:
    now = datetime.now(timezone.utc)
    article = NewsArticle(
        title="美联储维持利率不变",
        url="https://example.com",
        source_domain="reuters.com",
        published_at=now,
        language="zh",
        media_bias=MediaBias.WESTERN,
    )
    return NewsSnapshot(fetched_at=now, query="test", articles=[article],
                        western_count=1, eastern_count=0)


def test_build_prompt_contains_vix():
    prompt = _build_prompt(_make_market(), _make_macro(), _make_news())
    assert "22.5" in prompt


def test_build_prompt_contains_macro_series():
    prompt = _build_prompt(_make_market(), _make_macro(), _make_news())
    assert "联邦基金利率" in prompt
    assert "5.33" in prompt


def test_build_prompt_contains_news_title():
    prompt = _build_prompt(_make_market(), _make_macro(), _make_news())
    assert "美联储维持利率不变" in prompt


def test_build_prompt_is_string():
    prompt = _build_prompt(_make_market(), _make_macro(), _make_news())
    assert isinstance(prompt, str)
    assert len(prompt) > 100
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/analyzers/test_briefing.py -v
```
Expected: `ImportError: cannot import name '_build_prompt' from 'src.analyzers.briefing'`

- [ ] **Step 3: Create `src/analyzers/briefing.py` with `_build_prompt`**

```python
"""AI-powered macro briefing generator.

Synthesises market, macro, and news data into a structured Chinese-language
briefing via the DeepSeek LLM. All LLM calls route through LLMClient in llm.py.
"""

import json
import logging
from datetime import datetime, timezone

import openai

from src.analyzers.llm import LLMClient
from src.models.briefing import MacroBriefing, MarketSentiment
from src.models.macro import MacroSnapshot
from src.models.market import MarketSnapshot
from src.models.news import NewsSnapshot

logger = logging.getLogger(__name__)

# System prompt instructs DeepSeek to return a strict JSON object.
_BRIEFING_SYSTEM_PROMPT: str = (
    "你是专业的宏观经济分析师。根据提供的市场数据、宏观经济指标和新闻标题，"
    "生成一份简洁的宏观简报。\n"
    "规则：\n"
    "1. 只返回 JSON 对象，不要任何解释或额外文字\n"
    "2. JSON 格式如下：\n"
    '   {"summary": "3-5句话的宏观概述", '
    '"key_risks": ["风险1", "风险2", "风险3"], '
    '"market_sentiment": "bearish|bullish|neutral|volatile"}\n'
    "3. 所有文字使用简体中文\n"
    "4. summary 聚焦当前最重要的宏观趋势和市场驱动因素\n"
    "5. key_risks 列出3-5个具体风险，每条不超过20字"
)


def _build_prompt(market: MarketSnapshot, macro: MacroSnapshot, news: NewsSnapshot) -> str:
    """Format collected snapshot data into a compact LLM prompt.

    Args:
        market: Latest market snapshot (indices, VIX, commodities, FX).
        macro: Latest macro snapshot (FRED series).
        news: Latest news snapshot (articles with translated titles).

    Returns:
        Formatted prompt string ready to send as user message.
    """
    lines: list[str] = ["## 市场数据"]

    lines.append(f"VIX恐慌指数: {market.vix:.1f}")
    for idx in market.indices:
        direction = "↑" if idx.change_pct >= 0 else "↓"
        lines.append(f"{idx.name}: {idx.price:.1f} ({direction}{abs(idx.change_pct):.2f}%)")
    for c in market.commodities:
        direction = "↑" if c.change_pct >= 0 else "↓"
        lines.append(f"{c.name}: {c.price:.1f} ({direction}{abs(c.change_pct):.2f}%)")
    for fx in market.fx_rates:
        lines.append(f"{fx.name}: {fx.price:.4f}")

    lines.append("\n## 宏观经济指标")
    for s in macro.series:
        lines.append(f"{s.name}: {s.value:.2f}{s.unit} (截至{s.observation_date})")

    lines.append("\n## 近期新闻标题（已按东西方视角标注）")
    perspective_map = {
        "western": "西方", "eastern": "东方",
        "neutral": "中立", "unknown": "未知",
    }
    for article in news.articles[:15]:  # cap at 15 to control token cost
        perspective = perspective_map.get(article.media_bias.value, "未知")
        lines.append(f"[{perspective}] {article.title}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/analyzers/test_briefing.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/analyzers/briefing.py tests/analyzers/test_briefing.py
git commit -m "feat: add briefing prompt builder"
```

---

## Task 3: Response Parser

**Files:**
- Modify: `src/analyzers/briefing.py` (add `_parse_briefing_response`)
- Modify: `tests/analyzers/test_briefing.py` (add parser tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/analyzers/test_briefing.py`:

```python
from src.analyzers.briefing import _parse_briefing_response


def test_parse_valid_response():
    raw = json.dumps({
        "summary": "市场整体偏谨慎。",
        "key_risks": ["通胀风险", "地缘政治"],
        "market_sentiment": "bearish",
    })
    briefing = _parse_briefing_response(raw, articles_analysed=10, macro_series_count=5)
    assert briefing is not None
    assert briefing.summary == "市场整体偏谨慎。"
    assert briefing.market_sentiment == MarketSentiment.BEARISH
    assert briefing.articles_analysed == 10
    assert briefing.is_fallback is False


def test_parse_response_strips_markdown_fences():
    raw = '```json\n{"summary": "ok", "key_risks": [], "market_sentiment": "neutral"}\n```'
    briefing = _parse_briefing_response(raw, articles_analysed=0, macro_series_count=0)
    assert briefing is not None
    assert briefing.summary == "ok"


def test_parse_invalid_json_returns_none():
    result = _parse_briefing_response("not json at all", articles_analysed=0, macro_series_count=0)
    assert result is None


def test_parse_missing_fields_returns_none():
    raw = json.dumps({"summary": "ok"})  # missing key_risks and market_sentiment
    result = _parse_briefing_response(raw, articles_analysed=0, macro_series_count=0)
    assert result is None


def test_parse_invalid_sentiment_returns_none():
    raw = json.dumps({"summary": "ok", "key_risks": [], "market_sentiment": "confused"})
    result = _parse_briefing_response(raw, articles_analysed=0, macro_series_count=0)
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/analyzers/test_briefing.py -v -k "parse"
```
Expected: `ImportError: cannot import name '_parse_briefing_response'`

- [ ] **Step 3: Add `_parse_briefing_response` to `src/analyzers/briefing.py`**

Add after `_build_prompt`:

```python
def _parse_briefing_response(
    raw: str,
    articles_analysed: int,
    macro_series_count: int,
) -> MacroBriefing | None:
    """Parse the LLM JSON response into a MacroBriefing.

    Args:
        raw: Raw string from LLM (may include markdown code fences).
        articles_analysed: Count of news articles fed to the LLM.
        macro_series_count: Count of FRED series fed to the LLM.

    Returns:
        MacroBriefing on success; None if JSON is invalid or fields are missing/wrong type.
    """
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("Briefing response is not valid JSON: %s", exc)
        return None

    try:
        return MacroBriefing(
            generated_at=datetime.now(timezone.utc),
            summary=data["summary"],
            key_risks=data["key_risks"],
            market_sentiment=data["market_sentiment"],
            articles_analysed=articles_analysed,
            macro_series_count=macro_series_count,
            is_fallback=False,
        )
    except (KeyError, ValueError, Exception) as exc:
        logger.warning("Failed to construct MacroBriefing from response: %s", exc)
        return None
```

- [ ] **Step 4: Run all briefing tests**

```bash
python3 -m pytest tests/analyzers/test_briefing.py -v
```
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/analyzers/briefing.py tests/analyzers/test_briefing.py
git commit -m "feat: add briefing response parser"
```

---

## Task 4: `generate_briefing()` Integration Function

**Files:**
- Modify: `src/analyzers/briefing.py` (add `generate_briefing` + `_fallback_briefing`)
- Modify: `tests/analyzers/test_briefing.py` (add integration tests with mocked LLM)

- [ ] **Step 1: Write the failing tests**

Add to `tests/analyzers/test_briefing.py`:

```python
import openai
from unittest.mock import MagicMock, patch

from src.analyzers.briefing import generate_briefing
from src.analyzers.llm import LLMClient
from src.models.briefing import MarketSentiment


def _make_valid_llm_response() -> str:
    return json.dumps({
        "summary": "全球市场承压，VIX偏高。",
        "key_risks": ["美联储政策不确定性", "地缘政治风险"],
        "market_sentiment": "bearish",
    })


def test_generate_briefing_returns_macro_briefing():
    mock_client = MagicMock(spec=LLMClient)
    mock_client.chat.return_value = _make_valid_llm_response()
    result = generate_briefing(mock_client, _make_market(), _make_macro(), _make_news())
    assert result.market_sentiment == MarketSentiment.BEARISH
    assert result.articles_analysed == 1
    assert result.is_fallback is False


def test_generate_briefing_passes_correct_messages_to_llm():
    mock_client = MagicMock(spec=LLMClient)
    mock_client.chat.return_value = _make_valid_llm_response()
    generate_briefing(mock_client, _make_market(), _make_macro(), _make_news())
    call_args = mock_client.chat.call_args
    # Support both positional and keyword call styles
    messages = call_args.args[0] if call_args.args else call_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "VIX" in messages[1]["content"]


def test_generate_briefing_returns_fallback_on_openai_error():
    mock_client = MagicMock(spec=LLMClient)
    mock_client.chat.side_effect = openai.APIConnectionError(request=MagicMock())
    result = generate_briefing(mock_client, _make_market(), _make_macro(), _make_news())
    assert result.market_sentiment == MarketSentiment.NEUTRAL
    assert "无法生成" in result.summary
    assert result.is_fallback is True


def test_generate_briefing_returns_fallback_on_parse_failure():
    mock_client = MagicMock(spec=LLMClient)
    mock_client.chat.return_value = "this is not json"
    result = generate_briefing(mock_client, _make_market(), _make_macro(), _make_news())
    assert result.market_sentiment == MarketSentiment.NEUTRAL
    assert "无法生成" in result.summary
    assert result.is_fallback is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/analyzers/test_briefing.py -v -k "generate"
```
Expected: `ImportError: cannot import name 'generate_briefing'`

- [ ] **Step 3: Add `generate_briefing` and `_fallback_briefing` to `src/analyzers/briefing.py`**

Add after `_parse_briefing_response`:

```python
def generate_briefing(
    client: LLMClient,
    market: MarketSnapshot,
    macro: MacroSnapshot,
    news: NewsSnapshot,
) -> MacroBriefing:
    """Generate a structured macro briefing by calling DeepSeek.

    Builds a prompt from the three snapshots, calls the LLM, and parses
    the JSON response. Falls back to a neutral placeholder briefing on
    openai.OpenAIError or JSON parse failure.

    Args:
        client: Configured LLMClient instance.
        market: Latest market snapshot.
        macro: Latest macro snapshot.
        news: Latest news snapshot.

    Returns:
        MacroBriefing — LLM-generated (is_fallback=False) or fallback placeholder (is_fallback=True).
    """
    prompt = _build_prompt(market, macro, news)
    messages = [
        {"role": "system", "content": _BRIEFING_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    articles_count = len(news.articles)
    series_count = len(macro.series)

    try:
        raw = client.chat(messages, temperature=0.3)
    except openai.OpenAIError as exc:
        logger.warning("Briefing LLM call failed (%s: %s) — returning fallback", type(exc).__name__, exc)
        return _fallback_briefing(articles_count, series_count)

    briefing = _parse_briefing_response(raw, articles_count, series_count)
    if briefing is None:
        logger.warning("Briefing parse failed — returning fallback")
        return _fallback_briefing(articles_count, series_count)

    logger.info("Generated macro briefing (sentiment=%s)", briefing.market_sentiment.value)
    return briefing


def _fallback_briefing(articles_analysed: int, macro_series_count: int) -> MacroBriefing:
    """Return a safe placeholder when briefing generation fails."""
    return MacroBriefing(
        generated_at=datetime.now(timezone.utc),
        summary="无法生成宏观简报，请稍后重试。",
        key_risks=[],
        market_sentiment=MarketSentiment.NEUTRAL,
        articles_analysed=articles_analysed,
        macro_series_count=macro_series_count,
        is_fallback=True,
    )
```

- [ ] **Step 4: Run all briefing tests**

```bash
python3 -m pytest tests/analyzers/test_briefing.py -v
```
Expected: `13 passed`

- [ ] **Step 5: Run full test suite**

```bash
python3 -m pytest --tb=short -q
```
Expected: all existing 35+ pass, no regressions

- [ ] **Step 6: Commit**

```bash
git add src/analyzers/briefing.py tests/analyzers/test_briefing.py
git commit -m "feat: add generate_briefing with LLM integration and fallback"
```

---

## Task 5: `/api/brief` Endpoint

**Files:**
- Modify: `src/api/server.py`
- Modify: `tests/api/test_server.py`

**Key design decisions:**
1. Import `generate_briefing` at module level (`from src.analyzers.briefing import generate_briefing`) — required so the test can patch it as `src.api.server.generate_briefing`.
2. Inside `_generate`, re-use the existing per-source cache by calling `_cached_collect` for `"market"`, `"macro"`, and `"news"`, then reconstruct model objects from the cached dicts. This avoids redundant external API calls when fresh data is already cached.

- [ ] **Step 1: Write the failing tests**

Add to `tests/api/test_server.py`:

```python
def test_brief_endpoint_exists(client, monkeypatch):
    """Endpoint must exist, collectors and LLM must be mocked."""
    from src.models.briefing import MacroBriefing, MarketSentiment
    from datetime import datetime, timezone

    monkeypatch.setenv("FRED_API_KEY", "test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")

    fallback = MacroBriefing(
        generated_at=datetime.now(timezone.utc),
        summary="测试简报",
        key_risks=[],
        market_sentiment=MarketSentiment.NEUTRAL,
        articles_analysed=0,
        macro_series_count=0,
    )

    with patch("src.api.server.MarketCollector") as mock_mc, \
         patch("src.api.server.MacroCollector") as mock_macro, \
         patch("src.api.server.NewsCollector") as mock_nc, \
         patch("src.api.server.generate_briefing", return_value=fallback):
        mock_mc.return_value.collect.return_value.model_dump.return_value = {"vix": 15.0}
        mock_macro.return_value.collect.return_value.model_dump.return_value = {"series": []}
        mock_nc.return_value.collect.return_value.model_dump.return_value = {"articles": []}
        response = client.get("/api/brief")

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "market_sentiment" in data
    assert "is_fallback" in data


def test_brief_endpoint_returns_503_without_fred_key(client, monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    response = client.get("/api/brief")
    assert response.status_code == 503


def test_brief_endpoint_returns_503_without_deepseek_key(client, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    response = client.get("/api/brief")
    assert response.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/api/test_server.py -v -k "brief"
```
Expected: `404` or `ImportError`

- [ ] **Step 3: Modify `src/api/server.py`**

Add to the imports at the top:
```python
from src.analyzers.briefing import generate_briefing
from src.models.briefing import MacroBriefing
from src.models.macro import MacroSnapshot
from src.models.market import MarketSnapshot
from src.models.news import NewsSnapshot
```

Add the endpoint after the `collect` function:

```python
@app.get("/api/brief")
def brief() -> dict[str, Any]:
    """Generate an AI macro briefing from all three data sources.

    Re-uses the existing per-source cache (market/macro/news) to avoid
    redundant external API calls. The briefing result is itself cached
    under key 'brief' for CACHE_TTL_SECONDS.

    Returns:
        Serialised MacroBriefing dict (is_fallback=True if LLM/parse failed).

    Raises:
        HTTPException 503: If FRED_API_KEY or DEEPSEEK_API_KEY is missing.
        HTTPException 500: On unexpected collector or LLM errors.
    """
    fred_key = os.environ.get("FRED_API_KEY", "")
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY", "")

    if not fred_key:
        raise HTTPException(
            status_code=503,
            detail={"error": "FRED_API_KEY environment variable not set"},
        )
    if not deepseek_key:
        raise HTTPException(
            status_code=503,
            detail={"error": "DEEPSEEK_API_KEY environment variable not set"},
        )

    try:
        def _generate() -> dict:
            # Re-use per-source cache to avoid redundant external API calls.
            market_dict = _cached_collect(
                "market",
                lambda: MarketCollector().collect().model_dump(mode="json"),
            )
            macro_dict = _cached_collect(
                "macro",
                lambda: MacroCollector(api_key=fred_key).collect().model_dump(mode="json"),
            )
            news_dict = _cached_collect(
                "news",
                lambda: NewsCollector().collect(DEFAULT_NEWS_QUERY).model_dump(mode="json"),
            )

            # Reconstruct typed model objects from the (possibly cached) dicts.
            market = MarketSnapshot.model_validate(market_dict)
            macro = MacroSnapshot.model_validate(macro_dict)
            news = NewsSnapshot.model_validate(news_dict)

            llm = LLMClient(api_key=deepseek_key)
            briefing = generate_briefing(llm, market, macro, news)
            return briefing.model_dump(mode="json")

        return _cached_collect("brief", _generate)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Briefing generation failed: %s", exc)
        raise HTTPException(status_code=500, detail={"error": str(exc)}) from exc
```

- [ ] **Step 4: Run all tests**

```bash
python3 -m pytest --tb=short -q
```
Expected: all pass (38+ tests)

- [ ] **Step 5: Commit**

```bash
git add src/api/server.py tests/api/test_server.py
git commit -m "feat: add /api/brief endpoint with cache-aware data collection"
```

---

## Task 6: Frontend 宏观简报 Card

**Files:**
- Modify: `src/api/static/index.html`

This task has no unit tests (UI). Manual verification: load `http://localhost:8765/`, click "生成宏观简报" button, see the card populate.

- [ ] **Step 1: Read current `index.html` to understand existing structure**

Read `src/api/static/index.html` in full — study the existing grid layout, CSS variables (colour palette, spacing), and JS fetch/render pattern before making changes.

- [ ] **Step 2: Add 宏观简报 section**

Insert a new `<section id="brief-section">` **above** the existing market data grid. The card must:
- Show a "生成宏观简报" `<button>` that calls `GET /api/brief` on click
- Display a loading spinner while fetching (add/remove a CSS class)
- On success, render:
  - `market_sentiment` as a coloured badge: `bullish` → green (`var(--green)`), `bearish` → red (`var(--red)`), `neutral` → grey (`#888`), `volatile` → amber (`#f0a500`)
  - `summary` as a paragraph
  - `key_risks` as a `<ul>` bullet list (hidden if empty)
  - Footnote: `分析了 {articles_analysed} 篇新闻 · {macro_series_count} 项宏观指标`
  - If `is_fallback` is true, prepend a subtle warning line: `⚠ AI 分析暂不可用`
- On HTTP error, show "生成失败，请稍后重试" in red
- Match the existing dark-mode Bloomberg-inspired design (use existing CSS variables; ≤12px border-radius; no animation)

- [ ] **Step 3: Manual verification**

```bash
# Confirm server is running
curl -s http://localhost:8765/ | head -3
```
Then open `http://localhost:8765/` in browser:
1. Click "生成宏观简报" → loading state appears
2. Result populates with sentiment badge, summary paragraph, risks list
3. Badge colour matches sentiment value
4. If `is_fallback=true`, warning line is visible
5. No console errors (check DevTools)

- [ ] **Step 4: Commit**

```bash
git add src/api/static/index.html
git commit -m "feat: add 宏观简报 card to dashboard"
```

---

## Final Verification

- [ ] `python3 -m pytest -v` — all tests pass
- [ ] `python3 -m mypy src/` — no type errors
- [ ] `python3 -m ruff check .` — no lint errors
- [ ] `curl http://localhost:8765/api/brief` — returns JSON with `summary`, `market_sentiment`, `is_fallback`
- [ ] Call `/api/brief` twice within 10 min — second call returns instantly (cache hit, check server logs for "Cache hit for 'brief'")

---

## Scope Note

This plan covers **Stage 2 only** (AI Analysis Engine). Stages 3 (portfolio advice) and 4 (automation/scheduling) are separate plans.
