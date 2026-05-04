/**
 * Tests for ProactiveCardManager (MAIC-411.2).
 *
 * The MAIC-411.2 risk regression net: never re-render a card for an
 * already-consumed discussion. Manager reads engine.getSnapshot()
 * .consumedDiscussions synchronously on every render — no caching.
 */
import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ProactiveCardManager } from '../ProactiveCardManager';
import type { PlaybackEngine } from '../../../lib/maic-v2/playback-engine';
import type { PlaybackSnapshot, TriggerEvent } from '../../../lib/maic-v2/playback-types';


/** Minimal engine stub — we only need `getSnapshot()` for these tests. */
function makeEngineStub(consumedDiscussions: string[]): PlaybackEngine {
  const stub: Partial<PlaybackEngine> = {
    getSnapshot(): PlaybackSnapshot {
      return {
        sceneIndex: 0,
        actionIndex: 0,
        consumedDiscussions,
      };
    },
  };
  return stub as PlaybackEngine;
}


function makeTrigger(overrides: Partial<TriggerEvent> = {}): TriggerEvent {
  return {
    id: 'd1',
    question: 'topic question',
    ...overrides,
  };
}


describe('ProactiveCardManager', () => {
  test('renders nothing when trigger is null', () => {
    const { container } = render(
      <ProactiveCardManager
        engine={makeEngineStub([])}
        trigger={null}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('maic-v2-proactive-card')).toBeNull();
  });

  test('renders a ProactiveCard when trigger is set and NOT consumed', () => {
    render(
      <ProactiveCardManager
        engine={makeEngineStub([])}
        trigger={makeTrigger({ id: 'd-fresh' })}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    expect(screen.getByTestId('maic-v2-proactive-card')).toBeInTheDocument();
    expect(
      screen.getByTestId('maic-v2-proactive-card'),
    ).toHaveAttribute('data-trigger-id', 'd-fresh');
  });

  test('drops the card silently when trigger.id is already in consumedDiscussions', () => {
    // The MAIC-411.2 dedup regression net: a snapshot/restore can
    // re-fire `_dispatchDiscussion`, but the engine's own consumed-set
    // filter catches it. The manager adds a second-line check.
    const { container } = render(
      <ProactiveCardManager
        engine={makeEngineStub(['d-consumed'])}
        trigger={makeTrigger({ id: 'd-consumed' })}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    expect(container.firstChild).toBeNull();
    expect(screen.queryByTestId('maic-v2-proactive-card')).toBeNull();
  });

  test('forwards onJoin and onSkip props to the underlying ProactiveCard', () => {
    // Sanity that the manager doesn't intercept the callbacks.
    const onJoin = vi.fn();
    const onSkip = vi.fn();
    render(
      <ProactiveCardManager
        engine={makeEngineStub([])}
        trigger={makeTrigger()}
        onJoin={onJoin}
        onSkip={onSkip}
      />,
    );
    screen.getByTestId('maic-v2-proactive-card-join').click();
    expect(onJoin).toHaveBeenCalledTimes(1);
    screen.getByTestId('maic-v2-proactive-card-skip').click();
    expect(onSkip).toHaveBeenCalledTimes(1);
  });

  test('reads consumedDiscussions on EVERY render (no caching)', () => {
    // If the manager ever caches the consumed-set in module-level
    // state, this test catches it: the same trigger toggles between
    // shown / dropped as the engine's set mutates between renders.
    let consumed: string[] = [];
    const stubEngine: Partial<PlaybackEngine> = {
      getSnapshot(): PlaybackSnapshot {
        return { sceneIndex: 0, actionIndex: 0, consumedDiscussions: consumed };
      },
    };

    const trigger = makeTrigger({ id: 'd-toggle' });
    const { rerender, container } = render(
      <ProactiveCardManager
        engine={stubEngine as PlaybackEngine}
        trigger={trigger}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    // First render: not consumed → shown
    expect(screen.getByTestId('maic-v2-proactive-card')).toBeInTheDocument();

    // Mutate the consumed-set, then re-render with the same trigger.
    consumed = ['d-toggle'];
    rerender(
      <ProactiveCardManager
        engine={stubEngine as PlaybackEngine}
        trigger={trigger}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    // Second render: now consumed → dropped
    expect(container.firstChild).toBeNull();
  });
});
