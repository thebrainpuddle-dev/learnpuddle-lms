/**
 * Tests for src/lib/maic-v2/action-engine.ts (Phase 1 stub).
 *
 * The Phase 1 ActionEngine is intentionally a no-op for sync actions.
 * These tests document that the contract resolves immediately so the
 * playback engine's await advances without delay or deadlock.
 */
import { describe, test, expect, vi, beforeEach } from 'vitest';

import { ActionEngine } from '../action-engine';
import type { Action } from '../action-types';


describe('ActionEngine (Phase 1 stub)', () => {
  let engine: ActionEngine;

  beforeEach(() => {
    engine = new ActionEngine();
  });

  test('execute returns a resolved Promise immediately for wb_open', async () => {
    const action: Action = { id: 'a1', type: 'wb_open' };
    const start = performance.now();
    await engine.execute(action);
    const elapsed = performance.now() - start;
    // No-op stub should resolve synchronously — generously allow 50 ms
    // to absorb microtask scheduling on slow CI.
    expect(elapsed).toBeLessThan(50);
  });

  test('execute returns a resolved Promise for every wb_* action', async () => {
    const wbActions: Action[] = [
      { id: 'a', type: 'wb_open' },
      { id: 'b', type: 'wb_close' },
      { id: 'c', type: 'wb_clear' },
      { id: 'd', type: 'wb_delete', elementId: 'e' },
      { id: 'e', type: 'wb_draw_text', content: 'x', x: 0, y: 0 },
      { id: 'f', type: 'wb_draw_shape', shape: 'rectangle', x: 0, y: 0, width: 1, height: 1 },
    ];
    for (const action of wbActions) {
      await expect(engine.execute(action)).resolves.toBeUndefined();
    }
  });

  test('execute returns a resolved Promise for widget_* actions', async () => {
    const widgetActions: Action[] = [
      { id: 'a', type: 'widget_highlight', target: '#x' },
      { id: 'b', type: 'widget_setState', state: { foo: 1 } },
      { id: 'c', type: 'widget_annotation', target: '#x' },
      { id: 'd', type: 'widget_reveal', target: '#x' },
    ];
    for (const action of widgetActions) {
      await expect(engine.execute(action)).resolves.toBeUndefined();
    }
  });

  test('execute returns a resolved Promise for play_video and discussion', async () => {
    await expect(
      engine.execute({ id: 'a', type: 'play_video', elementId: 'v' }),
    ).resolves.toBeUndefined();
    await expect(
      engine.execute({ id: 'b', type: 'discussion', topic: 'x' }),
    ).resolves.toBeUndefined();
  });

  test('execute logs at debug for visibility in dev tooling', async () => {
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    await engine.execute({ id: 'a', type: 'wb_open' });
    expect(debugSpy).toHaveBeenCalledWith(
      expect.stringContaining('ActionEngine'),
      'wb_open',
      'a',
    );
    debugSpy.mockRestore();
  });

  test('clearEffects is callable and returns nothing', () => {
    expect(engine.clearEffects()).toBeUndefined();
  });

  test('execute does not deadlock on a long sequence of sync actions', async () => {
    // Simulate the playback engine's await-loop over a sequence of
    // 50 wb_* actions. Phase 1 stub should resolve all near-instantly.
    const start = performance.now();
    for (let i = 0; i < 50; i++) {
      await engine.execute({ id: `a-${i}`, type: 'wb_open' });
    }
    const elapsed = performance.now() - start;
    expect(elapsed).toBeLessThan(100);
  });
});
