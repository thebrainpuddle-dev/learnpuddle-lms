/**
 * ASR (Automatic Speech Recognition) Provider Implementation — Client-Side
 *
 * In the LearnPuddle architecture, ASR for server-side providers (OpenAI Whisper)
 * is proxied through the Django backend. The client POSTs audio to
 * `/api/v1/{role}/maic/transcribe/` and receives back transcribed text.
 *
 * For browser-native ASR, use the Web Speech API directly on the client
 * (via the SpeechRecognition API or a dedicated hook).
 *
 * Adapted from OpenMAIC upstream for LearnPuddle LMS.
 */

import type { ASRModelConfig, ASRProviderId } from './types';
import { isCustomASRProvider } from './types';
import { ASR_PROVIDERS } from './constants';
import api from '../../config/api';

/**
 * Result of ASR transcription
 */
export interface ASRTranscriptionResult {
  text: string;
}

/**
 * Transcribe audio using the specified ASR provider via the Django backend.
 *
 * For openai-whisper (and custom providers), POSTs audio as FormData to the
 * backend transcription endpoint.
 *
 * For browser-native, throws an error directing callers to use the
 * Web Speech API client-side.
 */
export async function transcribeAudio(
  config: ASRModelConfig,
  audioBlob: Blob,
  role: 'teacher' | 'student' = 'teacher',
): Promise<ASRTranscriptionResult> {
  if (config.providerId === 'browser-native') {
    throw new Error(
      'Browser Native ASR must be handled client-side using the Web Speech API ' +
        '(SpeechRecognition). This provider cannot be used via server proxy.',
    );
  }

  // Validate provider
  const provider = ASR_PROVIDERS[config.providerId as keyof typeof ASR_PROVIDERS];
  if (!provider && !isCustomASRProvider(config.providerId)) {
    throw new Error(`Unsupported ASR provider: ${config.providerId}`);
  }

  const endpoint = `/v1/${role}/maic/transcribe/`;

  const formData = new FormData();
  formData.append('audio', audioBlob, 'recording.webm');
  formData.append('providerId', config.providerId);
  if (config.modelId) {
    formData.append('modelId', config.modelId);
  }
  if (config.language && config.language !== 'auto') {
    formData.append('language', config.language);
  }

  const response = await api.post<{ text: string }>(endpoint, formData);
  return { text: response.data.text || '' };
}

/**
 * Get current ASR configuration from the MAIC settings store.
 *
 * Reads the persisted ASR provider, language, and model settings
 * to build an ASRModelConfig suitable for transcribeAudio().
 */
export function getCurrentASRConfig(): ASRModelConfig {
  // Dynamic import to avoid circular dependency at module load time.
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { useMAICSettingsStore } = require('../../stores/maicSettingsStore');
  const state = useMAICSettingsStore.getState();

  const providerId: ASRProviderId = state.asrProviderId ?? 'browser-native';
  const providerSettings = state.asrProvidersConfig?.[providerId];

  return {
    providerId,
    modelId:
      providerSettings?.modelId ||
      ASR_PROVIDERS[providerId as keyof typeof ASR_PROVIDERS]?.defaultModelId ||
      '',
    apiKey: providerSettings?.apiKey,
    baseUrl: providerSettings?.baseUrl,
    language: state.asrLanguage ?? 'en',
  };
}

// Re-export helpers from constants for convenience
export { getAllASRProviders, getASRProvider, getASRSupportedLanguages } from './constants';
