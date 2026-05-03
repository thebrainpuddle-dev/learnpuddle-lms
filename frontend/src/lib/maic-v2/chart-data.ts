/**
 * Chart data adapter — converts the wire-format column-major
 * {labels, legends, series: number[][]} (modelled on upstream
 * echarts) into recharts-friendly row-major shapes.
 *
 * Used by:
 *   - frontend/src/components/maic-v2/whiteboard/ChartElement.tsx (MAIC-213.2)
 *
 * Source: THU-MAIC/OpenMAIC main components/slide-renderer/components/
 *         element/ChartElement/chartOption.ts (the per-chartType data
 *         shape decisions are mirrored here; the actual recharts
 *         components live in ChartElement.tsx).
 *
 * Why a separate module?
 *   - Pure function, fully test-able without React or recharts
 *   - Highest-risk piece of MAIC-213 per the Phase 2 plan — isolating
 *     it lets us land it as MAIC-213.1 with bullet-proof coverage
 *     before we ship the renderer in 213.2
 *
 * Design:
 *   - Discriminated union return type — the ChartElement switches on
 *     `kind` to pick the right recharts component
 *   - Defensive: empty/short series, missing legends, mismatched
 *     label/series lengths all return a renderable shape rather than
 *     throwing — the agent's intent is best-effort, not protocol-
 *     guaranteed
 */
import type { Action } from './action-types';


type ChartAction = Extract<Action, { type: 'wb_draw_chart' }>;
export type ChartType = ChartAction['chartType'];
export type ChartData = ChartAction['data'];

/** Upstream default theme (engine.ts:414). */
export const DEFAULT_THEME_COLORS: readonly string[] = [
  '#5b9bd5',
  '#ed7d31',
  '#a5a5a5',
  '#ffc000',
  '#4472c4',
] as const;


// ── Output shape ───────────────────────────────────────────────────


export interface CartesianRow {
  /** x-axis category for bar/line/area; ignored on the "column"
   *  variant which swaps axes (see ChartElement). */
  name: string;
  /** Per-legend numeric values; key is the legend name (or `series-N`
   *  when no legend supplied). */
  [seriesKey: string]: string | number;
}

export interface PieRow {
  name: string;
  value: number;
}

export interface RadarRow {
  subject: string;
  [seriesKey: string]: string | number;
}

export interface ScatterRow {
  x: number;
  y: number;
}

export type RechartsData =
  | { kind: 'cartesian'; chartType: 'bar' | 'column' | 'line' | 'area'; rows: CartesianRow[]; seriesNames: string[] }
  | { kind: 'pie'; chartType: 'pie' | 'ring'; rows: PieRow[] }
  | { kind: 'radar'; rows: RadarRow[]; seriesNames: string[] }
  | { kind: 'scatter'; rows: ScatterRow[] };


// ── Helpers ────────────────────────────────────────────────────────


/**
 * Resolve a legend name for series index `k`. Falls back to
 * `series-1`, `series-2`, … when the wire-format `legends` array is
 * shorter than `series[]` (which happens when an agent emits a
 * single-series chart and forgets the legend).
 */
function legendName(legends: readonly string[] | undefined, k: number): string {
  return legends?.[k]?.trim() || `series-${k + 1}`;
}


// ── Transform ──────────────────────────────────────────────────────


/**
 * Convert upstream's column-major chart payload into the row-major
 * shape recharts wants. Pure: never mutates `data`.
 *
 * Behaviour by chartType:
 *
 *   bar / line / area
 *     rows[i] = { name: labels[i], [legendName(0)]: series[0][i], ... }
 *     One row per category, one column per series.
 *
 *   column
 *     Same shape as bar; ChartElement.tsx renders with
 *     `<BarChart layout="vertical">` so the bars run horizontally.
 *
 *   pie / ring
 *     rows[i] = { name: labels[i], value: series[0][i] }
 *     Single-series only; series[k>0] is ignored. Mirrors upstream
 *     chartOption.ts:178-183.
 *
 *   radar
 *     rows[i] = { subject: labels[i], [legendName(0)]: series[0][i], ... }
 *     Mirrors the cartesian shape but uses `subject` as the spoke key
 *     (recharts RadarChart's `dataKey` prop).
 *
 *   scatter
 *     rows[i] = { x: series[0][i], y: series[1][i] ?? series[0][i] }
 *     Mirrors upstream chartOption.ts:312-317 — when a second series
 *     is absent, x and y collapse so the scatter plots y=x.
 */
export function toRechartsData(chartType: ChartType, data: ChartData): RechartsData {
  const labels = data?.labels ?? [];
  const legends = data?.legends ?? [];
  const series = data?.series ?? [];

  switch (chartType) {
    case 'bar':
    case 'column':
    case 'line':
    case 'area': {
      const seriesNames = series.map((_, k) => legendName(legends, k));
      const rows: CartesianRow[] = labels.map((label, i) => {
        const row: CartesianRow = { name: String(label) };
        series.forEach((vals, k) => {
          row[seriesNames[k]] = numberAt(vals, i);
        });
        return row;
      });
      return { kind: 'cartesian', chartType, rows, seriesNames };
    }

    case 'pie':
    case 'ring': {
      const first = series[0] ?? [];
      const rows: PieRow[] = labels.map((label, i) => ({
        name: String(label),
        value: numberAt(first, i),
      }));
      return { kind: 'pie', chartType, rows };
    }

    case 'radar': {
      const seriesNames = series.map((_, k) => legendName(legends, k));
      const rows: RadarRow[] = labels.map((label, i) => {
        const row: RadarRow = { subject: String(label) };
        series.forEach((vals, k) => {
          row[seriesNames[k]] = numberAt(vals, i);
        });
        return row;
      });
      return { kind: 'radar', rows, seriesNames };
    }

    case 'scatter': {
      const xs = series[0] ?? [];
      const ys = series[1] ?? series[0] ?? [];
      const rows: ScatterRow[] = xs.map((x, i) => ({
        x: Number(x) || 0,
        y: Number(ys[i] ?? x) || 0,
      }));
      return { kind: 'scatter', rows };
    }
  }
}


/** Coerce series[i] to number; missing/NaN cells become 0 so the chart
 *  renders rather than throwing on `Number(undefined) → NaN`. */
function numberAt(vals: readonly number[] | undefined, i: number): number {
  const v = vals?.[i];
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}
