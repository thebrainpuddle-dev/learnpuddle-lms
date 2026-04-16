/**
 * Type definitions for the generation pipeline.
 * Adapted from upstream OpenMAIC pipeline-types.ts for client-side use.
 */

// ==================== Agent Info ====================

/** Lightweight agent info passed to the generation pipeline */
export interface AgentInfo {
  id: string;
  name: string;
  role: string;
  persona?: string;
}

// ==================== Cross-Page Context ====================

/** Cross-page context for maintaining speech coherence across scenes */
export interface SceneGenerationContext {
  pageIndex: number; // Current page (1-based)
  totalPages: number; // Total number of pages
  allTitles: string[]; // All page titles in order
  previousSpeeches: string[]; // Speech texts from the previous page only
}

// ==================== Generated Slide Data Interface ====================

/**
 * AI-generated slide data structure.
 * Used to parse AI responses into typed slide content.
 */
export interface GeneratedSlideData {
  elements: Array<{
    type: 'text' | 'image' | 'video' | 'shape' | 'chart' | 'latex' | 'line';
    left: number;
    top: number;
    width: number;
    height: number;
    [key: string]: unknown;
  }>;
  background?: {
    type: 'solid' | 'gradient';
    color?: string;
    gradient?: {
      type: 'linear' | 'radial';
      colors: Array<{ pos: number; color: string }>;
      rotate: number;
    };
  };
  remark?: string;
}

// ==================== Result & Callback Types ====================

export interface GenerationResult<T> {
  success: boolean;
  data?: T;
  error?: string;
}

export interface GenerationCallbacks {
  onProgress?: (progress: GenerationProgress) => void;
  onStageComplete?: (stage: number, result: unknown) => void;
  onError?: (error: string) => void;
}

export interface GenerationProgress {
  stage: string;
  current: number;
  total: number;
  message: string;
}

export type AICallFn = (
  systemPrompt: string,
  userPrompt: string,
  images?: Array<{ id: string; src: string }>,
) => Promise<string>;
