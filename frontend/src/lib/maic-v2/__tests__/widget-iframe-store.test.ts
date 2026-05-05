/**
 * Tests for widget-iframe-store (MAIC-604).
 *
 * Validates the lift of upstream's Zustand iframe-registration
 * pattern. The store is the indirection layer between the playback
 * engine (which knows nothing about iframe lifecycles) and the
 * InteractiveRenderer (which mounts/unmounts iframes per scene).
 *
 * No mocks — exercise the real Zustand store. State is reset
 * between tests by re-registering or clearing.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useWidgetIframeStore } from '../widget-iframe-store';

function resetStore() {
  // Drain registrations + active scene; the store is a singleton so
  // tests must clean up after themselves.
  const state = useWidgetIframeStore.getState();
  Object.keys(state.sendMessageByScene).forEach((sceneId) => {
    state.registerIframe(sceneId, null);
  });
  state.setActiveScene(null);
}

beforeEach(resetStore);
afterEach(resetStore);

describe('useWidgetIframeStore — registration', () => {
  it('registers an iframe callback under the given sceneId', () => {
    const cb = vi.fn();
    useWidgetIframeStore.getState().registerIframe('scene-1', cb);
    expect(useWidgetIframeStore.getState().sendMessageByScene['scene-1']).toBe(cb);
  });

  it('unregisters when callback is null', () => {
    const cb = vi.fn();
    useWidgetIframeStore.getState().registerIframe('scene-1', cb);
    useWidgetIframeStore.getState().registerIframe('scene-1', null);
    expect(useWidgetIframeStore.getState().sendMessageByScene['scene-1']).toBeUndefined();
  });

  it('register replaces any previous callback for the same sceneId', () => {
    const first = vi.fn();
    const second = vi.fn();
    useWidgetIframeStore.getState().registerIframe('scene-1', first);
    useWidgetIframeStore.getState().registerIframe('scene-1', second);
    expect(useWidgetIframeStore.getState().sendMessageByScene['scene-1']).toBe(second);
    expect(useWidgetIframeStore.getState().sendMessageByScene['scene-1']).not.toBe(first);
  });

  it('isolates registrations across multiple sceneIds', () => {
    const a = vi.fn();
    const b = vi.fn();
    useWidgetIframeStore.getState().registerIframe('scene-a', a);
    useWidgetIframeStore.getState().registerIframe('scene-b', b);
    expect(useWidgetIframeStore.getState().sendMessageByScene).toEqual({
      'scene-a': a,
      'scene-b': b,
    });
  });
});

describe('useWidgetIframeStore — getSendMessage', () => {
  it('returns the callback for an explicit sceneId', () => {
    const cb = vi.fn();
    useWidgetIframeStore.getState().registerIframe('scene-1', cb);
    const found = useWidgetIframeStore.getState().getSendMessage('scene-1');
    expect(found).toBe(cb);
  });

  it('returns null for an unregistered sceneId', () => {
    const cb = vi.fn();
    useWidgetIframeStore.getState().registerIframe('scene-1', cb);
    expect(useWidgetIframeStore.getState().getSendMessage('other-scene')).toBeNull();
  });

  it('falls back to the active scene when sceneId is omitted', () => {
    const cb = vi.fn();
    useWidgetIframeStore.getState().registerIframe('active-scene', cb);
    useWidgetIframeStore.getState().setActiveScene('active-scene');
    expect(useWidgetIframeStore.getState().getSendMessage()).toBe(cb);
  });

  it('returns null when no sceneId given AND no active scene set', () => {
    const cb = vi.fn();
    useWidgetIframeStore.getState().registerIframe('scene-1', cb);
    expect(useWidgetIframeStore.getState().getSendMessage()).toBeNull();
  });

  it('returns null when active scene is set but no callback registered for it', () => {
    useWidgetIframeStore.getState().setActiveScene('orphan-scene');
    expect(useWidgetIframeStore.getState().getSendMessage()).toBeNull();
  });
});

describe('useWidgetIframeStore — round-trip', () => {
  it('postMessage round-trip: dispatcher calls registered callback', () => {
    const sent: Array<{ type: string; payload: Record<string, unknown> }> = [];
    const cb = (type: string, payload: Record<string, unknown>) => {
      sent.push({ type, payload });
    };

    useWidgetIframeStore.getState().registerIframe('scene-1', cb);

    const send = useWidgetIframeStore.getState().getSendMessage('scene-1');
    expect(send).not.toBeNull();
    send!('highlight', { target: '#answer-A', color: '#ffeb3b' });
    send!('setState', { numerator: 3 });

    expect(sent).toEqual([
      { type: 'highlight', payload: { target: '#answer-A', color: '#ffeb3b' } },
      { type: 'setState', payload: { numerator: 3 } },
    ]);
  });

  it('after unregister, dispatcher returns null and prior callback is not called', () => {
    const cb = vi.fn();
    useWidgetIframeStore.getState().registerIframe('scene-1', cb);
    useWidgetIframeStore.getState().registerIframe('scene-1', null);

    expect(useWidgetIframeStore.getState().getSendMessage('scene-1')).toBeNull();
    expect(cb).not.toHaveBeenCalled();
  });
});

describe('useWidgetIframeStore — active scene', () => {
  it('setActiveScene updates state.activeSceneId', () => {
    useWidgetIframeStore.getState().setActiveScene('s-42');
    expect(useWidgetIframeStore.getState().activeSceneId).toBe('s-42');
  });

  it('setActiveScene(null) clears it', () => {
    useWidgetIframeStore.getState().setActiveScene('s-42');
    useWidgetIframeStore.getState().setActiveScene(null);
    expect(useWidgetIframeStore.getState().activeSceneId).toBeNull();
  });
});
