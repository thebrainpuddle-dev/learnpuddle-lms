"""
Unified LLM service supporting OpenRouter (cloud) and Ollama (local) with
automatic fallback.

Priority order (configurable via LLM_PROVIDER setting):
  1. OpenRouter  -- uses native `models` array for built-in failover across
                    free/cheap models (Qwen3, DeepSeek, etc.)
  2. Ollama      -- local self-hosted model (Mistral by default)
  3. None        -- caller is responsible for deterministic fallback

Usage:
    from utils.llm_service import llm_generate
    response_text = llm_generate(prompt="...", system_prompt="...")
    if response_text is None:
        # all providers failed; use deterministic fallback
"""

import json
import logging
import time
from typing import Any

import requests as http_requests

logger = logging.getLogger(__name__)

# OpenRouter retry config: 10s base, 2 retries (3 attempts total)
OPENROUTER_BACKOFF_BASE_SEC = 10
OPENROUTER_MAX_RETRIES = 2


def _get_settings():
    """Lazy import to avoid Django AppRegistryNotReady at module level."""
    from django.conf import settings as conf
    return conf


# ---------------------------------------------------------------------------
# OpenRouter provider
# ---------------------------------------------------------------------------

def _call_openrouter(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str | None:
    """
    Call the OpenRouter chat-completions endpoint.

    Uses the native ``models`` array so OpenRouter automatically fails over
    between the listed models if the primary is down / rate-limited.

    Returns the assistant message text, or None on failure.
    """
    conf = _get_settings()

    api_key = getattr(conf, "OPENROUTER_API_KEY", "")
    if not api_key:
        logger.debug("OpenRouter skipped: OPENROUTER_API_KEY not configured")
        return None

    base_url = getattr(conf, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    default_model = getattr(conf, "OPENROUTER_DEFAULT_MODEL", "qwen/qwen3-30b-a3b:free")

    # Build fallback model list
    fallback_raw = getattr(conf, "OPENROUTER_FALLBACK_MODELS", "")
    fallback_models = [m.strip() for m in fallback_raw.split(",") if m.strip()] if fallback_raw else []
    all_models = [default_model] + [m for m in fallback_models if m != default_model]

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": default_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # If we have fallback models, include the models array for automatic failover
    if len(all_models) > 1:
        payload["models"] = all_models

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": getattr(conf, "PLATFORM_DOMAIN", "lms.com"),
        "X-Title": getattr(conf, "PLATFORM_NAME", "Brain LMS"),
    }

    for attempt in range(OPENROUTER_MAX_RETRIES + 1):
        try:
            if attempt > 0:
                backoff_sec = OPENROUTER_BACKOFF_BASE_SEC * (2 ** (attempt - 1))
                logger.info("OpenRouter retry %d/%d after %ds backoff", attempt, OPENROUTER_MAX_RETRIES, backoff_sec)
                time.sleep(backoff_sec)

            resp = http_requests.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            # Log which model actually served the request
            used_model = data.get("model", default_model)
            choices = data.get("choices") or []
            if not choices:
                logger.warning("OpenRouter returned empty choices for model %s", used_model)
                continue

            text = choices[0].get("message", {}).get("content", "").strip()
            if text:
                logger.info("OpenRouter LLM response via model=%s (tokens: %s)", used_model,
                            json.dumps(data.get("usage", {})))
                return text

            logger.warning("OpenRouter returned blank content from model %s", used_model)

        except http_requests.ConnectionError:
            logger.info("OpenRouter unreachable (connection error)")
        except http_requests.Timeout:
            logger.warning("OpenRouter timed out after %ds", timeout)
        except http_requests.HTTPError as e:
            logger.warning("OpenRouter HTTP error: %s - %s", e.response.status_code if e.response is not None else "?",
                          e.response.text[:500] if e.response is not None else str(e))
        except Exception as e:
            logger.warning("OpenRouter call failed: %s", e)

    return None


# ---------------------------------------------------------------------------
# Ollama provider (local)
# ---------------------------------------------------------------------------

def _call_ollama(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.7,
    timeout: int = 120,
) -> str | None:
    """
    Call local Ollama ``/api/generate`` endpoint.
    Returns the response text, or None on failure.
    """
    conf = _get_settings()
    base_url = getattr(conf, "OLLAMA_BASE_URL", "http://localhost:11434")
    model = getattr(conf, "OLLAMA_MODEL", "mistral")

    # Ollama /api/generate uses a single prompt; prepend system prompt if given.
    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

    try:
        resp = http_requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": full_prompt,
                "stream": False,
                "options": {"temperature": temperature},
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        if text:
            logger.info("Ollama LLM response via model=%s", model)
            return text

        logger.warning("Ollama returned blank response from model %s", model)
        return None

    except http_requests.ConnectionError:
        logger.info("Ollama not available (connection refused)")
    except http_requests.Timeout:
        logger.warning("Ollama timed out after %ds", timeout)
    except Exception as e:
        logger.warning("Ollama call failed: %s", e)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def llm_generate(
    prompt: str,
    system_prompt: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str | None:
    """
    Generate text from an LLM using the configured provider chain.

    The ``LLM_PROVIDER`` setting controls behaviour:
      - ``"auto"``       (default) try OpenRouter first, then Ollama
      - ``"openrouter"`` only use OpenRouter
      - ``"ollama"``     only use local Ollama

    Returns the assistant's response text, or ``None`` if all providers failed
    (caller should handle deterministic fallback).
    """
    conf = _get_settings()
    provider = getattr(conf, "LLM_PROVIDER", "auto").lower().strip()

    if provider in ("auto", "openrouter"):
        result = _call_openrouter(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        if result is not None:
            return result
        if provider == "openrouter":
            # Explicitly requested openrouter only; don't fall through to Ollama
            return None

    if provider in ("auto", "ollama"):
        result = _call_ollama(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            timeout=timeout,
        )
        if result is not None:
            return result

    logger.warning("All LLM providers exhausted (provider=%s). Caller should use deterministic fallback.", provider)
    return None
