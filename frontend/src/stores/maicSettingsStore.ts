// stores/maicSettingsStore.ts — User preferences for AI Classroom player

import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { MAICSlideTransition } from '../types/maic';
import type {
  TTSProviderId,
  ASRProviderId,
  TTSProviderSettings,
  ASRProviderSettings,
} from '../lib/audio/types';

interface MAICSettingsState {
  audioVolume: number;
  autoPlay: boolean;
  fontSize: 'small' | 'medium' | 'large';
  showChatPanel: boolean;
  showWhiteboard: boolean;
  playbackSpeed: number;
  browserTTSEnabled: boolean;
  slideTransition: MAICSlideTransition;

  // TTS provider settings
  ttsProviderId: TTSProviderId;
  ttsVoice: string;
  ttsSpeed: number;
  ttsModelId: string;
  ttsProvidersConfig: Record<string, TTSProviderSettings>;

  // ASR provider settings
  asrProviderId: ASRProviderId;
  asrLanguage: string;
  asrProvidersConfig: Record<string, ASRProviderSettings>;

  // Setters — general
  setAudioVolume: (volume: number) => void;
  setAutoPlay: (auto: boolean) => void;
  setFontSize: (size: 'small' | 'medium' | 'large') => void;
  setShowChatPanel: (show: boolean) => void;
  setShowWhiteboard: (show: boolean) => void;
  setPlaybackSpeed: (speed: number) => void;
  setBrowserTTSEnabled: (enabled: boolean) => void;
  setSlideTransition: (transition: MAICSlideTransition) => void;

  // Setters — TTS
  setTTSProviderId: (id: TTSProviderId) => void;
  setTTSVoice: (voice: string) => void;
  setTTSSpeed: (speed: number) => void;
  setTTSModelId: (modelId: string) => void;
  setTTSProvidersConfig: (config: Record<string, TTSProviderSettings>) => void;

  // Setters — ASR
  setASRProviderId: (id: ASRProviderId) => void;
  setASRLanguage: (language: string) => void;
  setASRProvidersConfig: (config: Record<string, ASRProviderSettings>) => void;
}

export const useMAICSettingsStore = create<MAICSettingsState>()(
  persist(
    (set) => ({
      audioVolume: 0.8,
      autoPlay: true,
      fontSize: 'medium',
      showChatPanel: true,
      showWhiteboard: false,
      playbackSpeed: 1,
      browserTTSEnabled: true,
      slideTransition: 'fade',

      // TTS defaults — browser-native works without API keys
      ttsProviderId: 'browser-native-tts' as TTSProviderId,
      ttsVoice: 'default',
      ttsSpeed: 1.0,
      ttsModelId: '',
      ttsProvidersConfig: {},

      // ASR defaults — browser-native works without API keys
      asrProviderId: 'browser-native' as ASRProviderId,
      asrLanguage: 'en',
      asrProvidersConfig: {},

      // Setters — general
      setAudioVolume: (volume) => set({ audioVolume: Math.max(0, Math.min(1, volume)) }),
      setAutoPlay: (auto) => set({ autoPlay: auto }),
      setFontSize: (size) => set({ fontSize: size }),
      setShowChatPanel: (show) => set({ showChatPanel: show }),
      setShowWhiteboard: (show) => set({ showWhiteboard: show }),
      setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),
      setBrowserTTSEnabled: (enabled) => set({ browserTTSEnabled: enabled }),
      setSlideTransition: (transition) => set({ slideTransition: transition }),

      // Setters — TTS
      setTTSProviderId: (id) => set({ ttsProviderId: id }),
      setTTSVoice: (voice) => set({ ttsVoice: voice }),
      setTTSSpeed: (speed) => set({ ttsSpeed: speed }),
      setTTSModelId: (modelId) => set({ ttsModelId: modelId }),
      setTTSProvidersConfig: (config) => set({ ttsProvidersConfig: config }),

      // Setters — ASR
      setASRProviderId: (id) => set({ asrProviderId: id }),
      setASRLanguage: (language) => set({ asrLanguage: language }),
      setASRProvidersConfig: (config) => set({ asrProvidersConfig: config }),
    }),
    {
      name: 'maic-settings',
    }
  )
);
