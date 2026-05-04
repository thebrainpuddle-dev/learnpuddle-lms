"""Tests for `apps.maic.generation.interactive_post_processor` (MAIC-426)."""
from __future__ import annotations

from apps.maic.generation.interactive_post_processor import (
    post_process_interactive_html,
)


# ── LaTeX delimiter conversion ────────────────────────────────────


class TestLatexDelimiterConversion:
    def test_display_math_dollar_dollar_converted(self):
        html = "<p>The formula $$E = mc^2$$ is famous.</p>"
        out = post_process_interactive_html(html)
        assert r"\[E = mc^2\]" in out
        # Original $$...$$ should be gone
        assert "$$E" not in out

    def test_inline_math_single_dollar_converted(self):
        html = "<p>Let $x = 5$ be the value.</p>"
        out = post_process_interactive_html(html)
        assert r"\(x = 5\)" in out
        assert "$x = 5$" not in out

    def test_mixed_inline_and_display_math(self):
        html = "<p>Inline $a^2 + b^2$ and display $$c^2 = a^2 + b^2$$.</p>"
        out = post_process_interactive_html(html)
        assert r"\(a^2 + b^2\)" in out
        assert r"\[c^2 = a^2 + b^2\]" in out

    def test_inline_math_does_not_match_across_newlines(self):
        """The inline regex excludes newlines so it can't match
        $...$ that crosses paragraph boundaries (false-positive risk)."""
        html = "<p>One $value\nanother$ thing.</p>"
        out = post_process_interactive_html(html)
        # Should NOT have been converted
        assert "\\(value" not in out

    def test_no_math_passes_through_unchanged(self):
        # A doc with `katex` already in the head — the post-processor
        # should not re-inject. (Use lower-case "katex" to match the
        # case-insensitive presence check.)
        html = '<html><head><meta name="katex"></head><body><p>plain</p></body></html>'
        out = post_process_interactive_html(html)
        assert out == html


# ── Script tag protection ────────────────────────────────────────


class TestScriptTagProtection:
    def test_dollar_signs_inside_script_preserved(self):
        """Critical correctness: a script body using jQuery `$` or
        template-literal `$` chars must NOT be mangled by the LaTeX
        converter."""
        original_script = (
            "<script>const sum = $('#total').val(); "
            "console.log(`$${sum}`);</script>"
        )
        html = (
            "<html><head></head><body>"
            + original_script
            + "</body></html>"
        )
        out = post_process_interactive_html(html)
        # The original script must appear in the output verbatim — its
        # $ characters were stashed during conversion and restored
        # unchanged.
        assert original_script in out

    def test_multiple_scripts_each_protected(self):
        html = (
            "<html><head></head><body>"
            '<script>let a = "$x";</script>'
            "<p>real math: $y$</p>"
            "<script>let b = `$$pair$$`;</script>"
            "</body></html>"
        )
        out = post_process_interactive_html(html)
        # Real math converted
        assert r"\(y\)" in out
        # Both scripts unchanged
        assert 'let a = "$x";' in out
        assert "let b = `$$pair$$`;" in out


# ── KaTeX injection ───────────────────────────────────────────────


class TestKatexInjection:
    def test_injects_before_head_close_when_present(self):
        html = "<html><head><title>X</title></head><body></body></html>"
        out = post_process_interactive_html(html)
        # KaTeX CSS link must appear before </head>
        head_close = out.index("</head>")
        katex_css = out.index("katex.min.css")
        assert katex_css < head_close
        # Body content untouched
        assert "<body></body>" in out

    def test_injects_before_body_close_when_no_head(self):
        html = "<html><body><p>x</p></body></html>"
        out = post_process_interactive_html(html)
        body_close = out.index("</body>")
        katex_css = out.index("katex.min.css")
        assert katex_css < body_close

    def test_appends_at_end_when_no_head_or_body(self):
        """Bare HTML fragment with no head/body — KaTeX appends."""
        html = "<p>x</p>"
        out = post_process_interactive_html(html)
        assert out.startswith("<p>x</p>")
        assert "katex.min.css" in out

    def test_does_not_inject_when_katex_already_present(self):
        """Idempotent — running the post-processor twice doesn't
        double-inject."""
        html = "<html><head></head><body><p>$x$</p></body></html>"
        once = post_process_interactive_html(html)
        twice = post_process_interactive_html(once)
        # Same result both times — second run sees "katex" already
        # present and skips injection.
        assert once == twice

    def test_katex_options_include_all_four_delimiters(self):
        """The injected JS configures KaTeX to render \\[...\\],
        \\(...\\), $$...$$, and $...$ — locking the option block so a
        future upstream sync diff is easy."""
        html = "<html><head></head><body></body></html>"
        out = post_process_interactive_html(html)
        # Each delimiter type is configured
        assert "left: '\\\\['" in out  # display \[
        assert "left: '\\\\('" in out  # inline \(
        assert "left: '$$'" in out  # display $$
        assert "left: '$'" in out  # inline $


# ── Idempotency ───────────────────────────────────────────────────


def test_double_invocation_is_idempotent():
    html = "<html><head></head><body><p>$x$ and $$y$$</p></body></html>"
    once = post_process_interactive_html(html)
    twice = post_process_interactive_html(once)
    assert once == twice
