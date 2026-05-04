/**
 * Playback Engine — state machine for AI Classroom playback.
 *
 * Source:
 *   /Volumes/CrucialX9/OpenMAIC/lib/playback/engine.ts (745 lines)
 *
 * Phase 1 scope:
 *   - speech actions via AudioPlayer (with reading-time fallback when
 *     no audioUrl present)
 *   - spotlight / laser → onEffectFire callback (fire-and-forget)
 *   - wb_*, widget_*, play_video, discussion → ActionEngine.execute()
 *     (Phase 1 stub — resolves immediately; Phase 2 fills wb_*)
 *   - pause/resume with audio state preservation + timer remaining
 *   - snapshot/restore for cross-reload resume
 *   - handleUserInterrupt → 'live' mode entry (Phase 3 fully wires)
 *
 * Phase 1 deferrals (signposted with comments — DO NOT remove until
 *                    the linked ticket lands):
 *   - 401.4 — Browser-native TTS chunked playback (Chrome 15s bug)
 *   - 401.5 — Discussion → ProactiveCard 3 s delay + confirmation
 *   - Phase 3 (MAIC-410) — full live mode + handleEndDiscussion
 *
 * State machine:
 *
 *                  start()                  pause()
 *   idle ──────────────────→ playing ──────────────→ paused
 *     ▲                         ▲                       │
 *     │                         │  resume()             │
 *     │                         └───────────────────────┘
 *     │
 *     │  handleEndDiscussion()
 *     │                         confirmDiscussion()
 *     │                         / handleUserInterrupt()
 *     │                              │
 *     │                              ▼         pause()
 *     └──────────────────────── live ──────────────→ paused
 *                                 ▲                    │
 *                                 │ resume / user msg  │
 *                                 └────────────────────┘
 */
import { ActionEngine } from './action-engine';
import type {
  Action,
  DiscussionAction,
  SpeechAction,
} from './action-types';
import type { AudioPlayer } from './audio-player';
import {
  createBrowserTTSPlayer,
  type BrowserTTSPlayer,
} from './browser-tts';
import type {
  Effect,
  EngineMode,
  PlaybackEngineCallbacks,
  PlaybackSnapshot,
  TopicState,
  TriggerEvent,
} from './playback-types';


/**
 * Scene shape consumed by the engine. Matches `state.storeState.scenes[]`
 * on the backend (apps/maic/orchestration/state.py StoreState.scenes).
 */
export interface Scene {
  id: string;
  type?: string;
  actions?: Action[];
}


/** If >30% of characters are CJK, treat the text as Chinese for TTS. */
const CJK_LANG_THRESHOLD = 0.3;

/** Min reading time when there's no pre-generated audio (Phase 1). */
const READING_TIMER_MIN_MS = 2000;
/** Per-character reading time for CJK text (matches upstream). */
const READING_MS_PER_CJK_CHAR = 150;
/** Per-word reading time for non-CJK (250 WPM ≈ 240ms/word). */
const READING_MS_PER_WORD = 240;

/**
 * Estimated-reading-time threshold above which a no-audio speech
 * routes through `BrowserTTSPlayer` instead of the silent reading-
 * timer fallback (MAIC-413.2). 15s is the practical cutoff point:
 * below it, the reading-timer's predictability beats speechSynthesis
 * quirks; above it, a long silent reading-timer is worse UX than
 * any browser-TTS glitch.
 */
const BROWSER_TTS_THRESHOLD_MS = 15000;


export class PlaybackEngine {
  // ── Scene cursor ────────────────────────────────────────────────
  private scenes: Scene[];
  private sceneIndex = 0;
  private actionIndex = 0;
  private sceneId: string | undefined;

  // ── State machine ──────────────────────────────────────────────
  private mode: EngineMode = 'idle';
  private currentTopicState: TopicState | null = null;

  // ── Discussion (Phase 1 minimal — Phase 3 fully wires) ─────────
  private consumedDiscussions: Set<string> = new Set();
  private currentTrigger: TriggerEvent | null = null;
  private triggerDelayTimer: ReturnType<typeof setTimeout> | null = null;
  private savedSceneIndex: number | null = null;
  private savedActionIndex: number | null = null;

  // ── Reading-time timer (when no pre-generated audio) ───────────
  private speechTimer: ReturnType<typeof setTimeout> | null = null;
  private speechTimerStart = 0;
  private speechTimerRemaining = 0;

  // ── Browser-TTS fallback (MAIC-413) ────────────────────────────
  private browserTts: BrowserTTSPlayer;
  private _browserTtsActive = false;

  // ── Dependencies ───────────────────────────────────────────────
  private audioPlayer: AudioPlayer;
  private actionEngine: ActionEngine;
  private callbacks: PlaybackEngineCallbacks;

  constructor(
    scenes: Scene[],
    actionEngine: ActionEngine,
    audioPlayer: AudioPlayer,
    callbacks: PlaybackEngineCallbacks = {},
    browserTts?: BrowserTTSPlayer,
  ) {
    this.scenes = scenes;
    this.sceneId = scenes[0]?.id;
    this.actionEngine = actionEngine;
    this.audioPlayer = audioPlayer;
    this.callbacks = callbacks;
    // Default to the real provider; tests inject a stub via the
    // optional 5th arg.
    this.browserTts = browserTts ?? createBrowserTTSPlayer();
  }

  // ── Public API ─────────────────────────────────────────────────

  getMode(): EngineMode {
    return this.mode;
  }

  getSnapshot(): PlaybackSnapshot {
    return {
      sceneIndex: this.sceneIndex,
      actionIndex: this.actionIndex,
      consumedDiscussions: [...this.consumedDiscussions],
      sceneId: this.sceneId,
    };
  }

  restoreFromSnapshot(snapshot: PlaybackSnapshot): void {
    // Discard if scene drifted between sessions (matches upstream).
    if (snapshot.sceneId && snapshot.sceneId !== this.sceneId) {
      return;
    }
    this.sceneIndex = snapshot.sceneIndex;
    this.actionIndex = snapshot.actionIndex;
    this.consumedDiscussions = new Set(snapshot.consumedDiscussions);
  }

  /** idle → playing (from beginning). */
  start(): void {
    if (this.mode !== 'idle') {
      console.warn('[PlaybackEngine] start ignored: mode is', this.mode);
      return;
    }
    this.sceneIndex = 0;
    this.actionIndex = 0;
    this.setMode('playing');
    this.processNext();
  }

  /** idle → playing (from current position; e.g., after end-of-discussion). */
  continuePlayback(): void {
    if (this.mode !== 'idle') {
      console.warn('[PlaybackEngine] continuePlayback ignored: mode is', this.mode);
      return;
    }
    this.setMode('playing');
    this.processNext();
  }

  /** playing|live → paused. Saves audio + timer state for resume(). */
  pause(): void {
    if (this.mode === 'playing') {
      if (this.triggerDelayTimer) {
        clearTimeout(this.triggerDelayTimer);
        this.triggerDelayTimer = null;
      }
      if (this.speechTimer) {
        // Compute remaining time so resume() can reschedule precisely.
        const elapsed = Date.now() - this.speechTimerStart;
        this.speechTimerRemaining = Math.max(0, this.speechTimerRemaining - elapsed);
        clearTimeout(this.speechTimer);
        this.speechTimer = null;
      }
      this.setMode('paused');
      // Freeze TTS — but skip if waiting on ProactiveCard (no active speech).
      if (!this.currentTrigger && this.audioPlayer.isPlaying()) {
        this.audioPlayer.pause();
      }
      // MAIC-413.3: forward pause to browser-TTS when it owns the
      // current speech. The provider's own watchdog freezes alongside
      // so resume() doesn't fire spuriously while we're paused.
      if (this._browserTtsActive) {
        this.browserTts.pause();
      }
    } else if (this.mode === 'live') {
      this.setMode('paused');
      this.currentTopicState = 'pending';
      // (Caller is responsible for aborting any in-flight SSE/WS reads.)
    } else {
      console.warn('[PlaybackEngine] pause ignored: mode is', this.mode);
    }
  }

  /** paused → playing (TTS resume) | paused-in-discussion → live. */
  resume(): void {
    if (this.mode !== 'paused') {
      console.warn('[PlaybackEngine] resume ignored: mode is', this.mode);
      return;
    }

    if (this.currentTopicState === 'pending') {
      // Resume discussion → live (Phase 3 fully wires).
      this.currentTopicState = 'active';
      this.setMode('live');
      return;
    }

    if (this.currentTrigger) {
      // Waiting on ProactiveCard — just resume mode, don't touch audio.
      this.setMode('playing');
      return;
    }

    // Resume lecture
    this.setMode('playing');
    if (this.audioPlayer.hasActiveAudio()) {
      this.audioPlayer.resume();
      // onEnded will fire processNext when audio completes.
    } else if (this._browserTtsActive) {
      // MAIC-413.3: browser-TTS owns the current speech.
      // `browserTts.resume()` rearms its internal watchdog with the
      // remaining time captured at pause(); the existing onEnded
      // callback continues to drive processNext when speech finishes.
      this.browserTts.resume();
    } else if (this.speechTimerRemaining > 0) {
      // Reading-time path: reschedule with remaining ms.
      this.speechTimerStart = Date.now();
      this.speechTimer = setTimeout(() => {
        this.speechTimer = null;
        this.speechTimerRemaining = 0;
        this.callbacks.onSpeechEnd?.();
        if (this.mode === 'playing') this.processNext();
      }, this.speechTimerRemaining);
    } else {
      // TTS finished while paused — continue with the next action.
      this.processNext();
    }
  }

  /** Whatever mode → idle. */
  stop(): void {
    // Set mode BEFORE stopping audio — audio onended may fire
    // synchronously in some browsers, and processNext checks
    // mode==='playing' before advancing.
    this.setMode('idle');
    this.audioPlayer.stop();
    // MAIC-413.2: cancel browser-TTS if it's the active path. The
    // `cancel()` drops the pending onEnded callback so we don't
    // racily re-enter processNext after stop().
    if (this._browserTtsActive) {
      this.browserTts.cancel();
      this._browserTtsActive = false;
    }
    this.actionEngine.clearEffects();
    if (this.triggerDelayTimer) {
      clearTimeout(this.triggerDelayTimer);
      this.triggerDelayTimer = null;
    }
    if (this.speechTimer) {
      clearTimeout(this.speechTimer);
      this.speechTimer = null;
    }
    this.speechTimerRemaining = 0;
    this.sceneIndex = 0;
    this.actionIndex = 0;
    this.savedSceneIndex = null;
    this.savedActionIndex = null;
    this.currentTopicState = null;
    this.currentTrigger = null;
  }

  /** Confirm a discussion trigger from the ProactiveCard UI → live. */
  confirmDiscussion(): void {
    // Phase 1 skeleton — Phase 3 (MAIC-410) wires the full discussion
    // lifecycle. Documented here so the API surface is stable.
    if (!this.currentTrigger) {
      console.warn('[PlaybackEngine] confirmDiscussion called but no trigger');
      return;
    }
    this.consumedDiscussions.add(this.currentTrigger.id);
    this.savedSceneIndex = this.sceneIndex;
    this.savedActionIndex = this.actionIndex;
    this.currentTopicState = 'active';
    this.setMode('live');
    this.callbacks.onProactiveHide?.();
    this.callbacks.onDiscussionConfirmed?.(
      this.currentTrigger.question,
      this.currentTrigger.prompt,
      this.currentTrigger.agentId,
    );
    this.currentTrigger = null;
  }

  /** Skip a discussion trigger (user hit "skip" on ProactiveCard). */
  skipDiscussion(): void {
    if (this.currentTrigger) {
      this.consumedDiscussions.add(this.currentTrigger.id);
      this.currentTrigger = null;
    }
    this.callbacks.onProactiveHide?.();
    if (this.mode === 'playing') {
      this.processNext();
    }
  }

  /** End an active discussion → idle (user clicks Continue to resume lecture). */
  handleEndDiscussion(): void {
    this.actionEngine.clearEffects();
    this.currentTopicState = 'closed';
    this.callbacks.onDiscussionEnd?.();
    this.restoreSavedLectureState();
    this.setMode('idle');
  }

  /** User typed a message during playback → enter live mode. */
  handleUserInterrupt(text: string): void {
    if (this.mode === 'playing' || this.mode === 'paused') {
      // Save lecture state BEFORE stopping audio. actionIndex was
      // already incremented by processNext, so subtract 1 to replay
      // the interrupted line on resume.  Guard against overwriting
      // a previously saved position (e.g. live → paused → new msg).
      if (this.savedSceneIndex === null) {
        this.savedSceneIndex = this.sceneIndex;
        this.savedActionIndex = Math.max(0, this.actionIndex - 1);
      }
      if (this.triggerDelayTimer) {
        clearTimeout(this.triggerDelayTimer);
        this.triggerDelayTimer = null;
      }
    }
    // Set mode BEFORE stopping audio (see stop() comment).
    this.currentTopicState = 'active';
    this.setMode('live');
    this.audioPlayer.stop();
    // MAIC-413.2: same reasoning as stop() — cancel any active
    // browser-TTS so the pending onEnded doesn't fire during live
    // mode.
    if (this._browserTtsActive) {
      this.browserTts.cancel();
      this._browserTtsActive = false;
    }
    this.callbacks.onUserInterrupt?.(text);
  }

  /** True iff no remaining unconsumed actions exist. */
  isExhausted(): boolean {
    let si = this.sceneIndex;
    let ai = this.actionIndex;
    while (si < this.scenes.length) {
      const actions = this.scenes[si].actions || [];
      while (ai < actions.length) {
        const action = actions[ai];
        if (action.type === 'discussion' && this.consumedDiscussions.has(action.id)) {
          ai++;
          continue;
        }
        return false;
      }
      si++;
      ai = 0;
    }
    return true;
  }

  // ── Private ─────────────────────────────────────────────────────

  private setMode(mode: EngineMode): void {
    if (this.mode === mode) return;
    this.mode = mode;
    this.callbacks.onModeChange?.(mode);
  }

  private restoreSavedLectureState(): void {
    if (this.savedSceneIndex !== null && this.savedActionIndex !== null) {
      this.sceneIndex = this.savedSceneIndex;
      this.actionIndex = this.savedActionIndex;
    }
    this.savedSceneIndex = null;
    this.savedActionIndex = null;
  }

  private getCurrentAction(): { action: Action; sceneId: string } | null {
    while (this.sceneIndex < this.scenes.length) {
      const scene = this.scenes[this.sceneIndex];
      const actions = scene.actions || [];
      if (this.actionIndex < actions.length) {
        return { action: actions[this.actionIndex], sceneId: scene.id };
      }
      this.sceneIndex++;
      this.actionIndex = 0;
    }
    return null;
  }

  /** Core dispatch loop — consume the next action. */
  private async processNext(): Promise<void> {
    if (this.mode !== 'playing') return;

    // Scene boundary — emit onSceneChange + clear effects.
    if (this.actionIndex === 0 && this.sceneIndex < this.scenes.length) {
      const scene = this.scenes[this.sceneIndex];
      this.actionEngine.clearEffects();
      this.callbacks.onSceneChange?.(scene.id);
      this.callbacks.onSpeakerChange?.('teacher');
    }

    const current = this.getCurrentAction();
    if (!current) {
      this.actionEngine.clearEffects();
      this.setMode('idle');
      this.callbacks.onComplete?.();
      return;
    }

    const { action } = current;

    // Notify progress BEFORE advancing — snapshot points at the action
    // we're about to play, so restore replays it (correct for speech
    // where the user may have only heard half).
    this.callbacks.onProgress?.(this.getSnapshot());
    this.actionIndex++;

    switch (action.type) {
      case 'speech':
        this._dispatchSpeech(action);
        break;

      case 'spotlight':
      case 'laser':
        // Fire-and-forget — emit through onEffectFire and continue.
        // queueMicrotask avoids stack overflow from long sequences.
        this.callbacks.onEffectFire?.(this._actionToEffect(action));
        queueMicrotask(() => this.processNext());
        break;

      case 'discussion':
        this._dispatchDiscussion(action as DiscussionAction);
        break;

      case 'play_video':
      case 'wb_open':
      case 'wb_close':
      case 'wb_clear':
      case 'wb_delete':
      case 'wb_draw_text':
      case 'wb_draw_shape':
      case 'wb_draw_chart':
      case 'wb_draw_latex':
      case 'wb_draw_table':
      case 'wb_draw_line':
      case 'wb_draw_code':
      case 'wb_edit_code':
      case 'widget_highlight':
      case 'widget_setState':
      case 'widget_annotation':
      case 'widget_reveal':
        // Synchronous actions — await ActionEngine then continue.
        // Phase 1 ActionEngine resolves immediately; Phase 2/6 fill in.
        await this.actionEngine.execute(action);
        if (this.mode === 'playing') this.processNext();
        break;

      default: {
        // Unknown action type — log and skip.
        const unknownType: string = (action as { type?: string }).type ?? 'unknown';
        console.warn('[PlaybackEngine] unknown action type — skipping:', unknownType);
        this.processNext();
      }
    }
  }

  private _actionToEffect(action: Action): Effect {
    if (action.type === 'spotlight') {
      return {
        kind: 'spotlight',
        targetId: action.elementId,
        dimOpacity: action.dimOpacity,
      };
    }
    return {
      kind: 'laser',
      targetId: (action as { elementId: string }).elementId,
      color: (action as { color?: string }).color,
    };
  }

  private _dispatchSpeech(action: SpeechAction): void {
    this.callbacks.onSpeechStart?.(action.text);

    // Audio onEnded → processNext.  Always re-arm because each speech
    // owns its own onEnded handler.
    this.audioPlayer.onEnded(() => {
      this.callbacks.onSpeechEnd?.();
      if (this.mode === 'playing') this.processNext();
    });

    this.audioPlayer
      .play(action.audioId || '', action.audioUrl)
      .then((started) => {
        if (!started) {
          // No pre-generated audio for this speech — fall back per
          // MAIC-413.2: long text → browser-native TTS, short text →
          // reading-time timer (more reliable than speechSynthesis
          // for sub-15s utterances).
          this._dispatchSpeechFallback(action);
        }
      })
      .catch((err) => {
        console.error('[PlaybackEngine] audio play error', err);
        this._dispatchSpeechFallback(action);
      });
  }

  /**
   * Choose between the silent reading-timer and the browser-TTS path
   * for a no-audio speech action (MAIC-413.2). Long estimates favor
   * browser TTS — a 30s silent timer is worse UX than any
   * speechSynthesis glitch — but only when the runtime actually
   * exposes `speechSynthesis` (jsdom / happy-dom fall through to the
   * timer).
   */
  private _dispatchSpeechFallback(action: SpeechAction): void {
    const estimateMs = this._estimateReadingMs(action);
    if (
      estimateMs >= BROWSER_TTS_THRESHOLD_MS &&
      this.browserTts.isAvailable()
    ) {
      this._dispatchBrowserTts(action);
    } else {
      this._scheduleReadingTimer(action, estimateMs);
    }
  }

  /** Dispatch via `speechSynthesis` (chunked + watchdogged). */
  private _dispatchBrowserTts(action: SpeechAction): void {
    this._browserTtsActive = true;
    this.browserTts.speak(action.text, () => {
      this._browserTtsActive = false;
      this.callbacks.onSpeechEnd?.();
      if (this.mode === 'playing') this.processNext();
    });
  }

  /**
   * Estimate reading time for a speech action's text. CJK characters
   * use a per-char ms cost; non-CJK uses a per-word cost. Speed
   * multiplier comes from the host (StageControls' speed picker, etc).
   */
  private _estimateReadingMs(action: SpeechAction): number {
    const text = action.text;
    const cjkCount =
      (text.match(/[一-鿿㐀-䶿぀-ゟ゠-ヿ가-힯]/g) || [])
        .length;
    const isCJK = cjkCount > text.length * CJK_LANG_THRESHOLD;
    const speed = this.callbacks.getPlaybackSpeed?.() ?? 1;
    const rawMs = isCJK
      ? Math.max(READING_TIMER_MIN_MS, text.length * READING_MS_PER_CJK_CHAR)
      : Math.max(
          READING_TIMER_MIN_MS,
          text.split(/\s+/).filter(Boolean).length * READING_MS_PER_WORD,
        );
    return rawMs / speed;
  }

  private _scheduleReadingTimer(action: SpeechAction, estimateMs?: number): void {
    const readingMs = estimateMs ?? this._estimateReadingMs(action);
    this.speechTimerStart = Date.now();
    this.speechTimerRemaining = readingMs;
    this.speechTimer = setTimeout(() => {
      this.speechTimer = null;
      this.speechTimerRemaining = 0;
      this.callbacks.onSpeechEnd?.();
      if (this.mode === 'playing') this.processNext();
    }, readingMs);
  }

  private _dispatchDiscussion(action: DiscussionAction): void {
    if (this.consumedDiscussions.has(action.id)) {
      this.processNext();
      return;
    }
    if (
      action.agentId &&
      this.callbacks.isAgentSelected &&
      !this.callbacks.isAgentSelected(action.agentId)
    ) {
      this.consumedDiscussions.add(action.id);
      this.processNext();
      return;
    }

    // 3 s delay before showing ProactiveCard so any prior speech
    // tail finishes naturally.  Phase 401.5 will refine the UX
    // (animation, double-trigger guard).
    const trigger: TriggerEvent = {
      id: action.id,
      question: action.topic,
      prompt: action.prompt,
      agentId: action.agentId,
    };
    this.triggerDelayTimer = setTimeout(() => {
      this.triggerDelayTimer = null;
      if (this.mode !== 'playing') return;
      this.currentTrigger = trigger;
      this.callbacks.onProactiveShow?.(trigger);
      // Engine pauses here — caller drives confirmDiscussion / skipDiscussion.
    }, 3000);
  }
}


/** Convenience factory — symmetric with createAudioPlayer/createActionEngine. */
export function createPlaybackEngine(
  scenes: Scene[],
  actionEngine: ActionEngine,
  audioPlayer: AudioPlayer,
  callbacks?: PlaybackEngineCallbacks,
  browserTts?: BrowserTTSPlayer,
): PlaybackEngine {
  return new PlaybackEngine(scenes, actionEngine, audioPlayer, callbacks, browserTts);
}
