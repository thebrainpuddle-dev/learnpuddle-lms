/**
 * useTTSPreview — React hook for TTS preview playback
 *
 * Supports both browser-native TTS (Web Speech API) and API-based TTS
 * providers (OpenAI, Azure, ElevenLabs) proxied through the Django backend.
 *
 * Adapted from OpenMAIC upstream use-tts-preview.ts for LearnPuddle LMS.
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import {
  ensureVoicesLoaded,
  isBrowserTTSAbortError,
  playBrowserTTSPreview,
} from '../lib/audio/browser-tts-preview';
import api from '../config/api';

/** Options passed to startPreview(). */
export interface TTSPreviewOptions {
  /** Text to speak */
  text: string;
  /** TTS provider ID */
  providerId: string;
  /** TTS model ID (provider-specific) */
  modelId?: string;
  /** Voice ID or name */
  voice: string;
  /** Playback speed (1.0 = normal) */
  speed: number;
  /** API key (optional — backend may have server-configured keys) */
  apiKey?: string;
  /** Base URL override (optional) */
  baseUrl?: string;
}

/**
 * Shared hook for TTS preview playback (browser-native and API-based).
 *
 * - `previewing`: true while a preview is active (including audio playback)
 * - `startPreview(opts)`: start a preview; rejects with non-abort errors
 * - `stopPreview()`: cancel any active preview and reset state
 *
 * @example
 * ```tsx
 * const { previewing, startPreview, stopPreview } = useTTSPreview();
 *
 * <button onClick={() => startPreview({ text: 'Hello', providerId: 'browser-native-tts', voice: 'default', speed: 1 })}>
 *   {previewing ? 'Stop' : 'Preview'}
 * </button>
 * ```
 */
export function useTTSPreview() {
  const [previewing, setPreviewing] = useState(false);
  const cancelRef = useRef<(() => void) | null>(null);
  const requestIdRef = useRef(0);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  /** Cancel in-flight work and release resources (no state update). */
  const cleanup = useCallback(() => {
    requestIdRef.current += 1;
    cancelRef.current?.();
    cancelRef.current = null;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  }, []);

  /** Cancel any active preview and reset the previewing flag. */
  const stopPreview = useCallback(() => {
    cleanup();
    setPreviewing(false);
  }, [cleanup]);

  // Cleanup on unmount (skip state update to avoid React warnings).
  useEffect(() => cleanup, [cleanup]);

  /**
   * Start a TTS preview.
   * Abort errors are swallowed; all other errors are re-thrown for the caller.
   */
  const startPreview = useCallback(
    async (options: TTSPreviewOptions): Promise<void> => {
      cleanup();
      const requestId = ++requestIdRef.current;
      const isStale = () => requestIdRef.current !== requestId;

      setPreviewing(true);
      try {
        // ── Browser-native TTS ──────────────────────────────────────────
        if (options.providerId === 'browser-native-tts') {
          if (typeof window === 'undefined' || !window.speechSynthesis) {
            throw new Error('Browser does not support Speech Synthesis API');
          }
          const voices = await ensureVoicesLoaded();
          if (isStale()) return;
          if (voices.length === 0) {
            throw new Error('No browser TTS voices available');
          }
          const controller = playBrowserTTSPreview({
            text: options.text,
            voice: options.voice,
            rate: options.speed,
            voices,
          });
          cancelRef.current = controller.cancel;
          await controller.promise;
          if (!isStale()) {
            cancelRef.current = null;
            setPreviewing(false);
          }
          return;
        }

        // ── API-based TTS (proxied through Django backend) ──────────────
        const payload: Record<string, unknown> = {
          text: options.text,
          providerId: options.providerId,
          modelId: options.modelId,
          voice: options.voice,
          speed: options.speed,
        };

        const res = await api.post('/v1/teacher/maic/generate/tts/', payload, {
          responseType: 'arraybuffer',
        });
        if (isStale()) return;

        const arrayBuffer: ArrayBuffer = res.data;
        if (!arrayBuffer || arrayBuffer.byteLength === 0) {
          throw new Error('TTS preview returned empty audio');
        }

        // Determine audio type from response headers
        const contentType = res.headers['content-type'] || 'audio/mp3';
        const blob = new Blob([arrayBuffer], { type: contentType });

        if (audioUrlRef.current) URL.revokeObjectURL(audioUrlRef.current);
        const url = URL.createObjectURL(blob);
        audioUrlRef.current = url;

        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => {
          if (!isStale()) {
            audioRef.current = null;
            setPreviewing(false);
          }
        };
        audio.onerror = () => {
          if (!isStale()) {
            audioRef.current = null;
            setPreviewing(false);
          }
        };
        await audio.play();
      } catch (error) {
        if (!isStale()) {
          cancelRef.current = null;
          setPreviewing(false);
        }
        if (!isBrowserTTSAbortError(error)) {
          throw error;
        }
      }
    },
    [cleanup],
  );

  return { previewing, startPreview, stopPreview };
}
