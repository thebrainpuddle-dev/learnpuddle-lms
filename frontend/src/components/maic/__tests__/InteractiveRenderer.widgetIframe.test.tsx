// InteractiveRenderer.widgetIframe.test.tsx — MAIC-605
//
// Validates the widget-iframe-store registration lifecycle and
// postMessage dispatch path. Uses real Zustand store + real DOM
// (jsdom under vitest) — no mocks. The iframe's contentWindow is
// the boundary where vitest+jsdom legitimately can't simulate a
// cross-origin sandbox, so we verify postMessage is dispatched on
// it and trust browser semantics for the actual delivery.

import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';

import { InteractiveRenderer } from '../InteractiveRenderer';
import { useWidgetIframeStore } from '../../../lib/maic-v2/widget-iframe-store';

function resetStore() {
  const state = useWidgetIframeStore.getState();
  Object.keys(state.sendMessageByScene).forEach((sceneId) => {
    state.registerIframe(sceneId, null);
  });
  state.setActiveScene(null);
}

beforeEach(resetStore);
afterEach(() => {
  cleanup();
  resetStore();
});

describe('InteractiveRenderer — widget-iframe-store integration', () => {
  test('registers iframe with store on mount keyed by sceneId', () => {
    render(
      <InteractiveRenderer
        html="<html><body><h1>hi</h1></body></html>"
        sceneId="scene-mount-1"
      />,
    );
    const state = useWidgetIframeStore.getState();
    expect(state.sendMessageByScene['scene-mount-1']).toBeDefined();
    expect(typeof state.sendMessageByScene['scene-mount-1']).toBe('function');
  });

  test('sets activeSceneId on mount', () => {
    render(
      <InteractiveRenderer
        html="<html><body></body></html>"
        sceneId="scene-active-1"
      />,
    );
    expect(useWidgetIframeStore.getState().activeSceneId).toBe('scene-active-1');
  });

  test('unregisters iframe and clears active scene on unmount', () => {
    const { unmount } = render(
      <InteractiveRenderer html="<html></html>" sceneId="scene-unmount-1" />,
    );
    expect(useWidgetIframeStore.getState().sendMessageByScene['scene-unmount-1']).toBeDefined();

    unmount();

    expect(useWidgetIframeStore.getState().sendMessageByScene['scene-unmount-1']).toBeUndefined();
    expect(useWidgetIframeStore.getState().activeSceneId).toBeNull();
  });

  test('does not clobber activeSceneId set by a sibling on unmount', () => {
    // Mount A, then mount B which becomes active, then unmount A.
    // A's cleanup must NOT clear activeSceneId because B is now active.
    const a = render(<InteractiveRenderer html="<html></html>" sceneId="scene-a" />);
    render(<InteractiveRenderer html="<html></html>" sceneId="scene-b" />);
    // scene-b's mount overwrote activeSceneId
    expect(useWidgetIframeStore.getState().activeSceneId).toBe('scene-b');

    a.unmount();

    // a's cleanup should leave scene-b as active
    expect(useWidgetIframeStore.getState().activeSceneId).toBe('scene-b');
    expect(useWidgetIframeStore.getState().sendMessageByScene['scene-a']).toBeUndefined();
    expect(useWidgetIframeStore.getState().sendMessageByScene['scene-b']).toBeDefined();
  });

  test('sendMessage callback dispatches postMessage on iframe contentWindow', () => {
    const { container } = render(
      <InteractiveRenderer html="<html></html>" sceneId="scene-pm-1" />,
    );
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    expect(iframe).toBeTruthy();

    // Spy on the iframe's contentWindow.postMessage.
    const postSpy = vi.fn();
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      get: () => ({ postMessage: postSpy }),
    });

    const send = useWidgetIframeStore.getState().getSendMessage('scene-pm-1');
    expect(send).not.toBeNull();
    send!('highlight', { target: '#answer-A', color: '#ffeb3b' });

    expect(postSpy).toHaveBeenCalledTimes(1);
    expect(postSpy).toHaveBeenCalledWith(
      { type: 'highlight', target: '#answer-A', color: '#ffeb3b' },
      '*',
    );
  });

  test('sendMessage is no-op when iframe contentWindow is null (post-unmount race)', () => {
    const { container, unmount: _unmount } = render(
      <InteractiveRenderer html="<html></html>" sceneId="scene-pm-null" />,
    );
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      get: () => null, // simulate dead iframe
    });

    const send = useWidgetIframeStore.getState().getSendMessage('scene-pm-null');
    // Must not throw — production iframe lifecycle has this race
    expect(() => send!('setState', { numerator: 3 })).not.toThrow();
  });

  test('re-mount with same sceneId replaces the registration cleanly', () => {
    const r1 = render(
      <InteractiveRenderer html="<html></html>" sceneId="scene-replay" />,
    );
    const cb1 = useWidgetIframeStore.getState().sendMessageByScene['scene-replay'];

    r1.unmount();
    render(<InteractiveRenderer html="<html></html>" sceneId="scene-replay" />);
    const cb2 = useWidgetIframeStore.getState().sendMessageByScene['scene-replay'];

    expect(cb2).toBeDefined();
    expect(cb2).not.toBe(cb1); // fresh callback bound to the fresh iframe
  });

  test('accepts optional widgetConfig prop without crashing or rendering it', () => {
    // widgetConfig is reserved for MAIC-606's action engine — this
    // component just types it through. Verify the component doesn't
    // try to render the config or barf on its presence.
    render(
      <InteractiveRenderer
        html="<html><body>iframe-content</body></html>"
        sceneId="scene-with-config"
        widgetConfig={{
          type: 'simulation',
          concept: 'Newton 2nd law',
          description: 'F=ma',
          variables: [
            { name: 'mass', label: 'Mass', min: 1, max: 10, default: 5 },
          ],
        }}
      />,
    );
    expect(useWidgetIframeStore.getState().sendMessageByScene['scene-with-config']).toBeDefined();
  });
});

describe('InteractiveRenderer — onWidgetEvent uplink (MAIC-607)', () => {
  test('forwards messages from the registered iframe to onWidgetEvent', () => {
    const onWidgetEvent = vi.fn();
    const { container } = render(
      <InteractiveRenderer
        html="<html></html>"
        sceneId="scene-up-1"
        onWidgetEvent={onWidgetEvent}
      />,
    );
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    // Pin a stable contentWindow we can spoof as the message source.
    const fakeWin = {} as Window;
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      get: () => fakeWin,
    });

    // Dispatch a message-event whose source matches the iframe's window.
    const evt = new MessageEvent('message', {
      data: { type: 'click', target: '#answer-A', payloadKey: 'value' },
      source: fakeWin,
    });
    window.dispatchEvent(evt);

    expect(onWidgetEvent).toHaveBeenCalledTimes(1);
    expect(onWidgetEvent).toHaveBeenCalledWith('click', {
      target: '#answer-A',
      payloadKey: 'value',
    });
  });

  test('drops messages from other windows (security: not trusting any sender)', () => {
    const onWidgetEvent = vi.fn();
    const { container } = render(
      <InteractiveRenderer
        html="<html></html>"
        sceneId="scene-up-2"
        onWidgetEvent={onWidgetEvent}
      />,
    );
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    const realWin = {} as Window;
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      get: () => realWin,
    });

    // Hostile message — source is some OTHER window.
    const fakeOtherWin = {} as Window;
    const evt = new MessageEvent('message', {
      data: { type: 'click', target: '#hijack' },
      source: fakeOtherWin,
    });
    window.dispatchEvent(evt);

    expect(onWidgetEvent).not.toHaveBeenCalled();
  });

  test('ignores messages without a string `type` field (malformed payload)', () => {
    const onWidgetEvent = vi.fn();
    const { container } = render(
      <InteractiveRenderer
        html="<html></html>"
        sceneId="scene-up-3"
        onWidgetEvent={onWidgetEvent}
      />,
    );
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    const fakeWin = {} as Window;
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      get: () => fakeWin,
    });

    // Various malformed payloads — none should reach onWidgetEvent.
    for (const data of [
      null,
      undefined,
      'string-not-object',
      42,
      { type: null },
      { type: '' },
      { notATypeField: 'click' },
    ] as unknown[]) {
      window.dispatchEvent(new MessageEvent('message', { data, source: fakeWin }));
    }
    expect(onWidgetEvent).not.toHaveBeenCalled();
  });

  test('strips `type` from payload before forwarding (clean event/payload split)', () => {
    const onWidgetEvent = vi.fn();
    const { container } = render(
      <InteractiveRenderer
        html="<html></html>"
        sceneId="scene-up-4"
        onWidgetEvent={onWidgetEvent}
      />,
    );
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    const fakeWin = {} as Window;
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      get: () => fakeWin,
    });

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'submit', answer: 42, score: 1 },
        source: fakeWin,
      }),
    );

    expect(onWidgetEvent).toHaveBeenCalledWith('submit', { answer: 42, score: 1 });
    // `type` must NOT leak into the payload — that's the verb, not data.
    const payload = onWidgetEvent.mock.calls[0][1];
    expect(payload).not.toHaveProperty('type');
  });

  test('removes the listener on unmount (no leak across scene changes)', () => {
    const onWidgetEvent = vi.fn();
    const { container, unmount } = render(
      <InteractiveRenderer
        html="<html></html>"
        sceneId="scene-up-5"
        onWidgetEvent={onWidgetEvent}
      />,
    );
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    const fakeWin = {} as Window;
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      get: () => fakeWin,
    });

    unmount();

    // Post-unmount message must not invoke the callback.
    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'click' },
        source: fakeWin,
      }),
    );
    expect(onWidgetEvent).not.toHaveBeenCalled();
  });

  test('without onWidgetEvent prop, no listener is attached (zero overhead default)', () => {
    // Spy on addEventListener to verify we don't register when no
    // callback is provided. Avoids a useless listener in non-uplink
    // playback contexts (e.g. read-only embeds).
    const addSpy = vi.spyOn(window, 'addEventListener');
    render(<InteractiveRenderer html="<html></html>" sceneId="scene-up-6" />);
    const messageRegistrations = addSpy.mock.calls.filter(
      (c) => c[0] === 'message',
    );
    expect(messageRegistrations.length).toBe(0);
    addSpy.mockRestore();
  });
});
