"""Tests for the LLM client and translation utilities."""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.analyzers.llm import LLMClient, translate_titles


# ---------------------------------------------------------------------------
# LLMClient.chat
# ---------------------------------------------------------------------------

@patch("src.analyzers.llm.openai.OpenAI")
def test_llm_client_chat_returns_content_string(mock_openai_cls: MagicMock) -> None:
    """chat() should return the content string from the first choice."""
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="hello"))]
    )

    client = LLMClient(api_key="test-key")
    result = client.chat([{"role": "user", "content": "hi"}])

    assert result == "hello"


@patch("src.analyzers.llm.openai.OpenAI")
def test_llm_client_chat_raises_on_api_error(mock_openai_cls: MagicMock) -> None:
    """chat() should propagate exceptions from the OpenAI client."""
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = RuntimeError("network error")

    client = LLMClient(api_key="test-key")
    with pytest.raises(RuntimeError, match="network error"):
        client.chat([{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# translate_titles
# ---------------------------------------------------------------------------

def _make_llm_client(response_content: str) -> LLMClient:
    """Return a LLMClient whose chat() always returns *response_content*."""
    client = MagicMock(spec=LLMClient)
    client.chat.return_value = response_content
    return client


def test_translate_titles_returns_translated_list() -> None:
    """translate_titles() should return a list of translated strings."""
    titles = ["Global tensions rise", "Markets fall on trade war fears"]
    translated = ["全球紧张局势升级", "贸易战忧虑拖累市场下跌"]
    client = _make_llm_client(json.dumps(translated))

    result = translate_titles(client, titles)

    assert result == translated


def test_translate_titles_returns_originals_on_malformed_json() -> None:
    """translate_titles() should fall back to originals if LLM returns invalid JSON."""
    titles = ["Title one", "Title two"]
    client = _make_llm_client("这不是JSON格式的响应")

    result = translate_titles(client, titles)

    assert result == titles


def test_translate_titles_returns_originals_on_length_mismatch() -> None:
    """translate_titles() should fall back to originals if LLM returns wrong count."""
    titles = ["A", "B", "C"]
    client = _make_llm_client(json.dumps(["甲", "乙"]))  # only 2 items

    result = translate_titles(client, titles)

    assert result == titles


def test_translate_titles_returns_empty_list_for_empty_input() -> None:
    """translate_titles() should return [] immediately without calling LLM."""
    client = _make_llm_client("[]")

    result = translate_titles(client, [])

    assert result == []
    client.chat.assert_not_called()


def test_translate_titles_returns_originals_on_llm_exception() -> None:
    """translate_titles() should fall back to originals when LLM raises."""
    titles = ["Breaking news"]
    client = MagicMock(spec=LLMClient)
    client.chat.side_effect = RuntimeError("timeout")

    result = translate_titles(client, titles)

    assert result == titles
