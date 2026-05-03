/**
 * Tests for src/lib/maic-v2/chart-data.ts (MAIC-213.1).
 *
 * The data transform is the highest-risk piece of MAIC-213 — easy to
 * mis-shape for `pie`/`ring` (single series, ignore extras) and
 * `scatter` (x,y pairs, fallback when only one series provided). One
 * parametrized fixture per chartType + targeted edge-case tests.
 */
import { describe, test, expect } from 'vitest';

import {
  DEFAULT_THEME_COLORS,
  toRechartsData,
  type ChartData,
  type ChartType,
} from '../chart-data';


function fixture(): ChartData {
  return {
    labels: ['Q1', 'Q2', 'Q3', 'Q4'],
    legends: ['Sales', 'Returns'],
    series: [
      [10, 20, 30, 40],   // Sales
      [1, 2, 3, 4],       // Returns
    ],
  };
}


// ── Cartesian (bar / column / line / area) ─────────────────────────


describe.each<ChartType>(['bar', 'column', 'line', 'area'])(
  'toRechartsData — chartType=%s (cartesian)',
  (chartType) => {
    test('returns kind=cartesian with one row per label', () => {
      const out = toRechartsData(chartType, fixture());
      expect(out.kind).toBe('cartesian');
      if (out.kind !== 'cartesian') throw new Error('unreachable');
      expect(out.chartType).toBe(chartType);
      expect(out.rows).toHaveLength(4);
    });

    test('row.name comes from labels', () => {
      const out = toRechartsData(chartType, fixture());
      if (out.kind !== 'cartesian') throw new Error('unreachable');
      expect(out.rows.map((r) => r.name)).toEqual(['Q1', 'Q2', 'Q3', 'Q4']);
    });

    test('row[legendName] = series[k][i]', () => {
      const out = toRechartsData(chartType, fixture());
      if (out.kind !== 'cartesian') throw new Error('unreachable');
      expect(out.rows[0]).toEqual({ name: 'Q1', Sales: 10, Returns: 1 });
      expect(out.rows[3]).toEqual({ name: 'Q4', Sales: 40, Returns: 4 });
    });

    test('seriesNames echoes legends', () => {
      const out = toRechartsData(chartType, fixture());
      if (out.kind !== 'cartesian') throw new Error('unreachable');
      expect(out.seriesNames).toEqual(['Sales', 'Returns']);
    });

    test('falls back to series-N when legends shorter than series', () => {
      const data: ChartData = {
        labels: ['a', 'b'],
        legends: ['Only'],
        series: [[1, 2], [3, 4]],
      };
      const out = toRechartsData(chartType, data);
      if (out.kind !== 'cartesian') throw new Error('unreachable');
      expect(out.seriesNames).toEqual(['Only', 'series-2']);
      expect(out.rows[0]).toEqual({ name: 'a', Only: 1, 'series-2': 3 });
    });
  },
);


// ── Pie / Ring ─────────────────────────────────────────────────────


describe.each<ChartType>(['pie', 'ring'])(
  'toRechartsData — chartType=%s',
  (chartType) => {
    test('returns kind=pie with name+value pairs from series[0]', () => {
      const out = toRechartsData(chartType, fixture());
      expect(out.kind).toBe('pie');
      if (out.kind !== 'pie') throw new Error('unreachable');
      expect(out.chartType).toBe(chartType);
      expect(out.rows).toEqual([
        { name: 'Q1', value: 10 },
        { name: 'Q2', value: 20 },
        { name: 'Q3', value: 30 },
        { name: 'Q4', value: 40 },
      ]);
    });

    test('ignores series[k>0] (matches upstream chartOption.ts:180)', () => {
      const out = toRechartsData(chartType, fixture());
      if (out.kind !== 'pie') throw new Error('unreachable');
      // The "Returns" series (1, 2, 3, 4) must NOT show up in any
      // row's value field.
      for (const r of out.rows) {
        expect([10, 20, 30, 40]).toContain(r.value);
      }
    });

    test('empty series → empty rows but valid kind', () => {
      const out = toRechartsData(chartType, { labels: [], legends: [], series: [] });
      expect(out.kind).toBe('pie');
      if (out.kind !== 'pie') throw new Error('unreachable');
      expect(out.rows).toEqual([]);
    });
  },
);


// ── Radar ──────────────────────────────────────────────────────────


describe('toRechartsData — chartType=radar', () => {
  test('returns kind=radar with subject + per-series keys', () => {
    const out = toRechartsData('radar', fixture());
    expect(out.kind).toBe('radar');
    if (out.kind !== 'radar') throw new Error('unreachable');
    expect(out.rows).toHaveLength(4);
    expect(out.rows[0]).toEqual({ subject: 'Q1', Sales: 10, Returns: 1 });
  });

  test('seriesNames echoes legends', () => {
    const out = toRechartsData('radar', fixture());
    if (out.kind !== 'radar') throw new Error('unreachable');
    expect(out.seriesNames).toEqual(['Sales', 'Returns']);
  });
});


// ── Scatter ────────────────────────────────────────────────────────


describe('toRechartsData — chartType=scatter', () => {
  test('returns kind=scatter with (x,y) pairs from series[0],series[1]', () => {
    const data: ChartData = {
      labels: [],
      legends: [],
      series: [
        [1, 2, 3],
        [10, 20, 30],
      ],
    };
    const out = toRechartsData('scatter', data);
    expect(out.kind).toBe('scatter');
    if (out.kind !== 'scatter') throw new Error('unreachable');
    expect(out.rows).toEqual([
      { x: 1, y: 10 },
      { x: 2, y: 20 },
      { x: 3, y: 30 },
    ]);
  });

  test('single-series scatter collapses to y=x (matches upstream chartOption.ts:312-317)', () => {
    const data: ChartData = { labels: [], legends: [], series: [[1, 2, 3]] };
    const out = toRechartsData('scatter', data);
    if (out.kind !== 'scatter') throw new Error('unreachable');
    expect(out.rows).toEqual([
      { x: 1, y: 1 },
      { x: 2, y: 2 },
      { x: 3, y: 3 },
    ]);
  });

  test('empty series → empty rows', () => {
    const out = toRechartsData('scatter', { labels: [], legends: [], series: [] });
    if (out.kind !== 'scatter') throw new Error('unreachable');
    expect(out.rows).toEqual([]);
  });
});


// ── Defensive edges (apply across all chartTypes) ──────────────────


describe('toRechartsData — defensive edges', () => {
  test('missing data fields default to empty (no throw)', () => {
    const out = toRechartsData('bar', { labels: [], legends: [], series: [] });
    expect(out.kind).toBe('cartesian');
    if (out.kind !== 'cartesian') throw new Error('unreachable');
    expect(out.rows).toEqual([]);
    expect(out.seriesNames).toEqual([]);
  });

  test('mismatched series length: short series → 0 fill', () => {
    const data: ChartData = {
      labels: ['a', 'b', 'c'],
      legends: ['x'],
      series: [[1, 2]],
    };
    const out = toRechartsData('bar', data);
    if (out.kind !== 'cartesian') throw new Error('unreachable');
    // Third row's "x" value is 0 (not undefined, not NaN).
    expect(out.rows[2]).toEqual({ name: 'c', x: 0 });
  });

  test('NaN values become 0 to keep chart renderable', () => {
    const data: ChartData = {
      labels: ['a'],
      legends: ['x'],
      series: [[NaN]],
    };
    const out = toRechartsData('bar', data);
    if (out.kind !== 'cartesian') throw new Error('unreachable');
    expect(out.rows[0]).toEqual({ name: 'a', x: 0 });
  });

  test('label coerced to string', () => {
    const data: ChartData = {
      labels: [1, 2, 3] as unknown as string[],
      legends: ['x'],
      series: [[10, 20, 30]],
    };
    const out = toRechartsData('bar', data);
    if (out.kind !== 'cartesian') throw new Error('unreachable');
    expect(out.rows.map((r) => r.name)).toEqual(['1', '2', '3']);
  });

  test('whitespace-only legend falls back to series-N', () => {
    const data: ChartData = {
      labels: ['a'],
      legends: ['   '],
      series: [[1]],
    };
    const out = toRechartsData('bar', data);
    if (out.kind !== 'cartesian') throw new Error('unreachable');
    expect(out.seriesNames).toEqual(['series-1']);
  });

  test('does not mutate the input data', () => {
    const data = fixture();
    const before = JSON.stringify(data);
    toRechartsData('bar', data);
    expect(JSON.stringify(data)).toBe(before);
  });
});


// ── DEFAULT_THEME_COLORS ───────────────────────────────────────────


describe('DEFAULT_THEME_COLORS', () => {
  test('matches upstream engine.ts:414 default palette verbatim', () => {
    expect(DEFAULT_THEME_COLORS).toEqual([
      '#5b9bd5',
      '#ed7d31',
      '#a5a5a5',
      '#ffc000',
      '#4472c4',
    ]);
  });
});
