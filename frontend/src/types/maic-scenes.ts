// types/maic-scenes.ts — Scene type system for MAIC classroom playback

import type { MAICAction } from './maic-actions';
import type { MAICSlideElement } from './maic';

// ─── Multi-Slide Scene Types ───────────────────────────────────────────────────

/** Bounds mapping for a single scene within the flat slides array */
export interface SceneSlideBounds {
  sceneIdx: number;
  startSlide: number;
  endSlide: number;
}

/** Student notes attached to a specific slide within a scene */
export interface MAICNote {
  sceneIdx: number;
  slideIdx: number;
  text: string;
  timestamp: number;
}

// ─── Mode & State Enums ─────────────────────────────────────────────────────

export type MAICSceneType = 'slide' | 'quiz' | 'interactive' | 'pbl';
export type MAICStageMode = 'autonomous' | 'playback';
export type MAICEngineMode = 'idle' | 'playing' | 'paused' | 'live';
export type MAICDiscussionSessionType = 'qa' | 'roundtable' | 'classroom';

// ─── Scene ──────────────────────────────────────────────────────────────────

export interface MAICScene {
  id: string;
  type: MAICSceneType;
  title: string;
  order: number;
  content: MAICSceneContent;
  actions?: MAICAction[];
  multiAgent?: {
    enabled: boolean;
    agentIds: string[];
    directorPrompt?: string;
  };
}

// ─── Scene Content Variants ─────────────────────────────────────────────────

export type MAICSceneContent =
  | MAICSlideContent
  | MAICQuizContent
  | MAICInteractiveContent
  | MAICPBLContent;

export interface MAICSlideContent {
  type: 'slide';
  elements: MAICSlideElement[];
  background?: string;
  speakerScript?: string;
  audioUrl?: string;
  /** Index of this slide within its parent scene (0-based). Used for multi-slide scenes. */
  slideIndex?: number;
}

export interface MAICQuizContent {
  type: 'quiz';
  questions: MAICQuizQuestion[];
}

export interface MAICQuizQuestion {
  id: string;
  type: 'single' | 'multiple' | 'short_answer';
  question: string;
  options?: { label: string; value: string }[];
  answer?: string[];
  analysis?: string;
  commentPrompt?: string;
  points?: number;
}

export interface MAICInteractiveContent {
  type: 'interactive';
  html: string;
  url?: string;
}

export interface MAICPBLContent {
  type: 'pbl';
  projectTitle: string;
  description: string;
  roles: { id: string; name: string; description: string }[];
  milestones: { id: string; title: string; description: string; order: number }[];
  deliverables: string[];
}
