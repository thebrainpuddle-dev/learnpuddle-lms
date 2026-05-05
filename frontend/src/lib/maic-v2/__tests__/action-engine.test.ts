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

import { ActionEngine, applyEditOperation } from '../action-engine';
import type { Action } from '../action-types';
import { useWidgetIframeStore } from '../widget-iframe-store';
import type {
  CodeLine,
  WhiteboardController,
  WhiteboardElement,
} from '../whiteboard-state';


// ── Helpers ────────────────────────────────────────────────────────


function makeController(seedElements: WhiteboardElement[] = []): WhiteboardController & {
  calls: Array<{ method: string; args: unknown[] }>;
  elements: WhiteboardElement[];
} {
  const calls: Array<{ method: string; args: unknown[] }> = [];
  // Mutable element registry for getElement() — the engine's
  // wb_edit_code reads it after a wb_draw_code add. addElement /
  // updateElement / deleteElement mutate this so a sequence of
  // [draw, edit] reflects realistic state.
  const elements: WhiteboardElement[] = [...seedElements];
  const keyOf = (el: WhiteboardElement) =>
    (el as { elementId?: string }).elementId ?? (el as { id: string }).id;
  return {
    calls,
    elements,
    setOpen(open) {
      calls.push({ method: 'setOpen', args: [open] });
    },
    setClearing(clearing) {
      calls.push({ method: 'setClearing', args: [clearing] });
    },
    addElement(element) {
      calls.push({ method: 'addElement', args: [element] });
      const k = keyOf(element);
      const idx = elements.findIndex((e) => keyOf(e) === k);
      if (idx >= 0) elements[idx] = element;
      else elements.push(element);
    },
    updateElement(key, patch) {
      calls.push({ method: 'updateElement', args: [key, patch] });
      const idx = elements.findIndex((e) => keyOf(e) === key);
      if (idx >= 0) elements[idx] = { ...elements[idx], ...patch } as WhiteboardElement;
    },
    deleteElement(key) {
      calls.push({ method: 'deleteElement', args: [key] });
      const idx = elements.findIndex((e) => keyOf(e) === key);
      if (idx >= 0) elements.splice(idx, 1);
    },
    clear() {
      calls.push({ method: 'clear', args: [] });
      elements.length = 0;
    },
    getElement(key) {
      return elements.find((e) => keyOf(e) === key);
    },
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

  test('wb_draw_code adds element augmented with lines + waits 800 ms', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });
    const action: Action = {
      id: 'a1', type: 'wb_draw_code', language: 'javascript',
      code: 'const x = 42;\nconsole.log(x);', x: 0, y: 0,
    };

    await engine.execute(action);

    // ActionEngine augments wb_draw_code with `lines: [{id, content}]`
    // before adding to the registry — wb_edit_code (MAIC-214.2) targets
    // these stable IDs.
    expect(ctl.calls).toHaveLength(1);
    expect(ctl.calls[0].method).toBe('addElement');
    const added = ctl.calls[0].args[0] as {
      type: string;
      lines: Array<{ id: string; content: string }>;
    };
    expect(added.type).toBe('wb_draw_code');
    expect(added.lines).toHaveLength(2);
    expect(added.lines[0]).toEqual({ id: 'L1', content: 'const x = 42;' });
    expect(added.lines[1]).toEqual({ id: 'L2', content: 'console.log(x);' });
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
  test('wb_edit_code resolves without handler (MAIC-214.2 fills it)', async () => {
    const engine = new ActionEngine({ delay: noDelay() });
    await expect(
      engine.execute({
        id: '8',
        type: 'wb_edit_code',
        elementId: 'c1',
        operation: 'insert_after',
        lineId: 'L1',
        content: 'x',
      }),
    ).resolves.toBeUndefined();
  });

  test('widget_* without registered iframe warns + still resolves; play_video stays deferred', async () => {
    // MAIC-606 wired widget_* through the widget-iframe-store. With
    // no scene/iframe registered, dispatch logs a warning and the
    // action still resolves so the playback loop's pacing stays
    // consistent across active and non-interactive scenes.
    const engine = new ActionEngine({ delay: noDelay() });
    const actions: Action[] = [
      { id: '1', type: 'widget_highlight', target: '#x' },
      { id: '2', type: 'widget_setState', state: { foo: 1 } },
      { id: '3', type: 'widget_annotation', target: '#x' },
      { id: '4', type: 'widget_reveal', target: '#x' },
      { id: '5', type: 'play_video', elementId: 'v' },  // still deferred
    ];
    for (const a of actions) {
      await expect(engine.execute(a)).resolves.toBeUndefined();
    }
  });
});


// ── MAIC-606: widget_* dispatch through widget-iframe-store ──────────


describe('ActionEngine — widget_* dispatch (MAIC-606)', () => {
  // Reset the widget-iframe-store between tests since it's a singleton.
  function resetWidgetStore() {
    const state = useWidgetIframeStore.getState();
    Object.keys(state.sendMessageByScene).forEach((sceneId) => {
      state.registerIframe(sceneId, null);
    });
    state.setActiveScene(null);
  }

  beforeEach(resetWidgetStore);

  test('widget_highlight posts HIGHLIGHT_ELEMENT to active iframe', async () => {
    const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
    useWidgetIframeStore.getState().registerIframe('s1', (type, payload) => {
      sent.push({ type, payload });
    });
    useWidgetIframeStore.getState().setActiveScene('s1');

    const engine = new ActionEngine({ delay: noDelay() });
    await engine.execute({ id: 'a1', type: 'widget_highlight', target: '#answer-A' });

    expect(sent).toEqual([
      { type: 'HIGHLIGHT_ELEMENT', payload: { target: '#answer-A' } },
    ]);
  });

  test('widget_setState posts SET_WIDGET_STATE with state payload', async () => {
    const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
    useWidgetIframeStore.getState().registerIframe('s1', (type, payload) => {
      sent.push({ type, payload });
    });
    useWidgetIframeStore.getState().setActiveScene('s1');

    const engine = new ActionEngine({ delay: noDelay() });
    await engine.execute({
      id: 'a2',
      type: 'widget_setState',
      state: { numerator: 3, denominator: 7 },
    });

    expect(sent).toEqual([
      {
        type: 'SET_WIDGET_STATE',
        payload: { state: { numerator: 3, denominator: 7 } },
      },
    ]);
  });

  test('widget_annotation posts ANNOTATE_ELEMENT', async () => {
    const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
    useWidgetIframeStore.getState().registerIframe('s1', (type, payload) => {
      sent.push({ type, payload });
    });
    useWidgetIframeStore.getState().setActiveScene('s1');

    const engine = new ActionEngine({ delay: noDelay() });
    await engine.execute({ id: 'a3', type: 'widget_annotation', target: '#step-2' });

    expect(sent).toEqual([
      { type: 'ANNOTATE_ELEMENT', payload: { target: '#step-2' } },
    ]);
  });

  test('widget_reveal posts REVEAL_ELEMENT', async () => {
    const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
    useWidgetIframeStore.getState().registerIframe('s1', (type, payload) => {
      sent.push({ type, payload });
    });
    useWidgetIframeStore.getState().setActiveScene('s1');

    const engine = new ActionEngine({ delay: noDelay() });
    await engine.execute({ id: 'a4', type: 'widget_reveal', target: '#hidden-hint' });

    expect(sent).toEqual([
      { type: 'REVEAL_ELEMENT', payload: { target: '#hidden-hint' } },
    ]);
  });

  test('widget action with no registered iframe is a warn-but-continue no-op', async () => {
    // No registerIframe call: getSendMessage() returns null.
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const engine = new ActionEngine({ delay: noDelay() });

    await expect(
      engine.execute({ id: 'a5', type: 'widget_highlight', target: '#x' }),
    ).resolves.toBeUndefined();

    // Warning fired
    expect(warnSpy).toHaveBeenCalled();
    const msg = warnSpy.mock.calls.flat().join(' ');
    expect(msg).toMatch(/no widget-iframe callback/i);
    warnSpy.mockRestore();
  });

  test('uses ACTIVE iframe when multiple scenes are registered', async () => {
    // Two scenes registered; setActiveScene picks the destination.
    const sentToA: Array<string> = [];
    const sentToB: Array<string> = [];
    useWidgetIframeStore.getState().registerIframe('a', (type) => sentToA.push(type));
    useWidgetIframeStore.getState().registerIframe('b', (type) => sentToB.push(type));
    useWidgetIframeStore.getState().setActiveScene('b');

    const engine = new ActionEngine({ delay: noDelay() });
    await engine.execute({ id: 'a6', type: 'widget_highlight', target: '#x' });

    expect(sentToA).toEqual([]);
    expect(sentToB).toEqual(['HIGHLIGHT_ELEMENT']);
  });

  test('all four widget actions dispatched in order', async () => {
    // Mirrors a real classroom turn: highlight → setState → annotation → reveal.
    const sent: Array<string> = [];
    useWidgetIframeStore.getState().registerIframe('s1', (type) => sent.push(type));
    useWidgetIframeStore.getState().setActiveScene('s1');

    const engine = new ActionEngine({ delay: noDelay() });
    await engine.execute({ id: '1', type: 'widget_highlight', target: '#a' });
    await engine.execute({ id: '2', type: 'widget_setState', state: { x: 1 } });
    await engine.execute({ id: '3', type: 'widget_annotation', target: '#b' });
    await engine.execute({ id: '4', type: 'widget_reveal', target: '#c' });

    expect(sent).toEqual([
      'HIGHLIGHT_ELEMENT',
      'SET_WIDGET_STATE',
      'ANNOTATE_ELEMENT',
      'REVEAL_ELEMENT',
    ]);
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


// ── applyEditOperation pure helper (MAIC-214.2) ────────────────────


function fiveLines(): CodeLine[] {
  return [
    { id: 'L1', content: 'function fib(n) {' },
    { id: 'L2', content: '  if (n < 2)' },
    { id: 'L3', content: '    return n;' },
    { id: 'L4', content: '  return fib(n-1) + fib(n-2);' },
    { id: 'L5', content: '}' },
  ];
}


describe('applyEditOperation — insert_after', () => {
  test('inserts the content after lineId, preserving existing ids', () => {
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'insert_after', lineId: 'L2', content: '// added',
      },
      fiveLines(),
    );
    expect(result).toHaveLength(6);
    expect(result.map((l) => l.id).slice(0, 2)).toEqual(['L1', 'L2']);
    expect(result[2].content).toBe('// added');
    expect(result[2].id).not.toBe('L1');
    expect(result[2].id).not.toBe('L2');
    expect(result[2].id).not.toBe('L3');
    expect(result.slice(3).map((l) => l.id)).toEqual(['L3', 'L4', 'L5']);
  });

  test('multi-line content split on \\n with unique ids per line', () => {
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'insert_after', lineId: 'L1', content: 'a\nb\nc',
      },
      fiveLines(),
    );
    expect(result).toHaveLength(8);
    const newIds = [result[1].id, result[2].id, result[3].id];
    expect(new Set(newIds).size).toBe(3);  // all unique
    expect(result.slice(1, 4).map((l) => l.content)).toEqual(['a', 'b', 'c']);
  });

  test('no-op when lineId not found (returns same reference)', () => {
    const before = fiveLines();
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'insert_after', lineId: 'no-such-id', content: 'x',
      },
      before,
    );
    expect(result).toBe(before);
  });

  test('no-op when lineId omitted', () => {
    const before = fiveLines();
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'insert_after', content: 'x',
      } as Action & { type: 'wb_edit_code' },
      before,
    );
    expect(result).toBe(before);
  });
});


describe('applyEditOperation — insert_before', () => {
  test('inserts the content before lineId', () => {
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'insert_before', lineId: 'L3', content: '// note',
      },
      fiveLines(),
    );
    expect(result).toHaveLength(6);
    expect(result.slice(0, 2).map((l) => l.id)).toEqual(['L1', 'L2']);
    expect(result[2].content).toBe('// note');
    expect(result.slice(3).map((l) => l.id)).toEqual(['L3', 'L4', 'L5']);
  });

  test('insert_before L1 puts content at index 0', () => {
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'insert_before', lineId: 'L1', content: 'header',
      },
      fiveLines(),
    );
    expect(result[0].content).toBe('header');
    expect(result.slice(1).map((l) => l.id)).toEqual(['L1', 'L2', 'L3', 'L4', 'L5']);
  });
});


describe('applyEditOperation — delete_lines', () => {
  test('removes every line whose id is in lineIds', () => {
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'delete_lines', lineIds: ['L2', 'L4'],
      },
      fiveLines(),
    );
    expect(result.map((l) => l.id)).toEqual(['L1', 'L3', 'L5']);
  });

  test('no-op when none of the ids match', () => {
    const before = fiveLines();
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'delete_lines', lineIds: ['Lxx', 'Lyy'],
      },
      before,
    );
    expect(result).toBe(before);
  });

  test('partial match still removes the matching ones', () => {
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'delete_lines', lineIds: ['L1', 'no-such'],
      },
      fiveLines(),
    );
    expect(result.map((l) => l.id)).toEqual(['L2', 'L3', 'L4', 'L5']);
  });

  test('empty lineIds is a no-op', () => {
    const before = fiveLines();
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'delete_lines', lineIds: [],
      },
      before,
    );
    expect(result).toBe(before);
  });
});


describe('applyEditOperation — replace_lines', () => {
  test('removes the targeted lines and inserts content at their first position', () => {
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'replace_lines', lineIds: ['L2', 'L3'], content: 'X\nY',
      },
      fiveLines(),
    );
    expect(result).toHaveLength(5);
    expect(result.map((l) => l.id).slice(0, 1)).toEqual(['L1']);
    expect(result[1].content).toBe('X');
    expect(result[2].content).toBe('Y');
    expect(result.slice(3).map((l) => l.id)).toEqual(['L4', 'L5']);
  });

  test('replace_lines with non-contiguous ids — first match position is the insertion point', () => {
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'replace_lines', lineIds: ['L2', 'L4'], content: 'M',
      },
      fiveLines(),
    );
    // L2 + L4 removed; replacement 'M' inserted at the position L2
    // used to occupy among the survivors → between L1 and L3.
    expect(result.map((l) => l.id).slice(0, 1)).toEqual(['L1']);
    expect(result[1].content).toBe('M');
    expect(result.slice(2).map((l) => l.id)).toEqual(['L3', 'L5']);
  });

  test('no-op when lineIds is empty', () => {
    const before = fiveLines();
    const result = applyEditOperation(
      {
        id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
        operation: 'replace_lines', lineIds: [], content: 'X',
      },
      before,
    );
    expect(result).toBe(before);
  });
});


describe('ActionEngine — wb_edit_code dispatch', () => {
  function preDrawnCodeElement(): WhiteboardElement {
    return {
      id: 'a-draw-1', elementId: 'c1', type: 'wb_draw_code',
      language: 'javascript',
      code: 'A\nB\nC',
      x: 0, y: 0,
      lines: [
        { id: 'L1', content: 'A' },
        { id: 'L2', content: 'B' },
        { id: 'L3', content: 'C' },
      ],
    };
  }

  test('dispatch: insert_after issues updateElement with the spliced lines + waits 600ms', async () => {
    const ctl = makeController([preDrawnCodeElement()]);
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    await engine.execute({
      id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
      operation: 'insert_after', lineId: 'L1', content: 'NEW',
    });

    const updateCall = ctl.calls.find((c) => c.method === 'updateElement');
    expect(updateCall).toBeDefined();
    expect(updateCall!.args[0]).toBe('c1');
    const patch = updateCall!.args[1] as { lines: CodeLine[] };
    expect(patch.lines.map((l) => l.content)).toEqual(['A', 'NEW', 'B', 'C']);
    expect(recorded).toEqual([600]);
  });

  test('dispatch: missing element — warns + waits + does NOT call updateElement', async () => {
    const ctl = makeController();  // empty registry
    const { delay, recorded } = recordingDelay();
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    await engine.execute({
      id: 'edit-1', type: 'wb_edit_code', elementId: 'no-such',
      operation: 'insert_after', lineId: 'L1', content: 'x',
    });

    expect(ctl.calls.some((c) => c.method === 'updateElement')).toBe(false);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('not found'));
    expect(recorded).toEqual([600]);
    warnSpy.mockRestore();
  });

  test('dispatch: missing elementId on action — warns + waits', async () => {
    const ctl = makeController();
    const { delay, recorded } = recordingDelay();
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    await engine.execute({
      id: 'edit-1', type: 'wb_edit_code',
      operation: 'insert_after', lineId: 'L1', content: 'x',
    } as Action);

    expect(ctl.calls.some((c) => c.method === 'updateElement')).toBe(false);
    expect(warnSpy).toHaveBeenCalledWith(expect.stringContaining('elementId'));
    expect(recorded).toEqual([600]);
    warnSpy.mockRestore();
  });

  test('dispatch: no-op edit (insert_after unknown lineId) does NOT call updateElement', async () => {
    const ctl = makeController([preDrawnCodeElement()]);
    const { delay, recorded } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    await engine.execute({
      id: 'edit-1', type: 'wb_edit_code', elementId: 'c1',
      operation: 'insert_after', lineId: 'no-such-id', content: 'x',
    });

    expect(ctl.calls.some((c) => c.method === 'updateElement')).toBe(false);
    expect(recorded).toEqual([600]);
  });

  test('end-to-end: wb_draw_code → wb_edit_code(insert_after) flows through addElement→updateElement', async () => {
    const ctl = makeController();  // empty
    const { delay } = recordingDelay();
    const engine = new ActionEngine({ whiteboard: ctl, delay });

    // Draw
    await engine.execute({
      id: 'a-draw', type: 'wb_draw_code', elementId: 'c1',
      language: 'javascript', code: 'one\ntwo\nthree',
      x: 0, y: 0,
    });
    // After add, the controller's getElement should expose lines L1..L3
    const drawn = ctl.getElement('c1') as WhiteboardElement;
    expect(drawn).toBeDefined();
    expect(drawn.type).toBe('wb_draw_code');
    expect((drawn as { lines: CodeLine[] }).lines.map((l) => l.content)).toEqual(['one', 'two', 'three']);

    // Edit
    await engine.execute({
      id: 'a-edit', type: 'wb_edit_code', elementId: 'c1',
      operation: 'insert_after', lineId: 'L2', content: 'two-and-a-half',
    });

    const edited = ctl.getElement('c1') as WhiteboardElement;
    const lines = (edited as { lines: CodeLine[] }).lines;
    expect(lines.map((l) => l.content)).toEqual([
      'one', 'two', 'two-and-a-half', 'three',
    ]);
    // Original ids preserved on surviving lines
    expect(lines[0].id).toBe('L1');
    expect(lines[1].id).toBe('L2');
    expect(lines[3].id).toBe('L3');
    // New line has a generated id distinct from L1..L3
    expect(['L1', 'L2', 'L3']).not.toContain(lines[2].id);
  });
});
