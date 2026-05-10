/**
 * VideoPlayer — minimal HTML5 video element wrapper for Phase 9 media.
 *
 * Source: this is our component (no upstream OpenMAIC reference —
 *         upstream's slide renderer uses raw <video> tags inline; we
 *         wrap to centralize controls + placeholder UX).
 *
 * Used by:
 *   - slide elements whose type === 'video' (when SlideRenderer adds
 *     the video branch in a future polish ticket)
 *   - direct-render surfaces in admin / dev pages
 *
 * Discipline:
 *   - Same `gen_vid_*` placeholder handling as images: empty src or
 *     placeholder → render skeleton, NOT a broken <video> element
 *   - autoPlay defaults to false (browser autoplay policies make
 *     autoPlay-with-sound silently fail; opt-in only)
 *   - muted required when autoPlay=true (browser policy)
 *   - controls default to true so end-users always have a fallback
 *     when our wrapper UX falls short
 */
import { useState } from 'react';

import { cn } from '../../lib/utils';

export interface VideoPlayerProps {
  src: string;
  alt?: string;
  poster?: string;
  controls?: boolean;
  autoPlay?: boolean;
  loop?: boolean;
  muted?: boolean;
  className?: string;
  onError?: (err: Error) => void;
  /** Test hook for the skeleton state (no real <video> emitted). */
  skeletonTestId?: string;
}

/** Returns true when the src is a Phase-9 placeholder, not a real URL. */
function _isPlaceholderSrc(src: string): boolean {
  const trimmed = src.trim();
  return trimmed === '' || trimmed.startsWith('gen_vid_');
}

export function VideoPlayer({
  src,
  alt,
  poster,
  controls = true,
  autoPlay = false,
  loop = false,
  muted = false,
  className,
  onError,
  skeletonTestId,
}: VideoPlayerProps) {
  const [errored, setErrored] = useState(false);

  // Skeleton path — empty src OR a Phase 9 placeholder that wasn't
  // server-resolved (MAIC-915 failure preserved it). Surfaced as a
  // gray pulse box rather than a broken <video> with an X icon.
  if (_isPlaceholderSrc(src)) {
    return (
      <div
        role="img"
        aria-label={alt || 'Video pending'}
        data-testid={skeletonTestId || 'video-skeleton'}
        className={cn(
          'animate-pulse bg-gray-200 rounded-md flex items-center justify-center',
          'min-h-[180px] text-xs text-gray-500',
          className,
        )}
      >
        Video generating…
      </div>
    );
  }

  // Error path — <video> failed to load (404, CORS, codec). We
  // intentionally don't auto-retry; calling code can retry with a
  // fresh useGenerateVideo() mutation if needed.
  if (errored) {
    return (
      <div
        role="img"
        aria-label={alt || 'Video unavailable'}
        className={cn(
          'bg-red-50 border border-red-200 rounded-md flex items-center justify-center',
          'min-h-[180px] text-xs text-red-700 p-3',
          className,
        )}
      >
        Video unavailable
      </div>
    );
  }

  // Real video. autoPlay+unmuted is silently blocked by browsers, so
  // we force mute=true when autoPlay is on (matches WHATWG behavior).
  const effectiveMuted = autoPlay ? true : muted;

  return (
    // eslint-disable-next-line jsx-a11y/media-has-caption
    <video
      src={src}
      poster={poster}
      controls={controls}
      autoPlay={autoPlay}
      muted={effectiveMuted}
      loop={loop}
      aria-label={alt}
      className={cn('rounded-md max-w-full', className)}
      onError={() => {
        setErrored(true);
        onError?.(new Error(`video failed to load: ${src}`));
      }}
    />
  );
}
