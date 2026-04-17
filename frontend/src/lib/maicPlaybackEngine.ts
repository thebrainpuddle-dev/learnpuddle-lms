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

  constructor(actionEngine: MAICActionEngine, callbacks?: PlaybackCallbacks) {
    this.actionEngine = actionEngine;
    this.onStateChange = callbacks?.onStateChange;
    this.onActionStart = callbacks?.onActionStart;
    this.onSceneComplete = callbacks?.onSceneComplete;
    this.onDiscussionPending = callbacks?.onDiscussionPending;
  }

  // ─── Scene Loading ──────────────────────────────────────────────────

  /**
   * Load a scene's actions into the engine. Resets playback position to 0.
   */
  loadScene(scene: MAICScene): void {
    this.stop();
    this.actions = scene.actions ? [...scene.actions] : [];
    this.currentActionIndex = 0;
    this.consumedDiscussions.clear();
    this.checkpoint = null;
    this.discussionPending = false;
  }

  // ─── Playback Controls ─────────────────────────────────────────────

  /**
   * Start or resume playing from the current action index.
   * Non-blocking: kicks off recursive processNext chain.
   */
  play(): void {
    if (this.disposed) return;
    if (this.actions.length === 0) return;

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
   */
  pause(): void {
    if (this.mode !== 'playing') return;
    this.setMode('paused');
    this.actionEngine.pauseCurrentAudio();
  }

  /**
   * Resume playback after a pause. If audio was paused, it resumes and
   * the onEnded chain continues. If no audio (completed during pause),
   * processNext is called directly.
   */
  resume(): void {
    if (this.mode !== 'paused') return;
    this.setMode('playing');

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
   * Scan forward from `startIdx` and prefetch the first N speech
   * actions so their TTS audio is decoded by the time playback reaches
   * them. N is small (2) to bound memory — the action engine's LRU
   * cache caps at 4 entries total. Best-effort: each prefetchSpeech
   * call is a no-op on any error condition.
   */
  private prefetchUpcomingSpeech(startIdx: number): void {
    const MAX_LOOKAHEAD = 2;
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
        const disc = action as import('../types/maic-actions').DiscussionAction;
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
