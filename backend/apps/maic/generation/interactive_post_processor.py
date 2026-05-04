"""Interactive HTML Post-Processor.

Direct port of upstream `lib/generation/interactive-post-processor.ts`
(160 lines).

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/generation/interactive-post-processor.ts
    /Volumes/CrucialX9/OpenMAIC/lib/generation/interactive-post-processor.ts

Used by:
    - apps.maic.generation.scene_generator (Phase 4 / MAIC-422.x) —
      runs after interactive scene HTML is generated to prepare the
      content for browser rendering.

Handles:
  - LaTeX delimiter conversion ($$...$$ → \\[...\\], $...$ → \\(...\\))
  - KaTeX CSS / JS / auto-render / MutationObserver injection
  - Script tag protection during LaTeX conversion (script bodies may
    contain $ characters that the regex would otherwise mangle)
"""
from __future__ import annotations

import re


# ── Public API ────────────────────────────────────────────────────


def post_process_interactive_html(html: str) -> str:
    """Post-process generated interactive HTML.

    Mirrors upstream `postProcessInteractiveHtml`. Converts LaTeX
    delimiters and injects KaTeX rendering resources if not already
    present. The "katex" presence check is case-insensitive.
    """
    processed = _convert_latex_delimiters(html)
    if "katex" not in processed.lower():
        processed = _inject_katex(processed)
    return processed


# ── Internal: LaTeX delimiter conversion ──────────────────────────


_SCRIPT_BLOCK_RE = re.compile(
    r"<script[^>]*>[\s\S]*?</script>", re.IGNORECASE
)
_DISPLAY_MATH_RE = re.compile(r"\$\$([^$]+)\$\$")
# Inline math: non-greedy match, exclude newlines to avoid false positives.
_INLINE_MATH_RE = re.compile(r"\$([^$\n]+?)\$")


def _convert_latex_delimiters(html: str) -> str:
    """Convert $$...$$ → \\[...\\] (display) and $...$ → \\(...\\)
    (inline), while protecting <script> bodies from accidental
    rewrites.

    Mirrors upstream `convertLatexDelimiters`. Uses placeholder swap
    (not lookbehinds) to handle script bodies containing $ chars
    that would otherwise confuse re.sub's substitution syntax.
    """
    script_blocks: list[str] = []

    def _stash_script(match: re.Match[str]) -> str:
        script_blocks.append(match.group(0))
        return f"__SCRIPT_BLOCK_{len(script_blocks) - 1}__"

    processed = _SCRIPT_BLOCK_RE.sub(_stash_script, html)

    # Convert display math: $$...$$ → \[...\]
    # `\\[$1\\]` in TS becomes `\\[\\1\\]` in Python re.sub backrefs;
    # use a string literal with escaped backslashes.
    processed = _DISPLAY_MATH_RE.sub(r"\\[\1\\]", processed)

    # Convert inline math: $...$ → \(...\)
    processed = _INLINE_MATH_RE.sub(r"\\(\1\\)", processed)

    # Restore script blocks using string find + slice rather than
    # re.sub — re.sub interprets `$` and backreferences in the
    # replacement string, which would mangle script bodies that
    # contain those characters.
    for i, script in enumerate(script_blocks):
        placeholder = f"__SCRIPT_BLOCK_{i}__"
        idx = processed.find(placeholder)
        if idx != -1:
            processed = (
                processed[:idx]
                + script
                + processed[idx + len(placeholder):]
            )

    return processed


# ── Internal: KaTeX injection ─────────────────────────────────────


# Verbatim from upstream — line-for-line copy of the JS payload so
# any future upstream sync only diffs against ONE owned region.
_KATEX_INJECTION = '''
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
<script>
document.addEventListener("DOMContentLoaded", function() {
    const katexOptions = {
        delimiters: [
            {left: '\\\\[', right: '\\\\]', display: true},
            {left: '\\\\(', right: '\\\\)', display: false},
            {left: '$$', right: '$$', display: true},
            {left: '$', right: '$', display: false}
        ],
        throwOnError: false,
        strict: false,
        trust: true
    };

    let renderTimeout;
    function safeRender() {
        if (renderTimeout) clearTimeout(renderTimeout);
        renderTimeout = setTimeout(() => {
            renderMathInElement(document.body, katexOptions);
        }, 100);
    }

    renderMathInElement(document.body, katexOptions);

    const observer = new MutationObserver((mutations) => {
        let shouldRender = false;
        mutations.forEach((mutation) => {
            if (mutation.target &&
                mutation.target.className &&
                typeof mutation.target.className === 'string' &&
                mutation.target.className.includes('katex')) {
                return;
            }
            shouldRender = true;
        });

        if (shouldRender) {
            safeRender();
        }
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true
    });

    setInterval(() => {
        const text = document.body.innerText;
        if (text.includes('\\\\(') || text.includes('$$')) {
            safeRender();
        }
    }, 2000);
});
</script>'''


def _inject_katex(html: str) -> str:
    """Inject KaTeX CSS / JS / auto-render / MutationObserver.

    Mirrors upstream `injectKatex`. Insertion priority:
      1. Before </head> (preferred)
      2. Before </body> (fallback when no <head>)
      3. Append at end (last resort)

    Uses string find + slice rather than re.sub or str.replace because
    the injection payload contains $ characters that those APIs would
    interpret as substitution patterns.
    """
    head_close_idx = html.find("</head>")
    if head_close_idx != -1:
        return (
            html[:head_close_idx]
            + _KATEX_INJECTION
            + "\n</head>"
            + html[head_close_idx + len("</head>"):]
        )

    body_close_idx = html.find("</body>")
    if body_close_idx != -1:
        return (
            html[:body_close_idx]
            + _KATEX_INJECTION
            + "\n</body>"
            + html[body_close_idx + len("</body>"):]
        )

    # Last resort: append at end
    return html + _KATEX_INJECTION
