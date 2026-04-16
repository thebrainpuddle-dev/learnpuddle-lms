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
   *   2. Move the cursor to the transition action.
   *   3. Set mode to 'playing' and call processNext() with a fresh token.
   *
   * If no transition action matches `slideIndex`, this is a no-op — callers
   * that want a hard jump (e.g. scene-switch) should use `goToScene()` on
   * the stage store instead.
   */
  seekToSlide(slideIndex: number): void {
    const target = this.actions.findIndex(
      (a) =>
        a.type === 'transition' &&
        (a as import('../types/maic-actions').TransitionAction).slideIndex === slideIndex,
    );
    if (target === -1) return;
    this.stop(); // token++, synchronous clean teardown
    this.currentActionIndex = target;
    this.setMode('playing');
    void this.processNext();
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
