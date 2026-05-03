/**
 * TextElement — renders a wb_draw_text element.
 *
 * Source: THU-MAIC/OpenMAIC main components/slide-renderer/components/
 *         element/TextElement/BaseTextElement.tsx (heavily simplified —
 *         no shadows, no outlines, no rotation; Phase 2 protocol's
 *         wb_draw_text shape is intentionally minimal).
 *
 * Wire shape (apps/maic/protocol/actions.py WbDrawTextAction):
 *   id, elementId?, content, x, y, width?, height?, fontSize?, color?
 *
 * Content can be HTML or plain text. Mirrors upstream engine.ts:347-350
 * — if content has no leading `<`, we wrap it in a `<p>` with the
 * fontSize. Otherwise we trust the agent's HTML.
 *
 * data-element-id attribute is set to enable SpotlightOverlay
 * (MAIC-215) DOM measurement of this element.
 */
import type { Action } from '../../../lib/maic-v2/action-types';

type TextAction = Extract<Action, { type: 'wb_draw_text' }>;

export interface TextElementProps {
  element: TextAction;
}

export function TextElement({ element }: TextElementProps) {
  const fontSize = element.fontSize ?? 18;
  const width = element.width ?? 400;
  const height = element.height ?? 100;
  const color = element.color ?? '#333333';
  const elementKey = element.elementId ?? element.id;

  // Match upstream engine.ts:347-350: if content has no leading tag,
  // wrap in a <p> with the requested fontSize.
  const html = element.content.startsWith('<')
    ? element.content
    : `<p style="font-size:${fontSize}px;margin:0;">${element.content}</p>`;

  return (
    <div
      data-testid="maic-v2-wb-text"
      data-element-id={elementKey}
      className="absolute"
      style={{
        top: `${element.y}px`,
        left: `${element.x}px`,
        width: `${width}px`,
        minHeight: `${height}px`,
        color,
        lineHeight: 1.5,
        wordBreak: 'break-word',
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
