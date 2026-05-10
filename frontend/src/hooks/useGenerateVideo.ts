/**
 * React Query mutation hook for video generation (Phase 9, MAIC-916).
 *
 * Same shape as useGenerateImage but for video. Per-attempt latency
 * is much higher (Veo/Kling can take 30-300 seconds); callers should
 * keep the UI patient and surface latency_ms back to the user.
 *
 * Source: frontend/src/lib/media/api.ts:generateVideo.
 *
 * Used by:
 *   - admin video-element editors
 *   - dev probe regenerate buttons
 */
import { useMutation, type UseMutationOptions } from '@tanstack/react-query';

import { generateVideo } from '../lib/media/api';
import type {
  VideoGenerationRequest,
  VideoGenerationResult,
} from '../lib/media/types';

type Options = Omit<
  UseMutationOptions<VideoGenerationResult, Error, VideoGenerationRequest>,
  'mutationFn'
>;

export function useGenerateVideo(options?: Options) {
  return useMutation<VideoGenerationResult, Error, VideoGenerationRequest>({
    mutationFn: generateVideo,
    ...options,
  });
}
