/**
 * Tests for ProactiveCardManager (MAIC-411.2).
 *
 * The MAIC-411.2 risk regression net: never re-render a card for an
 * already-consumed discussion. Manager reads engine.getSnapshot()
 * .consumedDiscussions synchronously on every render — no caching.
 *
 * Per the project's no-mocks rule, these tests use a REAL
 * `PlaybackEngine` instance (with real `AudioPlayer` + `ActionEngine`
 * deps) and seed the consumed-discussions set via the engine's
 * public `restoreFromSnapshot` API — the same path the persistence
 * layer (MAIC-412) uses in production.
 */
import { describe, expect, test, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ActionEngine } from '../../../lib/maic-v2/action-engine';
import { AudioPlayer } from '../../../lib/maic-v2/audio-player';
import { PlaybackEngine } from '../../../lib/maic-v2/playback-engine';
import { ProactiveCardManager } from '../ProactiveCardManager';
import type { TriggerEvent } from '../../../lib/maic-v2/playback-types';


/**
 * Build a real PlaybackEngine with a seeded `consumedDiscussions` set.
 * No stubs — real constructor path; `restoreFromSnapshot` is the
 * production-real API for setting consumed-IDs (MAIC-412 calls it
 * on every page reload).
 */
function makeEngine(consumedDiscussions: string[] = []): PlaybackEngine {
  const audioPlayer = new AudioPlayer();
  const actionEngine = new ActionEngine({ delay: () => Promise.resolve() });
  const engine = new PlaybackEngine(
    [{ id: 's1', actions: [] }],
    actionEngine,
    audioPlayer,
    {},
  );
  if (consumedDiscussions.length > 0) {
    engine.restoreFromSnapshot({
      sceneIndex: 0,
      actionIndex: 0,
      consumedDiscussions,
      sceneId: 's1',
    });
  }
  return engine;
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
        engine={makeEngine()}
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
        engine={makeEngine()}
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
        engine={makeEngine(['d-consumed'])}
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
        engine={makeEngine()}
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
    // If the manager ever caches the consumed-set, this test catches
    // it: the same trigger toggles between shown / dropped as we
    // mutate the engine's consumed-set between renders via the
    // production-real `restoreFromSnapshot` path.
    const engine = makeEngine();
    const trigger = makeTrigger({ id: 'd-toggle' });
    const { rerender, container } = render(
      <ProactiveCardManager
        engine={engine}
        trigger={trigger}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    // First render: not consumed → shown
    expect(screen.getByTestId('maic-v2-proactive-card')).toBeInTheDocument();

    // Mutate the engine's consumed-set via real restoreFromSnapshot
    // (same path the persistence layer uses on page reload), then
    // re-render with the same trigger.
    engine.restoreFromSnapshot({
      sceneIndex: 0,
      actionIndex: 0,
      consumedDiscussions: ['d-toggle'],
      sceneId: 's1',
    });
    rerender(
      <ProactiveCardManager
        engine={engine}
        trigger={trigger}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    // Second render: now consumed → dropped
    expect(container.firstChild).toBeNull();
  });
});
