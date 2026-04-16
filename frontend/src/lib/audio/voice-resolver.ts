/**
 * Voice Resolver
 *
 * Resolves which TTS provider and voice to use for a given agent.
 * Adapted from OpenMAIC upstream for LearnPuddle LMS.
 */

import type { TTSProviderId, TTSProviderSettings } from './types';
import { isCustomTTSProvider } from './types';
import { TTS_PROVIDERS } from './constants';

/** Resolved voice configuration for an agent. */
export interface ResolvedVoice {
  providerId: TTSProviderId;
  modelId?: string;
  voiceId: string;
}

/** A provider that has voices available. */
export interface ProviderWithVoices {
  providerId: TTSProviderId;
  providerName: string;
  voices: Array<{ id: string; name: string; language?: string }>;
}

/** Agent config shape (minimal subset needed by the resolver). */
export interface AgentVoiceConfig {
  voiceConfig?: {
    providerId: TTSProviderId;
    modelId?: string;
    voiceId: string;
  };
}

/**
 * Resolve the TTS provider + voice for an agent.
 *
 * 1. If agent has voiceConfig and the voice is still valid, use it
 * 2. Otherwise, use the first available provider + deterministic voice by index
 * 3. Falls back to browser-native-tts if nothing else is available
 */
export function resolveAgentVoice(
  agent: AgentVoiceConfig,
  agentIndex: number,
  availableProviders: ProviderWithVoices[],
): ResolvedVoice {
  // Agent-specific config
  if (agent.voiceConfig) {
    // Browser-native voices are dynamic, skip validation
    if (agent.voiceConfig.providerId === 'browser-native-tts') {
      return {
        providerId: agent.voiceConfig.providerId,
        modelId: agent.voiceConfig.modelId,
        voiceId: agent.voiceConfig.voiceId,
      };
    }

    const list = getServerVoiceList(agent.voiceConfig.providerId);
    const fromAvailable = availableProviders
      .find((p) => p.providerId === agent.voiceConfig!.providerId)
      ?.voices.map((v) => v.id);
    const allVoiceIds = new Set([...list, ...(fromAvailable || [])]);

    if (allVoiceIds.has(agent.voiceConfig.voiceId)) {
      return {
        providerId: agent.voiceConfig.providerId,
        modelId: agent.voiceConfig.modelId,
        voiceId: agent.voiceConfig.voiceId,
      };
    }
  }

  // Fallback: first available provider, deterministic voice by index
  if (availableProviders.length > 0) {
    const first = availableProviders[0];
    return {
      providerId: first.providerId,
      voiceId: first.voices[agentIndex % first.voices.length].id,
    };
  }

  // Last resort: browser-native
  return { providerId: 'browser-native-tts', voiceId: 'default' };
}

/**
 * Get the list of voice IDs for a TTS provider.
 * For browser-native-tts, returns empty (browser voices are dynamic).
 * For custom providers, reads from ttsProvidersConfig.customVoices.
 */
export function getServerVoiceList(
  providerId: TTSProviderId,
  ttsProvidersConfig?: Record<string, TTSProviderSettings>,
): string[] {
  if (providerId === 'browser-native-tts') return [];

  if (isCustomTTSProvider(providerId) && ttsProvidersConfig) {
    const customVoices = ttsProvidersConfig[providerId]?.customVoices;
    return customVoices?.map((v) => v.id) || [];
  }

  const provider = TTS_PROVIDERS[providerId as keyof typeof TTS_PROVIDERS];
  if (!provider) return [];
  return provider.voices.map((v) => v.id);
}

/**
 * Get all available providers and their voices for the voice picker UI.
 * A provider is available if it has an API key or is server-configured.
 * Browser-native-tts is excluded (no static voice list).
 */
export function getAvailableProvidersWithVoices(
  ttsProvidersConfig: Record<string, TTSProviderSettings>,
): ProviderWithVoices[] {
  const result: ProviderWithVoices[] = [];

  // Built-in providers
  for (const [id, config] of Object.entries(TTS_PROVIDERS)) {
    const providerId = id as TTSProviderId;
    if (providerId === 'browser-native-tts') continue;
    if (config.voices.length === 0) continue;

    const providerConfig = ttsProvidersConfig[providerId];
    const hasApiKey = providerConfig?.apiKey && providerConfig.apiKey.trim().length > 0;
    const isServerConfigured = providerConfig?.isServerConfigured === true;

    if (hasApiKey || isServerConfigured) {
      const voices = config.voices.map((v) => ({
        id: v.id,
        name: v.name,
        language: v.language,
      }));

      result.push({
        providerId,
        providerName: config.name,
        voices,
      });
    }
  }

  // Custom providers
  for (const [id, providerConfig] of Object.entries(ttsProvidersConfig)) {
    if (!isCustomTTSProvider(id)) continue;
    const customVoices = providerConfig.customVoices || [];
    if (customVoices.length === 0) continue;

    const providerId = id as TTSProviderId;
    const providerName = providerConfig.customName || id;
    const voices = customVoices.map((v) => ({ id: v.id, name: v.name }));

    result.push({ providerId, providerName, voices });
  }

  return result;
}

/**
 * Find a voice display name across all providers.
 */
export function findVoiceDisplayName(
  providerId: TTSProviderId,
  voiceId: string,
  ttsProvidersConfig?: Record<string, TTSProviderSettings>,
): string {
  if (isCustomTTSProvider(providerId) && ttsProvidersConfig) {
    const customVoices = ttsProvidersConfig[providerId]?.customVoices;
    const voice = customVoices?.find((v) => v.id === voiceId);
    return voice?.name ?? voiceId;
  }

  const provider = TTS_PROVIDERS[providerId as keyof typeof TTS_PROVIDERS];
  if (!provider) return voiceId;
  const voice = provider.voices.find((v) => v.id === voiceId);
  return voice?.name ?? voiceId;
}
