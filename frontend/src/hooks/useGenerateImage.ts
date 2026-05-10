/**
 * React Query mutation hook for image generation (Phase 9, MAIC-916).
 *
 * Wraps frontend/src/lib/media/api.ts:generateImage with React Query's
 * useMutation so callers get isPending / isError / data / mutate /
 * mutateAsync out of the box.
 *
 * Source: frontend/src/lib/media/api.ts (the typed POST helper).
 *
 * Used by:
 *   - regenerate-image buttons (admin slide editor, dev probe)
 *   - any UI surface that needs to kick off a one-shot image gen
 *
 * NOT used by the live classroom playback path — that's already
 * resolved server-side via MAIC-915 before the scene is persisted.
 */
import { useMutation, type UseMutationOptions } from '@tanstack/react-query';

import { generateImage } from '../lib/media/api';
import type {
  ImageGenerationRequest,
  ImageGenerationResult,
} from '../lib/media/types';

type Options = Omit<
  UseMutationOptions<ImageGenerationResult, Error, ImageGenerationRequest>,
  'mutationFn'
>;

export function useGenerateImage(options?: Options) {
  return useMutation<ImageGenerationResult, Error, ImageGenerationRequest>({
    mutationFn: generateImage,
    ...options,
  });
}
