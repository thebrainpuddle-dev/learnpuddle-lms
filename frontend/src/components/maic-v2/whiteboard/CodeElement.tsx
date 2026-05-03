/**
 * CodeElement — renders a wb_draw_code element with syntax highlighting.
 *
 * Source: THU-MAIC/OpenMAIC main components/slide-renderer/components/
 *         element/CodeElement/BaseCodeElement.tsx (630 lines —
 *         heavily simplified). Upstream uses Shiki with 17 pre-loaded
 *         languages + a typing animation; we use lowlight (already
 *         installed at frontend/package.json:51) which is synchronous,
 *         smaller, and outputs HAST instead of Shiki's HTML strings.
 *
 * Wire shape (apps/maic/protocol/actions.py WbDrawCodeAction):
 *   id, elementId?, language, code, x, y, width?, height?, fileName?
 *
 * Architecture:
 *   - Module-level lazy singleton for the lowlight instance (registers
 *     `common` languages once)
 *   - useMemo-cached HAST tree per (language, code) tuple
 *   - HAST → JSX via a small recursive renderer (~30 lines below) so
 *     we don't need a transitive `hast-util-to-jsx-runtime` dep
 *   - Line splitting at render time: code.split('\n') → stable
 *     deterministic IDs `L1, L2, ...` per index. MAIC-214.2 will
 *     introduce truly stable IDs when wb_edit_code lands.
 *
 * Phase 2 deferrals signposted:
 *   - Typing-stutter animation (upstream BaseCodeElement.tsx:78-117)
 *     — agent paces the timeline via the 800 ms post-add wait, no
 *     visual delay needed for Phase 2
 *   - File-tab UI / line numbers chrome
 *   - Per-line edit animations (highlight insertions in green / deletes
 *     in red) — handled by MAIC-214.2 once stable IDs land
 *   - Theme switching (light/dark) — fixed to `github` light theme
 *
 * Theme: highlight.js's github.css is imported once at the module
 * level. The `.hljs-keyword`, `.hljs-string`, etc. classes that
 * lowlight emits map to its colour palette.
 */
import { useMemo } from 'react';
import { common, createLowlight } from 'lowlight';
import 'highlight.js/styles/github.css';

import type { Action } from '../../../lib/maic-v2/action-types';

type CodeAction = Extract<Action, { type: 'wb_draw_code' }>;


// ── Lowlight singleton ─────────────────────────────────────────────


let _lowlight: ReturnType<typeof createLowlight> | null = null;

function getLowlight() {
  if (!_lowlight) _lowlight = createLowlight(common);
  return _lowlight;
}


// ── HAST → JSX ──────────────────────────────────────────────────────


/**
 * HAST node shape we care about. lowlight emits `root` containing a
 * mix of `text` and `element` children; elements may have a
 * `properties.className` array (highlight.js token names).
 */
type HastNode =
  | { type: 'text'; value: string }
  | {
      type: 'element';
      tagName?: string;
      properties?: { className?: string[] | string };
      children?: HastNode[];
    }
  | {
      type: 'root';
      children?: HastNode[];
    };


function renderHast(node: HastNode, key: string | number): React.ReactNode {
  if (node.type === 'text') return node.value;
  if (node.type === 'root') {
    return (node.children ?? []).map((c, i) => renderHast(c, i));
  }
  // element
  const className = Array.isArray(node.properties?.className)
    ? node.properties!.className!.join(' ')
    : node.properties?.className;
  const tag = (node.tagName ?? 'span') as 'span';
  return (
    <span key={key} className={className}>
      {(node.children ?? []).map((c, i) => renderHast(c, i))}
    </span>
  );
}


// ── Line splitting ─────────────────────────────────────────────────


/**
 * Split highlighted source into per-line HAST trees. Lowlight returns
 * a single `root` for the whole source; to render line-by-line we
 * highlight each line independently. Slightly redundant cost vs. one
 * highlight call, but for typical code blocks (<200 lines) it's
 * imperceptible and keeps the per-line key model trivial.
 */
function highlightLines(language: string, code: string): React.ReactNode[] {
  const lowlight = getLowlight();
  const lines = code.split('\n');
  return lines.map((line, i) => {
    let tree: HastNode;
    try {
      tree = lowlight.highlight(language, line) as HastNode;
    } catch {
      // Unknown language → fall through to plain text rendering
      return [line];
    }
    return renderHast(tree, `L${i + 1}-content`);
  });
}


// ── Component ──────────────────────────────────────────────────────


const DEFAULT_WIDTH = 400;
const DEFAULT_HEIGHT = 240;
const HEADER_HEIGHT = 22;  // when fileName present


export interface CodeElementProps {
  element: CodeAction;
}


export function CodeElement({ element }: CodeElementProps) {
  const elementKey = element.elementId ?? element.id;
  const width = element.width ?? DEFAULT_WIDTH;
  const height = element.height ?? DEFAULT_HEIGHT;
  const language = (element.language ?? 'plaintext').toLowerCase();
  const code = element.code ?? '';
  const fileName = element.fileName;

  // Memoise the line-highlighted JSX per (language, code) pair so
  // re-renders from unrelated state changes don't re-walk the HAST.
  const renderedLines = useMemo(
    () => highlightLines(language, code),
    [language, code],
  );

  return (
    <div
      data-testid="maic-v2-wb-code"
      data-element-id={elementKey}
      data-language={language}
      className="absolute overflow-hidden rounded border bg-white shadow-sm font-mono"
      style={{
        top: `${element.y}px`,
        left: `${element.x}px`,
        width: `${width}px`,
        height: `${height}px`,
        fontSize: '13px',
      }}
    >
      {fileName && (
        <div
          data-testid="maic-v2-wb-code-filename"
          className="px-2 border-b bg-gray-50 text-gray-600 text-xs truncate"
          style={{ height: `${HEADER_HEIGHT}px`, lineHeight: `${HEADER_HEIGHT}px` }}
        >
          {fileName}
        </div>
      )}

      <div
        className="overflow-auto p-2"
        style={{
          height: fileName ? `calc(100% - ${HEADER_HEIGHT}px)` : '100%',
        }}
      >
        <pre className="hljs m-0" style={{ background: 'transparent', padding: 0 }}>
          <code className={`language-${language}`}>
            {renderedLines.map((line, i) => (
              <div
                key={`L${i + 1}`}
                data-line-id={`L${i + 1}`}
                className="whitespace-pre"
                style={{ minHeight: '1.4em', lineHeight: 1.4 }}
              >
                {/*
                  Empty line edge case: an empty string would collapse
                  the div height; insert a non-breaking space so the
                  line takes vertical space.
                */}
                {(Array.isArray(line) ? line : [line]).length === 0 ||
                (Array.isArray(line) && line.length === 1 && line[0] === '') ? (
                  ' '
                ) : (
                  line
                )}
              </div>
            ))}
          </code>
        </pre>
      </div>
    </div>
  );
}
