"""
LLM provider chain for TASK-059 RAG Chatbot.

Mirror of `apps.course_generator.outline_service` provider pattern:
  OpenRouter → Ollama → Stub

Stub raises `StubNotAllowed` in production unless `CHATBOT_ALLOW_STUB=1`
(or `DEBUG=True`).
"""

from __future__ import annotations

import logging
import requests
import time

from django.conf import settings

logger = logging.getLogger(__name__)

# Maximum tokens requested for chatbot completion (answer capped at ~200 words)
MAX_COMPLETION_TOKENS = 400
# Maximum tokens in the context window sent to the model
MAX_CONTEXT_TOKENS = 2000


class ChatProviderError(Exception):
    """Raised when a provider fails to produce a completion."""


class StubNotAllowed(ChatProviderError):
    """Raised when the stub provider is invoked in production."""


class ChatProvider:
    """Abstract base for chatbot LLM providers."""

    name: str = "abstract"
    model: str = ""

    def complete(self, prompt: str) -> tuple[str, int, int]:
        """
        Send the grounding prompt to the LLM.

        Returns
        -------
        (answer_text, tokens_prompt, tokens_completion)
        """
        raise NotImplementedError


class OpenRouterChatProvider(ChatProvider):
    name = "openrouter"

    def __init__(self) -> None:
        self.api_key = getattr(settings, "OPENROUTER_API_KEY", "") or ""
        self.base_url = getattr(
            settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        )
        self.model = getattr(
            settings,
            "CHATBOT_OPENROUTER_MODEL",
            "meta-llama/llama-3.1-70b-instruct",
        )
        if not self.api_key:
            raise ChatProviderError("OPENROUTER_API_KEY is not configured")

    def complete(self, prompt: str) -> tuple[str, int, int]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": MAX_COMPLETION_TOKENS,
        }
        backoff = 1.0
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                resp = requests.post(
                    f"{self.base_url}/chat/completions",
                    json=body,
                    headers=headers,
                    timeout=60,
                )
                if resp.status_code >= 500:
                    raise ChatProviderError(
                        f"OpenRouter 5xx: {resp.status_code}"
                    )
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                return (
                    content,
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                )
            except ChatProviderError:
                raise
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                if attempt == 2:
                    raise ChatProviderError(
                        f"OpenRouter failed after retries: {exc}"
                    ) from exc
                time.sleep(backoff)
                backoff *= 2
        raise ChatProviderError(f"OpenRouter exhausted retries: {last_err}")


class OllamaChatProvider(ChatProvider):
    name = "ollama"

    def __init__(self) -> None:
        self.base_url = (
            getattr(settings, "OLLAMA_BASE_URL", "") or "http://localhost:11434"
        )
        self.model = getattr(settings, "CHATBOT_OLLAMA_MODEL", "llama3")

    def complete(self, prompt: str) -> tuple[str, int, int]:
        body = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": MAX_COMPLETION_TOKENS},
        }
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=body,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("response", "")
            # Ollama's /api/generate response includes token counts under
            # prompt_eval_count (prompt tokens) and eval_count (completion tokens).
            tokens_prompt = data.get("prompt_eval_count", 0) or 0
            tokens_completion = data.get("eval_count", 0) or 0
            return content, tokens_prompt, tokens_completion
        except Exception as exc:
            raise ChatProviderError(f"Ollama failed: {exc}") from exc


class StubChatProvider(ChatProvider):
    name = "stub"

    def __init__(self) -> None:
        self.model = "stub-1"
        if not self._stub_allowed():
            raise StubNotAllowed(
                "Stub chatbot provider disabled: set DEBUG=True or "
                "CHATBOT_ALLOW_STUB=1 to enable."
            )

    @staticmethod
    def _stub_allowed() -> bool:
        debug = bool(getattr(settings, "DEBUG", False))
        allow = bool(getattr(settings, "CHATBOT_ALLOW_STUB", False))
        return debug or allow

    def complete(self, prompt: str) -> tuple[str, int, int]:  # noqa: ARG002
        answer = (
            "According to the course material [1], the key concept is well explained. "
            "The context blocks provide clear guidance [2]."
        )
        return answer, 50, 30


def get_provider() -> ChatProvider:
    """Resolve chatbot LLM provider from settings with fallback chain."""
    provider_name = (
        getattr(settings, "CHATBOT_LLM_PROVIDER", "auto") or "auto"
    ).lower().strip()

    if provider_name == "openrouter":
        attempts: list[type[ChatProvider]] = [OpenRouterChatProvider]
    elif provider_name == "ollama":
        attempts = [OllamaChatProvider]
    elif provider_name == "stub":
        attempts = [StubChatProvider]
    else:
        attempts = [OpenRouterChatProvider, OllamaChatProvider, StubChatProvider]

    last_err: Exception | None = None
    for cls in attempts:
        try:
            return cls()
        except ChatProviderError as exc:
            last_err = exc
            logger.info("Chatbot provider %s unavailable: %s", cls.__name__, exc)
            continue

    raise ChatProviderError(f"No chatbot provider available ({last_err})")
