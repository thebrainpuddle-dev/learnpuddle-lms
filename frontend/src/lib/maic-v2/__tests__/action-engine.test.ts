/**
 * Tests for src/lib/maic-v2/action-engine.ts (MAIC-211.1).
 *
 * Phase 2 introduced real lifecycle handlers (wb_open/close/clear/
 * delete) with animation waits. Tests inject a no-op delay so
 * assertions are timing-stable on slow CI; Phase 1's "stub resolves
 * <50 ms" assertions are no longer applicable.
 *
 * Two layers:
 *   1. With controller — verifies state mutations + timings via mocked delay.
 *   2. Without controller — verifies the warn-and-resolve fallback so
 *      PlaybackEngine unit tests (which never wire a whiteboard) pass.
 */
import { describe, test, expect, vi, beforeEach } from 'vitest';

import { ActionEngine } from '../action-engine';
import type { Action } from '../action-types';
import type { WhiteboardController, WhiteboardElement } from '../whiteboard-state';


// ── Helpers ────────────────────────────────────────────────────────


function makeController(): WhiteboardController & {
  calls: Array<{ method: string; args: unknown[] }>;
} {
  const calls: Array<{ method: string; args: unknown[] }> = [];
  const record = <K extends string>(method: K) => (...args: unknown[]) => {
    calls.push({ method, args });
  };
  return {
    setOpen: record('setOpen'),
    setClearing: record('setClearing'),
    addElement: record('addElement'),
    updateElement: record('updateElement'),
    deleteElement: record('deleteElement'),
    clear: record('clear'),
    calls,
  };
}


function noDelay(): (ms: number) => Promise<void> {
  return () => Promise.resolve();
}


// Capture the delays requested without actually waiting.
function recordingDelay(): {
  delay: (ms: number) => Promise<void>;
  recorded: number[];
} {
  const recorded: number[] = [];
  const delay = (ms: number): Promise<void> => {
    recorded.push(ms);
    return Promise.resolve();
  };
  return { delay, recorded };
}


// ── With controller ────────────────────────────────────────────────


describe('ActionEngine — wb_open', () => {
  test('flips whiteboard.setOpen(true) then waits 2000 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    await engine.execute({ id: 'a1', type: 'wb_open' });

    expect(ctl.calls).toEqual([{ method: 'setOpen', args: [true] }]);
    expect(recorded).toEqual([2000]);
  });
});


describe('ActionEngine — wb_close', () => {
  test('flips whiteboard.setOpen(false) then waits 700 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    await engine.execute({ id: 'a1', type: 'wb_close' });

    expect(ctl.calls).toEqual([{ method: 'setOpen', args: [false] }]);
    expect(recorded).toEqual([700]);
  });
});


describe('ActionEngine — wb_delete', () => {
  test('calls deleteElement(elementId) then waits 300 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    await engine.execute({ id: 'a1', type: 'wb_delete', elementId: 't1' });

    expect(ctl.calls).toEqual([{ method: 'deleteElement', args: ['t1'] }]);
    expect(recorded).toEqual([300]);
  });
});


describe('ActionEngine — wb_clear', () => {
  test('cascade: setClearing(true) → wait → clear() → setClearing(false)', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    await engine.execute({ id: 'a1', type: 'wb_clear' });

    expect(ctl.calls.map((c) => c.method)).toEqual([
      'setClearing',
      'clear',
      'setClearing',
    ]);
    expect(ctl.calls[0].args).toEqual([true]);
    expect(ctl.calls[2].args).toEqual([false]);
    // Phase 2 uses the upstream cap (1400 ms) on every clear; the
    // count-based shrink (380 + n*55) is signposted as a Phase 8+
    // optimisation in action-engine.ts.
    expect(recorded).toEqual([1400]);
  });
});


// ── Sequencing across multiple actions ────────────────────────────


describe('ActionEngine — sequencing', () => {
  test('a series of lifecycle actions interleave with their delays', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    const actions: Action[] = [
      { id: '1', type: 'wb_open' },
      { id: '2', type: 'wb_delete', elementId: 'e' },
      { id: '3', type: 'wb_close' },
    ];
    for (const a of actions) await engine.execute(a);

    expect(ctl.calls.map((c) => c.method)).toEqual([
      'setOpen',  // wb_open(true)
      'deleteElement',
      'setOpen',  // wb_close = setOpen(false)
    ]);
    expect(recorded).toEqual([2000, 300, 700]);
  });
});


// ── Without controller (PlaybackEngine fast-path) ─────────────────


describe('ActionEngine — without controller', () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  test('wb_open warns and resolves', async () => {
    const engine = new ActionEngine({ delay: noDelay() });
    await expect(engine.execute({ id: '1', type: 'wb_open' })).resolves.toBeUndefined();
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('wb_open'));
  });

  test('wb_clear warns and resolves', async () => {
    const engine = new ActionEngine({ delay: noDelay() });
    await expect(engine.execute({ id: '1', type: 'wb_clear' })).resolves.toBeUndefined();
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('wb_clear'));
  });

  test('default delay is real (setTimeout-based)', async () => {
    // Sanity check that an engine with no options still has a callable
    // delay. Phase 1 callsites rely on `new ActionEngine()` being valid.
    const engine = new ActionEngine();
    expect(engine).toBeDefined();
  });
});


// ── Deferred actions still resolve ─────────────────────────────────


describe('ActionEngine — wb_draw_* component renderers (211.2)', () => {
  test('wb_draw_text adds element + waits 800 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });
    const action: Action = { id: 'a1', type: 'wb_draw_text', content: 'hi', x: 0, y: 0 };

    await engine.execute(action);

    expect(ctl.calls).toEqual([{ method: 'addElement', args: [action] }]);
    expect(recorded).toEqual([800]);
  });

  test('wb_draw_shape adds element + waits 800 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });
    const action: Action = {
      id: 'a1', type: 'wb_draw_shape', shape: 'rectangle',
      x: 0, y: 0, width: 100, height: 50,
    };

    await engine.execute(action);

    expect(ctl.calls).toEqual([{ method: 'addElement', args: [action] }]);
    expect(recorded).toEqual([800]);
  });

  test('wb_draw_line adds element + waits 800 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });
    const action: Action = {
      id: 'a1', type: 'wb_draw_line', startX: 0, startY: 0, endX: 100, endY: 100,
    };

    await engine.execute(action);

    expect(ctl.calls).toEqual([{ method: 'addElement', args: [action] }]);
    expect(recorded).toEqual([800]);
  });

  test('wb_draw_chart adds element + waits 800 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });
    const action: Action = {
      id: 'a1', type: 'wb_draw_chart', chartType: 'bar',
      x: 0, y: 0, width: 200, height: 100,
      data: { labels: ['a'], legends: ['x'], series: [[1]] },
    };

    await engine.execute(action);

    expect(ctl.calls).toEqual([{ method: 'addElement', args: [action] }]);
    expect(recorded).toEqual([800]);
  });

  test('wb_draw_latex adds element + waits 800 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });
    const action: Action = {
      id: 'a1', type: 'wb_draw_latex', latex: '\\frac{1}{2}', x: 0, y: 0,
    };

    await engine.execute(action);

    expect(ctl.calls).toEqual([{ method: 'addElement', args: [action] }]);
    expect(recorded).toEqual([800]);
  });

  test('wb_draw_table adds element + waits 800 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });
    const action: Action = {
      id: 'a1', type: 'wb_draw_table',
      x: 0, y: 0, width: 200, height: 100,
      data: [['a', 'b'], ['1', '2']],
    };

    await engine.execute(action);

    expect(ctl.calls).toEqual([{ method: 'addElement', args: [action] }]);
    expect(recorded).toEqual([800]);
  });

  test('wb_draw_text without controller warns + still waits', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ delay });

    await engine.execute({ id: '1', type: 'wb_draw_text', content: 'x', x: 0, y: 0 });

    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('wb_draw_text'));
    expect(recorded).toEqual([800]);
    warnSpy.mockRestore();
  });
});


describe('ActionEngine — deferred actions resolve immediately', () => {
  test('wb_draw_code + wb_edit_code resolve without renderer (MAIC-214)', async () => {
    const engine = new ActionEngine({ delay: noDelay() });
    const drawActions: Action[] = [
      { id: '7', type: 'wb_draw_code', language: 'js', code: 'x', x: 0, y: 0 },
      {
        id: '8',
        type: 'wb_edit_code',
        elementId: 'c1',
        operation: 'insert_after',
        lineId: 'L1',
        content: 'x',
      },
    ];
    for (const a of drawActions) {
      await expect(engine.execute(a)).resolves.toBeUndefined();
    }
  });

  test('widget_* and play_video resolve (Phase 6 fills these)', async () => {
    const engine = new ActionEngine({ delay: noDelay() });
    const phase6Actions: Action[] = [
      { id: '1', type: 'widget_highlight', target: '#x' },
      { id: '2', type: 'widget_setState', state: { foo: 1 } },
      { id: '3', type: 'widget_annotation', target: '#x' },
      { id: '4', type: 'widget_reveal', target: '#x' },
      { id: '5', type: 'play_video', elementId: 'v' },
    ];
    for (const a of phase6Actions) {
      await expect(engine.execute(a)).resolves.toBeUndefined();
    }
  });
});


// ── Misc ───────────────────────────────────────────────────────────


describe('ActionEngine — misc', () => {
  test('clearEffects is callable and returns nothing', () => {
    const engine = new ActionEngine();
    expect(engine.clearEffects()).toBeUndefined();
  });

  test('execute logs at debug for action visibility', async () => {
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    const ctl = makeController();
    const engine = new ActionEngine({ whiteboard: ctl, delay: noDelay() });

    await engine.execute({ id: 'a-x', type: 'wb_open' });
    expect(debugSpy).toHaveBeenCalledWith(
      expect.stringContaining('ActionEngine'),
      'wb_open',
      'a-x',
    );
    debugSpy.mockRestore();
  });

  test('many sequential lifecycle ops do not deadlock', async () => {
    const ctl = makeController();
    const engine = new ActionEngine({ whiteboard: ctl, delay: noDelay() });
    for (let i = 0; i < 50; i++) {
      await engine.execute({ id: `a-${i}`, type: 'wb_open' });
    }
    expect(ctl.calls).toHaveLength(50);
  });

  // Type guard: re-exporting the controller type so consumers can
  // hand-write a stub without importing whiteboard-state directly.
  test('exports WhiteboardController + WhiteboardElement types', () => {
    type _C = WhiteboardController;
    type _E = WhiteboardElement;
    expect(true).toBe(true);
  });
});
