// stores/maicStageStore.ts — Stage state: slides, playback, active agents, engine

import { create } from 'zustand';
import type { MAICSlide, MAICAgent, MAICViewMode, MAICChatMessage } from '../types/maic';
import type { MAICScene, MAICEngineMode, MAICDiscussionSessionType, SceneSlideBounds, MAICNote } from '../types/maic-scenes';

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

  // Multi-slide scene bounds (maps scene index to slide range in flat slides[])
  sceneSlideBounds: SceneSlideBounds[];
  setSceneSlideBounds: (bounds: SceneSlideBounds[]) => void;
  /** Returns only the slides belonging to the current scene */
  getCurrentSceneSlides: () => MAICSlide[];

  // Notes
  notes: MAICNote[];
  showNotesPanel: boolean;
  addNote: (note: MAICNote) => void;
  toggleNotesPanel: () => void;

  // Speech state
  speechText: string | null;
  setSpeechText: (text: string | null) => void;
  /** True while the engine is waiting on a TTS fetch for the next
   *  speaker. Used by PresentationSpeechOverlay to show thinking dots
   *  during the silent window before audio starts. (Sprint 1 · B.3) */
  speechFetchLoading: boolean;
  setSpeechFetchLoading: (loading: boolean) => void;
  /** True while audio is actively playing (or reading-timer running)
   *  for the current speech action. Separated from `speakingAgentId`
   *  so we can hold the bubble on the last spoken line between agents
   *  — matches OpenMAIC's "last sentence stays on screen" feel (T0.2).
   *  Drives VoiceWaveIndicator's animation. */
  isSpeaking: boolean;
  setIsSpeaking: (speaking: boolean) => void;

  // Discussion mode
  discussionMode: MAICDiscussionSessionType | null;
  setDiscussionMode: (mode: MAICDiscussionSessionType | null) => void;

  // Discussion pending — the engine has paused for a discussion but the
  // panel hasn't opened yet. Used for the "breath + Join/Skip countdown"
  // UX so discussions never pop the panel on screen mid-speech without
  // warning. The UI layer (DiscussionGateCard) owns the transition from
  // `discussionPending` → `discussionMode`.
  discussionPending: {
    topic: string;
    agentIds: string[];
    sessionType: MAICDiscussionSessionType;
    triggerAgentId?: string;
  } | null;
  setDiscussionPending: (
    pending: {
      topic: string;
      agentIds: string[];
      sessionType: MAICDiscussionSessionType;
      triggerAgentId?: string;
    } | null,
  ) => void;

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

  // Generation failure tracking — T4. `failedOutlineIds` lists outline
  // scene ids whose content/actions generation threw. The scene sidebar
  // reads this to paint a retry affordance on the matching tile, and
  // `retryScene` (in lib/maicGenerationRetry) clears the id on success.
  failedOutlineIds: string[];
  markOutlineFailed: (outlineId: string) => void;
  clearOutlineFailure: (outlineId: string) => void;
  /** Reset the failed set — called by the wizard's reset flow. */
  clearAllOutlineFailures: () => void;

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
  sceneSlideBounds: [] as SceneSlideBounds[],
  notes: [] as MAICNote[],
  showNotesPanel: false,
  speechText: null as string | null,
  speechFetchLoading: false,
  isSpeaking: false,
  discussionMode: null as MAICDiscussionSessionType | null,
  discussionPending: null as MAICStageState['discussionPending'],
  viewMode: 'slides' as MAICViewMode,
  isFullscreen: false,
  chatMessages: [] as MAICChatMessage[],
  classroomId: null as string | null,
  failedOutlineIds: [] as string[],
};

export const useMAICStageStore = create<MAICStageState>((set, get) => ({
  ...initialState,

  // Slides — multi-slide aware: derives scene index from sceneSlideBounds
  setSlides: (slides) => set({ slides }),
  goToSlide: (index) => {
    const { slides, sceneSlideBounds } = get();
    const max = slides.length - 1;
    if (max < 0) return;
    const clamped = Math.max(0, Math.min(index, max));
    const updates: Partial<MAICStageState> = { currentSlideIndex: clamped };
    // Derive scene index from bounds if available
    if (sceneSlideBounds.length > 0) {
      const sceneIdx = sceneSlideBounds.findIndex(
        (b) => clamped >= b.startSlide && clamped <= b.endSlide,
      );
      if (sceneIdx >= 0) {
        updates.currentSceneIndex = sceneIdx;
      }
    } else {
      // Legacy 1:1 fallback
      updates.currentSceneIndex = clamped;
    }
    set(updates);
  },
  nextSlide: () => {
    const { currentSlideIndex, slides } = get();
    const max = slides.length - 1;
    if (currentSlideIndex < max) {
      get().goToSlide(currentSlideIndex + 1);
    }
  },
  prevSlide: () => {
    const { currentSlideIndex } = get();
    if (currentSlideIndex > 0) {
      get().goToSlide(currentSlideIndex - 1);
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

  // Scenes — multi-slide aware: uses sceneSlideBounds to map to slide index
  setScenes: (scenes) => set({ scenes, currentSceneIndex: 0, currentSlideIndex: 0 }),
  goToScene: (index) => {
    const { scenes, sceneSlideBounds } = get();
    const max = scenes.length - 1;
    if (max < 0) return;
    const clamped = Math.max(0, Math.min(index, max));
    // Jump to the first slide of the target scene
    if (sceneSlideBounds.length > 0 && sceneSlideBounds[clamped]) {
      set({ currentSceneIndex: clamped, currentSlideIndex: sceneSlideBounds[clamped].startSlide });
    } else {
      // Legacy 1:1 fallback
      set({ currentSceneIndex: clamped, currentSlideIndex: clamped });
    }
  },
  nextScene: () => {
    const { currentSceneIndex, scenes } = get();
    if (currentSceneIndex < scenes.length - 1) {
      get().goToScene(currentSceneIndex + 1);
    }
  },

  // Multi-slide scene bounds
  setSceneSlideBounds: (bounds) => set({ sceneSlideBounds: bounds }),
  getCurrentSceneSlides: () => {
    const { slides, currentSceneIndex, sceneSlideBounds } = get();
    if (sceneSlideBounds.length > 0 && sceneSlideBounds[currentSceneIndex]) {
      const { startSlide, endSlide } = sceneSlideBounds[currentSceneIndex];
      return slides.slice(startSlide, endSlide + 1);
    }
    // Legacy 1:1 fallback — return the single slide at currentSceneIndex
    return slides[currentSceneIndex] ? [slides[currentSceneIndex]] : [];
  },

  // Notes
  addNote: (note) => set((s) => ({ notes: [...s.notes, note] })),
  toggleNotesPanel: () => set((s) => ({ showNotesPanel: !s.showNotesPanel })),

  // Speech
  setSpeechText: (text) => set({ speechText: text }),
  setSpeechFetchLoading: (loading) => set({ speechFetchLoading: loading }),
  setIsSpeaking: (speaking) => set({ isSpeaking: speaking }),

  // Discussion
  setDiscussionMode: (mode) => set({ discussionMode: mode }),
  setDiscussionPending: (pending) => set({ discussionPending: pending }),

  // View
  setViewMode: (mode) => set({ viewMode: mode }),
  setFullscreen: (fs) => set({ isFullscreen: fs }),

  // Chat
  addChatMessage: (msg) => set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  setChatMessages: (msgs) => set({ chatMessages: msgs }),

  // Classroom context
  setClassroomId: (id) => set({ classroomId: id }),

  // T4 — generation failure set
  markOutlineFailed: (outlineId) =>
    set((s) =>
      s.failedOutlineIds.includes(outlineId)
        ? s
        : { failedOutlineIds: [...s.failedOutlineIds, outlineId] },
    ),
  clearOutlineFailure: (outlineId) =>
    set((s) => ({ failedOutlineIds: s.failedOutlineIds.filter((id) => id !== outlineId) })),
  clearAllOutlineFailures: () => set({ failedOutlineIds: [] }),

  // Reset
  reset: () => set(initialState),
}));
