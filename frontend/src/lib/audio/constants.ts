/**
 * Audio Provider Constants
 *
 * Registry of all TTS and ASR providers with their metadata.
 * This file is client-safe and can be imported anywhere.
 *
 * Adapted from OpenMAIC upstream for LearnPuddle LMS.
 * Focused on English-language providers relevant to education.
 *
 * To add a new provider:
 * 1. Add the provider ID to TTSProviderId or ASRProviderId in types.ts
 * 2. Add provider configuration to TTS_PROVIDERS or ASR_PROVIDERS below
 * 3. Implement provider logic in tts-providers.ts or asr-providers.ts
 */

import type {
  BuiltInTTSProviderId,
  TTSProviderId,
  TTSProviderConfig,
  TTSVoiceInfo,
  BuiltInASRProviderId,
  ASRProviderId,
  ASRProviderConfig,
} from './types';

// ============================================================================
// TTS Provider Registry
// ============================================================================

/**
 * TTS Provider Registry
 *
 * Central registry for all TTS providers.
 * Keep in sync with TTSProviderId type definition.
 */
export const TTS_PROVIDERS: Record<BuiltInTTSProviderId, TTSProviderConfig> = {
  'openai-tts': {
    id: 'openai-tts',
    name: 'OpenAI TTS',
    requiresApiKey: true,
    defaultBaseUrl: 'https://api.openai.com/v1',
    icon: '/logos/openai.svg',
    models: [
      { id: 'gpt-4o-mini-tts', name: 'GPT-4o Mini TTS' },
      { id: 'tts-1', name: 'TTS-1' },
      { id: 'tts-1-hd', name: 'TTS-1 HD' },
    ],
    defaultModelId: 'gpt-4o-mini-tts',
    voices: [
      {
        id: 'alloy',
        name: 'Alloy',
        language: 'en',
        gender: 'neutral',
        description: 'Balanced and versatile voice',
      },
      {
        id: 'echo',
        name: 'Echo',
        language: 'en',
        gender: 'male',
        description: 'Clear and direct male voice',
      },
      {
        id: 'fable',
        name: 'Fable',
        language: 'en',
        gender: 'neutral',
        description: 'Warm British accent, great for storytelling',
      },
      {
        id: 'onyx',
        name: 'Onyx',
        language: 'en',
        gender: 'male',
        description: 'Deep and authoritative male voice',
      },
      {
        id: 'nova',
        name: 'Nova',
        language: 'en',
        gender: 'female',
        description: 'Friendly and expressive female voice',
      },
      {
        id: 'shimmer',
        name: 'Shimmer',
        language: 'en',
        gender: 'female',
        description: 'Soft and pleasant female voice',
      },
    ],
    supportedFormats: ['mp3', 'opus', 'aac', 'flac'],
    speedRange: { min: 0.25, max: 4.0, default: 1.0 },
  },

  'azure-tts': {
    id: 'azure-tts',
    name: 'Azure TTS',
    requiresApiKey: true,
    defaultBaseUrl: 'https://{region}.tts.speech.microsoft.com',
    icon: '/logos/azure.svg',
    models: [],
    defaultModelId: '',
    voices: [
      {
        id: 'en-US-GuyNeural',
        name: 'Guy',
        language: 'en-US',
        gender: 'male',
        description: 'Professional male voice',
      },
      {
        id: 'en-US-JennyNeural',
        name: 'Jenny',
        language: 'en-US',
        gender: 'female',
        description: 'Friendly conversational female voice',
      },
      {
        id: 'en-US-AriaNeural',
        name: 'Aria',
        language: 'en-US',
        gender: 'female',
        description: 'Expressive and clear female voice',
      },
      {
        id: 'en-US-DavisNeural',
        name: 'Davis',
        language: 'en-US',
        gender: 'male',
        description: 'Calm and authoritative male voice',
      },
      {
        id: 'en-US-SaraNeural',
        name: 'Sara',
        language: 'en-US',
        gender: 'female',
        description: 'Young and enthusiastic female voice',
      },
    ],
    supportedFormats: ['mp3', 'wav', 'ogg'],
    speedRange: { min: 0.5, max: 2.0, default: 1.0 },
  },

  'elevenlabs-tts': {
    id: 'elevenlabs-tts',
    name: 'ElevenLabs TTS',
    requiresApiKey: true,
    defaultBaseUrl: 'https://api.elevenlabs.io/v1',
    icon: '/logos/elevenlabs.svg',
    models: [
      { id: 'eleven_multilingual_v2', name: 'Multilingual v2' },
      { id: 'eleven_turbo_v2_5', name: 'Turbo v2.5' },
    ],
    defaultModelId: 'eleven_multilingual_v2',
    voices: [
      {
        id: 'EXAVITQu4vr4xnSDxMaL',
        name: 'Rachel',
        language: 'en-US',
        gender: 'female',
        description: 'Calm and confident female voice',
      },
      {
        id: 'AZnzlk1XvdvUeBnXmlld',
        name: 'Domi',
        language: 'en-US',
        gender: 'female',
        description: 'Strong and assertive female voice',
      },
      {
        id: 'jBpfuIE2acCO8z3wKNLl',
        name: 'Bella',
        language: 'en-US',
        gender: 'female',
        description: 'Soft and warm female voice',
      },
      {
        id: 'ErXwobaYiN019PkySvjV',
        name: 'Antoni',
        language: 'en-US',
        gender: 'male',
        description: 'Well-rounded and informative male voice',
      },
      {
        id: 'MF3mGyEYCl7XYWbV9V6O',
        name: 'Elli',
        language: 'en-US',
        gender: 'female',
        description: 'Young and emotional female voice',
      },
      {
        id: 'TxGEqnHWrfWFTfGW9XjX',
        name: 'Josh',
        language: 'en-US',
        gender: 'male',
        description: 'Deep and engaging male voice',
      },
      {
        id: 'VR6AewLTigWG4xSOukaG',
        name: 'Arnold',
        language: 'en-US',
        gender: 'male',
        description: 'Crisp and authoritative male voice',
      },
      {
        id: 'pNInz6obpgDQGcFmaJgB',
        name: 'Adam',
        language: 'en-US',
        gender: 'male',
        description: 'Deep and professional male voice',
      },
      {
        id: 'yoZ06aMxZJJ28mfd3POQ',
        name: 'Sam',
        language: 'en-US',
        gender: 'male',
        description: 'Raspy and dynamic male voice',
      },
    ],
    supportedFormats: ['mp3', 'opus', 'pcm', 'wav', 'ulaw', 'alaw'],
    speedRange: { min: 0.7, max: 1.2, default: 1.0 },
  },

  'browser-native-tts': {
    id: 'browser-native-tts',
    name: 'Browser Native (Web Speech API)',
    requiresApiKey: false,
    icon: '/logos/browser.svg',
    models: [],
    defaultModelId: '',
    voices: [
      // Actual voices are determined by the browser and OS at runtime.
      // These are placeholders; real voices are fetched via speechSynthesis.getVoices().
      { id: 'default', name: 'Default', language: 'en-US', gender: 'neutral' },
    ],
    supportedFormats: ['browser'],
    speedRange: { min: 0.1, max: 10.0, default: 1.0 },
  },
};

// ============================================================================
// ASR Provider Registry
// ============================================================================

/**
 * ASR Provider Registry
 *
 * Central registry for all ASR providers.
 * Keep in sync with ASRProviderId type definition.
 */
export const ASR_PROVIDERS: Record<BuiltInASRProviderId, ASRProviderConfig> = {
  'openai-whisper': {
    id: 'openai-whisper',
    name: 'OpenAI Whisper',
    requiresApiKey: true,
    defaultBaseUrl: 'https://api.openai.com/v1',
    icon: '/logos/openai.svg',
    models: [
      { id: 'whisper-1', name: 'Whisper-1' },
      { id: 'gpt-4o-mini-transcribe', name: 'GPT-4o Mini Transcribe' },
    ],
    defaultModelId: 'whisper-1',
    supportedLanguages: [
      'auto',
      'en',
      'es',
      'fr',
      'de',
      'it',
      'pt',
      'ru',
      'ja',
      'ko',
      'zh',
      'ar',
      'hi',
      'nl',
      'pl',
      'sv',
      'tr',
      'da',
      'fi',
      'no',
      'cs',
      'el',
      'hu',
      'ro',
      'uk',
    ],
    supportedFormats: ['mp3', 'mp4', 'mpeg', 'mpga', 'm4a', 'wav', 'webm'],
  },

  'browser-native': {
    id: 'browser-native',
    name: 'Browser Native ASR (Web Speech API)',
    requiresApiKey: false,
    icon: '/logos/browser.svg',
    models: [],
    defaultModelId: '',
    supportedLanguages: [
      'en-US',
      'en-GB',
      'en-AU',
      'en-CA',
      'en-IN',
      'es-ES',
      'es-MX',
      'fr-FR',
      'de-DE',
      'it-IT',
      'pt-BR',
      'pt-PT',
      'ja-JP',
      'ko-KR',
      'zh-CN',
      'zh-TW',
      'ru-RU',
      'ar-SA',
      'hi-IN',
      'nl-NL',
      'pl-PL',
      'sv-SE',
      'tr-TR',
    ],
    supportedFormats: ['webm'],
  },
};

// ============================================================================
// Defaults
// ============================================================================

/** Default voice for each TTS provider. */
export const DEFAULT_TTS_VOICES: Record<BuiltInTTSProviderId, string> = {
  'openai-tts': 'alloy',
  'azure-tts': 'en-US-GuyNeural',
  'elevenlabs-tts': 'EXAVITQu4vr4xnSDxMaL',
  'browser-native-tts': 'default',
};

/** Default model for each TTS provider. */
export const DEFAULT_TTS_MODELS: Record<BuiltInTTSProviderId, string> = {
  'openai-tts': 'gpt-4o-mini-tts',
  'azure-tts': '',
  'elevenlabs-tts': 'eleven_multilingual_v2',
  'browser-native-tts': '',
};

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Get all available TTS providers (built-in + optional custom).
 */
export function getAllTTSProviders(
  customProviders?: Record<string, TTSProviderConfig>,
): TTSProviderConfig[] {
  const builtIn = Object.values(TTS_PROVIDERS);
  const custom = customProviders ? Object.values(customProviders) : [];
  return [...builtIn, ...custom];
}

/**
 * Get TTS provider by ID (checks built-in first, then custom).
 */
export function getTTSProvider(
  providerId: TTSProviderId,
  customProviders?: Record<string, TTSProviderConfig>,
): TTSProviderConfig | undefined {
  if (providerId in TTS_PROVIDERS) {
    return TTS_PROVIDERS[providerId as BuiltInTTSProviderId];
  }
  return customProviders?.[providerId];
}

/**
 * Get voices for a specific TTS provider.
 */
export function getTTSVoices(
  providerId: TTSProviderId,
  customProviders?: Record<string, TTSProviderConfig>,
): TTSVoiceInfo[] {
  return getTTSProvider(providerId, customProviders)?.voices || [];
}

/**
 * Get all available ASR providers (built-in + optional custom).
 */
export function getAllASRProviders(
  customProviders?: Record<string, ASRProviderConfig>,
): ASRProviderConfig[] {
  const builtIn = Object.values(ASR_PROVIDERS);
  const custom = customProviders ? Object.values(customProviders) : [];
  return [...builtIn, ...custom];
}

/**
 * Get ASR provider by ID (checks built-in first, then custom).
 */
export function getASRProvider(
  providerId: ASRProviderId,
  customProviders?: Record<string, ASRProviderConfig>,
): ASRProviderConfig | undefined {
  if (providerId in ASR_PROVIDERS) {
    return ASR_PROVIDERS[providerId as BuiltInASRProviderId];
  }
  return customProviders?.[providerId];
}

/**
 * Get supported languages for a specific ASR provider.
 */
export function getASRSupportedLanguages(
  providerId: ASRProviderId,
  customProviders?: Record<string, ASRProviderConfig>,
): string[] {
  return getASRProvider(providerId, customProviders)?.supportedLanguages || [];
}
