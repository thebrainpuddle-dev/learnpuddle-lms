"""Tests for apps.maic.prompts.loader.

Uses tmp_path to write fake template directories so we don't depend on
the real templates landing (those come in MAIC-204/205). The loader's
behavior is tested in isolation; real-template smoke is part of MAIC-204.
"""
from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from apps.maic.exceptions import MaicConfigError
from apps.maic.prompts import loader as L


@pytest.fixture
def fake_prompts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect the loader at a fresh tmp dir per test, with empty
    templates/ and snippets/ subdirs ready to be populated by the
    test body. Clears the snippet cache between tests."""
    templates = tmp_path / "templates"
    snippets = tmp_path / "snippets"
    templates.mkdir()
    snippets.mkdir()
    monkeypatch.setattr(L, "_TEMPLATES_DIR", templates)
    monkeypatch.setattr(L, "_SNIPPETS_DIR", snippets)
    L.clear_cache()
    yield tmp_path
    L.clear_cache()


def _write_template(root: Path, prompt_id: str, system: str, user: str | None = None):
    d = root / "templates" / prompt_id
    d.mkdir(parents=True)
    (d / "system.md").write_text(system, encoding="utf-8")
    if user is not None:
        (d / "user.md").write_text(user, encoding="utf-8")


def _write_snippet(root: Path, snippet_id: str, content: str):
    (root / "snippets" / f"{snippet_id}.md").write_text(content, encoding="utf-8")


# ── Snippet loading ────────────────────────────────────────────────────


def test_load_snippet_reads_and_strips(fake_prompts_dir):
    _write_snippet(fake_prompts_dir, "speech-guidelines", "  Speak clearly.\n  ")
    assert L.load_snippet("speech-guidelines") == "Speak clearly."


def test_load_snippet_missing_raises_config_error(fake_prompts_dir):
    with pytest.raises(MaicConfigError, match="Snippet not found: nope"):
        L.load_snippet("nope")


def test_load_snippet_caches_disk_reads(fake_prompts_dir):
    _write_snippet(fake_prompts_dir, "x", "first")
    L.load_snippet("x")
    # Mutate the file on disk; cached read should NOT see the new content
    (fake_prompts_dir / "snippets" / "x.md").write_text("second", encoding="utf-8")
    assert L.load_snippet("x") == "first"  # served from cache
    L.clear_cache()
    assert L.load_snippet("x") == "second"  # cache cleared, fresh read


# ── process_snippets ──────────────────────────────────────────────────


def test_process_snippets_replaces_inclusion(fake_prompts_dir):
    _write_snippet(fake_prompts_dir, "guidelines", "Be clear.")
    out = L.process_snippets("Speak: {{snippet:guidelines}}")
    assert out == "Speak: Be clear."


def test_process_snippets_replaces_multiple(fake_prompts_dir):
    _write_snippet(fake_prompts_dir, "a", "AAA")
    _write_snippet(fake_prompts_dir, "b", "BBB")
    out = L.process_snippets("{{snippet:a}}/{{snippet:b}}")
    assert out == "AAA/BBB"


def test_process_snippets_missing_raises(fake_prompts_dir):
    with pytest.raises(MaicConfigError):
        L.process_snippets("hello {{snippet:not-there}}")


# ── process_conditional_blocks ────────────────────────────────────────


def test_conditional_kept_when_truthy(fake_prompts_dir):
    out = L.process_conditional_blocks(
        "Hello{{#if showBio}}, my bio is X{{/if}}.",
        {"showBio": True},
    )
    assert out == "Hello, my bio is X."


def test_conditional_dropped_when_falsy(fake_prompts_dir):
    out = L.process_conditional_blocks(
        "Hello{{#if showBio}}, my bio is X{{/if}}.",
        {"showBio": False},
    )
    assert out == "Hello."


def test_conditional_dropped_when_missing(fake_prompts_dir):
    out = L.process_conditional_blocks(
        "Hello{{#if showBio}}!{{/if}}",
        {},
    )
    assert out == "Hello"


def test_conditional_does_not_nest(fake_prompts_dir):
    """Documenting the known non-feature: blocks DO NOT nest. With nested
    input the outer match's content captures the literal inner `{{#if}}`,
    and a trailing literal `{{/if}}` survives in the output. Real
    templates avoid nesting; tests in MAIC-204 grep for accidental
    nested `{{#if}}` patterns."""
    template = "{{#if outer}}A{{#if inner}}B{{/if}}C{{/if}}"
    out = L.process_conditional_blocks(template, {"outer": True, "inner": True})
    # Outer matched `{{#if outer}}A{{#if inner}}B{{/if}}` (content=`A{{#if inner}}B`);
    # trailing `C{{/if}}` is left verbatim.
    assert out == "A{{#if inner}}BC{{/if}}"


# ── interpolate_variables ─────────────────────────────────────────────


def test_interpolate_basic_string(fake_prompts_dir):
    out = L.interpolate_variables("Hello {{agentName}}", {"agentName": "Alice"})
    assert out == "Hello Alice"


def test_interpolate_unknown_left_intact(fake_prompts_dir):
    out = L.interpolate_variables("Hi {{unknownVar}}", {})
    assert out == "Hi {{unknownVar}}"


def test_interpolate_dict_values_become_pretty_json(fake_prompts_dir):
    out = L.interpolate_variables(
        "Cfg: {{config}}",
        {"config": {"a": 1, "b": [2, 3]}},
    )
    # json.dumps with indent=2 — multi-line
    assert "\"a\": 1" in out
    assert "\"b\": [" in out


def test_interpolate_kebab_case_passes_through(fake_prompts_dir):
    """Per upstream: `\\w+` doesn't match hyphens; kebab placeholders
    are left untouched."""
    out = L.interpolate_variables("X {{kebab-case}}", {"kebab-case": "should-not-replace"})
    assert out == "X {{kebab-case}}"


# ── load_prompt ───────────────────────────────────────────────────────


def test_load_prompt_returns_loaded_prompt(fake_prompts_dir):
    _write_template(fake_prompts_dir, "test-id", "system text", "user text")
    p = L.load_prompt("test-id")
    assert p is not None
    assert p.id == "test-id"
    assert p.systemPrompt == "system text"
    assert p.userPromptTemplate == "user text"


def test_load_prompt_user_is_optional(fake_prompts_dir):
    _write_template(fake_prompts_dir, "no-user", "just system")
    p = L.load_prompt("no-user")
    assert p is not None
    assert p.userPromptTemplate == ""


def test_load_prompt_missing_returns_none(fake_prompts_dir):
    assert L.load_prompt("nonexistent") is None


def test_load_prompt_resolves_snippets_at_load_time(fake_prompts_dir):
    _write_snippet(fake_prompts_dir, "guide", "BE NICE")
    _write_template(fake_prompts_dir, "id", "Rules: {{snippet:guide}}")
    p = L.load_prompt("id")
    assert p is not None
    assert p.systemPrompt == "Rules: BE NICE"


def test_load_prompt_missing_snippet_raises(fake_prompts_dir):
    """A typo in `{{snippet:foo}}` must fail loud — we never want to
    ship literal `{{snippet:foo}}` text to the LLM."""
    _write_template(fake_prompts_dir, "broken", "Hello {{snippet:does-not-exist}}")
    with pytest.raises(MaicConfigError):
        L.load_prompt("broken")


# ── build_prompt — full pipeline ──────────────────────────────────────


def test_build_prompt_full_pipeline(fake_prompts_dir):
    _write_snippet(fake_prompts_dir, "rules", "rule-one")
    _write_template(
        fake_prompts_dir,
        "demo",
        "Hello {{name}}.\nRules: {{snippet:rules}}.\n{{#if mood}}I'm {{mood}}.{{/if}}",
        "User says: {{question}}",
    )

    out = L.build_prompt("demo", {"name": "Alice", "mood": "happy", "question": "hi?"})
    assert out is not None
    assert out.system == "Hello Alice.\nRules: rule-one.\nI'm happy."
    assert out.user == "User says: hi?"


def test_build_prompt_skips_missing_template(fake_prompts_dir):
    assert L.build_prompt("missing", {}) is None


def test_build_prompt_omitted_conditional(fake_prompts_dir):
    _write_template(fake_prompts_dir, "cond", "{{#if x}}gated{{/if}}static")
    out = L.build_prompt("cond", {"x": False})
    assert out is not None
    assert out.system == "static"


# ── list helpers ──────────────────────────────────────────────────────


def test_list_available_prompts(fake_prompts_dir):
    _write_template(fake_prompts_dir, "alpha", "A")
    _write_template(fake_prompts_dir, "beta", "B")
    assert L.list_available_prompts() == ["alpha", "beta"]


def test_list_available_snippets(fake_prompts_dir):
    _write_snippet(fake_prompts_dir, "x", "X")
    _write_snippet(fake_prompts_dir, "y", "Y")
    assert L.list_available_snippets() == ["x", "y"]
