// SceneRenderer.widgetEvent.test.tsx — MAIC-608
//
// Validates the SceneRenderer → InteractiveRenderer onWidgetEvent
// wiring: when a scene is interactive AND the parent provides an
// onWidgetEvent callback, iframe-emitted messages reach the parent
// with the sceneId bound from scene.id (not re-derived). This is the
// integration the production classroom UI uses to forward widget
// events to channel.send({action:'widget_event', ...}).

import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';

import { SceneRenderer } from '../SceneRenderer';
import { useWidgetIframeStore } from '../../../lib/maic-v2/widget-iframe-store';
import type { MAICScene } from '../../../types/maic-scenes';

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

const interactiveScene: MAICScene = {
  id: 'scene-int-42',
  title: 'Fraction Bar',
  type: 'interactive',
  content: {
    type: 'interactive',
    html: '<html><body>fake widget</body></html>',
  },
};

describe('SceneRenderer — interactive scene + onWidgetEvent (MAIC-608)', () => {
  test('forwards iframe messages to onWidgetEvent with scene.id bound', () => {
    const onWidgetEvent = vi.fn();
    const { container } = render(
      <SceneRenderer scene={interactiveScene} onWidgetEvent={onWidgetEvent} />,
    );
    const iframe = container.querySelector('iframe') as HTMLIFrameElement;
    const fakeWin = {} as Window;
    Object.defineProperty(iframe, 'contentWindow', {
      configurable: true,
      get: () => fakeWin,
    });

    window.dispatchEvent(
      new MessageEvent('message', {
        data: { type: 'drag', numerator: 3 },
        source: fakeWin,
      }),
    );

    // Three-arg form: (sceneId, event, payload)
    expect(onWidgetEvent).toHaveBeenCalledWith(
      'scene-int-42',
      'drag',
      { numerator: 3 },
    );
  });

  test('without onWidgetEvent prop, no listener attaches (zero overhead)', () => {
    // Interactive scene + no callback — InteractiveRenderer's
    // useEffect short-circuits before addEventListener.
    const addSpy = vi.spyOn(window, 'addEventListener');
    render(<SceneRenderer scene={interactiveScene} />);
    const messageRegs = addSpy.mock.calls.filter((c) => c[0] === 'message');
    expect(messageRegs.length).toBe(0);
    addSpy.mockRestore();
  });

  test('iframe registered with widget-iframe-store (round-trip with action engine works)', () => {
    render(<SceneRenderer scene={interactiveScene} />);
    // SceneRenderer didn't pass widgetConfig nor a callback —
    // registration should still happen since it's purely sceneId-based.
    expect(
      useWidgetIframeStore.getState().sendMessageByScene['scene-int-42'],
    ).toBeDefined();
  });

  test('quiz scene does NOT spawn an iframe or register a widget callback', () => {
    const quizScene: MAICScene = {
      id: 'scene-quiz-1',
      title: 'Quick check',
      type: 'quiz',
      content: {
        type: 'quiz',
        questions: [
          {
            question: 'Pick one',
            options: ['A', 'B'],
            correctAnswerIndex: 0,
          },
        ],
      },
    };
    const { container } = render(
      <SceneRenderer
        scene={quizScene}
        onWidgetEvent={() => {
          throw new Error('should not be called for quiz scenes');
        }}
      />,
    );
    expect(container.querySelector('iframe')).toBeNull();
    expect(
      useWidgetIframeStore.getState().sendMessageByScene['scene-quiz-1'],
    ).toBeUndefined();
  });

  test('scene re-render with same scene id keeps the registration alive', () => {
    const onWidgetEvent = vi.fn();
    const { rerender, container } = render(
      <SceneRenderer scene={interactiveScene} onWidgetEvent={onWidgetEvent} />,
    );
    const iframeBefore = container.querySelector('iframe');

    rerender(<SceneRenderer scene={interactiveScene} onWidgetEvent={onWidgetEvent} />);

    // Same sceneId → same iframe element retained, registration still live.
    expect(container.querySelector('iframe')).toBe(iframeBefore);
    expect(
      useWidgetIframeStore.getState().sendMessageByScene['scene-int-42'],
    ).toBeDefined();
  });

  test('switching to a different interactive scene swaps iframe + registration', () => {
    const onWidgetEvent = vi.fn();
    const { rerender, container } = render(
      <SceneRenderer scene={interactiveScene} onWidgetEvent={onWidgetEvent} />,
    );
    expect(
      useWidgetIframeStore.getState().sendMessageByScene['scene-int-42'],
    ).toBeDefined();

    const otherScene: MAICScene = {
      ...interactiveScene,
      id: 'scene-int-99',
    };
    rerender(<SceneRenderer scene={otherScene} onWidgetEvent={onWidgetEvent} />);

    // Old registration cleared, new one in place.
    expect(
      useWidgetIframeStore.getState().sendMessageByScene['scene-int-42'],
    ).toBeUndefined();
    expect(
      useWidgetIframeStore.getState().sendMessageByScene['scene-int-99'],
    ).toBeDefined();
    expect(container.querySelector('iframe')).not.toBeNull();
  });
});
