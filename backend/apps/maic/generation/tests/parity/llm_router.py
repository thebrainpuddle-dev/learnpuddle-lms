"""Prompt-routed stub for parity tests.

Real OpenRouter calls are non-deterministic — even with temperature=0
upstream models drift slightly across runs, and they cost money. The
stub provider in `apps.maic.orchestration.ai_adapter` returns ONE
canned JSON array regardless of prompt, which doesn't match what each
generation stage expects.

`PromptRoutedStub` bridges the gap: it inspects the prompt's text,
matches the longest registered marker, and returns the registered
canned response. Fixtures supply the marker → response map via
`llm_responses.json`.

This lets parity tests:
    1. Run the FULL pipeline (Stage 1 outline → Stage 2 scenes).
    2. Stay deterministic across CI runs.
    3. Catch regressions in any module the pipeline touches
       (parser, dispatcher, formatters, action processor).

The gate **does NOT** catch upstream-vs-our-port divergence — that's
MAIC-430.B (real-OpenRouter Pass B, Session 7). What this catches is
"our pipeline used to produce X, now produces Y" regressions, which
is the Session-5 close criterion (don't move to Celery + WS until the
in-process pipeline is locked).
"""
from __future__ import annotations

from typing import Any


class PromptRoutedStub:
    """Test-time replacement for `apps.maic.generation.scene_generator.generate_text`.

    The pipeline flows multiple distinct prompts through generate_text
    (outline, slide-content, slide-actions, quiz-content, quiz-actions,
    each widget-content, widget-teacher-actions, interactive-actions,
    pbl-actions). The router matches on prompt markers — keys are
    ordered from most-specific to least-specific so the first match
    wins.

    Markers are checked against the concatenated content of the
    `messages` argument (system + user joined by space). Matching is a
    plain `in` check; tests can use unique strings from each template
    as keys.

    Construction:
        router = PromptRoutedStub({
            "JSON object with the following structure": OUTLINE_RESPONSE,
            "Generate slide content": SLIDE_CONTENT_RESPONSE,
            "Output as a JSON array directly": ACTIONS_RESPONSE,
            ...
        })

    Usage:
        with patch(
            "apps.maic.generation.scene_generator.generate_text",
            new=router,
        ):
            ...

    Unmatched prompts raise to surface mis-configured fixtures (the
    test fails loudly rather than silently producing empty pipeline
    output).
    """

    def __init__(self, responses: dict[str, str]):
        # Order keys by length (longest first) so a more specific
        # marker takes precedence over a shorter superset.
        self._rules = sorted(
            responses.items(), key=lambda kv: -len(kv[0])
        )
        self.calls: list[tuple[str, str]] = []  # (marker, prompt-snippet)

    async def __call__(self, *, messages, language_model_id, **kwargs) -> str:
        prompt_text = " ".join(_extract_content(m) for m in messages)
        for marker, response in self._rules:
            if marker in prompt_text:
                self.calls.append((marker, prompt_text[:200]))
                return response
        raise RuntimeError(
            "PromptRoutedStub: no rule matched. Prompt prefix: "
            f"{prompt_text[:300]!r}\n"
            f"Registered markers: {[k for k, _ in self._rules]}"
        )


def _extract_content(message: Any) -> str:
    """Pull the .content off a langchain BaseMessage (tolerates plain
    strings + dicts as a defensive fallback)."""
    if hasattr(message, "content"):
        return str(getattr(message, "content"))
    if isinstance(message, dict):
        return str(message.get("content", ""))
    return str(message)
