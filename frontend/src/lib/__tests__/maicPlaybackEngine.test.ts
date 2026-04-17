// maicPlaybackEngine.test.ts — unit tests for Chunk 5 playback engine fixes.
//
// Covers:
//   1. Checkpoint on discussion sets actionIndex = currentActionIndex - 1
//      (so the interrupted sentence replays on resume — matches OpenMAIC).
//   2. seekToSlide(n) jumps to the `transition` action for slide n, not
//      the speech before/after it.
//   3. seekToSlide(n) is idempotent w.r.t. a no-match (returns no-op).

import { describe, test, expect, vi, beforeEach } from 'vitest';
import { MAICPlaybackEngine } from '../maicPlaybackEngine';
import { MAICActionEngine } from '../maicActionEngine';
import { useMAICStageStore } from '../../stores/maicStageStore';

beforeEach(() => {
  useMAICStageStore.setState({
    agents: [{ id: 'a1', name: 'X', role: 'professor' } as any],
  });
});

describe('MAICPlaybackEngine checkpoint', () => {
  test('checkpoint rewinds -1 on discussion trigger (replays interrupted sentence)', async () => {
    const ae = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    // Short-circuit execute() so it doesn't try to hit the network — we're
    // testing playback engine wiring, not the action engine itself.
    vi.spyOn(ae, 'execute').mockImplementation(() => Promise.resolve());
    const pe = new MAICPlaybackEngine(ae);

    pe.loadScene({
      id: 's1',
      title: 's',
      type: 'lecture',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'one' },
        { type: 'speech', agentId: 'a1', text: 'two' },
        { type: 'discussion', sessionType: 'qa', topic: 't', agentIds: ['a1'] },
        { type: 'speech', agentId: 'a1', text: 'three' },
      ],
    } as any);

    // Drive cursor to the discussion action (index 2) and invoke processNext.
    // @ts-expect-error private — test-only access
    pe.currentActionIndex = 2;
    // @ts-expect-error private — test-only access
    pe.mode = 'playing';
    // @ts-expect-error private — test-only access
    await pe.processNext();

    // processNext post-increments currentActionIndex → 3.
    // Checkpoint is max(0, 3 - 1) = 2 — the discussion action itself.
    // This is the "replay the interrupted action" behaviour: on resume we
    // re-enter the discussion action, but consumedDiscussions blocks the
    // callback, so we fall through to action index 3 (the speech after).
    // @ts-expect-error private — test-only access
    expect(pe.checkpoint?.actionIndex).toBe(2);
  });
});

describe('MAICPlaybackEngine.seekToSlide', () => {
  test('jumps to transition action for the matching slideIndex', () => {
    const ae = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    vi.spyOn(ae, 'execute').mockImplementation(() => Promise.resolve());
    const pe = new MAICPlaybackEngine(ae);

    pe.loadScene({
      id: 's1',
      title: 's',
      type: 'lecture',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'intro' }, // 0
        { type: 'transition', slideIndex: 1 }, //              1
        { type: 'speech', agentId: 'a1', text: 'slide 2' }, // 2
        { type: 'transition', slideIndex: 2 }, //              3
        { type: 'speech', agentId: 'a1', text: 'slide 3' }, // 4
      ],
    } as any);

    pe.seekToSlide(2);
    // After seekToSlide, processNext has started on index 3 and incremented
    // to 4 by the time we observe. Either value is acceptable; assert the
    // engine is past the transition (index >= 3).
    expect(pe.getCurrentActionIndex()).toBeGreaterThanOrEqual(3);
  });

  test('falls back to nearest transition below when no exact match (Chunk 10)', () => {
    // Chunk 10 changed the contract: seekToSlide must NEVER no-op.
    // If no exact transition matches, pick the greatest transition ≤
    // target, else action 0. Previously the method silently returned
    // and the caller was left with a mismatched slide/action cursor,
    // which manifested as "pressing Play restarts from the wrong
    // position" in the demo.
    const ae = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    vi.spyOn(ae, 'execute').mockImplementation(() => Promise.resolve());
    const pe = new MAICPlaybackEngine(ae);

    pe.loadScene({
      id: 's1',
      title: 's',
      type: 'lecture',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'intro' },     // 0
        { type: 'transition', slideIndex: 1 },                // 1
        { type: 'speech', agentId: 'a1', text: 'body' },      // 2
        { type: 'transition', slideIndex: 3 },                // 3
        { type: 'speech', agentId: 'a1', text: 'outro' },     // 4
      ],
    } as any);

    // Target slide 5 has no transition — nearest below is slideIndex=3
    // at action index 3. After seekToSlide fires processNext, cursor
    // advances past 3, so ≥ 3 is the acceptable landing zone.
    pe.seekToSlide(5);
    expect(pe.getCurrentActionIndex()).toBeGreaterThanOrEqual(3);
  });

  test('empty action list resolves to index 0 (defensive)', () => {
    const ae = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    vi.spyOn(ae, 'execute').mockImplementation(() => Promise.resolve());
    const pe = new MAICPlaybackEngine(ae);
    pe.loadScene({ id: 's0', title: '', type: 'lecture', actions: [] } as any);
    // Shouldn't throw; cursor stays at 0.
    pe.seekToSlide(99);
    expect(pe.getCurrentActionIndex()).toBe(0);
  });

  test('seekToSlidePaused leaves engine idle for user Play', () => {
    const ae = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    vi.spyOn(ae, 'execute').mockImplementation(() => Promise.resolve());
    const pe = new MAICPlaybackEngine(ae);

    pe.loadScene({
      id: 's1',
      title: 's',
      type: 'lecture',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'intro' },
        { type: 'transition', slideIndex: 1 },
        { type: 'speech', agentId: 'a1', text: 'body' },
      ],
    } as any);

    pe.seekToSlidePaused(1);
    expect(pe.getCurrentActionIndex()).toBe(1);
    expect(pe.getState()).toBe('idle');
  });
});
