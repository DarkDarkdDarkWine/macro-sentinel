"""DeepSeek LLM client and translation utilities.

All DeepSeek API calls in this project are routed through this module.
Other modules must not import openai or call the DeepSeek API directly.
"""

import json
import logging

import openai

logger = logging.getLogger(__name__)

# DeepSeek is OpenAI-API-compatible; only the base_url differs.
DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
DEFAULT_MODEL: str = "deepseek-chat"

# Timeout for a single LLM request in seconds.
REQUEST_TIMEOUT: int = 60

# Prompt instructing the model to return a JSON array of translated strings.
_TRANSLATE_SYSTEM_PROMPT: str = (
    "你是专业的新闻翻译助手。"
    "将用户提供的新闻标题翻译成简体中文。"
    "规则：\n"
    "1. 返回格式为 JSON 数组，与输入顺序一一对应\n"
    "2. 已经是中文的标题原文返回，不做修改\n"
    "3. 保持专业、简洁的新闻文风\n"
    "4. 只返回 JSON 数组，不要任何解释或额外文字"
)


class LLMClient:
    """Thin wrapper around the DeepSeek (OpenAI-compatible) chat API.

    Centralises model selection, timeout, and base URL so callers only
    need to supply messages.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEEPSEEK_BASE_URL,
        model: str = DEFAULT_MODEL,
    ) -> None:
        """Initialise the client.

        Args:
            api_key: DeepSeek API key.
            base_url: Base URL for the OpenAI-compatible endpoint.
            model: Model identifier to use for all requests.
        """
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def chat(self, messages: list[dict], **kwargs) -> str:
        """Send a chat completion request and return the response content.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            **kwargs: Additional parameters forwarded to the completions API
                (e.g. temperature, max_tokens).

        Returns:
            Content string from the first choice.

        Raises:
            openai.OpenAIError: On API errors (auth, rate limit, etc.).
            RuntimeError: On unexpected response shape.
        """
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            timeout=REQUEST_TIMEOUT,
            **kwargs,
        )
        return response.choices[0].message.content  # type: ignore[return-value]


def translate_titles(client: LLMClient, titles: list[str]) -> list[str]:
    """Translate a list of news titles to Simplified Chinese via the LLM.

    Sends all titles in a single request for efficiency.
    Falls back to the original titles on any error (malformed JSON,
    length mismatch, network failure) so that the rest of the pipeline
    is never blocked by a translation failure.

    Args:
        client: Configured LLMClient instance.
        titles: List of news headline strings (any language).

    Returns:
        List of Simplified Chinese strings in the same order as *titles*.
        On failure, returns the original *titles* list unchanged.
    """
    if not titles:
        return []

    user_content = json.dumps(titles, ensure_ascii=False)
    messages = [
        {"role": "system", "content": _TRANSLATE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        raw = client.chat(messages, temperature=0.1)
        # Strip markdown code fences if the model wraps output in ```json ... ```
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        translated: list[str] = json.loads(cleaned)

        if not isinstance(translated, list) or len(translated) != len(titles):
            logger.warning(
                "Translation length mismatch: expected %d, got %s — using originals",
                len(titles),
                len(translated) if isinstance(translated, list) else type(translated).__name__,
            )
            return titles

        logger.info("Translated %d titles via DeepSeek", len(titles))
        return translated

    except (json.JSONDecodeError, openai.OpenAIError) as exc:
        logger.warning("Translation failed (%s: %s) — using original titles", type(exc).__name__, exc)
        return titles
