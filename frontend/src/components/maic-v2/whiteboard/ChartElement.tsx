/**
 * ChartElement — renders a wb_draw_chart element via recharts.
 *
 * Source: THU-MAIC/OpenMAIC main components/slide-renderer/components/
 *         element/ChartElement/{BaseChartElement.tsx, Chart.tsx,
 *         chartOption.ts}.  Upstream uses ECharts; we use recharts
 *         (already installed at frontend/package.json:62) — the
 *         per-chartType *data shape* decisions are mirrored verbatim
 *         via lib/maic-v2/chart-data.ts (MAIC-213.1); the recharts
 *         component tree is the local-stack equivalent.
 *
 * Wire shape (apps/maic/protocol/actions.py WbDrawChartAction):
 *   id, elementId?, chartType, x, y, width, height,
 *   data: {labels, legends, series}, themeColors?
 *
 * 8 chartType variants supported:
 *   bar     — vertical BarChart (rows on x-axis)
 *   column  — horizontal BarChart (rows on y-axis; layout="vertical")
 *   line    — LineChart
 *   area    — AreaChart (line + filled area)
 *   pie     — PieChart with a full disc
 *   ring    — PieChart with innerRadius (donut)
 *   radar   — RadarChart with one polygon per legend
 *   scatter — ScatterChart with x,y pairs
 *
 * Theme colors default to upstream's 5-color palette
 * (DEFAULT_THEME_COLORS in chart-data.ts) and cycle when there are
 * more series than colors.
 *
 * Phase 2 deferrals (signposted): textColor / lineColor / outline /
 * shadow / rotation / pattern fill / stack mode (multi-series stacked
 * bars). All of these exist in upstream's BaseChartElement +
 * chartOption.ts but Phase 2's wire-format protocol doesn't ship them.
 *
 * Responsive sizing: the surface frame is 1000×562 (fixed); the chart
 * box's width/height are agent-supplied. We use recharts'
 * ResponsiveContainer so the chart fills its parent — robust against
 * viewport scaling at the Stage container level.
 */
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { Action } from '../../../lib/maic-v2/action-types';
import {
  DEFAULT_THEME_COLORS,
  toRechartsData,
} from '../../../lib/maic-v2/chart-data';


type ChartAction = Extract<Action, { type: 'wb_draw_chart' }>;


export interface ChartElementProps {
  element: ChartAction;
}


export function ChartElement({ element }: ChartElementProps) {
  const elementKey = element.elementId ?? element.id;
  const colors = element.themeColors?.length ? element.themeColors : DEFAULT_THEME_COLORS;
  const shaped = toRechartsData(element.chartType, element.data);

  return (
    <div
      data-testid="maic-v2-wb-chart"
      data-element-id={elementKey}
      data-chart-type={element.chartType}
      className="absolute"
      style={{
        top: `${element.y}px`,
        left: `${element.x}px`,
        width: `${element.width}px`,
        height: `${element.height}px`,
      }}
    >
      {renderChart(shaped, colors, element.width, element.height)}
    </div>
  );
}


/**
 * Why pass explicit width/height to recharts (instead of wrapping in
 * ResponsiveContainer)? Two reasons:
 *
 *   1. Tests — happy-dom doesn't compute layout, so
 *      ResponsiveContainer's parent ends up at 0×0 and recharts logs
 *      a console error then returns null. Explicit dimensions make
 *      tests deterministic.
 *
 *   2. The Whiteboard surface is rendered at the agent-emitted
 *      coordinate space (1000×562) — children with `top/left: Npx`
 *      use those literal pixels too. Charts use the same fixed
 *      dimensions, so an explicit width/height matches the rest of
 *      the surface's positioning model.
 *
 * The Whiteboard surface itself is responsive via aspect-ratio +
 * width:100% on its container; per-element CSS-transform scaling for
 * smaller viewports is a Phase 8+ concern (signposted in
 * Whiteboard.tsx).
 */
function renderChart(
  shaped: ReturnType<typeof toRechartsData>,
  colors: readonly string[],
  width: number,
  height: number,
): React.ReactElement {
  switch (shaped.kind) {
    case 'cartesian':
      return shaped.chartType === 'line'
        ? renderLine(shaped, colors, width, height)
        : shaped.chartType === 'area'
          ? renderArea(shaped, colors, width, height)
          : renderBar(shaped, colors, width, height);

    case 'pie':
      return renderPie(shaped, colors, width, height);

    case 'radar':
      return renderRadar(shaped, colors, width, height);

    case 'scatter':
      return renderScatter(shaped, colors, width, height);
  }
}


// ── Cartesian: bar / column ────────────────────────────────────────


function renderBar(
  shaped: Extract<ReturnType<typeof toRechartsData>, { kind: 'cartesian' }>,
  colors: readonly string[],
  width: number,
  height: number,
): React.ReactElement {
  const horizontal = shaped.chartType === 'column';
  return (
    <BarChart data={shaped.rows} layout={horizontal ? 'vertical' : 'horizontal'} width={width} height={height}>
      <CartesianGrid strokeDasharray="3 3" />
      {horizontal ? (
        <>
          <XAxis type="number" />
          <YAxis dataKey="name" type="category" />
        </>
      ) : (
        <>
          <XAxis dataKey="name" />
          <YAxis />
        </>
      )}
      <Tooltip />
      {shaped.seriesNames.length > 1 && <Legend />}
      {shaped.seriesNames.map((seriesName, k) => (
        <Bar key={seriesName} dataKey={seriesName} fill={colors[k % colors.length]} />
      ))}
    </BarChart>
  );
}


function renderLine(
  shaped: Extract<ReturnType<typeof toRechartsData>, { kind: 'cartesian' }>,
  colors: readonly string[],
  width: number,
  height: number,
): React.ReactElement {
  return (
    <LineChart data={shaped.rows} width={width} height={height}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="name" />
      <YAxis />
      <Tooltip />
      {shaped.seriesNames.length > 1 && <Legend />}
      {shaped.seriesNames.map((seriesName, k) => (
        <Line
          key={seriesName}
          dataKey={seriesName}
          stroke={colors[k % colors.length]}
          dot={false}
        />
      ))}
    </LineChart>
  );
}


function renderArea(
  shaped: Extract<ReturnType<typeof toRechartsData>, { kind: 'cartesian' }>,
  colors: readonly string[],
  width: number,
  height: number,
): React.ReactElement {
  return (
    <AreaChart data={shaped.rows} width={width} height={height}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="name" />
      <YAxis />
      <Tooltip />
      {shaped.seriesNames.length > 1 && <Legend />}
      {shaped.seriesNames.map((seriesName, k) => (
        <Area
          key={seriesName}
          dataKey={seriesName}
          stroke={colors[k % colors.length]}
          fill={colors[k % colors.length]}
          fillOpacity={0.4}
        />
      ))}
    </AreaChart>
  );
}


// ── Pie / Ring ─────────────────────────────────────────────────────


function renderPie(
  shaped: Extract<ReturnType<typeof toRechartsData>, { kind: 'pie' }>,
  colors: readonly string[],
  width: number,
  height: number,
): React.ReactElement {
  const isRing = shaped.chartType === 'ring';
  return (
    <PieChart width={width} height={height}>
      <Tooltip />
      <Pie
        data={shaped.rows}
        dataKey="value"
        nameKey="name"
        outerRadius="70%"
        innerRadius={isRing ? '40%' : 0}
        label
      >
        {shaped.rows.map((_, i) => (
          <Cell key={i} fill={colors[i % colors.length]} />
        ))}
      </Pie>
    </PieChart>
  );
}


// ── Radar ──────────────────────────────────────────────────────────


function renderRadar(
  shaped: Extract<ReturnType<typeof toRechartsData>, { kind: 'radar' }>,
  colors: readonly string[],
  width: number,
  height: number,
): React.ReactElement {
  return (
    <RadarChart data={shaped.rows} width={width} height={height}>
      <PolarGrid />
      <PolarAngleAxis dataKey="subject" />
      <Tooltip />
      {shaped.seriesNames.length > 1 && <Legend />}
      {shaped.seriesNames.map((seriesName, k) => (
        <Radar
          key={seriesName}
          dataKey={seriesName}
          name={seriesName}
          stroke={colors[k % colors.length]}
          fill={colors[k % colors.length]}
          fillOpacity={0.3}
        />
      ))}
    </RadarChart>
  );
}


// ── Scatter ────────────────────────────────────────────────────────


function renderScatter(
  shaped: Extract<ReturnType<typeof toRechartsData>, { kind: 'scatter' }>,
  colors: readonly string[],
  width: number,
  height: number,
): React.ReactElement {
  return (
    <ScatterChart width={width} height={height}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="x" type="number" />
      <YAxis dataKey="y" type="number" />
      <Tooltip cursor={{ strokeDasharray: '3 3' }} />
      <Scatter data={shaped.rows} fill={colors[0]} />
    </ScatterChart>
  );
}
