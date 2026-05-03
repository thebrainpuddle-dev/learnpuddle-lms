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
 *   - Reads element.lines (populated by ActionEngine on add) for
 *     stable per-line keys that survive wb_edit_code splices
 *   - Falls back to splitting `element.code` on '\n' when lines isn't
 *     populated (test-direct construction, static demo)
 *   - HAST → JSX via a small recursive renderer (~30 lines below) so
 *     we don't need a transitive `hast-util-to-jsx-runtime` dep
 *
 * Phase 2 deferrals signposted:
 *   - Typing-stutter animation (upstream BaseCodeElement.tsx:78-117)
 *     — agent paces the timeline via the post-add wait, no visual
 *     delay needed for Phase 2
 *   - File-tab UI / line numbers chrome
 *   - Per-line edit animations (highlight insertions in green / deletes
 *     in red) — handled by future polish; MAIC-214.2 ships the
 *     splice mechanics first
 *   - Theme switching (light/dark) — fixed to `github` light theme
 *
 * Theme: highlight.js's github.css is imported once at the module
 * level. The `.hljs-keyword`, `.hljs-string`, etc. classes that
 * lowlight emits map to its colour palette.
 */
import { useMemo } from 'react';
import { common, createLowlight } from 'lowlight';
import 'highlight.js/styles/github.css';

import type { WhiteboardCodeElement } from '../../../lib/maic-v2/whiteboard-state';


// ── Lowlight singleton ─────────────────────────────────────────────


let _lowlight: ReturnType<typeof createLowlight> | null = null;

function getLowlight() {
  if (!_lowlight) _lowlight = createLowlight(common);
  return _lowlight;
}


// ── HAST → JSX ──────────────────────────────────────────────────────


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


/**
 * Highlight one source line via lowlight. Failures (unknown grammar)
 * fall through to plain text rendering.
 */
function highlightLine(language: string, content: string): React.ReactNode {
  const lowlight = getLowlight();
  try {
    const tree = lowlight.highlight(language, content) as HastNode;
    return renderHast(tree, 'content');
  } catch {
    return content;
  }
}


// ── Component ──────────────────────────────────────────────────────


const DEFAULT_WIDTH = 400;
const DEFAULT_HEIGHT = 240;
const HEADER_HEIGHT = 22;


export interface CodeElementProps {
  element: WhiteboardCodeElement;
}


export function CodeElement({ element }: CodeElementProps) {
  const elementKey = element.elementId ?? element.id;
  const width = element.width ?? DEFAULT_WIDTH;
  const height = element.height ?? DEFAULT_HEIGHT;
  const language = (element.language ?? 'plaintext').toLowerCase();
  const fileName = element.fileName;

  // Resolve line list: prefer `element.lines` (populated by the
  // ActionEngine on add — stable IDs that survive wb_edit_code
  // splices). Fall back to splitting `element.code` for callsites
  // that build a WhiteboardCodeElement directly without going through
  // the engine (tests, the static demo).
  const lines = useMemo(() => {
    if (element.lines && element.lines.length > 0) return element.lines;
    return (element.code ?? '').split('\n').map((content, i) => ({
      id: `L${i + 1}`,
      content,
    }));
  }, [element.lines, element.code]);

  // Memoise highlight output per line. Recomputes when `lines`
  // identity changes (every wb_edit_code splice returns a fresh
  // array — that's fine).
  const highlighted = useMemo(
    () => lines.map((line) => highlightLine(language, line.content)),
    [lines, language],
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
            {lines.map((line, i) => (
              <div
                key={line.id}
                data-line-id={line.id}
                className="whitespace-pre"
                style={{ minHeight: '1.4em', lineHeight: 1.4 }}
              >
                {/* Empty-line edge case: render a single space so the
                    row keeps its vertical rhythm. */}
                {line.content === '' ? ' ' : highlighted[i]}
              </div>
            ))}
          </code>
        </pre>
      </div>
    </div>
  );
}
