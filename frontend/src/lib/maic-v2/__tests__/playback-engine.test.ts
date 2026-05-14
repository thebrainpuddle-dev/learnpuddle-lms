/**
 * Tests for src/lib/maic-v2/playback-engine.ts (Phase 1).
 *
 * Coverage:
 *   - State machine: idle → playing → paused → playing → idle
 *   - speech action dispatch with audio (audioPlayer fake)
 *   - speech action with no audio → reading-time timer fallback
 *   - spotlight/laser fire-and-forget → onEffectFire callback
 *   - wb_xxx and widget_xxx sync actions → ActionEngine.execute stub
 *   - snapshot / restore (incl. scene-mismatch discard)
 *   - handleUserInterrupt → live mode
 *   - isExhausted with consumed discussions
 *   - onComplete fires when all actions consumed
 */
import { describe, test, expect, beforeEach, vi } from 'vitest';

import { ActionEngine } from '../action-engine';
import type { Action } from '../action-types';
import { AudioPlayer } from '../audio-player';
import type { BrowserTTSPlayer } from '../browser-tts';
import { PlaybackEngine, type Scene } from '../playback-engine';
import type { PlaybackEngineCallbacks } from '../playback-types';


// ── Fakes ──────────────────────────────────────────────────────────


class FakeAudioPlayer extends AudioPlayer {
  // Override play() to return a controllable promise; tests trigger
  // ended manually via fireEnded().
  private endedCb: (() => void) | null = null;
  public playCalls: { audioId: string; audioUrl?: string }[] = [];
  public playReturn: boolean = true;

  override async play(audioId: string, audioUrl?: string): Promise<boolean> {
    this.playCalls.push({ audioId, audioUrl });
    return this.playReturn;
  }

  override onEnded(cb: () => void): void {
    this.endedCb = cb;
  }

  /** Test helper — synthesize the natural-end event. */
  fireEnded(): void {
    this.endedCb?.();
  }

  override pause(): void {}
  override resume(): void {}
  override stop(): void {}
  override isPlaying(): boolean { return false; }
  override hasActiveAudio(): boolean { return false; }
}


// Minimal scene helpers
function speechAction(id: string, text: string, audioUrl?: string): Action {
  return audioUrl
    ? { id, type: 'speech', text, audioUrl }
    : { id, type: 'speech', text };
}

function wbOpenAction(id: string): Action {
  return { id, type: 'wb_open' };
}

function spotlightAction(id: string, elementId: string): Action {
  return { id, type: 'spotlight', elementId };
}

function discussionAction(id: string, topic: string): Action {
  return { id, type: 'discussion', topic };
}

/**
 * Recordable BrowserTTSPlayer stub for MAIC-413.2 routing tests.
 * Real BrowserTTS integration is validated by the headless Chromium
 * smoke (no `speechSynthesis` in happy-dom).
 */
class StubBrowserTts implements BrowserTTSPlayer {
  public available = true;
  public speakCalls: { text: string; onEnded: () => void }[] = [];
  public cancelCalls = 0;
  public pauseCalls = 0;
  public resumeCalls = 0;
  isAvailable(): boolean { return this.available; }
  isSpeaking(): boolean { return false; }
  speak(text: string, onEnded: () => void): void {
    this.speakCalls.push({ text, onEnded });
  }
  pause(): void { this.pauseCalls++; }
  resume(): void { this.resumeCalls++; }
  cancel(): void { this.cancelCalls++; }
  /** Test helper — synthesize the natural completion of a speak(). */
  fireOnEnded(index = this.speakCalls.length - 1): void {
    this.speakCalls[index]?.onEnded();
  }
}


function makeEngine(
  scenes: Scene[],
  callbacks: PlaybackEngineCallbacks = {},
  player?: FakeAudioPlayer,
  browserTts?: BrowserTTSPlayer,
): {
  engine: PlaybackEngine;
  player: FakeAudioPlayer;
  engineActions: ActionEngine;
  browserTts: BrowserTTSPlayer | undefined;
} {
  const audioPlayer = player ?? new FakeAudioPlayer();
  // No-op delay so the wb_* lifecycle handlers (MAIC-211.1) don't
  // stall tests for 2000ms+ on each wb_open. PlaybackEngine tests
  // don't care about whiteboard state — only that ActionEngine.execute
  // resolves so the playback loop advances.
  const engineActions = new ActionEngine({ delay: () => Promise.resolve() });
  const engine = new PlaybackEngine(
    scenes, engineActions, audioPlayer, callbacks, browserTts,
  );
  return { engine, player: audioPlayer, engineActions, browserTts };
}


// ── State machine ───────────────────────────────────────────────────


describe('PlaybackEngine state machine', () => {
  test('starts in idle', () => {
    const { engine } = makeEngine([{ id: 's1', actions: [] }]);
    expect(engine.getMode()).toBe('idle');
  });

  test('start() transitions idle → playing → idle when scene is empty', async () => {
    const modes: string[] = [];
    const { engine } = makeEngine(
      [{ id: 's1', actions: [] }],
      { onModeChange: (m) => modes.push(m) },
    );
    engine.start();
    // Empty scene → processNext immediately calls onComplete + setMode('idle')
    await Promise.resolve();
    await Promise.resolve();  // flush microtasks
    expect(modes).toEqual(['playing', 'idle']);
  });

  test('start() while not idle is ignored', () => {
    const { engine } = makeEngine([{ id: 's1', actions: [] }]);
    engine.start();
    // Now the engine has reached idle (empty scene) — start should still work
    expect(engine.getMode()).toBe('idle');

    // Manually fake "playing" via private — we can't legally; instead
    // start a non-empty scene that holds in playing.
    const { engine: e2 } = makeEngine([{ id: 's', actions: [speechAction('a', 'hi')] }]);
    e2.start();
    expect(e2.getMode()).toBe('playing');
    // Re-starting while playing must be ignored
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    e2.start();
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  test('pause() while playing transitions to paused', () => {
    const { engine } = makeEngine([{ id: 's', actions: [speechAction('a', 'hi')] }]);
    engine.start();
    engine.pause();
    expect(engine.getMode()).toBe('paused');
  });

  test('resume() from paused returns to playing while audio is active', () => {
    // Override hasActiveAudio so resume() takes the audio path (audioPlayer.resume())
    // and stays in playing.  Without active audio resume falls through to
    // processNext() which (with a single-action scene) reaches end-of-scene
    // and correctly transitions to idle.
    class StillPlayingPlayer extends FakeAudioPlayer {
      override hasActiveAudio(): boolean { return true; }
    }
    const player = new StillPlayingPlayer();
    const { engine } = makeEngine(
      [{ id: 's', actions: [speechAction('a', 'hi', 'data:audio/mp3;base64,a')] }],
      {},
      player,
    );
    engine.start();
    engine.pause();
    engine.resume();
    expect(engine.getMode()).toBe('playing');
  });

  test('stop() returns to idle from any mode', () => {
    const { engine } = makeEngine([{ id: 's', actions: [speechAction('a', 'hi')] }]);
    engine.start();
    engine.stop();
    expect(engine.getMode()).toBe('idle');
  });
});


// ── Speech action dispatch ──────────────────────────────────────────


describe('PlaybackEngine speech action dispatch', () => {
  test('plays audio when audioUrl present, advances on ended', async () => {
    const events: string[] = [];
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [
        speechAction('a1', 'Hello', 'data:audio/mp3;base64,a'),
        wbOpenAction('a2'),
      ] }],
      {
        onSpeechStart: () => events.push('speech-start'),
        onSpeechEnd: () => events.push('speech-end'),
        onComplete: () => events.push('complete'),
      },
    );
    engine.start();
    await Promise.resolve();  // flush async play()

    expect(events).toEqual(['speech-start']);
    expect(player.playCalls).toHaveLength(1);
    expect(player.playCalls[0].audioUrl).toBe('data:audio/mp3;base64,a');

    // Simulate audio finished
    player.fireEnded();
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(events).toContain('speech-end');
    // wb_open follows; ActionEngine resolves immediately; processNext → complete
    expect(events).toContain('complete');
  });

  test('falls back to reading timer when no audioUrl', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const events: string[] = [];
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', 'Two short words')] }],
      {
        onSpeechStart: () => events.push('start'),
        onSpeechEnd: () => events.push('end'),
        onComplete: () => events.push('complete'),
      },
    );
    player.playReturn = false;  // simulate no audio source
    engine.start();

    // play() resolves to false → reading timer scheduled
    await vi.runAllTimersAsync();

    expect(events).toContain('end');
    expect(events).toContain('complete');
    vi.useRealTimers();
  });
});


// ── Spotlight / laser fire-and-forget ──────────────────────────────


describe('PlaybackEngine fire-and-forget effects', () => {
  test('spotlight emits onEffectFire and advances immediately', async () => {
    const effects: string[] = [];
    const { engine } = makeEngine(
      [{ id: 's', actions: [
        spotlightAction('a1', 'el-1'),
        spotlightAction('a2', 'el-2'),
      ] }],
      { onEffectFire: (e) => effects.push(`${e.kind}:${e.targetId}`) },
    );
    engine.start();
    // queueMicrotask between actions; flush a few cycles
    for (let i = 0; i < 5; i++) await Promise.resolve();

    expect(effects).toEqual(['spotlight:el-1', 'spotlight:el-2']);
  });
});


// ── Snapshot / restore ─────────────────────────────────────────────


describe('PlaybackEngine snapshot / restore', () => {
  test('getSnapshot returns the current cursor', () => {
    const { engine } = makeEngine([{ id: 's', actions: [wbOpenAction('a1'), wbOpenAction('a2')] }]);
    const snap = engine.getSnapshot();
    expect(snap.sceneIndex).toBe(0);
    expect(snap.actionIndex).toBe(0);
    expect(snap.consumedDiscussions).toEqual([]);
    expect(snap.sceneId).toBe('s');
  });

  test('restoreFromSnapshot sets the cursor when sceneId matches', () => {
    const { engine } = makeEngine([{ id: 's', actions: [wbOpenAction('a1'), wbOpenAction('a2')] }]);
    engine.restoreFromSnapshot({
      sceneIndex: 0, actionIndex: 1, consumedDiscussions: ['d-1'], sceneId: 's',
    });
    const snap = engine.getSnapshot();
    expect(snap.actionIndex).toBe(1);
    expect(snap.consumedDiscussions).toEqual(['d-1']);
  });

  test('restoreFromSnapshot DISCARDS when sceneId differs', () => {
    const { engine } = makeEngine([{ id: 's', actions: [wbOpenAction('a1'), wbOpenAction('a2')] }]);
    engine.restoreFromSnapshot({
      sceneIndex: 0, actionIndex: 1, consumedDiscussions: ['d-1'], sceneId: 'OTHER',
    });
    const snap = engine.getSnapshot();
    expect(snap.actionIndex).toBe(0);  // unchanged
    expect(snap.consumedDiscussions).toEqual([]);
  });
});


// ── handleUserInterrupt ────────────────────────────────────────────


describe('PlaybackEngine handleUserInterrupt', () => {
  test('moves playing → live and saves cursor', () => {
    const cb = vi.fn();
    const { engine } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', 'hi'), wbOpenAction('a2')] }],
      { onUserInterrupt: cb },
    );
    engine.start();
    engine.handleUserInterrupt('What?');
    expect(engine.getMode()).toBe('live');
    expect(cb).toHaveBeenCalledWith('What?');
  });
});


// ── isExhausted ────────────────────────────────────────────────────


describe('PlaybackEngine isExhausted', () => {
  test('false at start with non-empty actions', () => {
    const { engine } = makeEngine([{ id: 's', actions: [wbOpenAction('a1')] }]);
    expect(engine.isExhausted()).toBe(false);
  });

  test('true with empty actions list', () => {
    const { engine } = makeEngine([{ id: 's', actions: [] }]);
    expect(engine.isExhausted()).toBe(true);
  });

  test('true when only consumed discussions remain', () => {
    const { engine } = makeEngine([
      { id: 's', actions: [discussionAction('d1', 'topic')] },
    ]);
    // Manually mark consumed via skipDiscussion (sets consumedDiscussions)
    engine.start();
    // Discussion would have its 3s delay; we don't wait — just consume it manually
    // by calling skipDiscussion (which is the public API for this).
    // But there's no trigger yet. Use snapshot+restore to seed consumedDiscussions.
    engine.restoreFromSnapshot({
      sceneIndex: 0, actionIndex: 0, consumedDiscussions: ['d1'], sceneId: 's',
    });
    expect(engine.isExhausted()).toBe(true);
  });
});


// ── Sync action sequence (wb_*) ────────────────────────────────────


describe('PlaybackEngine sync action dispatch', () => {
  test('sequences multiple wb_open actions through ActionEngine', async () => {
    const events: string[] = [];
    const { engine } = makeEngine(
      [{ id: 's', actions: [
        wbOpenAction('a1'),
        wbOpenAction('a2'),
        wbOpenAction('a3'),
      ] }],
      { onComplete: () => events.push('complete') },
    );
    engine.start();
    // Allow async ActionEngine.execute to resolve for each
    for (let i = 0; i < 10; i++) await Promise.resolve();
    expect(events).toEqual(['complete']);
  });
});


// ── onProgress ─────────────────────────────────────────────────────


describe('PlaybackEngine onProgress', () => {
  test('fires once per consumed action with the snapshot pointing AT it', async () => {
    const snapshots: number[] = [];
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [
        speechAction('a1', 'hi', 'data:audio/mp3;base64,a'),
        speechAction('a2', 'bye', 'data:audio/mp3;base64,b'),
      ] }],
      { onProgress: (s) => snapshots.push(s.actionIndex) },
    );
    engine.start();
    await Promise.resolve();
    player.fireEnded();
    await Promise.resolve();
    await Promise.resolve();
    player.fireEnded();
    await Promise.resolve();
    // snapshots are taken BEFORE actionIndex++; first speech's snapshot
    // shows actionIndex=0, second's snapshot shows actionIndex=1
    expect(snapshots[0]).toBe(0);
    expect(snapshots[1]).toBe(1);
  });
});


// ── Browser-TTS fallback (MAIC-413.2) ──────────────────────────────


describe('PlaybackEngine browser-TTS fallback', () => {
  test('long no-audio text routes through BrowserTTS when available', async () => {
    // ~16s estimate at 240ms/word = ~67 words. Long enough to trip the
    // 15s threshold.
    const longText = Array.from({ length: 80 }, () => 'word').join(' ');
    const stub = new StubBrowserTts();
    const events: string[] = [];
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', longText)] }],
      {
        onSpeechStart: () => events.push('start'),
        onSpeechEnd: () => events.push('end'),
        onComplete: () => events.push('complete'),
      },
      undefined,
      stub,
    );
    player.playReturn = false;  // no audio source → fallback path
    engine.start();
    // Flush the audio.play() promise so the fallback runs.
    await Promise.resolve();
    await Promise.resolve();

    expect(stub.speakCalls).toHaveLength(1);
    expect(stub.speakCalls[0].text).toBe(longText);
    expect(events).toContain('start');
    expect(events).not.toContain('end');  // not yet — speak still in flight

    // Simulate browser-TTS completion
    stub.fireOnEnded();
    await Promise.resolve();
    expect(events).toContain('end');
    expect(events).toContain('complete');
  });

  test('short no-audio text uses reading-timer even when BrowserTTS available', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const stub = new StubBrowserTts();
    const events: string[] = [];
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', 'short msg')] }],
      {
        onSpeechStart: () => events.push('start'),
        onSpeechEnd: () => events.push('end'),
      },
      undefined,
      stub,
    );
    player.playReturn = false;
    engine.start();
    await vi.runAllTimersAsync();

    // BrowserTTS NEVER called for short text
    expect(stub.speakCalls).toHaveLength(0);
    expect(events).toContain('end');
    vi.useRealTimers();
  });

  test('long text falls back to reading-timer when BrowserTTS unavailable', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const longText = Array.from({ length: 80 }, () => 'word').join(' ');
    const stub = new StubBrowserTts();
    stub.available = false;
    const events: string[] = [];
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', longText)] }],
      {
        onSpeechStart: () => events.push('start'),
        onSpeechEnd: () => events.push('end'),
      },
      undefined,
      stub,
    );
    player.playReturn = false;
    engine.start();
    await vi.runAllTimersAsync();

    // Even though text is long, isAvailable=false → reading-timer path
    expect(stub.speakCalls).toHaveLength(0);
    expect(events).toContain('end');
    vi.useRealTimers();
  });

  test('stop() cancels active BrowserTTS session', async () => {
    const longText = Array.from({ length: 80 }, () => 'word').join(' ');
    const stub = new StubBrowserTts();
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', longText)] }],
      {},
      undefined,
      stub,
    );
    player.playReturn = false;
    engine.start();
    await Promise.resolve();
    await Promise.resolve();
    expect(stub.speakCalls).toHaveLength(1);
    expect(stub.cancelCalls).toBe(0);

    engine.stop();
    expect(stub.cancelCalls).toBe(1);
  });

  test('handleUserInterrupt cancels active BrowserTTS', async () => {
    const longText = Array.from({ length: 80 }, () => 'word').join(' ');
    const stub = new StubBrowserTts();
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', longText)] }],
      {},
      undefined,
      stub,
    );
    player.playReturn = false;
    engine.start();
    await Promise.resolve();
    await Promise.resolve();
    expect(stub.speakCalls).toHaveLength(1);

    engine.handleUserInterrupt('user wants to talk');
    expect(stub.cancelCalls).toBe(1);
    expect(engine.getMode()).toBe('live');
  });

  test('stop() does NOT cancel BrowserTTS when no session is active', () => {
    const stub = new StubBrowserTts();
    const { engine } = makeEngine(
      [{ id: 's', actions: [] }],
      {},
      undefined,
      stub,
    );
    engine.stop();
    // No browser-TTS in flight, so no cancel.
    expect(stub.cancelCalls).toBe(0);
  });

  test('engine works without an injected BrowserTTS (uses real default)', async () => {
    // No 5th arg → engine constructs a real createBrowserTTSPlayer().
    // In jsdom/happy-dom, isAvailable()=false so any speech routes
    // to the reading-timer path. This locks the constructor signature.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const events: string[] = [];
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', 'short')] }],
      {
        onSpeechEnd: () => events.push('end'),
      },
    );
    player.playReturn = false;
    engine.start();
    await vi.runAllTimersAsync();
    expect(events).toContain('end');
    vi.useRealTimers();
  });
});


// ── Browser-TTS pause/resume parity (MAIC-413.3) ──────────────────


describe('PlaybackEngine browser-TTS pause/resume parity', () => {
  function makeLongSpeechEngine() {
    const longText = Array.from({ length: 80 }, () => 'word').join(' ');
    const stub = new StubBrowserTts();
    const events: string[] = [];
    const result = makeEngine(
      [{ id: 's', actions: [speechAction('a1', longText)] }],
      {
        onSpeechStart: () => events.push('start'),
        onSpeechEnd: () => events.push('end'),
        onComplete: () => events.push('complete'),
        onModeChange: (m) => events.push(`mode:${m}`),
      },
      undefined,
      stub,
    );
    result.player.playReturn = false;
    return { ...result, stub, events };
  }

  test('pause() forwards to browserTts.pause when BrowserTTS active', async () => {
    const { engine, stub } = makeLongSpeechEngine();
    engine.start();
    await Promise.resolve();
    await Promise.resolve();
    expect(stub.speakCalls).toHaveLength(1);
    expect(stub.pauseCalls).toBe(0);

    engine.pause();
    expect(stub.pauseCalls).toBe(1);
    expect(engine.getMode()).toBe('paused');
  });

  test('resume() forwards to browserTts.resume after a pause', async () => {
    const { engine, stub } = makeLongSpeechEngine();
    engine.start();
    await Promise.resolve();
    await Promise.resolve();
    engine.pause();
    expect(stub.pauseCalls).toBe(1);
    expect(stub.resumeCalls).toBe(0);

    engine.resume();
    expect(stub.resumeCalls).toBe(1);
    expect(engine.getMode()).toBe('playing');
  });

  test('resume completes naturally via the existing onEnded callback', async () => {
    const { engine, stub, events } = makeLongSpeechEngine();
    engine.start();
    await Promise.resolve();
    await Promise.resolve();
    engine.pause();
    engine.resume();
    // Speech finishes while resumed → fire the saved onEnded
    stub.fireOnEnded();
    await Promise.resolve();
    expect(events).toContain('end');
    expect(events).toContain('complete');
  });

  test('pause() does NOT forward to browserTts when not active', () => {
    const stub = new StubBrowserTts();
    const { engine, player } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', 'hi', 'data:audio/mp3;base64,a')] }],
      {},
      undefined,
      stub,
    );
    // Audio path is active, not browser-TTS
    engine.start();
    player.fireEnded();  // wraps speech up but doesn't matter here
    engine.pause();  // While in playing/paused — but _browserTtsActive=false
    expect(stub.pauseCalls).toBe(0);
  });

  test('multiple pause/resume cycles each forward to browserTts', async () => {
    const { engine, stub } = makeLongSpeechEngine();
    engine.start();
    await Promise.resolve();
    await Promise.resolve();
    engine.pause();
    engine.resume();
    engine.pause();
    engine.resume();
    expect(stub.pauseCalls).toBe(2);
    expect(stub.resumeCalls).toBe(2);
  });
});


// ── confirmDiscussion / handleEndDiscussion round-trip (MAIC-410.1) ──


describe('PlaybackEngine confirmDiscussion / handleEndDiscussion round-trip', () => {
  function makeDiscussionScene() {
    // Scene with: speech → discussion → speech.  After confirmDiscussion
    // fires from the trigger delay, the cursor sits past the discussion
    // (it's already been consumed via processNext++).
    return [{
      id: 's1',
      actions: [
        speechAction('a1', 'first speech', 'data:audio/mp3;base64,a'),
        discussionAction('d1', 'fractions topic'),
        speechAction('a2', 'after discussion', 'data:audio/mp3;base64,b'),
      ],
    }];
  }

  test('confirmDiscussion → handleEndDiscussion preserves consumedDiscussions', () => {
    const events: string[] = [];
    const { engine, player } = makeEngine(
      makeDiscussionScene(),
      {
        onProactiveShow: () => events.push('proactive-show'),
        onDiscussionConfirmed: () => events.push('confirmed'),
        onDiscussionEnd: () => events.push('discussion-end'),
        onModeChange: (m) => events.push(`mode:${m}`),
      },
    );
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    engine.start();
    // Drain first speech so the loop reaches the discussion action.
    player.fireEnded();
    // 3-second proactive delay before currentTrigger is set.
    vi.advanceTimersByTime(3000);
    expect(events).toContain('proactive-show');

    engine.confirmDiscussion();
    expect(engine.getMode()).toBe('live');
    expect(events).toContain('confirmed');

    engine.handleEndDiscussion();
    expect(events).toContain('discussion-end');
    expect(engine.getMode()).toBe('idle');

    // The consumed-discussions set must include d1 even after the
    // round-trip — that's the dedup contract MAIC-411.2 leans on.
    const snap = engine.getSnapshot();
    expect(snap.consumedDiscussions).toContain('d1');
    vi.useRealTimers();
  });

  test('confirmDiscussion → handleEndDiscussion restores the cursor', () => {
    const { engine, player } = makeEngine(makeDiscussionScene());
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    engine.start();
    player.fireEnded();
    vi.advanceTimersByTime(3000);

    const beforeConfirm = engine.getSnapshot();
    engine.confirmDiscussion();
    engine.handleEndDiscussion();
    const afterEnd = engine.getSnapshot();
    // Cursor must be exactly where it was at confirmDiscussion (which
    // was right after the discussion action — the next action is `a2`).
    expect(afterEnd.sceneIndex).toBe(beforeConfirm.sceneIndex);
    expect(afterEnd.actionIndex).toBe(beforeConfirm.actionIndex);
    vi.useRealTimers();
  });

  test('handleEndDiscussion before any confirm is a safe no-op', () => {
    const events: string[] = [];
    const { engine } = makeEngine(
      [{ id: 's1', actions: [] }],
      { onDiscussionEnd: () => events.push('end') },
    );
    expect(engine.getMode()).toBe('idle');
    engine.handleEndDiscussion();
    // Must NOT fire onDiscussionEnd — there was nothing to end.
    expect(events).not.toContain('end');
    // Mode unchanged.
    expect(engine.getMode()).toBe('idle');
  });

  test('handleEndDiscussion fires from a paused-discussion (currentTopicState=pending) state', () => {
    const events: string[] = [];
    const { engine, player } = makeEngine(
      makeDiscussionScene(),
      {
        onDiscussionEnd: () => events.push('end'),
        onModeChange: (m) => events.push(`mode:${m}`),
      },
    );
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    engine.start();
    player.fireEnded();
    vi.advanceTimersByTime(3000);
    engine.confirmDiscussion();
    engine.pause();  // live → paused, sets currentTopicState='pending'
    engine.handleEndDiscussion();
    expect(events).toContain('end');
    expect(engine.getMode()).toBe('idle');
    vi.useRealTimers();
  });

  test('confirmDiscussion without a trigger warns + no-ops', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const events: string[] = [];
    const { engine } = makeEngine(
      [{ id: 's1', actions: [] }],
      { onDiscussionConfirmed: () => events.push('confirmed') },
    );
    engine.confirmDiscussion();
    expect(events).not.toContain('confirmed');
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });
});


// ── sendUserMessage (MAIC-410.2) ─────────────────────────────────────


describe('PlaybackEngine sendUserMessage', () => {
  test('fires onLiveUserMessage when in live mode', () => {
    const messages: string[] = [];
    const { engine } = makeEngine(
      [{ id: 's', actions: [
        speechAction('a1', 'hi', 'data:audio/mp3;base64,a'),
        discussionAction('d1', 'topic'),
      ] }],
      { onLiveUserMessage: (text) => messages.push(text) },
    );
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    engine.start();
    // Drain first speech and the 3s discussion delay so we can confirm.
    // Easier path: drive engine directly into live via handleUserInterrupt
    // (which sets mode='live' synchronously).
    engine.handleUserInterrupt('forced into live');
    expect(engine.getMode()).toBe('live');

    engine.sendUserMessage('what about edge cases?');
    expect(messages).toEqual(['what about edge cases?']);
    vi.useRealTimers();
  });

  test('warns + no-ops when called outside live mode', () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const messages: string[] = [];
    const { engine } = makeEngine(
      [{ id: 's', actions: [] }],
      { onLiveUserMessage: (text) => messages.push(text) },
    );
    expect(engine.getMode()).toBe('idle');
    engine.sendUserMessage('this should be dropped');
    expect(messages).toEqual([]);
    expect(warnSpy).toHaveBeenCalled();
    warnSpy.mockRestore();
  });

  test('multiple sendUserMessage calls in live mode each fire', () => {
    const messages: string[] = [];
    const { engine } = makeEngine(
      [{ id: 's', actions: [speechAction('a1', 'hi', 'data:audio/mp3;base64,a')] }],
      { onLiveUserMessage: (text) => messages.push(text) },
    );
    engine.handleUserInterrupt('first');
    engine.sendUserMessage('reply 1');
    engine.sendUserMessage('reply 2');
    expect(messages).toEqual(['reply 1', 'reply 2']);
  });
});
