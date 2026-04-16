/**
 * Audio Provider Type Definitions
 *
 * Unified types for TTS (Text-to-Speech) and ASR (Automatic Speech Recognition)
 * with extensible architecture to support multiple providers.
 *
 * Adapted from OpenMAIC upstream for LearnPuddle LMS.
 * Focused on English-language providers relevant to an LMS context.
 *
 * Supported TTS Providers:
 * - OpenAI TTS (https://platform.openai.com/docs/guides/text-to-speech)
 * - Azure TTS (https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech)
 * - ElevenLabs TTS (https://elevenlabs.io/docs/api-reference/text-to-speech/convert)
 * - Browser Native TTS (Web Speech API, client-side only)
 *
 * Supported ASR Providers:
 * - OpenAI Whisper (https://platform.openai.com/docs/guides/speech-to-text)
 * - Browser Native (Web Speech API, client-side only)
 *
 * HOW TO ADD A NEW PROVIDER:
 *
 * Step 1: Add provider ID to the union type (TTSProviderId or ASRProviderId)
 * Step 2: Add provider configuration to constants.ts
 * Step 3: Implement provider logic in tts-providers.ts or asr-providers.ts
 * Step 4: Update maicSettingsStore defaults if needed
 */

// ============================================================================
// TTS (Text-to-Speech) Types
// ============================================================================

/**
 * Built-in TTS Provider IDs.
 * Add new TTS providers here as union members.
 * Keep in sync with TTS_PROVIDERS registry in constants.ts.
 */
export type BuiltInTTSProviderId =
  | 'openai-tts'
  | 'azure-tts'
  | 'elevenlabs-tts'
  | 'browser-native-tts';

/** Provider ID type that supports custom providers. */
export type TTSProviderId = BuiltInTTSProviderId | `custom-tts-${string}`;

/**
 * Voice information for TTS
 */
export interface TTSVoiceInfo {
  id: string;
  name: string;
  language: string;
  localeName?: string;
  gender?: 'male' | 'female' | 'neutral';
  description?: string;
  /** Model IDs this voice is compatible with. Undefined = all models. */
  compatibleModels?: string[];
}

/**
 * TTS Provider Configuration
 */
export interface TTSProviderConfig {
  id: TTSProviderId;
  name: string;
  requiresApiKey: boolean;
  defaultBaseUrl?: string;
  icon?: string;
  /** Available models. Empty array means provider has no model concept (e.g. Azure, Browser Native). */
  models: Array<{ id: string; name: string }>;
  /** Default model ID used when user hasn't selected one. Empty string if no models. */
  defaultModelId: string;
  voices: TTSVoiceInfo[];
  supportedFormats: string[];
  speedRange?: {
    min: number;
    max: number;
    default: number;
  };
}

/**
 * TTS Model Configuration for API calls
 */
export interface TTSModelConfig {
  providerId: TTSProviderId;
  modelId?: string;
  apiKey?: string;
  baseUrl?: string;
  voice: string;
  speed?: number;
  format?: string;
  providerOptions?: Record<string, unknown>;
}

// ============================================================================
// ASR (Automatic Speech Recognition) Types
// ============================================================================

/**
 * Built-in ASR Provider IDs.
 * Add new ASR providers here as union members.
 * Keep in sync with ASR_PROVIDERS registry in constants.ts.
 */
export type BuiltInASRProviderId = 'openai-whisper' | 'browser-native';

/** Provider ID type that supports custom providers. */
export type ASRProviderId = BuiltInASRProviderId | `custom-asr-${string}`;

/**
 * ASR Provider Configuration
 */
export interface ASRProviderConfig {
  id: ASRProviderId;
  name: string;
  requiresApiKey: boolean;
  defaultBaseUrl?: string;
  icon?: string;
  models: Array<{ id: string; name: string }>;
  defaultModelId: string;
  supportedLanguages: string[];
  supportedFormats: string[];
}

/**
 * ASR Model Configuration for API calls
 */
export interface ASRModelConfig {
  providerId: ASRProviderId;
  modelId?: string;
  apiKey?: string;
  baseUrl?: string;
  language?: string;
}

// ============================================================================
// TTS Provider Settings (stored per-provider in maicSettingsStore)
// ============================================================================

/** Per-provider settings stored in the settings store. */
export interface TTSProviderSettings {
  apiKey?: string;
  baseUrl?: string;
  modelId?: string;
  enabled?: boolean;
  isServerConfigured?: boolean;
  customName?: string;
  customVoices?: Array<{ id: string; name: string }>;
}

/** Per-provider settings for ASR stored in the settings store. */
export interface ASRProviderSettings {
  apiKey?: string;
  baseUrl?: string;
  modelId?: string;
}

// ============================================================================
// Helpers
// ============================================================================

/** Returns true if the provider ID is a user-defined custom TTS provider. */
export function isCustomTTSProvider(id: string): boolean {
  return id.startsWith('custom-tts-');
}

/** Returns true if the provider ID is a user-defined custom ASR provider. */
export function isCustomASRProvider(id: string): boolean {
  return id.startsWith('custom-asr-');
}
