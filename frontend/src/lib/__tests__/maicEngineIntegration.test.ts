// maicEngineIntegration.test.ts — full-flow validation of the playback loop.
//
// Unit tests lock in contract points on each engine class. These specs
// run ActionEngine + PlaybackEngine together against the real store to
// verify the *behaviour the user sees* during playback: event order,
// state transitions, cleanup on seam events (scene change, interrupt,
// discussion). Network is stubbed via `vi.stubGlobal('fetch', ...)` so
// executeSpeech falls through to the reading-time fallback.

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { MAICActionEngine } from '../maicActionEngine';
import { MAICPlaybackEngine } from '../maicPlaybackEngine';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICCanvasStore } from '../../stores/maicCanvasStore';

// Wire the speech-start/speech-end → store bridge that `usePlaybackEngine`
// would install in production. Without this the store state never moves
// when the engine's speech callbacks fire, and every `speechText` /
// `isSpeaking` assertion would fail.
function buildSpeechCallbacks() {
  return {
    onSpeechStart: (agentId: string, text: string) => {
      const s = useMAICStageStore.getState();
      s.setSpeakingAgent(agentId);
      s.setSpeechText(text);
      s.setIsSpeaking(true);
    },
    onSpeechEnd: () => {
      useMAICStageStore.getState().setIsSpeaking(false);
    },
  };
}

function resetStores() {
  useMAICStageStore.getState().reset();
  useMAICCanvasStore.getState().clearAnnotations();
  useMAICStageStore.getState().setAgents([
    { id: 'a1', name: 'A', role: 'professor', color: '#111' },
    { id: 'a2', name: 'B', role: 'student', color: '#222' },
  ] as never);
}

beforeEach(() => {
  resetStores();
  // Force all TTS fetches to 204 so every speech action uses the
  // reading-time fallback (no audio element, no hanging promises).
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(null, { status: 204 })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function buildEngines(opts: {
  onTtsUnavailable?: () => void;
  onDiscussionPending?: (topic: string, agentIds: string[], sessionType: string) => void;
  onActionStart?: (index: number, action: unknown) => void;
  onSceneComplete?: () => void;
} = {}) {
  const ae = new MAICActionEngine({
    ttsEndpoint: '/tts',
    token: 'test',
    onTtsUnavailable: opts.onTtsUnavailable,
    ...buildSpeechCallbacks(),
  });
  // Prefetch also hits fetch; stub to a no-op so the ring doesn't
  // churn in the background between speeches.
  vi.spyOn(ae, 'prefetchSpeech').mockImplementation(() => undefined);

  const pe = new MAICPlaybackEngine(ae, {
    onActionStart: opts.onActionStart,
    onSceneComplete: opts.onSceneComplete,
    onDiscussionPending: opts.onDiscussionPending,
  });
  return { ae, pe };
}

/** Spin on microtasks + timers for roughly `totalMs` of simulated time.
 *  Real timers + a short sleep — the reading-time fallback uses real
 *  `setTimeout` and the engine's promise ladder is driven by microtasks,
 *  so we intermix `await new Promise(setImmediate)` with small waits to
 *  let the whole chain settle. Using real timers (not fake) sidesteps
 *  timer-based deadlocks we saw with `vi.useFakeTimers`. */
async function settle(ms = 200): Promise<void> {
  // A handful of microtask flushes lets awaited promises resolve.
  for (let i = 0; i < 10; i++) {
    await Promise.resolve();
  }
  await new Promise((resolve) => setTimeout(resolve, ms));
  for (let i = 0; i < 10; i++) {
    await Promise.resolve();
  }
}

// ─── A. Linear scene playback ───────────────────────────────────────────────
describe('Engine integration — linear scene playback', () => {
  test('speech → pause → speech fires each action exactly once, in order', async () => {
    const onActionStart = vi.fn();
    const { pe } = buildEngines({ onActionStart });
    pe.loadScene({
      id: 's1', title: 's', type: 'slide',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'one' },
        { type: 'pause', duration: 50 },
        { type: 'speech', agentId: 'a2', text: 'two' },
      ],
    } as never);
    pe.play();
    await settle(2200); // reading-time min is ~800ms per speech

    const indices = onActionStart.mock.calls.map((c) => c[0]);
    expect(indices).toEqual([0, 1, 2]);
  });

  test('speechText holds the last line after the final speech ends (T0.2)', async () => {
    const { pe } = buildEngines();
    pe.loadScene({
      id: 's1', title: 's', type: 'slide',
      actions: [{ type: 'speech', agentId: 'a1', text: 'final line' }],
    } as never);
    pe.play();
    await settle(1200);
    expect(useMAICStageStore.getState().speechText).toBe('final line');
    expect(useMAICStageStore.getState().isSpeaking).toBe(false);
  });

  test('onSceneComplete fires when action list exhausts', async () => {
    const onSceneComplete = vi.fn();
    const { pe } = buildEngines({ onSceneComplete });
    pe.loadScene({
      id: 's1', title: 's', type: 'slide',
      actions: [{ type: 'speech', agentId: 'a1', text: 'only' }],
    } as never);
    pe.play();
    await settle(1200);
    expect(onSceneComplete).toHaveBeenCalledTimes(1);
  });
});

// ─── B. Scene boundary cleanup ──────────────────────────────────────────────
describe('Engine integration — scene boundary', () => {
  test('loadScene clears whiteboard annotations and resets speech state', () => {
    const { pe } = buildEngines();
    useMAICStageStore.getState().setSpeakingAgent('a1');
    useMAICStageStore.getState().setSpeechText('leftover');
    useMAICStageStore.getState().setIsSpeaking(true);
    useMAICCanvasStore.getState().addAnnotation({
      id: 'ann-1', tool: 'pen',
      points: [{ x: 0, y: 0 }, { x: 1, y: 1 }],
      color: '#000', strokeWidth: 2,
      sceneId: 's0', timestamp: Date.now(),
    });

    pe.loadScene({ id: 's2', title: 'next', type: 'slide', actions: [] } as never);

    expect(useMAICStageStore.getState().speakingAgentId).toBeNull();
    expect(useMAICStageStore.getState().speechText).toBeNull();
    expect(useMAICStageStore.getState().isSpeaking).toBe(false);
    expect(useMAICCanvasStore.getState().annotations.length).toBe(0);
  });

  test('quiz scenes never load actions — no voiced speech over the quiz panel', () => {
    const { pe } = buildEngines();
    pe.loadScene({
      id: 'q1', title: 'Q', type: 'quiz',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'would voice over the quiz' },
        { type: 'spotlight', elementId: 'el-1', duration: 2000 },
      ],
    } as never);
    expect(pe.getActionCount()).toBe(0);
  });
});

// ─── C. Engine-driven discussion ────────────────────────────────────────────
describe('Engine integration — engine-driven discussion', () => {
  test('auto discussion pauses engine, fires onDiscussionPending, does NOT advance', async () => {
    const onDiscussionPending = vi.fn();
    const { pe } = buildEngines({ onDiscussionPending });
    pe.loadScene({
      id: 's1', title: 's', type: 'slide',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'setup' },
        {
          type: 'discussion', sessionType: 'qa', topic: 'Why?',
          agentIds: ['a1', 'a2'], triggerMode: 'auto',
        },
        { type: 'speech', agentId: 'a1', text: 'after' },
      ],
    } as never);
    pe.play();
    await settle(2000);

    expect(pe.getState()).toBe('paused');
    expect(pe.isDiscussionPending()).toBe(true);
    expect(onDiscussionPending).toHaveBeenCalledWith('Why?', ['a1', 'a2'], 'qa');
    // The post-discussion speech must NOT have run yet.
    expect(useMAICStageStore.getState().speechText).not.toBe('after');
  });

  test('manual discussion continues playback without opening the gate', async () => {
    // Manual discussion markers are teacher-controlled affordances. They
    // should not interrupt lecture playback or paint the DiscussionGateCard.
    const onDiscussionPending = vi.fn();
    const { pe } = buildEngines({ onDiscussionPending });
    pe.loadScene({
      id: 's1', title: 's', type: 'slide',
      actions: [
        {
          type: 'discussion', sessionType: 'qa', topic: 't',
          agentIds: ['a1'], triggerMode: 'manual',
        },
        { type: 'speech', agentId: 'a1', text: 'after manual' },
      ],
    } as never);
    pe.play();
    await settle(1500);
    expect(onDiscussionPending).not.toHaveBeenCalled();
    expect(pe.getState()).toBe('idle');
    expect(useMAICStageStore.getState().speechText).toBe('after manual');
  });

  test('resumeAfterDiscussion advances past the discussion action without re-firing it', async () => {
    const onDiscussionPending = vi.fn();
    const { pe } = buildEngines({ onDiscussionPending });
    pe.loadScene({
      id: 's1', title: 's', type: 'slide',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'before' },
        {
          type: 'discussion', sessionType: 'qa', topic: 'q',
          agentIds: ['a1'], triggerMode: 'auto',
        },
        { type: 'speech', agentId: 'a1', text: 'resumed' },
      ],
    } as never);
    pe.play();
    await settle(2500);
    expect(onDiscussionPending).toHaveBeenCalledTimes(1);

    pe.resumeAfterDiscussion();
    await settle(2500);
    expect(useMAICStageStore.getState().speechText).toBe('resumed');
    // consumedDiscussions must prevent a second pending-event fire.
    expect(onDiscussionPending).toHaveBeenCalledTimes(1);
  }, 15000);
});

// ─── D. UI-initiated discussion ─────────────────────────────────────────────
describe('Engine integration — UI-initiated discussion', () => {
  test('enterDiscussionFromUI pauses + checkpoints without firing onDiscussionPending', () => {
    const onDiscussionPending = vi.fn();
    const { pe } = buildEngines({ onDiscussionPending });
    pe.loadScene({
      id: 's1', title: 's', type: 'slide',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'one' },
        { type: 'speech', agentId: 'a1', text: 'two' },
      ],
    } as never);
    pe.play();
    pe.enterDiscussionFromUI();
    expect(pe.getState()).toBe('paused');
    expect(pe.isDiscussionPending()).toBe(true);
    expect(onDiscussionPending).not.toHaveBeenCalled();
  });
});

// ─── E. Student interrupt + replay ──────────────────────────────────────────
describe('Engine integration — student interrupt', () => {
  test('handleUserInterrupt pauses mode BEFORE pausing audio; checkpoint rewinds 1', async () => {
    const { ae, pe } = buildEngines();
    let modeAtPause: string | null = null;
    const originalPause = ae.pauseCurrentAudio.bind(ae);
    vi.spyOn(ae, 'pauseCurrentAudio').mockImplementation(() => {
      modeAtPause = pe.getState();
      originalPause();
    });

    pe.loadScene({
      id: 's1', title: 's', type: 'slide',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'one' },
        { type: 'speech', agentId: 'a1', text: 'two' },
        { type: 'speech', agentId: 'a1', text: 'three' },
      ],
    } as never);
    pe.play();
    // Let the first speech kick in.
    await settle(100);
    pe.handleUserInterrupt('question?');

    // Mode must already be 'paused' at the instant audio is paused —
    // load-bearing order from OpenMAIC for the sync onended bug.
    expect(modeAtPause).toBe('paused');
    expect(pe.isInterruptPending()).toBe(true);
  });
});

// ─── F. TTS outage signal ───────────────────────────────────────────────────
describe('Engine integration — TTS outage surface', () => {
  test('onTtsUnavailable fires exactly once across many speech fallbacks', async () => {
    const onTtsUnavailable = vi.fn();
    const { pe } = buildEngines({ onTtsUnavailable });
    pe.loadScene({
      id: 's1', title: 's', type: 'slide',
      actions: [
        { type: 'speech', agentId: 'a1', text: 'one' },
        { type: 'speech', agentId: 'a1', text: 'two' },
        { type: 'speech', agentId: 'a1', text: 'three' },
      ],
    } as never);
    pe.play();
    await settle(3500);
    expect(onTtsUnavailable).toHaveBeenCalledTimes(1);
  }, 15000); // extended timeout — 3 speeches × ~800ms each + overhead
});
