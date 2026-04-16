/**
 * TTS (Text-to-Speech) Provider Implementation — Client-Side
 *
 * In the LearnPuddle architecture, TTS for server-side providers (OpenAI, Azure,
 * ElevenLabs) is proxied through the Django backend. The client POSTs to
 * `/api/v1/{role}/maic/generate/tts/` with provider config, and the backend
 * handles the actual API call and returns audio data.
 *
 * For browser-native TTS, use the Web Speech API directly on the client
 * (see browser-tts-preview.ts and the useTTSPreview hook).
 *
 * Adapted from OpenMAIC upstream for LearnPuddle LMS.
 */

import type { TTSModelConfig, TTSProviderId } from './types';
import { isCustomTTSProvider } from './types';
import { TTS_PROVIDERS } from './constants';
import api from '../../config/api';

/**
 * Result of TTS generation
 */
export interface TTSGenerationResult {
  audio: Uint8Array;
  format: string;
}

/**
 * Thrown when a TTS provider returns a rate-limit / concurrency-quota error.
 * Allows downstream consumers to distinguish rate-limit errors from other TTS failures.
 */
export class TTSRateLimitError extends Error {
  constructor(
    public readonly provider: string,
    message: string,
  ) {
    super(message);
    this.name = 'TTSRateLimitError';
  }
}

/**
 * Generate speech using the specified TTS provider via the Django backend.
 *
 * For server-side providers (openai-tts, azure-tts, elevenlabs-tts, custom),
 * this POSTs to the backend TTS endpoint which handles the actual API call.
 *
 * For browser-native-tts, throws an error directing callers to use the
 * Web Speech API client-side via useTTSPreview or playBrowserTTSPreview.
 */
export async function generateTTS(
  config: TTSModelConfig,
  text: string,
  role: 'teacher' | 'student' = 'teacher',
): Promise<TTSGenerationResult> {
  if (config.providerId === 'browser-native-tts') {
    throw new Error(
      'Browser Native TTS must be handled client-side using Web Speech API. ' +
        'Use the useTTSPreview hook or playBrowserTTSPreview() instead.',
    );
  }

  // Validate that the provider exists (for built-in providers)
  const provider = TTS_PROVIDERS[config.providerId as keyof typeof TTS_PROVIDERS];
  if (!provider && !isCustomTTSProvider(config.providerId)) {
    throw new Error(`Unsupported TTS provider: ${config.providerId}`);
  }

  // POST to Django backend which proxies the TTS API call
  const endpoint = `/v1/${role}/maic/generate/tts/`;

  const payload: Record<string, unknown> = {
    text,
    providerId: config.providerId,
    voice: config.voice,
    speed: config.speed ?? 1.0,
    modelId: config.modelId || provider?.defaultModelId || '',
    format: config.format,
  };

  // Include provider-specific options if present
  if (config.providerOptions) {
    payload.providerOptions = config.providerOptions;
  }

  try {
    const response = await api.post(endpoint, payload, {
      responseType: 'arraybuffer',
    });

    const arrayBuffer: ArrayBuffer = response.data;
    const contentType = response.headers['content-type'] || '';

    // Determine format from response content-type
    let format = 'mp3';
    if (contentType.includes('wav')) format = 'wav';
    else if (contentType.includes('opus')) format = 'opus';
    else if (contentType.includes('ogg')) format = 'ogg';
    else if (contentType.includes('aac')) format = 'aac';
    else if (contentType.includes('flac')) format = 'flac';

    return {
      audio: new Uint8Array(arrayBuffer),
      format,
    };
  } catch (error: unknown) {
    // Check for rate limit errors (HTTP 429)
    if (
      error &&
      typeof error === 'object' &&
      'response' in error &&
      (error as { response?: { status?: number } }).response?.status === 429
    ) {
      throw new TTSRateLimitError(
        config.providerId,
        `Rate limit exceeded for TTS provider: ${config.providerId}`,
      );
    }
    throw error;
  }
}

/**
 * Get current TTS configuration from the MAIC settings store.
 *
 * Reads the persisted TTS provider, voice, speed, and model settings
 * to build a TTSModelConfig suitable for generateTTS().
 */
export function getCurrentTTSConfig(): TTSModelConfig {
  // Dynamic import to avoid circular dependency at module load time.
  // The store is always available in browser context when this is called.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { useMAICSettingsStore } = require('../../stores/maicSettingsStore');
  const state = useMAICSettingsStore.getState();

  const providerId: TTSProviderId = state.ttsProviderId ?? 'browser-native-tts';
  const providerSettings = state.ttsProvidersConfig?.[providerId];

  return {
    providerId,
    modelId:
      providerSettings?.modelId ||
      TTS_PROVIDERS[providerId as keyof typeof TTS_PROVIDERS]?.defaultModelId ||
      '',
    apiKey: providerSettings?.apiKey,
    baseUrl: providerSettings?.baseUrl,
    voice: state.ttsVoice ?? 'default',
    speed: state.ttsSpeed ?? 1.0,
  };
}

// Re-export helpers from constants for convenience
export { getAllTTSProviders, getTTSProvider, getTTSVoices } from './constants';
