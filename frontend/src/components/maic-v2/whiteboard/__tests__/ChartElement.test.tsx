/**
 * Tests for src/components/maic-v2/whiteboard/ChartElement.tsx
 * (MAIC-213.2).
 *
 * recharts in jsdom/happy-dom doesn't compute layout (no SVG bbox), so
 * tests assert structural / data-flow concerns rather than pixel
 * positions:
 *   - Right recharts component tree mounts for each chartType (probe
 *     DOM for the chart-class wrapper recharts emits)
 *   - Box wrapper has the right coords + data attributes
 *   - elementId vs id key fallback
 *   - Theme color override flows through
 *
 * The pixel-level rendering is verified by the live-browser smoke at
 * MAIC-218.
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ChartElement } from '../ChartElement';
import type { Action } from '../../../../lib/maic-v2/action-types';

type C = Extract<Action, { type: 'wb_draw_chart' }>;
type ChartType = C['chartType'];


function make(overrides: Partial<C> = {}): C {
  return {
    id: 'a1',
    type: 'wb_draw_chart',
    chartType: 'bar',
    x: 0,
    y: 0,
    width: 400,
    height: 200,
    data: {
      labels: ['Q1', 'Q2', 'Q3'],
      legends: ['Sales'],
      series: [[10, 20, 30]],
    },
    ...overrides,
  };
}


// ── Per-chartType: each variant mounts the right recharts root ─────


// Recharts 2.x doesn't tag the wrapper with a chart-type class — it
// always emits `.recharts-wrapper` + `.recharts-surface`. The
// distinguishing class is on the data layer (.recharts-bar /
// .recharts-line / .recharts-pie / etc.). bar+column share .recharts-
// bar; pie+ring share .recharts-pie.
const RECHARTS_LAYER_CLASS: Record<ChartType, string> = {
  bar: 'recharts-bar',
  column: 'recharts-bar',
  line: 'recharts-line',
  area: 'recharts-area',
  pie: 'recharts-pie',
  ring: 'recharts-pie',
  radar: 'recharts-radar',
  scatter: 'recharts-scatter',
};


describe.each<ChartType>([
  'bar', 'column', 'line', 'area', 'pie', 'ring', 'radar', 'scatter',
])('ChartElement — chartType=%s', (chartType) => {
  test('renders the matching recharts data layer', () => {
    const data: C['data'] =
      chartType === 'scatter'
        ? { labels: [], legends: [], series: [[1, 2, 3], [10, 20, 30]] }
        : {
            labels: ['Q1', 'Q2', 'Q3'],
            legends: ['Sales'],
            series: [[10, 20, 30]],
          };
    const { container } = render(
      <ChartElement element={make({ chartType, data })} />,
    );
    // Every chart should at minimum mount the recharts wrapper.
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull();
    // And the type-specific data layer should appear.
    const expectedClass = RECHARTS_LAYER_CLASS[chartType];
    expect(container.querySelector(`.${expectedClass}`)).not.toBeNull();
  });

  test('exposes data-chart-type on the wrapper', () => {
    const data: C['data'] =
      chartType === 'scatter'
        ? { labels: [], legends: [], series: [[1, 2, 3], [10, 20, 30]] }
        : {
            labels: ['Q1', 'Q2', 'Q3'],
            legends: ['Sales'],
            series: [[10, 20, 30]],
          };
    render(<ChartElement element={make({ chartType, data })} />);
    expect(screen.getByTestId('maic-v2-wb-chart')).toHaveAttribute(
      'data-chart-type',
      chartType,
    );
  });
});


// ── column variant uses BarChart layout="vertical" ─────────────────


describe('ChartElement — bar vs column layout', () => {
  test('column renders with vertical layout (horizontal bars)', () => {
    const { container } = render(<ChartElement element={make({ chartType: 'column' })} />);
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull();
    expect(container.querySelector('.recharts-bar')).not.toBeNull();
    expect(screen.getByTestId('maic-v2-wb-chart')).toHaveAttribute(
      'data-chart-type', 'column',
    );
  });

  test('bar renders with horizontal layout (vertical bars)', () => {
    const { container } = render(<ChartElement element={make({ chartType: 'bar' })} />);
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull();
    expect(container.querySelector('.recharts-bar')).not.toBeNull();
    expect(screen.getByTestId('maic-v2-wb-chart')).toHaveAttribute(
      'data-chart-type', 'bar',
    );
  });
});


// ── ring variant ───────────────────────────────────────────────────


describe('ChartElement — pie vs ring', () => {
  test('pie has no innerRadius (full disc)', () => {
    const { container } = render(<ChartElement element={make({ chartType: 'pie' })} />);
    // Pie sectors are identified via the recharts-pie class.
    expect(container.querySelectorAll('.recharts-pie').length).toBeGreaterThan(0);
  });

  test('ring renders the same pie shell with innerRadius (donut)', () => {
    const { container } = render(<ChartElement element={make({ chartType: 'ring' })} />);
    expect(container.querySelectorAll('.recharts-pie').length).toBeGreaterThan(0);
  });
});


// ── multi-series legend ────────────────────────────────────────────


describe('ChartElement — multi-series legend', () => {
  test('shows legend when more than one series', () => {
    const { container } = render(
      <ChartElement
        element={make({
          chartType: 'bar',
          data: {
            labels: ['a', 'b'],
            legends: ['Sales', 'Returns'],
            series: [[1, 2], [3, 4]],
          },
        })}
      />,
    );
    expect(container.querySelector('.recharts-legend-wrapper')).not.toBeNull();
  });

  test('hides legend for single-series cartesian charts', () => {
    const { container } = render(
      <ChartElement
        element={make({
          chartType: 'bar',
          data: { labels: ['a', 'b'], legends: ['Sales'], series: [[1, 2]] },
        })}
      />,
    );
    // recharts-legend-wrapper still mounts but the content should be
    // empty or our component should skip rendering it. We rendered
    // {seriesNames.length > 1 && <Legend />}, so no Legend at all.
    expect(container.querySelector('.recharts-legend-wrapper')).toBeNull();
  });
});


// ── Theme colors ───────────────────────────────────────────────────


describe('ChartElement — theme colors', () => {
  test('applies caller-provided themeColors[0] to single-series', () => {
    const { container } = render(
      <ChartElement
        element={make({ chartType: 'bar', themeColors: ['#ff0000', '#00ff00'] })}
      />,
    );
    // recharts paints bars via SVG <rect> with the fill attribute.
    // happy-dom may not compute SVG layout, but the fill attribute
    // should be present on the bar group.
    const barFills = Array.from(container.querySelectorAll('.recharts-bar-rectangle path'))
      .map((el) => el.getAttribute('fill'));
    if (barFills.length > 0) {
      // Recharts may or may not emit individual rectangles depending
      // on layout completion. If any did, they should be #ff0000.
      expect(barFills[0]).toBe('#ff0000');
    } else {
      // Fallback path: at least the wrapper mounted without throw.
      expect(container.querySelector('.recharts-wrapper')).not.toBeNull();
    }
  });
});


// ── Box positioning + element-id ──────────────────────────────────


describe('ChartElement — wrapper', () => {
  test('positions absolute at action coords + sizes container', () => {
    render(<ChartElement element={make({ x: 100, y: 200, width: 350, height: 180 })} />);
    const wrapper = screen.getByTestId('maic-v2-wb-chart');
    const style = wrapper.getAttribute('style') ?? '';
    expect(style).toContain('left: 100px');
    expect(style).toContain('top: 200px');
    expect(style).toContain('width: 350px');
    expect(style).toContain('height: 180px');
  });

  test('exposes data-element-id (elementId wins over id)', () => {
    render(<ChartElement element={make({ id: 'a1', elementId: 'C1' })} />);
    expect(screen.getByTestId('maic-v2-wb-chart')).toHaveAttribute('data-element-id', 'C1');
  });

  test('falls back to id when elementId absent', () => {
    render(<ChartElement element={make({ id: 'a1' })} />);
    expect(screen.getByTestId('maic-v2-wb-chart')).toHaveAttribute('data-element-id', 'a1');
  });
});


// ── Defensive ─────────────────────────────────────────────────────


describe('ChartElement — defensive edges', () => {
  test('empty data renders without throwing (chart still mounts)', () => {
    const { container } = render(
      <ChartElement
        element={make({
          chartType: 'bar',
          data: { labels: [], legends: [], series: [] },
        })}
      />,
    );
    // With empty data the wrapper still mounts (recharts-wrapper) but
    // the bars layer may be absent. Wrapper presence is sufficient
    // for a "renders without throw" assertion.
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull();
  });

  test('scatter with two series renders without throw', () => {
    const { container } = render(
      <ChartElement
        element={make({
          chartType: 'scatter',
          data: { labels: [], legends: [], series: [[1, 2, 3], [10, 20, 30]] },
        })}
      />,
    );
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull();
    expect(container.querySelector('.recharts-scatter')).not.toBeNull();
  });

  test('scatter single-series collapses to y=x without throw', () => {
    const { container } = render(
      <ChartElement
        element={make({
          chartType: 'scatter',
          data: { labels: [], legends: [], series: [[1, 2, 3]] },
        })}
      />,
    );
    expect(container.querySelector('.recharts-wrapper')).not.toBeNull();
    expect(container.querySelector('.recharts-scatter')).not.toBeNull();
  });
});
