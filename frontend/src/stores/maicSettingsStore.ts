// stores/maicSettingsStore.ts — User preferences for AI Classroom player

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface MAICSettingsState {
  audioVolume: number;
  autoPlay: boolean;
  fontSize: 'small' | 'medium' | 'large';
  showChatPanel: boolean;
  showWhiteboard: boolean;
  playbackSpeed: number;

  setAudioVolume: (volume: number) => void;
  setAutoPlay: (auto: boolean) => void;
  setFontSize: (size: 'small' | 'medium' | 'large') => void;
  setShowChatPanel: (show: boolean) => void;
  setShowWhiteboard: (show: boolean) => void;
  setPlaybackSpeed: (speed: number) => void;
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

      setAudioVolume: (volume) => set({ audioVolume: Math.max(0, Math.min(1, volume)) }),
      setAutoPlay: (auto) => set({ autoPlay: auto }),
      setFontSize: (size) => set({ fontSize: size }),
      setShowChatPanel: (show) => set({ showChatPanel: show }),
      setShowWhiteboard: (show) => set({ showWhiteboard: show }),
      setPlaybackSpeed: (speed) => set({ playbackSpeed: speed }),
    }),
    {
      name: 'maic-settings',
    }
  )
);
