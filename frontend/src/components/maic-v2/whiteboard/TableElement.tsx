/**
 * TableElement — renders a wb_draw_table element.
 *
 * Source: THU-MAIC/OpenMAIC main components/slide-renderer/components/
 *         element/TableElement/StaticTable.tsx (heavily simplified —
 *         no merged cells, no theme alternating-row colors, no
 *         per-cell styles; Phase 2 protocol's wb_draw_table ships a
 *         flat string[][] grid + an optional outline + an optional
 *         single theme color).
 *
 * Wire shape (apps/maic/protocol/actions.py WbDrawTableAction):
 *   id, elementId?, x, y, width, height, data: string[][],
 *   outline?: { width, style, color }, theme?: { color }
 *
 * Phase 2 deferrals (signposted): merged cells (colspan/rowspan),
 * alternating row backgrounds, per-cell text styles, row/col header
 * sub-themes — Phase 8+. Upstream's StaticTable is 125 lines doing all
 * of this; we ship the minimum that renders correctly for the agent's
 * intent.
 */
import type { Action } from '../../../lib/maic-v2/action-types';

type TableAction = Extract<Action, { type: 'wb_draw_table' }>;

const DEFAULT_OUTLINE_WIDTH = 1;
const DEFAULT_OUTLINE_COLOR = '#cccccc';
const DEFAULT_OUTLINE_STYLE: 'solid' | 'dashed' = 'solid';

export interface TableElementProps {
  element: TableAction;
}

export function TableElement({ element }: TableElementProps) {
  const elementKey = element.elementId ?? element.id;
  const data = element.data ?? [];
  const outlineWidth = element.outline?.width ?? DEFAULT_OUTLINE_WIDTH;
  const outlineStyle = element.outline?.style ?? DEFAULT_OUTLINE_STYLE;
  const outlineColor = element.outline?.color ?? DEFAULT_OUTLINE_COLOR;
  const themeColor = element.theme?.color;

  const border = `${outlineWidth}px ${outlineStyle} ${outlineColor}`;

  return (
    <div
      data-testid="maic-v2-wb-table"
      data-element-id={elementKey}
      className="absolute overflow-hidden"
      style={{
        top: `${element.y}px`,
        left: `${element.x}px`,
        width: `${element.width}px`,
        height: `${element.height}px`,
      }}
    >
      <table
        className="w-full h-full"
        style={{ borderCollapse: 'collapse', tableLayout: 'fixed' }}
      >
        <tbody>
          {data.map((row, rowIdx) => {
            const isHeader = rowIdx === 0 && themeColor !== undefined;
            return (
              <tr key={rowIdx}>
                {row.map((cell, colIdx) => (
                  <td
                    key={colIdx}
                    style={{
                      border,
                      padding: '5px',
                      verticalAlign: 'middle',
                      wordBreak: 'break-word',
                      backgroundColor: isHeader ? themeColor : undefined,
                      color: isHeader ? '#ffffff' : undefined,
                      fontWeight: isHeader ? 600 : undefined,
                    }}
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
