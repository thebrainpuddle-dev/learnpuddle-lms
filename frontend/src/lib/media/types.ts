/**
 * Media generation API types — TS mirror of backend Pydantic types.
 *
 * Source: backend/apps/maic/media/types.py (Phase 9 MAIC-901).
 *         Keep this file in lockstep with the Pydantic models —
 *         every shape here is a 1:1 mirror with the same field
 *         names, types, and bounds.
 *
 * Used by:
 *   - frontend/src/lib/media/api.ts (typed API client)
 *   - frontend/src/hooks/useGenerateImage.ts + useGenerateVideo.ts
 *   - frontend/src/components/maic/VideoPlayer.tsx
 */

export type ImageProviderId =
  | 'openai'
  | 'qwen'
  | 'grok'
  | 'minimax'
  | 'nano_banana'
  | 'seedream'
  | 'stability'
  | 'disabled';

export type VideoProviderId =
  | 'veo'
  | 'kling'
  | 'minimax_video'
  | 'seedance'
  | 'grok_video'
  | 'disabled';

export type ImageQuality = 'standard' | 'high';
export type VideoAspectRatio = '16:9' | '9:16' | '1:1';

export interface ImageGenerationRequest {
  prompt: string;
  width?: number;
  height?: number;
  quality?: ImageQuality;
  seed?: number | null;
  scene_id?: string | null;
}

export interface ImageGenerationResult {
  media_id: string;
  url: string;
  provider: ImageProviderId;
  model: string;
  latency_ms: number;
  cost_usd_estimate: number | null;
}

export interface VideoGenerationRequest {
  prompt: string;
  duration_seconds?: number;
  aspect_ratio?: VideoAspectRatio;
  seed?: number | null;
  scene_id?: string | null;
}

export interface VideoGenerationResult {
  media_id: string;
  url: string;
  provider: VideoProviderId;
  model: string;
  duration_seconds: number;
  latency_ms: number;
  cost_usd_estimate: number | null;
}
