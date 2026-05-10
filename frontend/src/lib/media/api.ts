/**
 * Typed API client for media generation (Phase 9, MAIC-916).
 *
 * Source: backend/apps/maic/media/views.py (MAIC-914 endpoints).
 *
 * Used by:
 *   - frontend/src/hooks/useGenerateImage.ts
 *   - frontend/src/hooks/useGenerateVideo.ts
 *   - any direct-call surface (admin slide editor, dev probe regenerate
 *     button, etc.)
 *
 * Discipline: this file is a thin typed wrapper around the shared
 * axios instance at frontend/src/config/api.ts. No retries here —
 * the backend orchestrator already retries; surfacing a retry-storm
 * from the browser on top would multiply provider cost.
 */
import api from '../../config/api';
import type {
  ImageGenerationRequest,
  ImageGenerationResult,
  VideoGenerationRequest,
  VideoGenerationResult,
} from './types';

const IMAGE_ENDPOINT = '/api/maic/v2/media/generate-image/';
const VIDEO_ENDPOINT = '/api/maic/v2/media/generate-video/';

export async function generateImage(
  req: ImageGenerationRequest,
): Promise<ImageGenerationResult> {
  const res = await api.post<ImageGenerationResult>(IMAGE_ENDPOINT, req);
  return res.data;
}

export async function generateVideo(
  req: VideoGenerationRequest,
): Promise<VideoGenerationResult> {
  const res = await api.post<VideoGenerationResult>(VIDEO_ENDPOINT, req);
  return res.data;
}
