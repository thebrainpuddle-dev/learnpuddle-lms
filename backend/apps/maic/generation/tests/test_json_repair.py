"""Tests for `apps.maic.generation.json_repair` (MAIC-425).

Mirrors upstream's behavioral expectations across the 3-strategy
parser stack. Worst-case JSON inputs collected from upstream's
known-bad LLM outputs (LaTeX in strings, truncated arrays, code-block
wrappers, control characters in Chinese text, etc.).
"""
from __future__ import annotations

import pytest

from apps.maic.generation.json_repair import (
    parse_json_response,
    try_parse_json,
)


# ── parse_json_response: 3-strategy fallback ──────────────────────


class TestParseJsonResponse:
    def test_plain_json_response(self):
        assert parse_json_response('{"a": 1}') == {"a": 1}
        assert parse_json_response("[1, 2, 3]") == [1, 2, 3]

    def test_json_inside_markdown_code_block(self):
        text = '```json\n{"name": "test"}\n```'
        assert parse_json_response(text) == {"name": "test"}

    def test_json_inside_unlabeled_code_block(self):
        text = "```\n[1, 2]\n```"
        assert parse_json_response(text) == [1, 2]

    def test_json_with_prose_prefix_and_suffix(self):
        text = (
            "Sure! Here is the data you requested:\n"
            '{"foo": "bar"}\n'
            "Let me know if you need anything else."
        )
        assert parse_json_response(text) == {"foo": "bar"}

    def test_array_after_prose(self):
        text = 'Here is the list: [{"id": 1}, {"id": 2}]'
        assert parse_json_response(text) == [{"id": 1}, {"id": 2}]

    def test_picks_first_of_multiple_code_blocks(self):
        """When there are multiple code blocks, the first parseable
        one wins (mirrors upstream's matchAll iteration order)."""
        text = '```json\n{"first": true}\n```\nthen ```json\n{"second": true}\n```'
        assert parse_json_response(text) == {"first": True}

    def test_returns_none_for_completely_unparseable(self):
        # Truly garbage inputs — no brackets, no quotes that could be
        # interpreted as JSON. json-repair is aggressive enough that
        # ANY bracket-shaped fragment will get coerced into something;
        # only inputs with zero JSON-shape fail all 3 strategies.
        assert parse_json_response("this has no JSON anywhere") is None
        assert parse_json_response("") is None

    def test_nested_objects_in_strings_dont_confuse_extraction(self):
        text = '{"a": "this is { not a brace } in a string", "b": [1, 2]}'
        result = parse_json_response(text)
        assert result["a"] == "this is { not a brace } in a string"
        assert result["b"] == [1, 2]

    def test_escaped_quotes_in_string_dont_confuse_extraction(self):
        text = '{"msg": "he said \\"hi\\" to me"}'
        result = parse_json_response(text)
        assert result["msg"] == 'he said "hi" to me'


# ── try_parse_json: 4-attempt fallback ────────────────────────────


class TestTryParseJson:
    def test_attempt_1_plain_json(self):
        assert try_parse_json('{"x": 1}') == {"x": 1}

    def test_attempt_2_latex_escape_fix(self):
        r"""LaTeX commands like \Rightarrow inside strings break plain
        json.loads (\R is not a valid JSON escape, unlike \f or \n);
        the Fix-1 regex double-escapes them so the parser sees \\R."""
        # Use raw string + explicit double-quote so the python literal
        # contains exactly: {"formula": "\Rightarrow"}
        text = r'{"formula": "\Rightarrow"}'
        result = try_parse_json(text)
        assert result is not None
        assert "Rightarrow" in result["formula"]

    def test_attempt_2_truncated_array(self):
        """Stage-2 fix: truncated array gets closed at the last
        complete object."""
        text = '[{"id": 1}, {"id": 2}, {"id": 3'  # truncated mid-object
        result = try_parse_json(text)
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 2  # only the 2 complete objects

    def test_attempt_2_truncated_object(self):
        """Stage-2 fix: truncated object gets close-braces appended."""
        text = '{"a": {"b": {"c": 1}'
        result = try_parse_json(text)
        assert result == {"a": {"b": {"c": 1}}}

    def test_attempt_3_jsonrepair_lib(self):
        """The python json-repair package handles malformed cases the
        regex fixes don't catch. E.g., trailing commas or unquoted keys."""
        # Trailing comma — invalid JSON, but json-repair fixes it.
        text = '[1, 2, 3,]'
        result = try_parse_json(text)
        assert result == [1, 2, 3]

    def test_attempt_4_strips_control_characters(self):
        """Control chars in a string break json.loads; Stage-4 strips
        non-whitespace controls and escapes whitespace controls."""
        # ASCII 0x01 (SOH control char) — invalid in JSON strings
        text = '{"text": "hello\x01world"}'
        result = try_parse_json(text)
        # The Fix-4 path strips the control char (returns "helloworld")
        assert result is not None
        assert "hello" in result["text"]
        assert "world" in result["text"]

    def test_returns_none_for_genuinely_garbage_input(self):
        assert try_parse_json("not json at all <<<") is None
        assert try_parse_json("") is None

    def test_chinese_text_with_unescaped_quotes(self):
        """A real-world failure mode: LLM output with unescaped quotes
        inside Chinese-language string content. json-repair handles
        this via its quote-balancing heuristics."""
        text = '{"text": "他说"你好"了"}'
        result = try_parse_json(text)
        # json-repair fixes this in Attempt 3; result must be a dict
        # with a non-empty text field.
        assert result is not None
        assert isinstance(result, dict)
        assert "text" in result


