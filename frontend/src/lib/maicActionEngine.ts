// lib/maicActionEngine.ts — Executes individual MAIC actions (TTS, whiteboard, effects)
//
// Speech pipeline (Chunk 5 rewrite):
//
//   1. `generationToken`: a monotonic counter incremented on every call to
//      `abortCurrentAction()` *and* on every new speech action. Every async
//      step (awaited fetch, `onplaying`/`onended`/`onerror` callback, `.then()`
//      promise handler, setTimeout continuation) checks
//      `token !== this.generationToken` and becomes a no-op when stale.
//      This is the single mechanism that makes scene/slide switches safe —
//      old audio elements cannot "wake up" and mutate state belonging to the
//      newly-loaded scene.
//
//   2. Subtitles + speaking indicator fire on the audio element's `playing`
//      event — NOT before `play()` — so the UI does not show subtitles for
//      speech that has not started yet (and does not leave them on-screen
//      when a scene change aborts before audio ever begins).
//
//   3. Pre-generated `action.audioUrl` is the preferred path (see Chunk 4
//      publish pipeline). When absent, fall back to the live TTS endpoint
//      (chat, discussion, or any pre-gen gap). When that fails too, fall
//      back to a reading-time timer (~60ms/char, min 2s) so slides don't
//      snap-advance instantly on TTS outage.
//
// See design doc §10 (WS-E).
//
import { useMAICStageStore } from '../stores/maicStageStore';
import { useMAICCanvasStore } from '../stores/maicCanvasStore';
import { useMAICSettingsStore } from '../stores/maicSettingsStore';
import { refreshAccessTokenForRequests } from '../config/api';
import { getAccessToken } from '../utils/authSession';
import { cacheAudio, getCachedAudio } from './maicDb';
import { resolveVoiceForAgent } from './voiceResolver';
import type { MAICAction } from '../types/maic-actions';
import type {
  SpeechAction,
  SpotlightAction,
  LaserAction,
  HighlightAction,
  PauseAction,
  TransitionAction,
  PlayVideoAction,
  WbDrawTextAction,
  WbDrawShapeAction,
  WbDrawChartAction,
  WbDrawLatexAction,
  WbDrawTableAction,
  WbDrawLineAction,
  WbDrawCodeAction,
  WbEditCodeAction,
  WbDeleteAction,
  DiscussionAction,
} from '../types/maic-actions';
import type { WhiteboardAnnotation, WhiteboardPoint } from '../types/maic';

// ─── Constants ──────────────────────────────────────────────────────────────

const EFFECT_AUTO_CLEAR_MS = 5000;
/** Max number of blob URLs held in the prefetch cache. Each entry is
 *  a decoded MP3 (typically 50-200 KB). Cap keeps memory bounded on
 *  long scenes. LRU eviction revokes the oldest URL.
 *
 *  Sized to hold a full scene's speech actions (most scenes have
 *  12-18 speech lines). Scene-wide prefetch (see prefetchSceneSpeeches)
 *  populates the cache eagerly on loadScene so every speech starts
 *  from a warm cache, matching OpenMAIC's "all TTS ready before
 *  playback" model without the IndexedDB persistence layer. At
 *  ~150 KB per MP3, 24 entries ≈ 3.6 MB peak — well under budget. */
const PREFETCH_CACHE_LIMIT = 24;
/** Default max parallel TTS fetches during scene-wide prefetch. Backend
 *  can handle more, but capping at 3 keeps request bursts polite and
 *  ensures speeches near the start of the scene decode first so
 *  playback can begin without waiting for the full tail.
 *
 *  MOB-P0-6: the *effective* value is derived at runtime from the
 *  Network Information API (see `getPrefetchConcurrency`). On slow
 *  networks we drop to 1 so the very first speech isn't fighting the
 *  tail of the scene for bandwidth. This constant is the fallback
 *  used when the API isn't available (Safari) or `effectiveType` is
 *  `4g`/unknown. */
const SCENE_PREFETCH_CONCURRENCY_DEFAULT = 3;

/**
 * MOB-P0-6 — return how many parallel TTS prefetches to run based on
 * the user's effective network quality. Slow-3G / 2G connections can
 * only spare bandwidth for one file at a time without starving the
 * first-speech decode; saveData users have opted into minimum traffic.
 *
 * Feature detection: `NetworkInformation` is not in Safari. When the
 * API is missing we return the desktop default (3). Chromium DevTools
 * "Slow 3G" throttling DOES set `effectiveType === 'slow-2g'` (because
 * the preset's RTT/downlink fall in that bucket), so this helper can
 * be exercised by toggling throttling during manual QA.
 *
 * Returns a number that is safe to use as a concurrency cap even if
 * callers forget to clamp it (never zero, never negative).
 */
export function getPrefetchConcurrency(): number {
  // Feature-detect across the three vendor-prefixed forms. Cast via
  // `unknown` because NetworkInformation isn't in the lib.dom types.
  const nav = typeof navigator !== 'undefined' ? navigator : undefined;
  const conn =
    (nav as unknown as { connection?: NetworkInformationLike }).connection ??
    (nav as unknown as { mozConnection?: NetworkInformationLike }).mozConnection ??
    (nav as unknown as { webkitConnection?: NetworkInformationLike }).webkitConnection;

  if (!conn) return SCENE_PREFETCH_CONCURRENCY_DEFAULT;

  // Data-saver mode — respect user's stated preference over anything else.
  if (conn.saveData === true) return 1;

  switch (conn.effectiveType) {
    case 'slow-2g':
    case '2g':
      return 1;
    case '3g':
      return 2;
    case '4g':
      return SCENE_PREFETCH_CONCURRENCY_DEFAULT;
    default:
      // Unknown / undefined effectiveType — behave as if desktop.
      return SCENE_PREFETCH_CONCURRENCY_DEFAULT;
  }
}

/** Minimal shape of the NetworkInformation API we consume. Declared
 *  locally to avoid depending on the un-shipped-everywhere `dom.d.ts`
 *  types and so the two vendor-prefixed globals (`mozConnection`,
 *  `webkitConnection`) can be typed uniformly. */
interface NetworkInformationLike {
  effectiveType?: 'slow-2g' | '2g' | '3g' | '4g' | string;
  saveData?: boolean;
}
// Whiteboard element entry animation. The renderer plays a motion
// fade+blur of this duration (see Whiteboard.tsx `ELEMENT_ENTRY_MS`) —
// if we changed one without the other the `await` here would either
// return too early (animation still playing) or introduce dead time.
// Keep the two constants in lockstep.
const WB_ELEMENT_FADE_IN_MS = 450;
const WB_CASCADE_DELETE_MS = 55;
const WB_CLOSE_DELAY_MS = 700;
/** Reading-fallback timing when TTS is unavailable. Tightened from the old
 *  60ms/char + 2s floor — it was stacking multi-second gaps between speakers
 *  on networks where TTS was slow. 30ms/char approximates a natural English
 *  reading pace and the 800ms floor still lets short utterances ("Right.",
 *  "Exactly.") land on screen. If the backend stamped a `durationMs` on the
 *  speech action (Chunk 5), we prefer that over the char-based estimate. */
const READING_FALLBACK_MS_PER_CHAR = 30;
const READING_FALLBACK_MIN_MS = 800;
/** Default transition animation duration when the action JSON doesn't
 *  specify one. Previously 600ms — shortened to 250ms so scene switches
 *  feel instant rather than sluggish. */
const DEFAULT_TRANSITION_DURATION_MS = 250;

// CG-P0-6 (2026-04-27): the old single-voice-per-role ROLE_VOICE_MAP was
// replaced by `resolveVoiceForAgent()` from `voiceResolver.ts` which cycles
// per-role pools by agent index, so two agents of the same role can no
// longer collapse to one fallback voice. Mirrors the backend's per-agent
// voice picker in apps/courses/maic_voices.py.

// ─── Helpers ────────────────────────────────────────────────────────────────

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** Convert whiteboard action coordinates to a single-point annotation. */
function makeAnnotation(
  id: string,
  tool: WhiteboardAnnotation['tool'],
  points: WhiteboardPoint[],
  color: string,
  strokeWidth: number,
  sceneId: string,
  agentId?: string,
): WhiteboardAnnotation {
  return {
    id,
    tool,
    points,
    color,
    strokeWidth,
    agentId,
    sceneId,
    timestamp: Date.now(),
  };
}

// ─── Engine ─────────────────────────────────────────────────────────────────

export interface MAICActionEngineOptions {
  ttsEndpoint: string;
  token: string;
  /** Classroom this engine instance is serving. Used for offline audio
   *  durability — when present, every successfully-prefetched TTS buffer
   *  is fire-and-forget persisted to IDB under
   *  `StoredClassroom.audioCache`, and live-TTS fetch failures fall back
   *  to that IDB cache. Optional so non-classroom uses (chat-only TTS
   *  previews, unit tests) keep working without IDB writes. */
  classroomId?: string;
  onSpeechStart?: (agentId: string, text: string) => void;
  onSpeechEnd?: () => void;
  onDiscussionTrigger?: (sessionType: string, topic: string, agentIds: string[]) => void;
  /** Invoked just before the engine changes the current slide via a
   *  `transition` action. Lets the host (usePlaybackEngine) flip its
   *  `engineDrivenSlideChangeRef` so Stage.tsx's auto-pause effect
   *  knows this slide change is playback-driven, not user-driven. */
  onEngineDrivenTransition?: (slideIndex: number) => void;
  /** Fired once per engine lifetime when the server returns no TTS blob
   *  for a speech action and we fall back to the reading-time timer.
   *  Used by the host to surface a single "Audio unavailable — reading
   *  along" toast so the user isn't left wondering why there's no sound.
   *  (Porting P1.4.) */
  onTtsUnavailable?: () => void;
}

export class MAICActionEngine {
  private stageStore = useMAICStageStore;
  private canvasStore = useMAICCanvasStore;
  private settingsStore = useMAICSettingsStore;

  private audioElement: HTMLAudioElement | null = null;
  /** F5 (2026-04-28): the lifetime-owned HTMLAudioElement reused across
   *  every speech action in this engine instance. Lazily allocated on
   *  first `playAudioSynced` call so SSR / pre-test-construction stays
   *  safe. After a speech ends or aborts, `audioElement` is nulled (the
   *  "currently bound" reference) but `_sharedAudio` stays — the next
   *  play just reattaches handlers and assigns `src`. Only `dispose()`
   *  drops it.
   *
   *  Saves 50-200 ms of audio-decode/setup cost per speaker handoff that
   *  the previous `new Audio()`-per-speech allocation paid. Matches the
   *  OpenMAIC `audio-player.ts` pattern (one `audio` field reused via
   *  `audio.src = …; audio.play()` cycles). */
  private _sharedAudio: HTMLAudioElement | null = null;
  /** F5 (2026-04-28): unsubscribe handle for the engine-lifetime
   *  settings-store subscription. Wired ONCE on first audio allocation
   *  (deferred from constructor so SSR / no-Audio-global tests don't
   *  pre-allocate). Lives until `dispose()` calls it. The subscription
   *  pushes settings.{playbackSpeed,audioVolume} changes to
   *  `_sharedAudio` whenever the store changes — gives mid-speech speed
   *  / volume slider drags an instant effect (AV-P0-1 / AV-P0-3 /
   *  AV-P2-12). */
  private _settingsUnsub: (() => void) | null = null;
  private audioResolve: (() => void) | null = null;
  /** F9 (2026-04-28): generation token captured at the time `audioResolve`
   *  was registered (inside `playAudioSynced`). The abort path uses this to
   *  decide whether to fire the planted resolve: it captures `myToken` from
   *  `this.generationToken` BEFORE bumping, then only calls `audioResolve()`
   *  when `audioResolveToken === myToken`. A stale planted resolve (e.g.
   *  the rare race where a `play().catch` reaction settled but its early-
   *  return token-check left `audioResolve` non-null) is silently dropped
   *  rather than double-fired on top of the normal play().catch resolve.
   *  Stays in lockstep with `audioResolve` — null when audioResolve is null. */
  private audioResolveToken: number | null = null;
  /** Currently-playing video element (from a `play_video` action).
   *  Tracked so `pauseCurrentAudio` can also pause video when the user
   *  pauses the engine, and so `abortCurrentAction` stops both. */
  private currentVideoElement: HTMLVideoElement | null = null;
  private currentFetchController: AbortController | null = null;
  /** F6 (2026-04-28): set true by `pauseMidFetch()` when it aborts an
   *  in-flight TTS fetch. `executeSpeech` checks this AFTER its
   *  `fetchTtsBlob` returns null — instead of falling into the
   *  reading-time fallback (which silently loses the speech), it awaits
   *  `_resumeWaiter` and re-runs the fetch when the user clicks Play.
   *  Reset to false at executeSpeech entry, after the resume-waiter
   *  resolves, and on abort. */
  private _pausedMidFetch = false;
  /** F6 (2026-04-28): resolve fn for the resume-waiter promise. Set by
   *  `executeSpeech` while paused mid-fetch, fired by either
   *  `resumeFromPauseMidFetch()` (user clicks Play) or
   *  `abortCurrentAction()` (scene change drops the speech entirely —
   *  the post-resume token check then bails executeSpeech out cleanly). */
  private _resumeWaiter: (() => void) | null = null;
  private effectTimers: ReturnType<typeof setTimeout>[] = [];
  /** AV-P0-4 (2026-04-24): handles for the scene-wide prefetch
   *  `waitForSlot` polling timers. Tracked separately from effectTimers
   *  because they live on the prefetch lifecycle (cleared by
   *  clearPrefetchCache) rather than the speech lifecycle. */
  private prefetchPollTimers: ReturnType<typeof setTimeout>[] = [];
  private readingTimer: ReturnType<typeof setTimeout> | null = null;

  /**
   * Monotonic counter. Every `abortCurrentAction()` call and every new speech
   * action increments this. Async callbacks capture `myToken = ++this.generationToken`
   * at entry and check `myToken !== this.generationToken` to detect staleness.
   * A no-op on stale means old audio/fetches cannot leak into a new scene.
   */
  private generationToken = 0;

  private onSpeechStart?: (agentId: string, text: string) => void;
  private onSpeechEnd?: () => void;
  private onDiscussionTrigger?: (sessionType: string, topic: string, agentIds: string[]) => void;
  private onEngineDrivenTransition?: (slideIndex: number) => void;
  private onTtsUnavailable?: () => void;
  /** Latch so we only fire `onTtsUnavailable` once per engine lifetime —
   *  a flaky TTS provider would otherwise spam the user. */
  private ttsUnavailableNotified = false;

  private ttsEndpoint: string;
  private token: string;
  /** Set from `MAICActionEngineOptions.classroomId`. When defined, gates the
   *  offline-audio-durability path: prefetched buffers persist to IDB and
   *  live-TTS failures fall back to `getCachedAudio`. Undefined for chat /
   *  preview engines that don't belong to a single classroom. */
  private classroomId: string | undefined;
  private disposed = false;

  /** Look-ahead prefetch cache for upcoming speech actions. Key is a
   *  content-hash of (voiceId, text); value is a ready-to-play blob URL.
   *  Populated by prefetchSpeech() called from the playback engine when
   *  a speech action starts. `fetchTtsBlob` consults this cache before
   *  hitting the network. Capped at PREFETCH_CACHE_LIMIT entries (LRU). */
  private prefetchCache = new Map<string, string>();
  /** In-flight prefetch fetch controllers keyed by cache-key. Used to
   *  abort parallel requests when the scene changes. */
  private prefetchControllers = new Map<string, AbortController>();

  /** MOB-P0-6 — cached network-aware concurrency cap. Sampled once at
   *  construction time because the overhead per scene is trivial but
   *  NIC type can technically change mid-session (e.g. phone drops
   *  from wifi to 3G). One sample per engine lifetime is a reasonable
   *  balance: a new engine is created per MAIC session / reload. */
  private prefetchConcurrency: number = SCENE_PREFETCH_CONCURRENCY_DEFAULT;
  /** MOB-P0-6 — lookahead cap derived from the same network hint.
   *  Halved on slow networks so the playback-time `prefetchUpcomingSpeech`
   *  (called from maicPlaybackEngine) doesn't compete with the currently
   *  playing speech for bandwidth. */
  private prefetchLookahead: number = 2;

  constructor(opts: MAICActionEngineOptions) {
    this.ttsEndpoint = opts.ttsEndpoint;
    this.token = opts.token;
    this.classroomId = opts.classroomId;
    this.onSpeechStart = opts.onSpeechStart;
    this.onSpeechEnd = opts.onSpeechEnd;
    this.onDiscussionTrigger = opts.onDiscussionTrigger;
    this.onEngineDrivenTransition = opts.onEngineDrivenTransition;
    this.onTtsUnavailable = opts.onTtsUnavailable;
    // Network-aware concurrency sampled at construction (MOB-P0-6).
    this.prefetchConcurrency = getPrefetchConcurrency();
    // Halve the lookahead on slow links (concurrency < default ⇒ slow).
    this.prefetchLookahead =
      this.prefetchConcurrency < SCENE_PREFETCH_CONCURRENCY_DEFAULT ? 1 : 2;

    // F11 (2026-04-28): visibility-driven unlock retry.
    // iOS Safari re-suspends AudioContext after the tab has been hidden for
    // ~30s. Without resetting the unlock latch, unlockAudio() short-circuits
    // forever (`_audioUnlocked === true`) and audio never recovers without
    // a page reload. On hide we drop both latches so the next user-gesture
    // call to unlockAudio() runs the full pipeline again. We attach a single
    // listener per engine instance, bound once, and detach in dispose().
    if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
      document.addEventListener('visibilitychange', this._onVisibilityChange);
    }
  }

  /** F11 (2026-04-28): bound handler so add/removeEventListener pair up.
   *  When the tab goes hidden, drop both unlock latches so the next user
   *  gesture re-runs unlockAudio(). Cheap; no-op while visible. */
  private _onVisibilityChange = (): void => {
    if (typeof document === 'undefined') return;
    if (document.hidden) {
      this._audioUnlocked = false;
      // The in-flight promise (if any) is for a now-stale unlock round.
      // Dropping the reference is safe — the original promise still settles
      // in the background but its only side-effect (setting _audioUnlocked
      // = true via .then) is fine because we'll get hidden→visible again
      // and reset on the next hide. The important invariant: the next
      // unlockAudio() call must NOT short-circuit on the latch.
      this._unlockInFlightPromise = null;
    }
  };

  /** MOB-P0-6 — used by `maicPlaybackEngine.prefetchUpcomingSpeech` to
   *  scale the in-flight look-ahead window with the same network hint
   *  we use for scene-wide prefetch concurrency. */
  getPrefetchLookahead(): number {
    return this.prefetchLookahead;
  }

  // ─── Lifecycle ──────────────────────────────────────────────────────

  /**
   * Abort the currently executing action.
   *
   * This is the heart of the scene/slide-switch fix:
   *   - Increments `generationToken` — any in-flight callback that captured
   *     the old token will see it's stale and bail out.
   *   - Cancels pending TTS fetch via AbortController.
   *   - Detaches all audio event handlers (onplaying/onended/onerror) so
   *     even if the audio decodes and fires an event, nothing runs.
   *   - Pauses and drops the audio element reference.
   *   - Clears the reading-time fallback timer.
   *   - Clears scheduled effect timers (spotlight auto-clear, etc).
   *   - Resets transient UI state (subtitles, speaking-agent indicator).
   *
   * Called by PlaybackEngine.stop() whenever the user navigates to a
   * different scene or the playback engine changes mode mid-action.
   */
  abortCurrentAction(): void {
    // F9 (2026-04-28): capture the pre-bump token so we can decide whether
    // the planted `audioResolve` belongs to the action we're aborting (its
    // `audioResolveToken` was set under the same generation as `myToken`)
    // or whether it's a stale leftover from a `play().catch` race. Only the
    // matching case fires the resolve — stale resolves are silently dropped
    // (along with the field) so there is no chance of a double-fire on top
    // of whatever already settled the awaiting promise.
    const myToken = this.generationToken;

    // Token bump FIRST — any live callback is now stale.
    this.generationToken++;

    // Cancel pending TTS fetch
    if (this.currentFetchController) {
      this.currentFetchController.abort();
      this.currentFetchController = null;
    }

    // Abort in-flight prefetches and release cached blob URLs — they
    // belong to the now-stale action sequence and the new sequence
    // will build its own cache.
    this.clearPrefetchCache();

    // Stop any live video from a `play_video` action. The polled
    // staleness check inside executePlayVideo will resolve the await
    // on next tick because we just bumped the generationToken.
    if (this.currentVideoElement) {
      try { this.currentVideoElement.pause(); } catch { /* silent */ }
      this.currentVideoElement = null;
    }

    // Stop playing audio; detach all handlers so buffered events are no-ops.
    // F5 (2026-04-28): the audio element is now engine-lifetime
    // (`_sharedAudio`). We detach handlers + revoke the blob URL but
    // KEEP `_sharedAudio` allocated for the next speech. Only `dispose()`
    // tears down the element itself. `audioElement` (the "currently
    // bound" alias) is nulled so `hasActiveAudio()` correctly reports
    // false during the abort window.
    if (this.audioElement) {
      this.audioElement.onplaying = null;
      this.audioElement.onended = null;
      this.audioElement.onerror = null;
      try {
        this.audioElement.pause();
      } catch {
        /* ignore pause failures (e.g. audio not yet loaded) */
      }
      if (this.audioElement.src && this.audioElement.src.startsWith('blob:')) {
        URL.revokeObjectURL(this.audioElement.src);
      }
      this.audioElement.src = '';
      this.audioElement = null;
    }

    // F6 (2026-04-28): clear paused-mid-fetch state. If a resume-waiter
    // is pending, fire it so the awaiting executeSpeech wakes — its
    // post-resume token check sees the just-bumped generationToken and
    // bails cleanly without playing audio.
    this._pausedMidFetch = false;
    if (this._resumeWaiter) {
      const waiter = this._resumeWaiter;
      this._resumeWaiter = null;
      try { waiter(); } catch { /* defensive */ }
    }

    if (this.audioResolve) {
      // F9 guard: only fire when the planted resolve matches the pre-bump
      // token we captured above. A stale planted resolve (older generation
      // — possible if a play().catch reaction returned early on a prior
      // staleness check without nulling the field) gets dropped silently.
      // Either way we clear the field + token so the next playAudioSynced
      // starts from a clean slate.
      if (this.audioResolveToken === myToken) {
        this.audioResolve();
      }
      this.audioResolve = null;
      this.audioResolveToken = null;
    }

    // Clear reading-time fallback timer if running.
    if (this.readingTimer) {
      clearTimeout(this.readingTimer);
      this.readingTimer = null;
    }

    // Clear scheduled effect timers (whiteboard fade-ins, spotlight auto-clear, etc.)
    for (const timer of this.effectTimers) {
      clearTimeout(timer);
    }
    this.effectTimers = [];

    // Reset transient state. T0.2 — isSpeaking is the live-playback
    // indicator; clear alongside speaker + text on abort/scene change
    // so a new scene opens without a lingering "speaking" state.
    this.stageStore.getState().setSpeakingAgent(null);
    this.stageStore.getState().setSpeechText(null);
    this.stageStore.getState().setSpeechFetchLoading(false);
    this.stageStore.getState().setIsSpeaking(false);
    this.stageStore.getState().setSpotlightElementId(null);
  }

  /**
   * Pause the currently playing audio element (if any).
   * Used by PlaybackEngine.pause() — audio stays loaded so it can resume.
   */
  pauseCurrentAudio(): void {
    this.stageStore.getState().setIsSpeaking(false);
    if (this.audioElement && !this.audioElement.paused) {
      this.audioElement.pause();
    }
    // Also pause a live video so "Pause class" during a play_video
    // action actually stops the frame clock + soundtrack.
    if (this.currentVideoElement && !this.currentVideoElement.paused) {
      try { this.currentVideoElement.pause(); } catch { /* silent */ }
    }
  }

  /**
   * CG-P1-13 (2026-04-28): abort the in-flight TTS fetch (if any).
   *
   * Used by PlaybackEngine.pause() to handle the case where Pause is
   * pressed BEFORE the speech's TTS fetch resolves. Without this:
   *   1. fetch resolves
   *   2. executeSpeech proceeds to playAudioSynced
   *   3. audio.play() runs even though engine.mode === 'paused'
   * Result: UI says paused, audio plays anyway.
   *
   * Aborting the fetch causes fetchTtsBlob to return null (its abort
   * handler at the catch site). Bumping generationToken makes any
   * post-fetch token check inside executeSpeech (line ~618) return
   * early, preventing the audio.play() call entirely.
   *
   * Returns true if a fetch was actually aborted (so the caller can
   * choose to rewind the action index for clean replay-on-resume).
   * Returns false if no fetch was in flight (audio was already
   * playing — pauseCurrentAudio handles that case).
   */
  abortInFlightFetch(): boolean {
    if (!this.currentFetchController) return false;
    this.currentFetchController.abort();
    this.currentFetchController = null;
    // Bump token so any post-fetch executeSpeech sees the staleness check
    // fire and returns before audio.play(). Also invalidates any
    // prefetches in flight; they'll be re-fetched on resume if still needed.
    this.generationToken++;
    return true;
  }

  /**
   * F6 (2026-04-28): pause-mid-fetch race fix.
   *
   * Called by the playback engine's `pause()` path INSTEAD of
   * `abortInFlightFetch()` + currentActionIndex rewind. The semantics:
   *
   *   1. Aborts the in-flight fetch controller (if any) — fetchTtsBlob
   *      catches the AbortError and returns null cleanly.
   *   2. Sets `_pausedMidFetch = true` — but does NOT bump the
   *      generationToken. Without the bump, executeSpeech's post-fetch
   *      token check passes and it falls through to a new branch that
   *      awaits `_resumeWaiter` instead of running readingTimeFallback
   *      (which would silently lose the speech).
   *   3. Returns true if a fetch was actually aborted (caller can use
   *      this to decide whether to take the audio-already-playing
   *      branch via `pauseCurrentAudio`).
   *
   * On `resumeFromPauseMidFetch()`, the resume-waiter resolves and
   * executeSpeech re-runs `fetchTtsBlob` with the same args, then
   * proceeds to play. If `abortCurrentAction()` fires while paused-mid-
   * fetch (scene change), it bumps the token AND clears the resume-
   * waiter — executeSpeech wakes, sees the stale token, and bails.
   *
   * Self-contained inside the action engine (the playback engine no
   * longer rewinds `currentActionIndex - 1`).
   */
  pauseMidFetch(): boolean {
    if (!this.currentFetchController) return false;
    this.currentFetchController.abort();
    this.currentFetchController = null;
    this._pausedMidFetch = true;
    // Deliberately NOT bumping generationToken: executeSpeech needs to
    // continue under its original token so the post-fetch / post-
    // resume code paths see the same identity as the action's myToken.
    return true;
  }

  /**
   * F6 (2026-04-28): resolve the pending resume-waiter (if any) so the
   * paused-mid-fetch executeSpeech wakes up and re-runs its fetch.
   * Idempotent — no-op when no waiter is pending.
   *
   * Returns true when an actual waiter was woken. The playback engine's
   * `resume()` uses this to decide whether to skip its own
   * `processNext()` chain: when a waiter was woken, the in-flight
   * `executeSpeech` promise will eventually settle and its `.then()`
   * already drives `processNext`. Calling `processNext()` again here
   * would race with the in-flight speech and double-advance the cursor.
   */
  resumeFromPauseMidFetch(): boolean {
    const waiter = this._resumeWaiter;
    this._resumeWaiter = null;
    this._pausedMidFetch = false;
    if (waiter) {
      try { waiter(); } catch { /* never throws but defensive */ }
      return true;
    }
    return false;
  }

  /**
   * F5 (2026-04-28): lazy-allocate the engine-lifetime shared audio
   * element + wire the engine-lifetime settings subscription.
   *
   * Called from `playAudioSynced` on first speech. Subsequent speeches
   * just reuse the element. SSR-safe: skipped when `Audio` is undefined.
   */
  private _ensureSharedAudio(): HTMLAudioElement | null {
    if (this._sharedAudio) return this._sharedAudio;
    if (typeof Audio === 'undefined') return null;
    const audio = new Audio();
    this._sharedAudio = audio;

    // Engine-lifetime subscription. Pushes settings updates to the
    // shared element on every store change. Survives every play —
    // unsubscribe only on dispose. AV-P0-1 / AV-P0-3 / AV-P2-12.
    try {
      this._settingsUnsub = this.settingsStore.subscribe(
        (s: { playbackSpeed: number; audioVolume: number }) => {
          if (!this._sharedAudio) return;
          if (this._sharedAudio.playbackRate !== s.playbackSpeed) {
            try { this._sharedAudio.playbackRate = s.playbackSpeed; } catch { /* ignore */ }
          }
          if (this._sharedAudio.volume !== s.audioVolume) {
            try { this._sharedAudio.volume = s.audioVolume; } catch { /* ignore */ }
          }
        },
      );
    } catch {
      /* older zustand / test mock without subscribe — non-fatal */
    }

    return audio;
  }

  /**
   * T0.3 — wipe ALL whiteboard annotations. Called by PlaybackEngine
   * from `loadScene` so a new scene never inherits the prior scene's
   * strokes or agent-drawn elements. Distinct from `wb_clear` (an
   * in-scene action) and `wb_close` (hides the panel). This is a
   * boundary reset, not an engine action.
   */
  clearWhiteboardForNewScene(): void {
    const annotations = this.canvasStore.getState().annotations;
    if (annotations.length === 0) return;
    this.canvasStore.getState().clearAnnotations();
  }

  /**
   * Resume a previously paused audio element.
   * Used by PlaybackEngine.resume() — when audio ends, the 'ended' event
   * resolves the play promise, which fires the .then() callback chain.
   */
  resumeCurrentAudio(): void {
    if (this.audioElement && this.audioElement.paused) {
      this.audioElement.play().catch((err) => {
        console.warn('Failed to resume audio:', err);
      });
    }
    if (this.currentVideoElement && this.currentVideoElement.paused) {
      this.currentVideoElement.play().catch((err) => {
        console.warn('Failed to resume video:', err);
      });
    }
  }

  /**
   * Whether there is an active audio element (playing or paused, not ended).
   * Used by PlaybackEngine.resume() to decide whether to resume audio or
   * call processNext() directly.
   */
  hasActiveAudio(): boolean {
    return this.audioElement !== null;
  }

  getAudioDebugState(): {
    audioCurrentTime: number;
    audioPaused: boolean | null;
    audioEnded: boolean | null;
    audioReadyState: number | null;
    audioNetworkState: number | null;
    audioSrc: string;
    contextCurrentTime: number;
    contextState: AudioContextState | null;
  } {
    const audio = this.audioElement ?? this._sharedAudio;
    return {
      audioCurrentTime: audio?.currentTime ?? 0,
      audioPaused: audio?.paused ?? null,
      audioEnded: audio?.ended ?? null,
      audioReadyState: audio?.readyState ?? null,
      audioNetworkState: audio?.networkState ?? null,
      audioSrc: audio?.src ?? '',
      contextCurrentTime: this._audioContext?.currentTime ?? 0,
      contextState: this._audioContext?.state ?? null,
    };
  }

  dispose(): void {
    this.disposed = true;
    this.abortCurrentAction();
    // F11 (2026-04-28): detach visibility listener to prevent leaks across
    // engine recreations. addEventListener was paired in the constructor
    // with the same bound handler reference, so removeEventListener resolves.
    if (typeof document !== 'undefined' && typeof document.removeEventListener === 'function') {
      document.removeEventListener('visibilitychange', this._onVisibilityChange);
    }
    // F5 (2026-04-28): tear down the engine-lifetime audio + settings sub.
    // Detach handlers first so any buffered events are no-ops, then drop.
    if (this._sharedAudio) {
      this._sharedAudio.onplaying = null;
      this._sharedAudio.onended = null;
      this._sharedAudio.onerror = null;
      try { this._sharedAudio.pause(); } catch { /* ignore */ }
      if (this._sharedAudio.src && this._sharedAudio.src.startsWith('blob:')) {
        try { URL.revokeObjectURL(this._sharedAudio.src); } catch { /* ignore */ }
      }
      this._sharedAudio.src = '';
      this._sharedAudio = null;
    }
    if (this._settingsUnsub) {
      try { this._settingsUnsub(); } catch { /* ignore */ }
      this._settingsUnsub = null;
    }
  }

  // ─── Main Dispatch ──────────────────────────────────────────────────

  async execute(action: MAICAction): Promise<void> {
    if (this.disposed) return;

    switch (action.type) {
      // Fire-and-forget
      case 'spotlight':
        this.executeSpotlight(action);
        return;
      case 'laser':
        this.executeLaser(action);
        return;

      // Awaited
      case 'speech':
        await this.executeSpeech(action);
        return;
      case 'play_video':
        await this.executePlayVideo(action);
        return;

      // Whiteboard
      case 'wb_open':
        await this.executeWbOpen();
        return;
      case 'wb_close':
        await this.executeWbClose();
        return;
      case 'wb_clear':
        await this.executeWbClear();
        return;
      case 'wb_draw_text':
        await this.executeWbDrawText(action);
        return;
      case 'wb_draw_shape':
        await this.executeWbDrawShape(action);
        return;
      case 'wb_draw_chart':
        await this.executeWbDrawChart(action);
        return;
      case 'wb_draw_latex':
        await this.executeWbDrawLatex(action);
        return;
      case 'wb_draw_table':
        await this.executeWbDrawTable(action);
        return;
      case 'wb_draw_line':
        await this.executeWbDrawLine(action);
        return;
      case 'wb_draw_code':
        await this.executeWbDrawCode(action);
        return;
      case 'wb_edit_code':
        await this.executeWbEditCode(action);
        return;
      case 'wb_delete':
        await this.executeWbDelete(action);
        return;

      // Discussion
      case 'discussion':
        this.executeDiscussion(action);
        return;

      // LLM-generated utility actions
      case 'highlight':
        this.executeHighlight(action);
        return;
      case 'pause':
        await this.executePause(action);
        return;
      case 'transition':
        await this.executeTransition(action);
        return;

      default:
        console.warn('Unknown action type:', (action as MAICAction).type);
    }
  }

  // ─── Speech ─────────────────────────────────────────────────────────

  /**
   * Execute a speech action.
   *
   * Token lifecycle:
   *   - Bumps `generationToken` on entry (`myToken = ++this.generationToken`).
   *   - Any concurrent abortCurrentAction() (e.g. user clicks a different
   *     slide, playback engine calls stop()) will increment the token again,
   *     making `myToken` stale — every subsequent check bails out.
   *
   * Path selection:
   *   1. `action.audioUrl` present → play it directly (pre-gen from Chunk 4).
   *   2. Otherwise → fetch TTS blob from backend, then play it.
   *   3. If fetch returns 204 / fails → reading-time fallback.
   */
  private async executeSpeech(action: SpeechAction): Promise<void> {
    const myToken = ++this.generationToken;
    // F6 (2026-04-28): clear any stale pause-mid-fetch state from a prior
    // action's lifecycle. resumeFromPauseMidFetch + abortCurrentAction
    // already handle their respective paths; this is a defensive reset
    // so the resume-waiter loop below starts with a clean flag.
    this._pausedMidFetch = false;
    const { agentId, text, ssml } = action;

    // Resolve per-agent voice ID (explicit on action > agent.voiceId > legacy
    // `agent.voice` > role-based default > fallback en-IN voice).
    const agents = this.stageStore.getState().agents;
    const agent = agents.find((a) => a.id === agentId);
    if (!agent && typeof console !== 'undefined') {
      // Diagnostic for future regressions: if we can't find the agent
      // in the store, every speech for this agentId will fall through
      // to the role-based default voice — which makes same-role agents
      // sound identical. Surface it in the console (non-error) so
      // production debugging can spot this quickly.
      console.warn(
        `[MAIC] speech for unknown agentId=${agentId} — falling back to cycled voice pool`,
      );
    }
    // CG-P0-6: cycle by agent index so two agents of the same role can't
    // collapse to the same fallback voice. See voiceResolver.ts.
    const voiceId =
      action.voiceId ||
      agent?.voiceId ||
      agent?.voice ||
      resolveVoiceForAgent(agent, agents);

    const volume = this.settingsStore.getState().audioVolume;
    const playbackSpeed = this.settingsStore.getState().playbackSpeed;

    // 1. Preferred: pre-generated audio URL (zero network lag).
    // Set the speaker avatar + agent state up-front, but DEFER the subtitle
    // text until audio.onplaying fires (same as live-TTS path). Previously
    // subtitles appeared ~50-300ms before the first audio frame — students
    // saw the line before hearing it. Holding subtitle state until playback
    // starts keeps text + voice in lockstep (matches OpenMAIC's StreamBuffer
    // "hold text until audio catches up" contract).
    if (action.audioUrl) {
      this.stageStore.getState().setSpeakingAgent(agentId);
      return this.playAudioSynced(
        action.audioUrl,
        text,
        agentId,
        volume,
        playbackSpeed,
        myToken,
        /*subtitlesAlreadyShown*/ false,
      );
    }

    // 2. Fallback: live TTS fetch. Show a "speaking indicator without
    //    subtitles" state while the backend generates audio — the agent
    //    avatar animates, but the transcript stays hidden so the student
    //    doesn't see words before hearing them. Subtitles land when
    //    audio.onplaying fires (inside playAudioSynced).
    this.stageStore.getState().setSpeakingAgent(agentId);
    this.stageStore.getState().setSpeechText(null);
    // Sprint 1 · B.3 — show thinking dots in the overlay while the TTS
    // roundtrip is in flight. Cleared in the finally below so stale
    // aborts and errors both reset the indicator.
    this.stageStore.getState().setSpeechFetchLoading(true);

    let blobUrl: string | null = null;
    // F6 (2026-04-28): wrap the fetch in a resume-waiter loop. If
    // `pauseMidFetch()` aborts the in-flight fetch, fetchTtsBlob
    // returns null AND `_pausedMidFetch === true`. Without bumping the
    // token, we await the resume-waiter and re-fetch the same speech
    // when the user clicks Play. abortCurrentAction also fires the
    // waiter (via the bumped-token + cleared-waiter path), and the
    // post-resume token check below bails the loop out cleanly.
    // Capped at a small retry count to defend against a pathological
    // pause-then-pause-again pattern.
    let pauseResumeAttempts = 0;
    const MAX_PAUSE_RESUME_ATTEMPTS = 5;
    // Fetch loop: re-enter when a pause aborted us.
    // eslint-disable-next-line no-constant-condition
    while (true) {
      try {
        blobUrl = await this.fetchTtsBlob(ssml || text, voiceId, myToken);
      } finally {
        if (myToken === this.generationToken) {
          this.stageStore.getState().setSpeechFetchLoading(false);
        }
      }
      if (myToken !== this.generationToken) {
        // Stale — abort happened after the fetch completed. Revoke the blob
        // we decoded so the URL doesn't linger for the page's lifetime.
        if (blobUrl) URL.revokeObjectURL(blobUrl);
        return;
      }
      // F6: paused-mid-fetch case. fetchTtsBlob returned null AND we
      // are NOT under a stale token (no abort). Await the resume-waiter
      // and re-run the fetch when it fires.
      if (
        !blobUrl
        && this._pausedMidFetch
        && pauseResumeAttempts < MAX_PAUSE_RESUME_ATTEMPTS
      ) {
        pauseResumeAttempts++;
        await new Promise<void>((r) => { this._resumeWaiter = r; });
        // Re-check token after the await — abortCurrentAction may have
        // bumped it and cleared the waiter to wake us.
        if (myToken !== this.generationToken) return;
        // Re-show the fetch-loading indicator for the retried fetch.
        this.stageStore.getState().setSpeechFetchLoading(true);
        continue;
      }
      break;
    }
    if (!blobUrl) {
      // 3. Final fallback: no audio at all. Fire subtitles now (nothing
      //    else to wait for) and run a reading-time timer. Prefer the
      //    backend-stamped durationMs over the char estimate.
      // P1.4 — surface the TTS outage to the user exactly once per engine
      // lifetime so they don't wonder why agents are silent. Subsequent
      // fallbacks stay silent (we already decided to degrade gracefully).
      if (!this.ttsUnavailableNotified) {
        this.ttsUnavailableNotified = true;
        this.onTtsUnavailable?.();
      }
      this.onSpeechStart?.(agentId, text);
      this.stageStore.getState().setSpeechText(text);
      return this.readingTimeFallback(text, agentId, myToken, action.durationMs);
    }
    try {
      await this.playAudioSynced(
        blobUrl, text, agentId, volume, playbackSpeed, myToken,
        /*subtitlesAlreadyShown*/ false,
      );
    } finally {
      // Revoke only the blob we created; pre-gen URLs are owned by Chunk 4.
      URL.revokeObjectURL(blobUrl);
    }
  }

  /**
   * Fetch a TTS blob from the backend `ttsEndpoint`. Returns a blob URL on
   * success, or null when the server says "no audio" (204) or the request
   * errors out / is aborted. Caller is responsible for revoking the URL.
   *
   * Consults the prefetch cache first — if a matching (voiceId, text)
   * blob was prefetched by a prior prefetchSpeech() call, return it
   * instantly and remove it from the cache so ownership transfers to
   * the caller (who will revoke it after use).
   *
   * Token check points:
   *   - After the await on `fetch()`
   *   - After the await on `res.blob()`
   * A stale token makes each return a no-op (null).
   */
  private async fetchTtsBlob(
    text: string,
    voiceId: string,
    token: number,
  ): Promise<string | null> {
    // Prefetch cache hit: transfer ownership to the caller.
    const cacheKey = this.prefetchKey(voiceId, text);
    const cached = this.prefetchCache.get(cacheKey);
    if (cached) {
      this.prefetchCache.delete(cacheKey);
      if (token !== this.generationToken) {
        // Stale at cache-lookup time — revoke and return null so the
        // caller doesn't try to play old-scene audio.
        URL.revokeObjectURL(cached);
        return null;
      }
      // AV-P0-3: a cache hit means TTS IS working. Reset the
      // unavailable-toast latch so a future outage can signal again.
      this.ttsUnavailableNotified = false;
      return cached;
    }

    const durableCached = await this.tryOfflineAudioFallback(cacheKey, token);
    if (durableCached) {
      this.ttsUnavailableNotified = false;
      return durableCached;
    }

    this.currentFetchController = new AbortController();
    try {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      const url = `${baseUrl}${this.ttsEndpoint}`;
      const body = JSON.stringify({ text, voiceId, voice_id: voiceId });
      const res = await this.postTts(url, body, this.currentFetchController.signal);
      if (token !== this.generationToken) return null;
      if (res.status === 204 || !res.ok) {
        return await this.tryOfflineAudioFallback(cacheKey, token);
      }
      const blob = await res.blob();
      if (token !== this.generationToken) return null;
      if (blob.size === 0) {
        return await this.tryOfflineAudioFallback(cacheKey, token);
      }
      // AV-P0-3 (2026-04-24): a successful fetch means TTS has recovered.
      // Reset the unavailable-toast latch so if TTS fails again later, the
      // "audio unavailable" toast can fire once more. Without this, a
      // single early blip silences the toast for the whole engine
      // lifetime — users who experience a brief outage never see a
      // recovery signal on subsequent outages.
      this.ttsUnavailableNotified = false;
      return URL.createObjectURL(blob);
    } catch (err) {
      if (this.isAbortError(err)) return null;
      console.warn('TTS fetch failed:', err);
      // Offline-audio-durability re-wire (2026-04-26): the network is
      // truly down. If we previously prefetched this utterance and
      // persisted it to IDB, build a fresh blob URL from that buffer
      // and play it — the student keeps hearing scenes they already
      // primed before going offline.
      return await this.tryOfflineAudioFallback(cacheKey, token);
    } finally {
      // Only clear if we still own it — a concurrent abort may have already
      // nulled it and bumped the token.
      if (token === this.generationToken) {
        this.currentFetchController = null;
      }
    }
  }

  /**
   * Look up a previously-cached TTS buffer in IDB and return a blob URL.
   * Used as a fallback from `fetchTtsBlob` when the live network call
   * fails (offline / 5xx / 204). Returns null when there is no
   * classroomId, no cached buffer, or the engine is stale (token bumped).
   *
   * Caller (fetchTtsBlob) hands the URL to `executeSpeech` exactly like a
   * live-fetched URL — playback then runs the normal `playAudioSynced`
   * pipeline so audio events fire as usual. The caller revokes the URL
   * after playback (existing contract — `URL.revokeObjectURL(blobUrl)`
   * inside the try/finally in executeSpeech).
   */
  private async tryOfflineAudioFallback(
    cacheKey: string,
    token: number,
  ): Promise<string | null> {
    if (!this.classroomId) return null;
    if (token !== this.generationToken) return null;
    try {
      const buffer = await getCachedAudio(this.classroomId, cacheKey);
      if (!buffer) return null;
      if (token !== this.generationToken) return null;
      const blob = new Blob([buffer], { type: 'audio/mpeg' });
      return URL.createObjectURL(blob);
    } catch {
      return null;
    }
  }

  /**
   * Build HTTP headers used by BOTH the main TTS fetch and prefetch
   * fetches. Reads the current stored token on every call so a long-running
   * classroom does not keep using the access token captured when this engine
   * was constructed.
   */
  private buildTtsHeaders(tokenOverride?: string): Record<string, string> {
    const token = tokenOverride || getAccessToken() || this.token;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    };
    if (typeof window !== 'undefined') {
      const hostname = window.location.hostname;
      if (
        hostname === 'localhost' ||
        hostname === '127.0.0.1' ||
        hostname.endsWith('.localhost')
      ) {
        const urlSubdomain = hostname.endsWith('.localhost')
          ? hostname.replace('.localhost', '')
          : null;
        const subdomain =
          urlSubdomain ||
          sessionStorage.getItem('tenant_subdomain') ||
          localStorage.getItem('tenant_subdomain');
        if (subdomain) {
          headers['X-Tenant-Subdomain'] = subdomain;
        }
      }
    }
    return headers;
  }

  private makeAbortError(): DOMException {
    if (typeof DOMException !== 'undefined') {
      return new DOMException('aborted', 'AbortError');
    }
    const err = new Error('aborted') as Error & { name: string };
    err.name = 'AbortError';
    return err as unknown as DOMException;
  }

  private isAbortError(err: unknown): boolean {
    return Boolean(
      err &&
      typeof err === 'object' &&
      'name' in err &&
      (err as { name?: string }).name === 'AbortError',
    );
  }

  private async postTts(
    url: string,
    body: string,
    signal: AbortSignal,
  ): Promise<Response> {
    const request = (tokenOverride?: string) =>
      fetch(url, {
        method: 'POST',
        headers: this.buildTtsHeaders(tokenOverride),
        body,
        signal,
      });

    let res = await request();
    if (!(await this.shouldRefreshTtsResponse(res))) {
      return res;
    }

    if (signal.aborted) {
      throw this.makeAbortError();
    }

    const refreshedToken = await refreshAccessTokenForRequests();
    if (signal.aborted) {
      throw this.makeAbortError();
    }

    res = await request(refreshedToken);
    return res;
  }

  private async shouldRefreshTtsResponse(res: Response): Promise<boolean> {
    if (res.status === 401) return true;
    if (res.status !== 403) return false;

    try {
      const data = await res.clone().json();
      const detail = String(data?.error || data?.detail || '').toLowerCase();
      const code = String(data?.code || '').toLowerCase();
      const messages = Array.isArray(data?.messages)
        ? data.messages.map((item: any) => String(item?.message || '')).join(' ').toLowerCase()
        : '';
      return (
        code.includes('token_not_valid') ||
        (detail.includes('token') && (detail.includes('expired') || detail.includes('invalid'))) ||
        messages.includes('token')
      );
    } catch {
      try {
        const text = (await res.clone().text()).toLowerCase();
        return text.includes('token') && (text.includes('expired') || text.includes('invalid'));
      } catch {
        return false;
      }
    }
  }

  /**
   * Deterministic cache key for a TTS request. Text is sliced to 200
   * chars — the backend preview endpoint caps at 200 anyway, and this
   * keeps the key size bounded for memory.
   */
  private prefetchKey(voiceId: string, text: string): string {
    return `${voiceId}::${(text || '').slice(0, 200)}`;
  }

  /**
   * Look-ahead prefetch for an upcoming speech action. Kicks off a
   * non-blocking `fetch()` to the TTS endpoint and stashes the decoded
   * blob URL in `prefetchCache`. Called by the playback engine after
   * starting the current speech action so that by the time the next
   * one is needed, its audio is already decoded and ready to play.
   *
   * Silent no-op when:
   *   - action has a pre-gen `audioUrl` (no fetch needed)
   *   - cache already holds a blob for this (voiceId, text)
   *   - disposed / cache at limit (graceful degradation)
   *
   * Errors are swallowed — prefetch is a best-effort optimization; a
   * miss just falls back to the regular fetchTtsBlob path at playtime.
   */
  prefetchSpeech(action: SpeechAction): void {
    if (this.disposed) return;
    if (action.audioUrl) return;  // already cached by the browser
    if (!action.text || !action.text.trim()) return;

    const agents = this.stageStore.getState().agents;
    const agent = agents.find((a) => a.id === action.agentId);
    const voiceId =
      action.voiceId ||
      agent?.voiceId ||
      agent?.voice ||
      resolveVoiceForAgent(agent, agents);

    const text = action.ssml || action.text;
    const key = this.prefetchKey(voiceId, text);

    // Already cached or in-flight — nothing to do.
    if (this.prefetchCache.has(key) || this.prefetchControllers.has(key)) return;

    // LRU eviction when cache is full — drop the oldest entry that is NOT
    // currently in flight. F12 (2026-04-28): the previous implementation
    // grabbed `keys().next().value` blindly, which could revoke a blob URL
    // that an in-flight `.then()` was about to write into the cache. The
    // race manifested as silent audio for the just-prefetched line because
    // the URL it held was already revoked.
    //
    // Fix: scan keys in insertion order (oldest first) and skip any whose
    // controller is still present in `prefetchControllers`. If every key is
    // in flight (rare — the cache full of brand-new fetches), allow the
    // cache to grow temporarily; the natural drain when those fetches
    // settle will bring us back under the cap. Letting active fetches
    // complete is strictly better than revoking their URLs.
    if (this.prefetchCache.size >= PREFETCH_CACHE_LIMIT) {
      let evictedKey: string | undefined;
      for (const candidate of this.prefetchCache.keys()) {
        if (!this.prefetchControllers.has(candidate)) {
          evictedKey = candidate;
          break;
        }
      }
      if (evictedKey !== undefined) {
        const oldUrl = this.prefetchCache.get(evictedKey);
        if (oldUrl) URL.revokeObjectURL(oldUrl);
        this.prefetchCache.delete(evictedKey);
      }
      // else: every entry is in flight — fall through and let the cache
      // exceed its cap by one rather than corrupt an active fetch.
    }

    const controller = new AbortController();
    this.prefetchControllers.set(key, controller);
    const myToken = this.generationToken;

    const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
    const url = `${baseUrl}${this.ttsEndpoint}`;
    const body = JSON.stringify({ text, voiceId, voice_id: voiceId });
    this.tryOfflineAudioFallback(key, myToken)
      .then((cachedUrl) => {
        if (!cachedUrl) return null;
        if (
          myToken !== this.generationToken ||
          this.disposed ||
          this.prefetchCache.has(key) ||
          !this.prefetchControllers.has(key)
        ) {
          URL.revokeObjectURL(cachedUrl);
          return true;
        }
        this.prefetchCache.set(key, cachedUrl);
        return true;
      })
      .then((usedDurableCache) => {
        if (usedDurableCache) return null;
        if (
          myToken !== this.generationToken ||
          this.disposed ||
          !this.prefetchControllers.has(key)
        ) {
          return null;
        }
        return this.postTts(url, body, controller.signal);
      })
      .then(async (res) => {
        if (!res) return;
        if (myToken !== this.generationToken) return;  // scene changed
        if (res.status === 204 || !res.ok) return;
        const blob = await res.blob();
        if (myToken !== this.generationToken) return;
        if (blob.size === 0) return;
        // Re-check the cache — a competing prefetch or the actual
        // fetchTtsBlob may have raced us. If so, drop ours.
        if (this.prefetchCache.has(key) || this.disposed) return;
        // AV-P0-2 (2026-04-24): clearPrefetchCache may have fired
        // between the fetch resolving and this .then running — it
        // aborts controllers AND calls this.prefetchControllers.clear().
        // The token/cache-has-key/disposed guards don't catch this. If
        // our own controller was deleted from the controllers map, the
        // cache was cleared. Create the blob URL, but revoke + delete
        // immediately rather than leak it into a cleared cache.
        const blobUrl = URL.createObjectURL(blob);
        if (!this.prefetchControllers.has(key)) {
          URL.revokeObjectURL(blobUrl);
          return;
        }
        this.prefetchCache.set(key, blobUrl);

        // Offline-audio-durability re-wire (2026-04-26): mirror the
        // decoded buffer into IDB so a reload-while-offline still hears
        // this scene. Fire-and-forget; failures must never break
        // playback. Skipped when no classroomId (chat/preview engines)
        // or when the AV-P0-2 controller-presence recheck fails (we
        // already returned above). Use the same `key` as the in-memory
        // cache so the live-TTS fallback path can look it up at play
        // time without re-deriving.
        if (this.classroomId) {
          blob
            .arrayBuffer()
            .then((buffer) => {
              if (myToken !== this.generationToken) return;
              if (this.disposed) return;
              return cacheAudio(this.classroomId as string, key, buffer);
            })
            .catch(() => {
              /* IDB persistence is best-effort */
            });
        }
      })
      .catch((err) => {
        if (this.isAbortError(err)) return;
        // Silent — prefetch is best-effort.
      })
      .finally(() => {
        this.prefetchControllers.delete(key);
      });
  }

  /**
   * Scene-wide TTS prefetch. Called from `MAICPlaybackEngine.loadScene`
   * the moment a new scene is handed to the engine, BEFORE the user
   * presses Play. Walks every action in scene order, kicks off TTS
   * fetches for every non-pre-gen speech action, and caches the decoded
   * blob URLs keyed by (voiceId, text). By the time playback reaches
   * each speech line, its audio is already decoded in memory — the
   * first line starts instantly, and inter-speaker gaps disappear.
   *
   * This is our port of OpenMAIC's "all scene TTS ready before playback"
   * contract (their `generateTTSForScene` writes to IndexedDB; we keep
   * it in an in-memory blob-URL cache sized to fit the whole scene).
   *
   * Concurrency is capped at `this.prefetchConcurrency` (MOB-P0-6 —
   * network-aware, sampled once at construction from
   * `getPrefetchConcurrency`). Order is preserved: the first N speeches
   * start immediately, each completion pulls the next queued one. That
   * way the earliest speeches in the scene decode first and are ready
   * when processNext() reaches them. On slow-2g / 2g / saveData we drop
   * to 1 so the opening speech isn't fighting tail prefetches for
   * bandwidth.
   *
   * generationToken semantics: captures the token at call time and
   * threads it through each `prefetchSpeech` call. A subsequent
   * `abortCurrentAction` (scene change / user-stop) bumps the token
   * AND calls `clearPrefetchCache`, which aborts in-flight controllers
   * and revokes cached URLs — the remaining items in our pending queue
   * are then no-ops when their slot opens because the token check
   * inside prefetchSpeech bails out.
   */
  prefetchSceneSpeeches(actions: ReadonlyArray<MAICAction>): void {
    if (this.disposed) return;

    // Filter in scene order so early speeches are prefetched first.
    const speechActions = actions.filter(
      (a): a is SpeechAction =>
        a.type === 'speech' && !!a.text && !a.audioUrl,
    );
    if (speechActions.length === 0) return;

    const sceneToken = this.generationToken;
    let cursor = 0;

    const startNext = () => {
      // Scene changed or engine disposed — drop out; remaining items
      // are now stale and should not be fetched.
      if (this.disposed) return;
      if (sceneToken !== this.generationToken) return;
      // Cache full — stop queueing. Any speeches past this point will
      // fall back to the regular live-TTS fetch at playtime (still
      // fast enough because at that point we're mid-scene with the
      // user attentive).
      if (this.prefetchCache.size >= PREFETCH_CACHE_LIMIT) return;
      if (cursor >= speechActions.length) return;

      const action = speechActions[cursor++];
      // prefetchSpeech is fire-and-forget; we peek at its internal
      // controllers map to detect completion via the `finally` block.
      // Simpler: just run it and schedule the next slot on the same
      // microtask cycle using the controllers map as a signal.
      this.prefetchSpeech(action);

      // Poll the controller map for THIS key to know when to pull the
      // next one. Cheap: we only do it while a scene is loading and
      // a slot is open. `controller.signal.onabort` would be cleaner
      // but the prefetchSpeech abstraction owns the controller.
      const agentsForFallback = this.stageStore.getState().agents;
      const agent = agentsForFallback.find((a) => a.id === action.agentId);
      const voiceId =
        action.voiceId ||
        agent?.voiceId ||
        agent?.voice ||
        resolveVoiceForAgent(agent, agentsForFallback);
      const key = this.prefetchKey(voiceId, action.ssml || action.text);

      const waitForSlot = () => {
        if (this.disposed) return;
        if (sceneToken !== this.generationToken) return;
        if (this.prefetchControllers.has(key)) {
          // Still in flight — check again on next macrotask. 25 ms
          // keeps CPU cost trivial while responsive enough to keep
          // the pipe full. AV-P0-4 (2026-04-24): track the handle in
          // `prefetchPollTimers` so `clearPrefetchCache` can cancel
          // every pending poll synchronously. Without tracking, rapid
          // scene-chip slams leak orphan polls that CPU-spin until
          // their guards fire.
          const h = setTimeout(waitForSlot, 25);
          this.prefetchPollTimers.push(h);
          return;
        }
        // Slot free — pull next.
        startNext();
      };
      waitForSlot();
    };

    // Seed the pipeline with N parallel starters.
    const initial = Math.min(this.prefetchConcurrency, speechActions.length);
    for (let i = 0; i < initial; i++) startNext();
  }

  /** Abort all in-flight prefetches and revoke all cached blob URLs. */
  private clearPrefetchCache(): void {
    for (const controller of this.prefetchControllers.values()) {
      controller.abort();
    }
    this.prefetchControllers.clear();
    for (const blobUrl of this.prefetchCache.values()) {
      URL.revokeObjectURL(blobUrl);
    }
    this.prefetchCache.clear();
    // AV-P0-4 (2026-04-24): cancel every pending waitForSlot poll so a
    // stale scene's pipe-filler doesn't continue CPU-spinning in the
    // background. Synchronous — the token/disposed guards inside
    // waitForSlot are a secondary defense only.
    for (const h of this.prefetchPollTimers) clearTimeout(h);
    this.prefetchPollTimers = [];
  }

  /**
   * Play `src` via a fresh HTMLAudioElement.
   *
   * Subtitle + speaking-indicator state fires EAGERLY at the start of
   * the speech action (see `executeSpeech`) so the audience sees the
   * line the moment the engine commits to playing it — not after the
   * audio element buffers and fires `onplaying`, which on slow networks
   * can lag by 500ms-2s and desync subtitles from audio.
   *
   * Here we just re-assert the state inside `onplaying` as an idempotent
   * guard: if a scene change bumped the generation token between the
   * eager fire and the actual audio start, the state was already cleared
   * and we skip re-setting it.
   *
   * Every callback checks `token !== this.generationToken` and:
   *   - For `onplaying`: pauses immediately so buffered audio stops.
   *   - For `onended`/`onerror`/`play().catch`: exits without resolving
   *     the promise (abortCurrentAction() already resolved it via audioResolve).
   */
  private playAudioSynced(
    src: string,
    text: string,
    agentId: string,
    volume: number,
    playbackRate: number,
    token: number,
    subtitlesAlreadyShown = false,
  ): Promise<void> {
    return new Promise((resolve) => {
      if (token !== this.generationToken) {
        resolve();
        return;
      }

      // F5 (2026-04-28): reuse the engine-lifetime shared audio element
      // instead of allocating `new Audio()` per speech. The element is
      // lazily allocated on first speech (so SSR / no-Audio-global tests
      // still construct cleanly) and persists for the engine lifetime.
      const audio = this._ensureSharedAudio();
      if (!audio) {
        // Audio global not available (SSR / locked-down env) — degrade
        // to a sub-tick resolve so the caller isn't left hanging.
        resolve();
        return;
      }
      // Detach any handlers left over from a prior speech (defensive —
      // abortCurrentAction also clears them, but a clean onended path
      // does not). Revoke the previous blob URL if any so we don't leak.
      audio.onplaying = null;
      audio.onended = null;
      audio.onerror = null;
      if (audio.src && audio.src.startsWith('blob:') && audio.src !== src) {
        try { URL.revokeObjectURL(audio.src); } catch { /* ignore */ }
      }
      this.audioElement = audio;
      this.audioResolve = resolve;
      // F9 (2026-04-28): pin the resolve to the action's token. abortCurrentAction
      // captures the pre-bump token and only fires this resolve when the tokens
      // match — protects against double-fire when a play().catch reaction
      // returns early (its existing token check skips before nulling) and
      // leaves the field non-null at the wrong generation.
      this.audioResolveToken = token;

      audio.volume = volume;
      audio.playbackRate = playbackRate;

      // F5 (2026-04-28): the per-play settings subscription is gone —
      // `_ensureSharedAudio` wired an engine-lifetime subscription that
      // pushes settings updates to `_sharedAudio` for as long as the
      // engine lives. Mid-speech speed/volume slider drags still work
      // (AV-P0-1 / AV-P0-3 / AV-P2-12) without per-play sub/unsub
      // churn. The terminal handlers no longer carry a `cleanup()` for
      // the subscription.

      audio.onplaying = () => {
        if (token !== this.generationToken) {
          try {
            audio.pause();
          } catch {
            /* ignore */
          }
          return;
        }
        // Audio has actually started playing. If subtitles were NOT
        // already shown by the caller (live-TTS path), reveal them
        // now — the wait time is over. If they WERE already shown
        // (pre-gen / reading-fallback path), re-assert state
        // idempotently in case a competing action briefly cleared it.
        if (!subtitlesAlreadyShown) {
          this.onSpeechStart?.(agentId, text);
        }
        this.stageStore.getState().setSpeakingAgent(agentId);
        this.stageStore.getState().setSpeechText(text);
      };

      audio.onended = () => {
        if (token !== this.generationToken) return;
        // T0.2 — hold the bubble on the last line between speakers.
        // Only clear `isSpeaking` (via onSpeechEnd); don't null the
        // speaker/text. Next action's onSpeechStart will overwrite.
        this.onSpeechEnd?.();
        // F5 (2026-04-28): null `audioElement` (the "currently bound"
        // alias) so `hasActiveAudio()` returns false. `_sharedAudio`
        // stays — next speech reuses it.
        this.audioElement = null;
        this.audioResolve = null;
        this.audioResolveToken = null;
        resolve();
      };

      audio.onerror = () => {
        if (token !== this.generationToken) return;
        // Fail-open: advance playback so one broken audio doesn't hang the
        // whole classroom. Do not flash subtitles for audio that never started.
        this.onSpeechEnd?.();
        this.audioElement = null;
        this.audioResolve = null;
        this.audioResolveToken = null;
        resolve();
      };

      audio.src = src;
      audio.play().catch((err) => {
        if (token !== this.generationToken) return;
        // Distinguish autoplay-block (NotAllowedError) from decode errors.
        // Autoplay block is the leading cause of "classroom plays with zero
        // audio" — browser rejects audio.play() when there's no recent user
        // gesture. We fire the same one-shot unavailable event used for TTS
        // 204 so Stage shows a toast; students can click Play to retry.
        const isAutoplayBlock = (err && (err.name === 'NotAllowedError'
          || /interact|gesture|user activation|play\(\)/i.test(String(err.message || ''))));
        if (isAutoplayBlock && !this.ttsUnavailableNotified) {
          this.ttsUnavailableNotified = true;
          this.onTtsUnavailable?.();
          if (typeof console !== 'undefined') {
            console.warn('[MAIC] audio.play() blocked by browser — click Play to unlock');
          }
        } else if (typeof console !== 'undefined') {
          console.warn('[MAIC] audio.play() rejected:', err);
        }
        this.onSpeechEnd?.();
        this.audioElement = null;
        this.audioResolve = null;
        this.audioResolveToken = null;
        resolve();
      });
    });
  }

  /**
   * Unlock the audio pipeline on first user gesture. Browsers require at
   * least one user-initiated play() before they trust programmatic playback.
   *
   * MOB-P0-5 (2026-04-23): the previous implementation used a silent
   * `<audio>` element at volume=0 which iOS Safari largely ignores —
   * engine-driven audio.play() calls later fail with NotAllowedError and
   * the whole class plays silently on iPhone.
   *
   * New strategy: two-pronged unlock, both fired on the user-gesture tick.
   *
   *   1. AudioContext.resume() + a 1-sample buffer played on the context.
   *      iOS WebKit unlocks the entire audio stack once an AudioContext
   *      has played ≥ 1 sample since a gesture — this is the canonical
   *      "iOS audio unlock" trick. We hold the context as a field so
   *      future gestures reuse it (no 32 lingering contexts).
   *
   *   2. Silent WAV on a cheap HTMLAudioElement — belt-and-suspenders
   *      for older engines / embedded webviews without an AudioContext.
   *
   * Idempotent. Safe to call from any click handler.
   */
  unlockAudio(): void {
    if (this._audioUnlocked) return;
    // In-flight Promise latch (SPRINT-2-BATCH-4-F2): if an unlock round is
    // already in progress, return the existing promise rather than spawning
    // duplicate AudioContext + Audio instances.  Both strategies run in
    // parallel via Promise.allSettled; the latch is released only when BOTH
    // settle — preventing a race where strategy 1's early .catch() clears the
    // latch while strategy 2's promise is still pending, which would let a
    // third call slip through and construct duplicate contexts.
    if (this._unlockInFlightPromise !== null) return;

    // NOTE: _audioUnlocked is set only inside the success callback of
    // resume() / Audio.play() — NOT here — so a first-attempt NotAllowedError
    // (pre-gesture call) does NOT permanently mark the engine as unlocked.
    // A subsequent call from a real user gesture will retry and succeed.
    // NOTE (same-engine retry): a same-instance retry is only possible if
    // BOTH strategies fail. If strategy 2 (silent WAV) succeeds even when
    // strategy 1 (resume) fails, the engine latches (_audioUnlocked = true)
    // and a fresh instance IS required for any subsequent unlock attempt.

    // Build a promise for each strategy.  Synchronous throws inside the
    // strategy body are caught and converted to settled promises so that a
    // broken environment (no AudioContext ctor, no Audio global) never leaves
    // _unlockInFlightPromise permanently non-null.
    // (SPRINT-2-BATCH-4-F1: sync-throw paths now always release the latch.)

    // Strategy 1: AudioContext (reliable on iOS 14.5+ + all modern desktop).
    let resumePromise: Promise<void>;
    try {
      type WebAudioCtor = typeof AudioContext;
      const Ctx: WebAudioCtor | undefined =
        (typeof window !== 'undefined'
          ? ((window as unknown as { AudioContext?: WebAudioCtor; webkitAudioContext?: WebAudioCtor })
              .AudioContext
              ?? (window as unknown as { webkitAudioContext?: WebAudioCtor }).webkitAudioContext)
          : undefined);
      if (Ctx) {
        const ctx = this._audioContext ?? new Ctx();
        this._audioContext = ctx;
        if (ctx.state === 'suspended') {
          resumePromise = ctx.resume().then(() => {
            this._audioUnlocked = true;
          }).catch(() => {
            // NotAllowedError on pre-gesture call — _audioUnlocked stays false
            // so the next user-gesture call can retry.
          });
        } else {
          // Context already running (e.g. already unlocked by an earlier call
          // that was interrupted, or running state on some platforms).
          // Setting _audioUnlocked synchronously here is intentional: the
          // context is already in a running state — there is no resume()
          // promise to await, so the flag can be committed immediately.
          this._audioUnlocked = true;
          resumePromise = Promise.resolve();
        }
        // iOS requires the context to have played ≥ 1 sample since the
        // gesture. 1 frame of silence satisfies it with zero perceptible
        // cost. The node is detached by the browser as soon as it ends.
        const buf = ctx.createBuffer(1, 1, 22050);
        const src = ctx.createBufferSource();
        src.buffer = buf;
        src.connect(ctx.destination);
        try { src.start(0); } catch { /* already started / unsupported */ }
      } else {
        resumePromise = Promise.resolve();
      }
    } catch {
      // Synchronous throw (e.g. AudioContext ctor fails on locked-down WebView).
      // Convert to a resolved promise so allSettled can still run and release
      // the latch. (SPRINT-2-BATCH-4-F1)
      resumePromise = Promise.resolve();
    }

    // Strategy 2: silent WAV fallback for environments without AudioContext.
    let audioPlayPromise: Promise<void>;
    try {
      const el = new Audio();
      // 200 ms of silence, 11 025 Hz mono WAV (smallest valid file).
      el.src = 'data:audio/wav;base64,UklGRjIAAABXQVZFZm10IBIAAAABAAEAIlYAAESsAAACABAAAABkYXRhAAAAAA==';
      el.volume = 0;
      audioPlayPromise = el.play().then(() => {
        this._audioUnlocked = true;
      }).catch(() => {
        // If even the silent unlock is blocked, _audioUnlocked stays false
        // so future user-gesture calls can retry.
      });
    } catch {
      // Synchronous throw (e.g. no Audio global in older WebView).
      // Convert to a resolved promise. (SPRINT-2-BATCH-4-F1)
      audioPlayPromise = Promise.resolve();
    }

    // Wait for both strategies to settle before releasing the latch.
    // This closes the race window (SPRINT-2-BATCH-4-F2): if strategy 1 rejects
    // quickly, strategy 2 is still pending — holding the latch prevents a
    // third sync call from spawning a duplicate context pair.
    this._unlockInFlightPromise = Promise.allSettled([resumePromise, audioPlayPromise]).then(() => {
      this._unlockInFlightPromise = null;
    });
  }

  private _audioUnlocked = false;
  /** @internal non-null while an unlock round is in progress; null when idle. */
  private _unlockInFlightPromise: Promise<void> | null = null;
  private _audioContext: AudioContext | null = null;

  /**
   * Reading-time fallback: when TTS is unavailable, advance on a timer
   * sized to either the backend-stamped `durationMs` (Chunk 5) or, if
   * that's missing, a char-based estimate (~30 ms/char, min 800 ms).
   *
   * Subtitles are NOT re-fired here because `executeSpeech` already fired
   * them eagerly on entry — we only need to clear them at the end.
   *
   * The resolve fn is stored in `audioResolve` so `abortCurrentAction()`
   * can release the pending await when a scene change interrupts reading
   * mode.
   */
  private readingTimeFallback(
    text: string,
    agentId: string,
    token: number,
    stampedDurationMs?: number,
  ): Promise<void> {
    return new Promise((resolve) => {
      if (token !== this.generationToken) {
        resolve();
        return;
      }

      // Register resolve with abort so interrupting the fallback releases the
      // awaiting playback engine immediately (rather than waiting the full
      // reading duration).
      this.audioResolve = resolve;
      // F9 (2026-04-28): pin the resolve to this fallback's token so the
      // abort path's pre-bump-token guard fires it correctly. Same shape
      // as the live-audio path in playAudioSynced.
      this.audioResolveToken = token;

      const ms = stampedDurationMs && stampedDurationMs > 0
        ? stampedDurationMs
        : Math.max(READING_FALLBACK_MIN_MS, text.length * READING_FALLBACK_MS_PER_CHAR);
      this.readingTimer = setTimeout(() => {
        if (token !== this.generationToken) return;
        // T0.2 — do NOT null `speakingAgent`/`speechText` here. The
        // overlay holds the last spoken line until either the next
        // speech action's `onSpeechStart` overwrites it or a scene
        // change clears state via `abortCurrentAction`.
        this.onSpeechEnd?.();
        this.readingTimer = null;
        this.audioResolve = null;
        this.audioResolveToken = null;
        resolve();
      }, ms);
      // agentId unused now that executeSpeech fires subtitles eagerly — keep
      // the parameter for future fallback variations.
      void agentId;
    });
  }

  // ─── Visual Effects ─────────────────────────────────────────────────

  private executeSpotlight(action: SpotlightAction): void {
    const duration = action.duration ?? EFFECT_AUTO_CLEAR_MS;
    this.stageStore.getState().setSpotlightElementId(action.elementId);

    const timer = setTimeout(() => {
      if (!this.disposed) {
        this.stageStore.getState().setSpotlightElementId(null);
      }
    }, duration);
    this.effectTimers.push(timer);
  }

  private executeLaser(action: LaserAction): void {
    const duration = action.duration ?? EFFECT_AUTO_CLEAR_MS;
    this.stageStore.getState().setLaser(action.elementId, action.color);

    const timer = setTimeout(() => {
      if (!this.disposed) {
        this.stageStore.getState().setLaser(null);
      }
    }, duration);
    this.effectTimers.push(timer);
  }

  // ─── Video ──────────────────────────────────────────────────────────

  private async executePlayVideo(action: PlayVideoAction): Promise<void> {
    // Find the video element in the DOM and play it
    const el = document.getElementById(action.elementId) as HTMLVideoElement | null;
    if (!el || !(el instanceof HTMLVideoElement)) {
      console.warn(`Video element not found: ${action.elementId}`);
      return;
    }

    const settings = this.settingsStore.getState();
    el.volume = settings.audioVolume;
    el.playbackRate = settings.playbackSpeed;
    this.currentVideoElement = el;

    // AV-P2-12 (2026-04-24): live-sync speed + volume to the in-flight
    // video element. Same pattern as AV-P0-1 for audio. Without this,
    // mid-video speed-slider changes don't apply until the video ends.
    let settingsUnsub: (() => void) | null = null;
    try {
      settingsUnsub = this.settingsStore.subscribe((s: { playbackSpeed: number; audioVolume: number }) => {
        if (this.currentVideoElement !== el) return;
        if (el.playbackRate !== s.playbackSpeed) {
          try { el.playbackRate = s.playbackSpeed; } catch { /* ignore */ }
        }
        if (el.volume !== s.audioVolume) {
          try { el.volume = s.audioVolume; } catch { /* ignore */ }
        }
      });
    } catch {
      /* older zustand / test mock without subscribe — non-fatal */
    }
    const cleanupSettings = () => {
      if (settingsUnsub) { try { settingsUnsub(); } catch { /* ignore */ } settingsUnsub = null; }
    };

    // Capture the token so a scene change / abort mid-playback drops
    // the await instead of hanging the engine forever. Also listen for
    // `error` so a codec failure doesn't block progression.
    const myToken = this.generationToken;

    try {
      await el.play();
      if (myToken !== this.generationToken) {
        try { el.pause(); } catch { /* silent */ }
        return;
      }
      await new Promise<void>((resolve) => {
        let settled = false;
        const cleanup = () => {
          el.removeEventListener('ended', done);
          el.removeEventListener('error', done);
          window.clearInterval(staleChecker);
        };
        const done = () => {
          if (settled) return;
          settled = true;
          cleanup();
          resolve();
        };
        el.addEventListener('ended', done);
        el.addEventListener('error', done);
        // Poll every 200 ms for stale token so abortCurrentAction /
        // loadScene drops us out instead of leaking a promise that
        // never resolves. The poll is cheap and only runs during video
        // playback which is always foreground.
        const staleChecker = window.setInterval(() => {
          if (myToken !== this.generationToken) {
            try { el.pause(); } catch { /* silent */ }
            done();
          }
        }, 200);
      });
    } catch (err) {
      console.warn('Video play failed:', err);
    } finally {
      cleanupSettings();
      if (this.currentVideoElement === el) {
        this.currentVideoElement = null;
      }
    }
  }

  // ─── Whiteboard ─────────────────────────────────────────────────────

  private getCurrentSceneId(): string {
    const state = this.stageStore.getState();
    const scenes = state.scenes;
    const idx = state.currentSceneIndex;
    return scenes[idx]?.id ?? 'unknown';
  }

  private async executeWbOpen(): Promise<void> {
    this.settingsStore.getState().setShowWhiteboard(true);
    // Give the whiteboard panel time to mount/animate
    await delay(300);
  }

  private async executeWbClose(): Promise<void> {
    // Clear annotations, then hide after a delay
    this.canvasStore.getState().clearAnnotations();
    await delay(WB_CLOSE_DELAY_MS);
    if (!this.disposed) {
      this.settingsStore.getState().setShowWhiteboard(false);
    }
  }

  private async executeWbClear(): Promise<void> {
    const annotations = this.canvasStore.getState().annotations;
    if (annotations.length === 0) return;

    // Cascade delete with staggered delays for animated removal
    for (let i = annotations.length - 1; i >= 0; i--) {
      if (this.disposed) return;
      this.canvasStore.getState().removeAnnotation(annotations[i].id);
      if (i > 0) {
        await delay(WB_CASCADE_DELETE_MS);
      }
    }
  }

  private async executeWbDrawText(action: WbDrawTextAction): Promise<void> {
    const sceneId = this.getCurrentSceneId();
    const points: WhiteboardPoint[] = [
      { x: action.left, y: action.top },
      { x: action.left + action.width, y: action.top + (action.height ?? 40) },
    ];

    const annotation = makeAnnotation(
      action.id,
      'text',
      points,
      action.color ?? '#000000',
      action.fontSize ?? 16,
      sceneId,
    );

    // Attach extra data via extended properties
    annotation.meta = {
      text: action.text,
      html: action.html,
      width: action.width,
      height: action.height,
      fontSize: action.fontSize,
    };

    this.canvasStore.getState().addAnnotation(annotation);
    await delay(WB_ELEMENT_FADE_IN_MS);
  }

  private async executeWbDrawShape(action: WbDrawShapeAction): Promise<void> {
    const sceneId = this.getCurrentSceneId();

    // Encode shape geometry as corner points
    const points: WhiteboardPoint[] = [
      { x: action.left, y: action.top },
      { x: action.left + action.width, y: action.top + action.height },
    ];

    const annotation = makeAnnotation(
      action.id,
      'shape',
      points,
      action.fill ?? action.stroke ?? '#3B82F6',
      action.strokeWidth ?? 2,
      sceneId,
    );

    annotation.meta = {
      shape: action.shape,
      fill: action.fill,
      stroke: action.stroke,
      width: action.width,
      height: action.height,
    };

    this.canvasStore.getState().addAnnotation(annotation);
    await delay(WB_ELEMENT_FADE_IN_MS);
  }

  private async executeWbDrawChart(action: WbDrawChartAction): Promise<void> {
    const sceneId = this.getCurrentSceneId();
    const points: WhiteboardPoint[] = [
      { x: action.left, y: action.top },
      { x: action.left + action.width, y: action.top + action.height },
    ];

    const annotation = makeAnnotation(
      action.id,
      'shape',
      points,
      '#3B82F6',
      1,
      sceneId,
    );

    annotation.meta = {
      chartType: action.chartType,
      data: action.data,
      width: action.width,
      height: action.height,
    };

    this.canvasStore.getState().addAnnotation(annotation);
    await delay(WB_ELEMENT_FADE_IN_MS);
  }

  private async executeWbDrawLatex(action: WbDrawLatexAction): Promise<void> {
    const sceneId = this.getCurrentSceneId();
    const points: WhiteboardPoint[] = [
      { x: action.left, y: action.top },
      { x: action.left + action.width, y: action.top + (action.height ?? 40) },
    ];

    const annotation = makeAnnotation(
      action.id,
      'text',
      points,
      '#000000',
      action.fontSize ?? 16,
      sceneId,
    );

    annotation.meta = {
      latex: action.latex,
      width: action.width,
      height: action.height,
      fontSize: action.fontSize,
    };

    this.canvasStore.getState().addAnnotation(annotation);
    await delay(WB_ELEMENT_FADE_IN_MS);
  }

  private async executeWbDrawTable(action: WbDrawTableAction): Promise<void> {
    const sceneId = this.getCurrentSceneId();
    const estimatedHeight = action.height ?? (action.rows.length + 1) * 32;
    const points: WhiteboardPoint[] = [
      { x: action.left, y: action.top },
      { x: action.left + action.width, y: action.top + estimatedHeight },
    ];

    const annotation = makeAnnotation(
      action.id,
      'shape',
      points,
      '#374151',
      1,
      sceneId,
    );

    annotation.meta = {
      headers: action.headers,
      rows: action.rows,
      width: action.width,
      height: estimatedHeight,
    };

    this.canvasStore.getState().addAnnotation(annotation);
    await delay(WB_ELEMENT_FADE_IN_MS);
  }

  private async executeWbDrawLine(action: WbDrawLineAction): Promise<void> {
    const sceneId = this.getCurrentSceneId();
    const points: WhiteboardPoint[] = [
      { x: action.start[0], y: action.start[1] },
      { x: action.end[0], y: action.end[1] },
    ];

    const annotation = makeAnnotation(
      action.id,
      'pen',
      points,
      action.color ?? '#000000',
      action.width ?? 2,
      sceneId,
    );

    annotation.meta = {
      startMarker: action.startMarker ?? 'none',
      endMarker: action.endMarker ?? 'none',
    };

    this.canvasStore.getState().addAnnotation(annotation);
    await delay(WB_ELEMENT_FADE_IN_MS);
  }

  private async executeWbDelete(action: WbDeleteAction): Promise<void> {
    this.canvasStore.getState().removeAnnotation(action.elementId);
    await delay(200);
  }

  // Porting P2.2 — live code on the whiteboard. `wb_draw_code` seeds a
  // code block; subsequent `wb_edit_code` actions mutate it line-by-line
  // so the agent can "type" code over the course of their explanation.
  // The annotation's `meta.codeLines` is the source of truth — the
  // renderer reads it and lays out each line. Edit ops mutate the
  // existing annotation's meta in place so the renderer's motion wrapper
  // doesn't re-mount (which would replay the entry animation on every
  // keystroke).
  private async executeWbDrawCode(action: WbDrawCodeAction): Promise<void> {
    const sceneId = this.getCurrentSceneId();
    const points: WhiteboardPoint[] = [
      { x: action.left, y: action.top },
      { x: action.left + action.width, y: action.top + (action.height ?? 120) },
    ];
    const annotation = makeAnnotation(
      action.id,
      'text',
      points,
      action.color ?? '#0F172A',
      action.fontSize ?? 14,
      sceneId,
    );
    annotation.meta = {
      code: true,
      codeLines: [...(action.lines ?? [])],
      language: action.language,
      width: action.width,
      height: action.height,
      fontSize: action.fontSize ?? 14,
    };
    this.canvasStore.getState().addAnnotation(annotation);
    await delay(WB_ELEMENT_FADE_IN_MS);
  }

  private async executeWbEditCode(action: WbEditCodeAction): Promise<void> {
    const store = this.canvasStore.getState();
    const target = store.annotations.find((a) => a.id === action.targetId);
    if (!target || !target.meta?.code) {
      // Silently skip — if the target wasn't drawn first the edit is
      // a prompt mistake, not worth halting playback for.
      return;
    }
    const current: string[] = Array.isArray(target.meta.codeLines)
      ? [...target.meta.codeLines]
      : [];
    const start = Math.max(0, Math.min(action.lineStart, current.length));
    const end = Math.max(start, Math.min(action.lineEnd ?? start, current.length - 1));
    let next: string[] = current;
    switch (action.operation) {
      case 'insert_after':
        next = [
          ...current.slice(0, start + 1),
          ...(action.content ?? []),
          ...current.slice(start + 1),
        ];
        break;
      case 'replace_lines':
        next = [
          ...current.slice(0, start),
          ...(action.content ?? []),
          ...current.slice(end + 1),
        ];
        break;
      case 'delete_lines':
        next = [...current.slice(0, start), ...current.slice(end + 1)];
        break;
    }
    // Mutate meta in place and re-add with the same id so the store
    // notifies subscribers without remounting the motion wrapper.
    store.updateAnnotation?.(action.targetId, {
      meta: { ...target.meta, codeLines: next },
    });
    // Per-line feel: short beat per inserted line, capped.
    const inserted = action.operation === 'delete_lines' ? 0 : (action.content?.length ?? 0);
    await delay(Math.min(450, 120 + inserted * 80));
  }

  // ─── Highlight / Pause / Transition ─────────────────────────────────

  private executeHighlight(action: HighlightAction): void {
    const duration = action.duration ?? EFFECT_AUTO_CLEAR_MS;
    // Reuse spotlight visual — same UX, different semantic origin
    this.stageStore.getState().setSpotlightElementId(action.elementId);

    const timer = setTimeout(() => {
      if (!this.disposed) {
        this.stageStore.getState().setSpotlightElementId(null);
      }
    }, duration);
    this.effectTimers.push(timer);
  }

  // F7 (2026-04-28, wave 3): the OpenMAIC reference engine has no `pause`
  // action — natural TTS cadence and the per-action async tick already give
  // listeners the breath they need. Earlier we clamped to 100ms (CG-P1-3)
  // but even that compounded with audio-decode latency into a perceptible
  // gap. This method is now a no-op so existing classrooms whose stored
  // JSON contains `{type:"pause"}` actions still match the dispatch switch
  // (no "unknown action" warnings) and deserialization keeps working —
  // they simply skip without waiting. The `PauseAction` type stays in the
  // union (see types/maic-actions.ts — deprecated; engine no-ops it). The
  // backend prompt directive that emits these actions is queued for
  // removal in a follow-up (apps/courses/maic_generation_service.py:2120,
  // 2144, 2190, 2435, 2467).
  private async executePause(_action: PauseAction): Promise<void> {
    return;
  }

  private async executeTransition(action: TransitionAction): Promise<void> {
    const playbackSpeed = this.settingsStore.getState().playbackSpeed;

    // Multi-slide navigation: if slideIndex is specified, advance to that slide
    // within the current scene's bounds
    if (action.slideIndex != null) {
      const bounds = this.stageStore.getState().sceneSlideBounds;
      const currentScene = this.stageStore.getState().currentSceneIndex;
      const sceneStart = bounds.find((b) => b.sceneIdx === currentScene)?.startSlide ?? 0;
      const absoluteSlideIndex = sceneStart + action.slideIndex;
      // Signal the host BEFORE mutating the store so Stage.tsx's
      // auto-pause effect (which reacts to currentSlideIndex changes)
      // sees the engine-driven flag set for this tick.
      this.onEngineDrivenTransition?.(absoluteSlideIndex);
      this.stageStore.getState().goToSlide(absoluteSlideIndex);
      await delay((action.duration ?? DEFAULT_TRANSITION_DURATION_MS) / playbackSpeed);
      return;
    }

    // Legacy transition: visual effect only, handled by Stage component
    await delay((action.duration ?? DEFAULT_TRANSITION_DURATION_MS) / playbackSpeed);
  }

  // ─── Discussion ─────────────────────────────────────────────────────

  /**
   * Roundtable-panel trigger. Gated behind `action.triggerMode === 'auto'`
   * so the panel never pops open mid-lesson unexpectedly. Legacy actions
   * (and everything the new prompt generates) default to 'manual' — the
   * panel only opens when the teacher explicitly clicks the Roundtable
   * control. Auto discussions remain possible if a future flow needs
   * them, but they must be explicit.
   */
  private executeDiscussion(action: DiscussionAction): void {
    const triggerMode = (action as DiscussionAction & { triggerMode?: string }).triggerMode;
    if (triggerMode !== 'auto') {
      // Manual discussions don't open the panel from engine playback —
      // they only open via the teacher's explicit roundtable control.
      return;
    }
    // NOTE: we intentionally do NOT call setDiscussionMode here. The
    // playback engine's case 'discussion' handler has already saved a
    // checkpoint and entered paused mode; it will fire `onDiscussionPending`
    // which drives the UI-side breath → Join/Skip → setDiscussionMode
    // flow in `DiscussionGateCard`. Previously calling setDiscussionMode
    // here meant the RoundtablePanel popped open instantly with no breath —
    // that's the "suddenly a discussion opens" seam users complained about.
    this.onDiscussionTrigger?.(action.sessionType, action.topic, action.agentIds);
  }
}
