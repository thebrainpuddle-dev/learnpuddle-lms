// lib/maicPlaybackEngine.ts — Sequences through a scene's action array

import { MAICActionEngine } from './maicActionEngine';
import type { MAICAction } from '../types/maic-actions';
import type { MAICScene } from '../types/maic-scenes';

// ─── Types ──────────────────────────────────────────────────────────────────

export type PlaybackState = 'idle' | 'playing' | 'paused';

export interface PlaybackCallbacks {
  onStateChange?: (state: PlaybackState) => void;
  onActionStart?: (index: number, action: MAICAction) => void;
  onSceneComplete?: () => void;
}

// ─── Engine ─────────────────────────────────────────────────────────────────

export class MAICPlaybackEngine {
  private actionEngine: MAICActionEngine;
  private state: PlaybackState = 'idle';
  private currentActionIndex = 0;
  private actions: MAICAction[] = [];
  private aborted = false;
  private pauseResolve: (() => void) | null = null;
  private disposed = false;

  private onStateChange?: (state: PlaybackState) => void;
  private onActionStart?: (index: number, action: MAICAction) => void;
  private onSceneComplete?: () => void;

  constructor(actionEngine: MAICActionEngine, callbacks?: PlaybackCallbacks) {
    this.actionEngine = actionEngine;
    this.onStateChange = callbacks?.onStateChange;
    this.onActionStart = callbacks?.onActionStart;
    this.onSceneComplete = callbacks?.onSceneComplete;
  }

  // ─── Scene Loading ──────────────────────────────────────────────────

  /**
   * Load a scene's actions into the engine. Resets playback position to 0.
   */
  loadScene(scene: MAICScene): void {
    this.stop();
    this.actions = scene.actions ? [...scene.actions] : [];
    this.currentActionIndex = 0;
    this.setState('idle');
  }

  // ─── Playback Controls ─────────────────────────────────────────────

  /**
   * Start or resume playing from the current action index.
   * This method resolves when all actions have been executed or playback is stopped.
   */
  async play(): Promise<void> {
    if (this.disposed) return;
    if (this.actions.length === 0) return;

    // If resuming from pause, just resume
    if (this.state === 'paused') {
      this.resume();
      return;
    }

    // Guard: prevent concurrent play loops (e.g. auto-advance + manual navigate)
    if (this.state === 'playing') return;

    this.aborted = false;
    this.setState('playing');

    while (this.currentActionIndex < this.actions.length && !this.aborted) {
      // Handle pause — wait until resume() is called
      // Note: state can be mutated by pause() from outside, so cast to bypass TS narrowing
      if ((this.state as PlaybackState) === 'paused') {
        await new Promise<void>((resolve) => {
          this.pauseResolve = resolve;
        });
        // After resume, re-check abort and continue
        if (this.aborted) break;
      }

      const idx = this.currentActionIndex;
      const action = this.actions[idx];

      // Notify listeners of action start
      this.onActionStart?.(idx, action);

      try {
        await this.actionEngine.execute(action);
      } catch (err) {
        console.error(`Action ${idx} (${action.type}) failed:`, err);
        // Continue to next action on failure
      }

      if (this.aborted) break;
      this.currentActionIndex++;
    }

    if (!this.aborted && !this.disposed) {
      this.setState('idle');
      this.onSceneComplete?.();
    }
  }

  /**
   * Pause playback at the current action. The currently executing action
   * will complete before the pause takes effect.
   */
  pause(): void {
    if (this.state !== 'playing') return;
    this.setState('paused');
  }

  /**
   * Resume playback after a pause.
   */
  resume(): void {
    if (this.state !== 'paused') return;
    this.setState('playing');

    // Release the pause promise so the play loop continues
    if (this.pauseResolve) {
      this.pauseResolve();
      this.pauseResolve = null;
    }
  }

  /**
   * Stop playback entirely. Resets to the beginning of the action list.
   * Immediately kills any in-progress audio/TTS so the user doesn't hear
   * stale speech from the previous scene after navigating.
   */
  stop(): void {
    this.aborted = true;

    // Kill current audio/TTS fetch immediately — this resolves the pending
    // playAudio promise so the play() loop can break on the next aborted check.
    this.actionEngine.abortCurrentAction();

    // Release any pending pause promise
    if (this.pauseResolve) {
      this.pauseResolve();
      this.pauseResolve = null;
    }

    this.currentActionIndex = 0;
    this.setState('idle');
  }

  /**
   * Jump to a specific action index. If currently playing, playback continues
   * from the new position. If idle or paused, it just sets the position.
   */
  seekTo(index: number): void {
    const clamped = Math.max(0, Math.min(index, this.actions.length - 1));
    this.currentActionIndex = clamped;
  }

  // ─── State ──────────────────────────────────────────────────────────

  getState(): PlaybackState {
    return this.state;
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
    this.onStateChange = undefined;
    this.onActionStart = undefined;
    this.onSceneComplete = undefined;
  }

  // ─── Internal ─────────────────────────────────────────────────────

  private setState(newState: PlaybackState): void {
    if (this.state === newState) return;
    this.state = newState;
    this.onStateChange?.(newState);
  }
}
