// lib/maicPlaybackEngine.ts — Sequences through a scene's action array
//
// Architecture aligned with upstream OpenMAIC PlaybackEngine:
//   - Recursive processNext() instead of while-loop
//   - Mode guard at every callback entry: if (mode !== 'playing') return
//   - stop() sets mode to 'idle' BEFORE stopping audio (prevents stale callbacks)
//   - Speech actions are callback-driven (non-blocking)
//   - Fire-and-forget actions use queueMicrotask for non-blocking progression

import { MAICActionEngine } from './maicActionEngine';
import type { MAICAction } from '../types/maic-actions';
import type { MAICScene } from '../types/maic-scenes';

// ─── Types ──────────────────────────────────────────────────────────────────

export type PlaybackState = 'idle' | 'playing' | 'paused';

export interface PlaybackCheckpoint {
  actionIndex: number;
  sceneId?: string;
}

export interface PlaybackCallbacks {
  onStateChange?: (state: PlaybackState) => void;
  onActionStart?: (index: number, action: MAICAction) => void;
  onSceneComplete?: () => void;
  onDiscussionPending?: (topic: string, agentIds: string[], sessionType: string) => void;
  /** Fired when a student interrupt happens mid-playback. Host (Stage/
   *  ChatPanel) is responsible for dispatching the chat stream; the
   *  engine has already saved a checkpoint so `resumeAfterInterrupt()`
   *  will replay the interrupted sentence. Porting P4.1. */
  onUserInterrupt?: (text: string) => void;
}

// ─── Engine ─────────────────────────────────────────────────────────────────

export class MAICPlaybackEngine {
  private actionEngine: MAICActionEngine;
  private mode: PlaybackState = 'idle';
  private currentActionIndex = 0;
  private actions: MAICAction[] = [];
  private disposed = false;

  // Monotonic session token — bumped by every stop() (directly or via
  // loadScene/seekToSlide). Every deferred callback captures the token
  // at dispatch time and no-ops when it changes. This prevents a stale
  // speech promise whose audio was aborted by seekToSlide from racing the
  // freshly-started chain and double-incrementing currentActionIndex.
  private sessionId = 0;

  // Discussion state
  private consumedDiscussions = new Set<number>();
  private checkpoint: PlaybackCheckpoint | null = null;
  private discussionPending = false;

  private onStateChange?: (state: PlaybackState) => void;
  private onActionStart?: (index: number, action: MAICAction) => void;
  private onSceneComplete?: () => void;
  private onDiscussionPending?: (topic: string, agentIds: string[], sessionType: string) => void;
  private onUserInterrupt?: (text: string) => void;
  /** Porting P4.1 — latched true between handleUserInterrupt() and
   *  resumeAfterInterrupt(). Keeps the engine paused without flipping
   *  to the discussion state machine. */
  private interruptPending = false;

  constructor(actionEngine: MAICActionEngine, callbacks?: PlaybackCallbacks) {
    this.actionEngine = actionEngine;
    this.onStateChange = callbacks?.onStateChange;
    this.onActionStart = callbacks?.onActionStart;
    this.onSceneComplete = callbacks?.onSceneComplete;
    this.onDiscussionPending = callbacks?.onDiscussionPending;
    this.onUserInterrupt = callbacks?.onUserInterrupt;

    // F10 (2026-04-28): pause the engine when the tab is backgrounded.
    // iOS Safari can re-suspend AudioContext on hide; without flipping mode
    // to 'paused' the engine would resume scheduling speeches into a
    // half-silent audio stack on return. This handler pauses ONLY — it does
    // not auto-resume on visible (autoplay policy would reject programmatic
    // play after a hide, and the action engine's F11 listener already resets
    // the unlock latches so the next user gesture re-runs the unlock
    // pipeline). The user clicks Play to resume; that gesture is the right
    // place to re-engage audio.
    if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
      document.addEventListener('visibilitychange', this._onVisibilityChange);
    }
  }

  /** F10 (2026-04-28): bound handler so add/removeEventListener pair up.
   *  Pause-on-hide only — pause() itself guards on mode === 'playing' so
   *  this is a no-op when idle/paused. We do NOT auto-resume on visible
   *  (see constructor comment). */
  private _onVisibilityChange = (): void => {
    if (typeof document === 'undefined') return;
    if (this.disposed) return;
    if (document.hidden && this.mode === 'playing') {
      this.setMode('paused');
      // Also stop the audio that's already playing — same shape as the
      // user-driven pause() above. abortInFlightFetch is intentionally
      // omitted here: the action engine's F11 listener fires on the same
      // event and resets unlock latches, and the user-gesture-required
      // resume path will handle a clean restart.
      this.actionEngine.pauseCurrentAudio();
    }
  };

  // ─── Scene Loading ──────────────────────────────────────────────────

  /**
   * Load a scene's actions into the engine. Resets playback position to 0.
   *
   * T0.1 — non-slide scene types (quiz / pbl / interactive) are pure
   * React surfaces; their React renderer owns user interaction. We
   * explicitly drop any actions the generator may have emitted for them
   * so the engine doesn't voice agents or fire spotlights over a quiz
   * card. Matches OpenMAIC where these scene types have no action array
   * at all (`components/stage.tsx:374-379`).
   */
  loadScene(scene: MAICScene): void {
    this.stop();
    // T0.3 — wipe whiteboard so the new scene opens clean. Scene-local
    // strokes (user or agent) from the prior scene would otherwise show
    // behind the first frame of this scene's content.
    this.actionEngine.clearWhiteboardForNewScene();
    const interactiveTypes = new Set(['quiz', 'pbl', 'interactive']);
    const rawActions = scene.actions ?? [];
    this.actions = interactiveTypes.has(scene.type) ? [] : [...rawActions];
    this.currentActionIndex = 0;
    this.consumedDiscussions.clear();
    this.checkpoint = null;
    this.discussionPending = false;

    // OpenMAIC-parity audio prefetch: kick off TTS fetches for every
    // speech action in the scene NOW, before the user hits Play. By the
    // time playback reaches each speech line, its audio is already
    // decoded and cached — the first line starts instantly and
    // inter-speaker gaps disappear. Bounded by SCENE_PREFETCH_
    // CONCURRENCY and PREFETCH_CACHE_LIMIT inside the action engine;
    // cancelled cleanly on stop()/loadScene() via generationToken.
    // Skipped for interactive scenes which have no linear action list.
    if (this.actions.length > 0) {
      this.actionEngine.prefetchSceneSpeeches(this.actions);
    }
  }

  hasPlayableActions(): boolean {
    return this.actions.length > 0;
  }

  // ─── Playback Controls ─────────────────────────────────────────────

  /**
   * Start or resume playing from the current action index.
   * Non-blocking: kicks off recursive processNext chain.
   */
  play(): void {
    if (this.disposed) return;
    if (this.actions.length === 0) {
      this.setMode('idle');
      return;
    }

    // If resuming from pause, delegate to resume()
    if (this.mode === 'paused') {
      this.resume();
      return;
    }

    // Guard: prevent concurrent play (e.g. auto-advance + manual navigate)
    if (this.mode === 'playing') return;

    this.setMode('playing');
    void this.processNext();
  }

  /**
   * Pause playback. Audio is paused immediately. The next processNext()
   * will see mode !== 'playing' and return without advancing.
   *
   * CG-P1-13 / F6 (2026-04-28): handle the pause-mid-fetch race. If the
   * currently-executing speech is still awaiting its TTS fetch (no
   * audio element yet), `pauseCurrentAudio` is a no-op. Without
   * intervention the fetch resolves and `playAudioSynced` calls
   * `audio.play()` despite the engine being paused.
   *
   * F6 fix shape (replaces the earlier index-rewind variant): the
   * action engine's `pauseMidFetch()` aborts the fetch controller AND
   * arms a resume-waiter inside the still-running `executeSpeech`.
   * `executeSpeech` enters a wait-for-resume loop instead of falling
   * into the reading-time fallback. On `resume()` we wake the waiter
   * and the same speech re-fetches and plays — no `currentActionIndex`
   * rewind required, the action remains in flight at the action-engine
   * level. Self-contained; the playback engine only signals.
   */
  pause(): void {
    if (this.mode !== 'playing') return;
    this.setMode('paused');
    this.actionEngine.pauseCurrentAudio();
    // F6 (2026-04-28): replace the prior `abortInFlightFetch` + index
    // rewind with `pauseMidFetch` + a resume-waiter inside the action
    // engine. Returns true if a fetch was actually mid-flight; the
    // playback engine doesn't need to react to that — `resume()` calls
    // `resumeFromPauseMidFetch()` unconditionally and the action
    // engine's own state knows whether to wake a waiter.
    this.actionEngine.pauseMidFetch();
  }

  /**
   * Resume playback after a pause. If audio was paused, it resumes and
   * the onEnded chain continues. If no audio (completed during pause),
   * processNext is called directly.
   *
   * F6 (2026-04-28): also signals the action engine to wake any
   * pending pause-mid-fetch waiter so the in-flight `executeSpeech`
   * re-fetches and plays the same speech. Safe to call when no waiter
   * is pending — `resumeFromPauseMidFetch()` is idempotent.
   */
  resume(): void {
    if (this.mode !== 'paused') return;
    this.setMode('playing');
    // F6 (2026-04-28): wake the action engine's pause-mid-fetch waiter
    // BEFORE the audio-resume branching. If we're resuming from a
    // pause-mid-fetch, this fires the waiter; executeSpeech re-runs
    // the fetch and proceeds. Returns true ONLY when a waiter was
    // actually woken — used below to skip the processNext chain (the
    // in-flight executeSpeech's `.then()` will drive it once the
    // speech completes).
    const wokeWaiter = this.actionEngine.resumeFromPauseMidFetch();
    if (wokeWaiter) {
      // The original execute() promise is still in flight; its `.then()`
      // (in processNext's `case 'speech':`) drives the next action
      // when this speech completes. Calling processNext here would
      // double-advance.
      return;
    }

    if (this.actionEngine.hasActiveAudio()) {
      // Audio is paused — resume it. When audio ends, the speech promise
      // resolves and the .then() callback fires processNext (with mode guard).
      this.actionEngine.resumeCurrentAudio();
    } else {
      // No active audio — speech finished during pause or non-speech action.
      // Continue processing from current position.
      void this.processNext();
    }
  }

  /**
   * Stop playback entirely. Resets to the beginning of the action list.
   *
   * CRITICAL: Sets mode to 'idle' BEFORE stopping audio — this is the
   * upstream OpenMAIC pattern that prevents stale onEnded/promise callbacks
   * from firing processNext() after the stop.
   */
  stop(): void {
    // Bump the playback session so any in-flight `.then()` / setTimeout
    // callback captured under the previous session becomes a no-op before
    // the next chain starts. Must happen BEFORE setMode / abortCurrentAction
    // so the racing callbacks see the new value immediately.
    this.sessionId++;
    // Set mode — blocks any callback still checking only the mode guard.
    this.setMode('idle');
    // Now safely clean up audio/timers/effects
    this.actionEngine.abortCurrentAction();
    this.currentActionIndex = 0;
  }

  /**
   * Jump to a specific action index. If currently playing, the next
   * processNext() call will pick up from the new position.
   */
  seekTo(index: number): void {
    const clamped = Math.max(0, Math.min(index, this.actions.length - 1));
    this.currentActionIndex = clamped;
  }

  /**
   * Jump to the first action of the `transition` that targets `slideIndex`,
   * then start playing from there.
   *
   * Flow:
   *   1. stop() — sets mode to 'idle' and calls abortCurrentAction() which
   *      bumps the action engine's generationToken. Any in-flight speech
   *      callback from the previous slide becomes stale immediately.
   *   2. Move the cursor to a sensible position for the target slide.
   *   3. Set mode to 'playing' and call processNext() with a fresh token.
   *
   * Chunk 10: never NO-OP. If no exact transition matches `slideIndex`,
   * fall back to the greatest transition ≤ target (prior slide's start),
   * else action 0 of the current scene. Previously the method silently
   * returned and the caller was left with a mismatched slide/action
   * cursor, which manifested as "pressing Play restarts from the wrong
   * position" in the demo.
   */
  seekToSlide(slideIndex: number): void {
    const target = this.resolveSlideSeekTarget(slideIndex);
    this.stop(); // token++, synchronous clean teardown
    this.currentActionIndex = target;
    this.setMode('playing');
    void this.processNext();
  }

  /**
   * Seek without auto-playing — used by scene-chip clicks that should
   * reposition the cursor but wait for the user's explicit Play. Keeps
   * the engine cleanly idle until the Play button fires.
   */
  seekToSlidePaused(slideIndex: number): void {
    const target = this.resolveSlideSeekTarget(slideIndex);
    this.stop();
    this.currentActionIndex = target;
    // Leave mode = 'idle'. Caller (usually the React hook) will trigger
    // play() on user's Play button click.
  }

  /**
   * Resolve the action index that best corresponds to `slideIndex`. Used
   * by seekToSlide + seekToSlidePaused to pick a landing spot that's
   * never a no-op.
   */
  private resolveSlideSeekTarget(slideIndex: number): number {
    if (this.actions.length === 0) return 0;

    // 1. Exact transition match.
    let exact = -1;
    let nearestBelow = -1;
    let nearestBelowSlide = -1;
    for (let i = 0; i < this.actions.length; i++) {
      const action = this.actions[i];
      if (action.type !== 'transition') continue;
      const transition = action as import('../types/maic-actions').TransitionAction;
      if (transition.slideIndex == null) continue;
      if (transition.slideIndex === slideIndex) {
        exact = i;
        break;
      }
      if (transition.slideIndex < slideIndex && transition.slideIndex > nearestBelowSlide) {
        nearestBelow = i;
        nearestBelowSlide = transition.slideIndex;
      }
    }
    if (exact !== -1) return exact;
    if (nearestBelow !== -1) return nearestBelow;
    // 2. No transition matches — start at action 0 (slide 0 of the scene).
    return 0;
  }

  /**
   * Enter a UI-initiated discussion (ProactiveCardManager "Let's discuss"
   * click, teacher's Roundtable button, etc.) without going through the
   * scripted `discussion` action in the scene. Pauses audio, saves a
   * checkpoint at the CURRENT action index (no rewind — we weren't in
   * the middle of executing a discussion action), and flags
   * `discussionPending` so `resumeAfterDiscussion()` works the same way
   * for engine-path and UI-path closes.
   *
   * Idempotent — safe to call twice if the user double-clicks Accept.
   */
  enterDiscussionFromUI(): void {
    if (this.disposed) return;
    if (this.discussionPending) return;
    this.checkpoint = { actionIndex: this.currentActionIndex };
    this.discussionPending = true;
    // engine.pause() is itself idempotent + no-ops when mode !== 'playing'.
    this.pause();
  }

  /**
   * Resume playback after a discussion ends. Restores the checkpoint
   * (saved action index) so playback continues from where it was
   * interrupted by the discussion trigger.
   */
  resumeAfterDiscussion(): void {
    if (!this.discussionPending) return;
    this.discussionPending = false;

    if (this.checkpoint) {
      this.currentActionIndex = this.checkpoint.actionIndex;
      this.checkpoint = null;
    }

    this.setMode('playing');
    void this.processNext();
  }

  /**
   * Whether the engine is waiting for a discussion to complete.
   */
  isDiscussionPending(): boolean {
    return this.discussionPending;
  }

  /**
   * Porting P4.1 — student interrupt mid-lecture.
   *
   * Ordering matters: we set mode to 'paused' BEFORE stopping audio.
   * Some browsers fire `audio.onended` synchronously on `pause()`, and
   * the speech promise's `.then(() => processNext())` checks the mode —
   * if we were still 'playing' at that instant the engine would
   * spuriously advance to the next action. Same dance OpenMAIC does.
   *
   * We save `currentActionIndex - 1` as the checkpoint so the
   * interrupted sentence replays on resume. Full-sentence replay is
   * deliberate: most students lose the thread once they stop to ask a
   * question, so rewinding one speech is the right UX.
   */
  handleUserInterrupt(text: string): void {
    if (this.disposed) return;
    if (this.mode !== 'playing') {
      // Even when paused/idle, still notify the host so it can route
      // the chat message through the normal channel.
      this.onUserInterrupt?.(text);
      return;
    }
    this.setMode('paused');
    this.actionEngine.pauseCurrentAudio();
    this.interruptPending = true;
    // Rewind one so the interrupted sentence replays on resume.
    // currentActionIndex is post-incremented in processNext; stepping
    // back once lands on the interrupted action.
    this.checkpoint = {
      actionIndex: Math.max(0, this.currentActionIndex - 1),
    };
    this.onUserInterrupt?.(text);
  }

  /**
   * Resume from a student interrupt — replay the saved action index.
   */
  resumeAfterInterrupt(): void {
    if (!this.interruptPending) return;
    this.interruptPending = false;
    if (this.checkpoint) {
      this.currentActionIndex = this.checkpoint.actionIndex;
      this.checkpoint = null;
    }
    this.setMode('playing');
    void this.processNext();
  }

  isInterruptPending(): boolean {
    return this.interruptPending;
  }

  /**
   * Scan forward from `startIdx` and prefetch the first N speech
   * actions so their TTS audio is decoded by the time playback reaches
   * them. N is small (default 2) to bound memory — the action engine's
   * LRU cache caps at 4 entries total. Best-effort: each prefetchSpeech
   * call is a no-op on any error condition.
   *
   * MOB-P0-6: the cap is now network-aware. The action engine reports
   * its own `getPrefetchLookahead()` derived from the Network Information
   * API — we halve to 1 on slow-2g/2g/3g/saveData so the currently-
   * playing speech doesn't compete with lookahead fetches for the pipe.
   */
  private prefetchUpcomingSpeech(startIdx: number): void {
    const lookahead = typeof (this.actionEngine as unknown as { getPrefetchLookahead?: () => number })
      .getPrefetchLookahead === 'function'
      ? (this.actionEngine as unknown as { getPrefetchLookahead: () => number }).getPrefetchLookahead()
      : 2;
    const MAX_LOOKAHEAD = Math.max(1, lookahead);
    let prefetched = 0;
    for (let i = startIdx; i < this.actions.length && prefetched < MAX_LOOKAHEAD; i++) {
      const a = this.actions[i];
      if (a.type !== 'speech') continue;
      const speech = a as import('../types/maic-actions').SpeechAction;
      if (speech.audioUrl) {
        // Pre-gen already handled; just count against the budget so a
        // long run of mixed pre-gen + live speech still warms 2 live
        // fetches ahead.
        prefetched++;
        continue;
      }
      this.actionEngine.prefetchSpeech(speech);
      prefetched++;
    }
  }

  // ─── State ──────────────────────────────────────────────────────────

  getState(): PlaybackState {
    return this.mode;
  }

  getCurrentActionIndex(): number {
    return this.currentActionIndex;
  }

  getActionCount(): number {
    return this.actions.length;
  }

  // ─── Lifecycle ──────────────────────────────────────────────────────

  dispose(): void {
    this.disposed = true;
    this.stop();
    this.actions = [];
    this.consumedDiscussions.clear();
    this.checkpoint = null;
    this.discussionPending = false;
    this.onStateChange = undefined;
    this.onActionStart = undefined;
    this.onSceneComplete = undefined;
    this.onDiscussionPending = undefined;
    // F10 (2026-04-28): detach the visibility listener attached in the
    // constructor. The bound handler reference is identical, so
    // removeEventListener pairs cleanly — no leak across engine recreations
    // (route changes / classroom reloads create a fresh engine).
    if (typeof document !== 'undefined' && typeof document.removeEventListener === 'function') {
      document.removeEventListener('visibilitychange', this._onVisibilityChange);
    }
  }

  // ─── Core Processing (Recursive, Mode-Guarded) ─────────────────────

  /**
   * Process the next action in the sequence.
   *
   * This method is called recursively — each action type determines how
   * and when to call processNext() again:
   *
   *   - Speech:        callback-driven — .then() fires processNext after audio ends
   *   - Fire-and-forget: queueMicrotask(() => processNext()) for non-blocking effects
   *   - Awaited:       await action, then processNext after mode guard
   *
   * Every entry point checks `if (this.mode !== 'playing') return` to prevent
   * stale callbacks from advancing the action index after stop/pause.
   */
  private async processNext(): Promise<void> {
    // ── MODE GUARD ── the core fix for stale audio/slide sync issues
    if (this.mode !== 'playing') return;

    // Check if scene is complete
    if (this.currentActionIndex >= this.actions.length) {
      this.setMode('idle');
      this.onSceneComplete?.();
      return;
    }

    const idx = this.currentActionIndex;
    const action = this.actions[idx];
    // Capture the session under which we're dispatching this action. Any
    // deferred callback (speech promise, setTimeout, etc.) compares against
    // this value — if stop() / loadScene() / seekToSlide() bumped the session
    // in between, the callback is stale and must not advance the cursor.
    const mySession = this.sessionId;

    // Notify listeners of action start
    this.onActionStart?.(idx, action);

    // Advance index BEFORE executing (upstream pattern — snapshot points at current)
    this.currentActionIndex++;

    switch (action.type) {
      // ── Speech: callback-driven, non-blocking ──
      // Don't await — the .then() callback drives progression when audio ends.
      // Gated on BOTH mode==='playing' AND session token matches. Prevents
      // a stale audio-end from racing a fresh seekToSlide → play() chain.
      case 'speech': {
        // Kick off a best-effort prefetch of the next 1-2 speech actions
        // so their TTS audio is decoded and ready by the time we reach
        // them. Covers the "brief silence between speakers on slow
        // networks" gap. Errors are swallowed inside prefetchSpeech —
        // a miss falls back to the normal live-TTS fetch at playtime.
        this.prefetchUpcomingSpeech(idx + 1);

        this.actionEngine
          .execute(action)
          .then(() => {
            if (mySession !== this.sessionId) return;
            if (this.mode === 'playing') {
              void this.processNext();
            }
          })
          .catch((err) => {
            if (mySession !== this.sessionId) return;
            console.error(`Speech action ${idx} failed:`, err);
            if (this.mode === 'playing') {
              void this.processNext();
            }
          });
        break;
      }

      // ── Fire-and-forget visual effects ──
      // Non-blocking — use queueMicrotask to avoid stack overflow from deep
      // synchronous recursion when many consecutive effects appear in sequence.
      case 'spotlight':
      case 'laser':
      case 'highlight': {
        try {
          this.actionEngine.execute(action);
        } catch (err) {
          console.error(`Action ${idx} (${action.type}) failed:`, err);
        }
        queueMicrotask(() => {
          if (mySession !== this.sessionId) return;
          if (this.mode === 'playing') {
            void this.processNext();
          }
        });
        break;
      }

      // ── Discussion: save checkpoint, soft-pause, notify ──
      // Playback pauses while discussion is active. After discussion ends,
      // call resumeAfterDiscussion() to continue from the checkpoint.
      case 'discussion': {
        const disc = action as import('../types/maic-actions').DiscussionAction;
        if ((disc as { triggerMode?: string }).triggerMode !== 'auto') {
          try {
            this.actionEngine.execute(action);
          } catch (err) {
            console.error(`Discussion action ${idx} failed:`, err);
          }
          queueMicrotask(() => {
            if (mySession !== this.sessionId) return;
            if (this.mode === 'playing') void this.processNext();
          });
          break;
        }

        if (this.consumedDiscussions.has(idx)) {
          // Already triggered this discussion — skip
          queueMicrotask(() => {
            if (this.mode === 'playing') void this.processNext();
          });
          break;
        }

        this.consumedDiscussions.add(idx);
        // Rewind -1 so the interrupted sentence replays on resume (matches
        // upstream OpenMAIC). Note: currentActionIndex has already been
        // post-incremented above, so subtracting 1 lands us at the discussion
        // action itself — whose consumedDiscussions entry prevents re-triggering.
        this.checkpoint = { actionIndex: Math.max(0, this.currentActionIndex - 1) };
        this.discussionPending = true;

        try {
          this.actionEngine.execute(action);
        } catch (err) {
          console.error(`Discussion action ${idx} failed:`, err);
        }

        // Soft-pause: set mode to paused but notify via discussion callback
        this.setMode('paused');
        this.onDiscussionPending?.(disc.topic, disc.agentIds, disc.sessionType);
        break;
      }

      // ── Awaited actions (whiteboard, video, pause, transition, etc.) ──
      // Await completion, then mode+session guard before continuing.
      default: {
        try {
          await this.actionEngine.execute(action);
        } catch (err) {
          console.error(`Action ${idx} (${action.type}) failed:`, err);
        }
        if (mySession !== this.sessionId) break;
        if (this.mode === 'playing') {
          void this.processNext();
        }
        break;
      }
    }
  }

  // ─── Internal ─────────────────────────────────────────────────────

  private setMode(newMode: PlaybackState): void {
    if (this.mode === newMode) return;
    this.mode = newMode;
    this.onStateChange?.(newMode);
  }
}
