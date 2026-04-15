// lib/maicActionEngine.ts — Executes individual MAIC actions (TTS, whiteboard, effects)

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
const SPEECH_FALLBACK_WPM = 160;

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

/** Estimate speech duration in ms from text length and playback speed. */
function estimateSpeechDuration(text: string, playbackSpeed: number): number {
  const words = text.split(/\s+/).length;
  const minutes = words / SPEECH_FALLBACK_WPM;
  return (minutes * 60 * 1000) / playbackSpeed;
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
}

export class MAICActionEngine {
  private stageStore = useMAICStageStore;
  private canvasStore = useMAICCanvasStore;
  private settingsStore = useMAICSettingsStore;

  private audioElement: HTMLAudioElement | null = null;
  private effectTimers: ReturnType<typeof setTimeout>[] = [];

  private onSpeechStart?: (agentId: string, text: string) => void;
  private onSpeechEnd?: () => void;
  private onDiscussionTrigger?: (sessionType: string, topic: string, agentIds: string[]) => void;

  private ttsEndpoint: string;
  private token: string;
  private disposed = false;

  constructor(opts: MAICActionEngineOptions) {
    this.ttsEndpoint = opts.ttsEndpoint;
    this.token = opts.token;
    this.onSpeechStart = opts.onSpeechStart;
    this.onSpeechEnd = opts.onSpeechEnd;
    this.onDiscussionTrigger = opts.onDiscussionTrigger;
  }

  // ─── Lifecycle ──────────────────────────────────────────────────────

  dispose(): void {
    this.disposed = true;

    // Stop audio
    if (this.audioElement) {
      this.audioElement.pause();
      if (this.audioElement.src.startsWith('blob:')) {
        URL.revokeObjectURL(this.audioElement.src);
      }
      this.audioElement = null;
    }

    // Clear all scheduled timers
    for (const timer of this.effectTimers) {
      clearTimeout(timer);
    }
    this.effectTimers = [];

    // Reset transient state
    this.stageStore.getState().setSpeakingAgent(null);
    this.stageStore.getState().setSpeechText(null);
    this.stageStore.getState().setSpotlightElementId(null);
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

  private async executeSpeech(action: SpeechAction): Promise<void> {
    const { agentId, text, ssml } = action;
    const settings = this.settingsStore.getState();
    const playbackSpeed = settings.playbackSpeed;
    const volume = settings.audioVolume;

    // Resolve per-agent voice ID
    const agents = this.stageStore.getState().agents;
    const agent = agents.find((a) => a.id === agentId);
    const voiceId = agent?.voice || (agent?.role ? ROLE_VOICE_MAP[agent.role] : undefined) || ROLE_VOICE_MAP.professor;

    // Notify listeners
    this.onSpeechStart?.(agentId, text);
    this.stageStore.getState().setSpeakingAgent(agentId);
    this.stageStore.getState().setSpeechText(text);

    try {
      // Build request to TTS proxy
      const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
      const fullUrl = `${baseUrl}${this.ttsEndpoint}`;

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.token}`,
      };

      // Include tenant subdomain for localhost dev
      const hostname = window.location.hostname;
      if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.endsWith('.localhost')) {
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

      const response = await fetch(fullUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify({ text: ssml || text, agentId, voice_id: voiceId }),
      });

      if (response.ok && response.status !== 204) {
        const blob = await response.blob();
        if (blob.size > 0) {
          const blobUrl = URL.createObjectURL(blob);
          await this.playAudio(blobUrl, volume, playbackSpeed);
          URL.revokeObjectURL(blobUrl);
        } else {
          // Empty audio response — fall back to timed silence
          await delay(estimateSpeechDuration(text, playbackSpeed));
        }
      } else {
        // TTS unavailable (204 or error) — fall back to timed silence
        await delay(estimateSpeechDuration(text, playbackSpeed));
      }
    } catch (err) {
      // Network error — fall back to timing estimate
      console.warn('TTS error, using timing estimate:', err);
      await delay(estimateSpeechDuration(text, playbackSpeed));
    } finally {
      if (!this.disposed) {
        this.stageStore.getState().setSpeakingAgent(null);
        this.stageStore.getState().setSpeechText(null);
        this.onSpeechEnd?.();
      }
    }
  }

  private playAudio(src: string, volume: number, playbackRate: number): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.disposed) {
        resolve();
        return;
      }

      // Clean up any existing audio element
      if (this.audioElement) {
        this.audioElement.pause();
        if (this.audioElement.src.startsWith('blob:')) {
          URL.revokeObjectURL(this.audioElement.src);
        }
      }

      const audio = new Audio();
      audio.preload = 'auto';
      audio.volume = volume;
      audio.playbackRate = playbackRate;
      this.audioElement = audio;

      audio.addEventListener('ended', () => {
        this.audioElement = null;
        resolve();
      });

      audio.addEventListener('error', () => {
        // Resolve instead of reject — playback errors shouldn't break the action sequence
        this.audioElement = null;
        resolve();
      });

      audio.src = src;
      audio.play().catch(() => {
        this.audioElement = null;
        resolve();
      });
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
    (annotation as WhiteboardAnnotation & { meta?: Record<string, unknown> }).meta = {
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

    (annotation as WhiteboardAnnotation & { meta?: Record<string, unknown> }).meta = {
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

    (annotation as WhiteboardAnnotation & { meta?: Record<string, unknown> }).meta = {
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

    (annotation as WhiteboardAnnotation & { meta?: Record<string, unknown> }).meta = {
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

    (annotation as WhiteboardAnnotation & { meta?: Record<string, unknown> }).meta = {
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

    (annotation as WhiteboardAnnotation & { meta?: Record<string, unknown> }).meta = {
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
    await delay(action.duration);
  }

  private async executeTransition(action: TransitionAction): Promise<void> {
    // Multi-slide navigation: if slideIndex is specified, advance to that slide
    // within the current scene's bounds
    if (action.slideIndex != null) {
      const bounds = this.stageStore.getState().sceneSlideBounds;
      const currentScene = this.stageStore.getState().currentSceneIndex;
      const sceneStart = bounds[currentScene]?.startSlide ?? 0;
      const absoluteSlideIndex = sceneStart + action.slideIndex;
      this.stageStore.getState().goToSlide(absoluteSlideIndex);
      // Allow time for transition animation
      await delay(action.duration ?? 600);
      return;
    }

    // Legacy transition: visual effect only, handled by Stage component
    await delay(action.duration ?? 500);
  }

  // ─── Discussion ─────────────────────────────────────────────────────

  private executeDiscussion(action: DiscussionAction): void {
    this.stageStore.getState().setDiscussionMode(action.sessionType);
    this.onDiscussionTrigger?.(action.sessionType, action.topic, action.agentIds);
  }
}
