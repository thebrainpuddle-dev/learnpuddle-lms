/**
 * Audio Player — wraps HTMLAudioElement for the playback engine.
 *
 * Source:
 *   /Volumes/CrucialX9/OpenMAIC/lib/utils/audio-player.ts (205 lines)
 *
 * Phase 1 deviations from upstream:
 *   - No IndexedDB cache lookup. Upstream plays from either a server
 *     URL or an IndexedDB Blob keyed by audioId. Phase 1's wire
 *     format ships base64 MP3 inline in `speech_audio` frames; the
 *     playback engine constructs a data: URL and calls play() with it.
 *     IndexedDB caching arrives in Phase 4 when generated classrooms
 *     pre-render audio offline.
 *   - Same public API (play, pause, stop, resume, isPlaying,
 *     hasActiveAudio, onEnded, setVolume, setMuted, setPlaybackRate,
 *     destroy) so 401.4/Phase 4 can swap implementations transparently.
 */

const _logger = {
  // Tiny log helper to avoid pulling in a real logger lib.
  error: (...args: unknown[]) => { if (typeof console !== 'undefined') console.error(...args); },
};

/**
 * AudioPlayer — single-channel HTMLAudioElement wrapper.
 *
 * Lifecycle: each call to `play()` stops any prior audio, creates a
 * new HTMLAudioElement, and starts playback. The `onEnded` callback
 * fires when the natural-end event arrives — NOT on stop()/destroy().
 */
export class AudioPlayer {
  private audio: HTMLAudioElement | null = null;
  private onEndedCallback: (() => void) | null = null;
  private muted: boolean = false;
  private volume: number = 1;
  private playbackRate: number = 1;
  /** Track blob URLs we own so we can revoke them on cleanup. */
  private ownedBlobUrl: string | null = null;

  /**
   * Play an audio source.
   *
   * @param audioId  Stable id; useful for logging/debugging only in
   *                 Phase 1 (Phase 4 IndexedDB lookup will key on it).
   * @param audioUrl Required: an https:// URL OR a `data:audio/...;base64,...`
   *                 URL OR a `blob:...` URL.  When omitted in Phase 1,
   *                 returns false (no playback).
   *
   * @returns true if audio started, false if no audio source available.
   *          Throws (Promise rejection) on browser-side playback errors
   *          (autoplay policy block, decoding failure, etc.).
   */
  public async play(audioId: string, audioUrl?: string): Promise<boolean> {
    if (!audioUrl) {
      // Phase 1: no IndexedDB fallback yet. Caller falls back to
      // reading-time timer or browser-native TTS (PE Phase 401.4).
      return false;
    }

    try {
      this.stop();

      this.audio = new Audio();
      this.audio.src = audioUrl;
      this.audio.volume = this.muted ? 0 : this.volume;
      this.audio.defaultPlaybackRate = this.playbackRate;
      this.audio.playbackRate = this.playbackRate;

      this.audio.addEventListener('ended', this._handleEnded);

      await this.audio.play();
      // Re-apply after play() — some browsers reset rate during load.
      this.audio.playbackRate = this.playbackRate;
      return true;
    } catch (error) {
      _logger.error('[AudioPlayer] play failed', { audioId, error });
      throw error;
    }
  }

  /** Pause playback if currently playing. No-op otherwise. */
  public pause(): void {
    if (this.audio && !this.audio.paused) {
      this.audio.pause();
    }
  }

  /**
   * Stop and clear the current audio.  Does NOT clear `onEndedCallback`
   * (upstream behavior — comment in upstream lines 108-111: stale
   * callbacks are harmless because the engine's mode check prevents
   * spurious processNext()).
   */
  public stop(): void {
    if (this.audio) {
      this.audio.pause();
      this.audio.currentTime = 0;
      this.audio.removeEventListener('ended', this._handleEnded);
      this.audio = null;
    }
    if (this.ownedBlobUrl) {
      URL.revokeObjectURL(this.ownedBlobUrl);
      this.ownedBlobUrl = null;
    }
  }

  /** Resume paused audio.  No-op if not paused or no audio loaded. */
  public resume(): void {
    if (this.audio?.paused) {
      this.audio.playbackRate = this.playbackRate;
      this.audio.play().catch((err) => {
        _logger.error('[AudioPlayer] resume failed', err);
      });
    }
  }

  /** True iff currently playing (not paused, not ended). */
  public isPlaying(): boolean {
    return this.audio !== null && !this.audio.paused;
  }

  /** True iff there's an audio element loaded (playing or paused). */
  public hasActiveAudio(): boolean {
    return this.audio !== null;
  }

  /** Current playback time in milliseconds. */
  public getCurrentTime(): number {
    return this.audio ? this.audio.currentTime * 1000 : 0;
  }

  /** Audio duration in milliseconds. NaN-safe (returns 0 before loadedmetadata). */
  public getDuration(): number {
    return this.audio && !Number.isNaN(this.audio.duration)
      ? this.audio.duration * 1000
      : 0;
  }

  /** Install the natural-end callback. Latest registration wins. */
  public onEnded(callback: () => void): void {
    this.onEndedCallback = callback;
  }

  public setMuted(muted: boolean): void {
    this.muted = muted;
    if (this.audio) {
      this.audio.volume = muted ? 0 : this.volume;
    }
  }

  public setVolume(volume: number): void {
    this.volume = Math.max(0, Math.min(1, volume));
    if (this.audio && !this.muted) {
      this.audio.volume = this.volume;
    }
  }

  public setPlaybackRate(rate: number): void {
    this.playbackRate = Math.max(0.5, Math.min(2, rate));
    if (this.audio) {
      this.audio.playbackRate = this.playbackRate;
    }
  }

  /** Final cleanup — call on Stage unmount. */
  public destroy(): void {
    this.stop();
    this.onEndedCallback = null;
  }

  // ── Private ─────────────────────────────────────────────────────

  /** Bound so removeEventListener finds it. */
  private _handleEnded = (): void => {
    if (this.ownedBlobUrl) {
      URL.revokeObjectURL(this.ownedBlobUrl);
      this.ownedBlobUrl = null;
    }
    this.onEndedCallback?.();
  };
}


/**
 * Construct a data: URL for inline base64 MP3 from a `speech_audio`
 * event.  The frontend playback engine calls this to convert the
 * wire-format payload into something AudioPlayer.play accepts.
 */
export function dataUrlForBase64Mp3(audioB64: string): string {
  return `data:audio/mp3;base64,${audioB64}`;
}


/** Factory for callers that want a fresh instance per Stage mount. */
export function createAudioPlayer(): AudioPlayer {
  return new AudioPlayer();
}
