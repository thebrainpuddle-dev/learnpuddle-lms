// stores/maicStageStore.ts — Stage state: slides, playback, active agents, engine

import { create } from 'zustand';
import type { MAICSlide, MAICAgent, MAICViewMode, MAICChatMessage } from '../types/maic';
import type { MAICScene, MAICEngineMode, MAICDiscussionSessionType } from '../types/maic-scenes';

interface MAICStageState {
  // Slides
  slides: MAICSlide[];
  currentSlideIndex: number;
  setSlides: (slides: MAICSlide[]) => void;
  goToSlide: (index: number) => void;
  nextSlide: () => void;
  prevSlide: () => void;

  // Agents
  agents: MAICAgent[];
  speakingAgentId: string | null;
  setAgents: (agents: MAICAgent[]) => void;
  setSpeakingAgent: (agentId: string | null) => void;

  // Playback
  isPlaying: boolean;
  setPlaying: (playing: boolean) => void;

  // Engine mode (idle / playing / paused / live)
  engineMode: MAICEngineMode;
  setEngineMode: (mode: MAICEngineMode) => void;

  // Visual effects
  spotlightElementId: string | null;
  setSpotlightElementId: (id: string | null) => void;
  laserElementId: string | null;
  laserColor: string | null;
  setLaser: (elementId: string | null, color?: string) => void;

  // Scenes (typed scene array with actions)
  scenes: MAICScene[];
  currentSceneIndex: number;
  setScenes: (scenes: MAICScene[]) => void;
  goToScene: (index: number) => void;
  nextScene: () => void;

  // Speech state
  speechText: string | null;
  setSpeechText: (text: string | null) => void;

  // Discussion mode
  discussionMode: MAICDiscussionSessionType | null;
  setDiscussionMode: (mode: MAICDiscussionSessionType | null) => void;

  // View
  viewMode: MAICViewMode;
  setViewMode: (mode: MAICViewMode) => void;
  isFullscreen: boolean;
  setFullscreen: (fs: boolean) => void;

  // Chat
  chatMessages: MAICChatMessage[];
  addChatMessage: (msg: MAICChatMessage) => void;
  setChatMessages: (msgs: MAICChatMessage[]) => void;

  // Classroom context
  classroomId: string | null;
  setClassroomId: (id: string | null) => void;

  // Reset
  reset: () => void;
}

const initialState = {
  slides: [] as MAICSlide[],
  currentSlideIndex: 0,
  agents: [] as MAICAgent[],
  speakingAgentId: null as string | null,
  isPlaying: false,
  engineMode: 'idle' as MAICEngineMode,
  spotlightElementId: null as string | null,
  laserElementId: null as string | null,
  laserColor: null as string | null,
  scenes: [] as MAICScene[],
  currentSceneIndex: 0,
  speechText: null as string | null,
  discussionMode: null as MAICDiscussionSessionType | null,
  viewMode: 'slides' as MAICViewMode,
  isFullscreen: false,
  chatMessages: [] as MAICChatMessage[],
  classroomId: null as string | null,
};

export const useMAICStageStore = create<MAICStageState>((set, get) => ({
  ...initialState,

  // Slides (synced with scenes — slide N ↔ scene N)
  setSlides: (slides) => set({ slides }),
  goToSlide: (index) => {
    const { slides, scenes } = get();
    const max = Math.max(slides.length, scenes.length) - 1;
    if (max < 0) return;
    const clamped = Math.max(0, Math.min(index, max));
    set({ currentSlideIndex: clamped, currentSceneIndex: clamped });
  },
  nextSlide: () => {
    const { currentSlideIndex, slides, scenes } = get();
    const max = Math.max(slides.length, scenes.length) - 1;
    if (currentSlideIndex < max) {
      set({ currentSlideIndex: currentSlideIndex + 1, currentSceneIndex: currentSlideIndex + 1 });
    }
  },
  prevSlide: () => {
    const { currentSlideIndex } = get();
    if (currentSlideIndex > 0) {
      set({ currentSlideIndex: currentSlideIndex - 1, currentSceneIndex: currentSlideIndex - 1 });
    }
  },

  // Agents
  setAgents: (agents) => set({ agents }),
  setSpeakingAgent: (agentId) => set({ speakingAgentId: agentId }),

  // Playback
  setPlaying: (playing) => set({ isPlaying: playing }),

  // Engine mode
  setEngineMode: (mode) => set({ engineMode: mode }),

  // Visual effects
  setSpotlightElementId: (id) => set({ spotlightElementId: id }),
  setLaser: (elementId, color) =>
    set({
      laserElementId: elementId,
      laserColor: elementId ? (color ?? '#EF4444') : null,
    }),

  // Scenes (synced with slides — scene N ↔ slide N)
  setScenes: (scenes) => set({ scenes, currentSceneIndex: 0, currentSlideIndex: 0 }),
  goToScene: (index) => {
    const max = get().scenes.length - 1;
    if (max < 0) return;
    const clamped = Math.max(0, Math.min(index, max));
    set({ currentSceneIndex: clamped, currentSlideIndex: clamped });
  },
  nextScene: () => {
    const { currentSceneIndex, scenes } = get();
    if (currentSceneIndex < scenes.length - 1) {
      set({ currentSceneIndex: currentSceneIndex + 1, currentSlideIndex: currentSceneIndex + 1 });
    }
  },

  // Speech
  setSpeechText: (text) => set({ speechText: text }),

  // Discussion
  setDiscussionMode: (mode) => set({ discussionMode: mode }),

  // View
  setViewMode: (mode) => set({ viewMode: mode }),
  setFullscreen: (fs) => set({ isFullscreen: fs }),

  // Chat
  addChatMessage: (msg) => set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  setChatMessages: (msgs) => set({ chatMessages: msgs }),

  // Classroom context
  setClassroomId: (id) => set({ classroomId: id }),

  // Reset
  reset: () => set(initialState),
}));
