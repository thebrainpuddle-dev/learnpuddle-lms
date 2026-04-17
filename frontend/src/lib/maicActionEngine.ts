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
  WbDeleteAction,
  DiscussionAction,
} from '../types/maic-actions';
import type { WhiteboardAnnotation, WhiteboardPoint } from '../types/maic';

// ─── Constants ──────────────────────────────────────────────────────────────

const EFFECT_AUTO_CLEAR_MS = 5000;
const WB_ELEMENT_FADE_IN_MS = 800;
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

/** Default voice mapping by agent role */
const ROLE_VOICE_MAP: Record<string, string> = {
  professor: 'en-US-GuyNeural',
  teaching_assistant: 'en-US-JennyNeural',
  student_rep: 'en-US-AriaNeural',
  moderator: 'en-US-DavisNeural',
  student: 'en-US-AriaNeural',
  assistant: 'en-US-JennyNeural',
};

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
  onSpeechStart?: (agentId: string, text: string) => void;
  onSpeechEnd?: () => void;
  onDiscussionTrigger?: (sessionType: string, topic: string, agentIds: string[]) => void;
  /** Invoked just before the engine changes the current slide via a
   *  `transition` action. Lets the host (usePlaybackEngine) flip its
   *  `engineDrivenSlideChangeRef` so Stage.tsx's auto-pause effect
   *  knows this slide change is playback-driven, not user-driven. */
  onEngineDrivenTransition?: (slideIndex: number) => void;
}

export class MAICActionEngine {
  private stageStore = useMAICStageStore;
  private canvasStore = useMAICCanvasStore;
  private settingsStore = useMAICSettingsStore;

  private audioElement: HTMLAudioElement | null = null;
  private audioResolve: (() => void) | null = null;
  private currentFetchController: AbortController | null = null;
  private effectTimers: ReturnType<typeof setTimeout>[] = [];
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

  private ttsEndpoint: string;
  private token: string;
  private disposed = false;

  constructor(opts: MAICActionEngineOptions) {
    this.ttsEndpoint = opts.ttsEndpoint;
    this.token = opts.token;
    this.onSpeechStart = opts.onSpeechStart;
    this.onSpeechEnd = opts.onSpeechEnd;
    this.onDiscussionTrigger = opts.onDiscussionTrigger;
    this.onEngineDrivenTransition = opts.onEngineDrivenTransition;
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
    // Token bump FIRST — any live callback is now stale.
    this.generationToken++;

    // Cancel pending TTS fetch
    if (this.currentFetchController) {
      this.currentFetchController.abort();
      this.currentFetchController = null;
    }

    // Stop playing audio; detach all handlers so buffered events are no-ops.
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

    if (this.audioResolve) {
      this.audioResolve();
      this.audioResolve = null;
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

    // Reset transient state
    this.stageStore.getState().setSpeakingAgent(null);
    this.stageStore.getState().setSpeechText(null);
    this.stageStore.getState().setSpotlightElementId(null);
  }

  /**
   * Pause the currently playing audio element (if any).
   * Used by PlaybackEngine.pause() — audio stays loaded so it can resume.
   */
  pauseCurrentAudio(): void {
    if (this.audioElement && !this.audioElement.paused) {
      this.audioElement.pause();
    }
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
  }

  /**
   * Whether there is an active audio element (playing or paused, not ended).
   * Used by PlaybackEngine.resume() to decide whether to resume audio or
   * call processNext() directly.
   */
  hasActiveAudio(): boolean {
    return this.audioElement !== null;
  }

  dispose(): void {
    this.disposed = true;
    this.abortCurrentAction();
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
    const { agentId, text, ssml } = action;

    // Fire subtitles + speaking indicator EAGERLY at speech entry so
    // the audience sees the line the same frame the engine commits to
    // it. Previously these fired inside audio.onplaying which lags by
    // 500ms-2s on slow networks. The token guard in onplaying + onend
    // still cleans up if a scene change interrupts before audio starts.
    this.onSpeechStart?.(agentId, text);
    this.stageStore.getState().setSpeakingAgent(agentId);
    this.stageStore.getState().setSpeechText(text);

    // Resolve per-agent voice ID (explicit on action > agent.voiceId > legacy
    // `agent.voice` > role-based default > fallback en-IN voice).
    const agents = this.stageStore.getState().agents;
    const agent = agents.find((a) => a.id === agentId);
    const voiceId =
      action.voiceId ||
      agent?.voiceId ||
      agent?.voice ||
      (agent?.role ? ROLE_VOICE_MAP[agent.role as keyof typeof ROLE_VOICE_MAP] : undefined) ||
      'en-IN-NeerjaNeural';

    const volume = this.settingsStore.getState().audioVolume;
    const playbackSpeed = this.settingsStore.getState().playbackSpeed;

    // 1. Preferred: pre-generated audio URL (zero network lag).
    if (action.audioUrl) {
      return this.playAudioSynced(
        action.audioUrl,
        text,
        agentId,
        volume,
        playbackSpeed,
        myToken,
      );
    }

    // 2. Fallback: live TTS fetch.
    const blobUrl = await this.fetchTtsBlob(ssml || text, voiceId, myToken);
    if (myToken !== this.generationToken) {
      // Stale — abort happened after the fetch completed. Revoke the blob
      // we decoded so the URL doesn't linger for the page's lifetime.
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      return;
    }
    if (!blobUrl) {
      // 3. Final fallback: timed reading window so slides don't snap-advance.
      //    Prefer the backend-stamped durationMs over a char estimate when
      //    present (Chunk 5 stamps this on every speech action).
      return this.readingTimeFallback(text, agentId, myToken, action.durationMs);
    }
    try {
      await this.playAudioSynced(blobUrl, text, agentId, volume, playbackSpeed, myToken);
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
    const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
    const url = `${baseUrl}${this.ttsEndpoint}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${this.token}`,
    };

    // Tenant subdomain injection for local dev (preserved from original).
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

    this.currentFetchController = new AbortController();
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({ text, voiceId, voice_id: voiceId }),
        signal: this.currentFetchController.signal,
      });
      if (token !== this.generationToken) return null;
      if (res.status === 204 || !res.ok) return null;
      const blob = await res.blob();
      if (token !== this.generationToken) return null;
      if (blob.size === 0) return null;
      return URL.createObjectURL(blob);
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return null;
      console.warn('TTS fetch failed:', err);
      return null;
    } finally {
      // Only clear if we still own it — a concurrent abort may have already
      // nulled it and bumped the token.
      if (token === this.generationToken) {
        this.currentFetchController = null;
      }
    }
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
  ): Promise<void> {
    return new Promise((resolve) => {
      if (token !== this.generationToken) {
        resolve();
        return;
      }

      const audio = new Audio();
      this.audioElement = audio;
      this.audioResolve = resolve;

      audio.volume = volume;
      audio.playbackRate = playbackRate;

      audio.onplaying = () => {
        if (token !== this.generationToken) {
          try {
            audio.pause();
          } catch {
            /* ignore */
          }
          return;
        }
        // Idempotent — executeSpeech already fired these eagerly. We
        // re-assert here in case setSpeakingAgent(null) was called by a
        // competing action between the eager fire and actual audio start.
        this.stageStore.getState().setSpeakingAgent(agentId);
        this.stageStore.getState().setSpeechText(text);
      };

      audio.onended = () => {
        if (token !== this.generationToken) return;
        this.onSpeechEnd?.();
        this.stageStore.getState().setSpeakingAgent(null);
        this.stageStore.getState().setSpeechText(null);
        // Clear the audioElement reference so hasActiveAudio() returns false.
        this.audioElement = null;
        this.audioResolve = null;
        resolve();
      };

      audio.onerror = () => {
        if (token !== this.generationToken) return;
        // Fail-open: advance playback so one broken audio doesn't hang the
        // whole classroom. Do not flash subtitles for audio that never started.
        this.onSpeechEnd?.();
        this.audioElement = null;
        this.audioResolve = null;
        resolve();
      };

      audio.src = src;
      audio.play().catch(() => {
        if (token !== this.generationToken) return;
        // play() rejected (autoplay blocked, decode error) — resolve so the
        // playback engine can advance.
        this.onSpeechEnd?.();
        this.audioElement = null;
        this.audioResolve = null;
        resolve();
      });
    });
  }

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

      const ms = stampedDurationMs && stampedDurationMs > 0
        ? stampedDurationMs
        : Math.max(READING_FALLBACK_MIN_MS, text.length * READING_FALLBACK_MS_PER_CHAR);
      this.readingTimer = setTimeout(() => {
        if (token !== this.generationToken) return;
        this.onSpeechEnd?.();
        this.stageStore.getState().setSpeakingAgent(null);
        this.stageStore.getState().setSpeechText(null);
        this.readingTimer = null;
        this.audioResolve = null;
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

  private executeLaser(_action: LaserAction): void {
    // Laser pointer removed — skip for legacy compatibility
    console.debug('Laser action skipped (deprecated)');
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

    try {
      await el.play();
      // Wait for video to end
      await new Promise<void>((resolve) => {
        const onEnded = () => {
          el.removeEventListener('ended', onEnded);
          resolve();
        };
        el.addEventListener('ended', onEnded);
      });
    } catch (err) {
      console.warn('Video play failed:', err);
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

  private async executePause(action: PauseAction): Promise<void> {
    const playbackSpeed = this.settingsStore.getState().playbackSpeed;
    await delay(action.duration / playbackSpeed);
  }

  private async executeTransition(action: TransitionAction): Promise<void> {
    const playbackSpeed = this.settingsStore.getState().playbackSpeed;

    // Multi-slide navigation: if slideIndex is specified, advance to that slide
    // within the current scene's bounds
    if (action.slideIndex != null) {
      const bounds = this.stageStore.getState().sceneSlideBounds;
      const currentScene = this.stageStore.getState().currentSceneIndex;
      const sceneStart = bounds[currentScene]?.startSlide ?? 0;
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
      // Intentional skip — not an error. Leaves the discussion metadata
      // on the action for any teacher-facing "Open roundtable" button to
      // consume later.
      return;
    }
    this.stageStore.getState().setDiscussionMode(action.sessionType);
    this.onDiscussionTrigger?.(action.sessionType, action.topic, action.agentIds);
  }
}
