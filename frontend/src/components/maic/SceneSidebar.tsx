// src/components/maic/SceneSidebar.tsx
//
// Scene navigation sidebar for the MAIC AI Classroom player. Displays a
// vertical list of scenes with type emoji icon, title, slide count badge,
// estimated duration, progress indicator, and active scene highlight with
// left border accent.

import React, { useCallback, useMemo, useState } from 'react';
import { X, GripVertical } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import type { MAICScene, MAICSceneType, SceneSlideBounds } from '../../types/maic-scenes';
import type { MAICSlide } from '../../types/maic';
import { useAuthBlobUrl } from '../../hooks/useAuthBlobUrl';
import { cn } from '../../lib/utils';

interface SceneSidebarProps {
  visible: boolean;
  onClose: () => void;
  /** T6 — optional gated seek. When provided, clicks route here instead
   *  of the store's `goToScene` so Stage.tsx can gate switches during
   *  active discussions with a confirm dialog. */
  onSceneSelect?: (sceneIndex: number) => void;
  /** T4 — when provided, tiles flagged in `failedOutlineIds` render a
   *  Retry button. Clicking it calls back with the scene's outline id;
   *  the caller re-runs action generation and clears the flag. When
   *  omitted, failed tiles still render the red state but without a
   *  retry affordance — used in the classroom surface where the
   *  wizard-owned retry callback isn't available. */
  onSceneRetry?: (outlineId: string) => void;
}

// ─── Scene type emoji map ─────────────────────────────────────────────────
const SCENE_EMOJI_MAP: Record<string, string> = {
  lecture: '\uD83D\uDCD6',       // book
  quiz: '\u2753',                // question mark
  discussion: '\uD83D\uDCAC',   // speech bubble
  activity: '\uD83C\uDFAF',     // dart / bullseye
  summary: '\uD83D\uDCCB',      // clipboard
  introduction: '\uD83D\uDC4B', // wave
  slide: '\uD83D\uDCCA',        // presentation
  interactive: '\uD83D\uDCBB',  // laptop
  pbl: '\uD83D\uDCA1',          // lightbulb
};

const SCENE_LABEL_MAP: Record<string, string> = {
  slide: 'Slide',
  quiz: 'Quiz',
  interactive: 'Interactive',
  pbl: 'Project',
  lecture: 'Lecture',
  discussion: 'Discussion',
  activity: 'Activity',
  summary: 'Summary',
  introduction: 'Introduction',
};

/** Compute estimated duration for a scene based on slide count and type. */
function estimateMinutes(scene: MAICScene, slideCount: number): number {
  // If the outline had estimatedMinutes, it would be passed through;
  // as a heuristic: 1 min per slide, quizzes take 2 min each
  if (scene.type === 'quiz') return Math.max(2, slideCount);
  return Math.max(1, slideCount);
}

/** Mini thumbnail preview showing the first slide's content as a preview card */
function SceneThumbnail({ slide, isActive }: { slide?: MAICSlide; isActive: boolean }) {
  // Extract first text element as preview
  const textEl = slide?.elements.find((e) => e.type === 'text');
  const imageEl = slide?.elements.find((e) => e.type === 'image');
  const imageSrc = (imageEl?.src || '').trim();
  const protectedImageSrc = imageSrc.startsWith('/media/') ? imageSrc : null;
  const imageBlobUrl = useAuthBlobUrl(protectedImageSrc);
  const previewImageSrc = protectedImageSrc ? imageBlobUrl : imageSrc;

  if (!slide) return null;

  const previewText = textEl?.content?.replace(/\\n/g, ' ').replace(/<[^>]*>/g, '').slice(0, 60) || '';

  return (
    <div
      className={cn(
        'w-full aspect-video rounded border overflow-hidden text-[6px] leading-tight',
        'flex items-center justify-center p-1',
        isActive
          ? 'border-primary-300 bg-primary-50'
          : 'border-gray-200 bg-gray-50',
      )}
      style={{ background: slide.background || '#ffffff' }}
    >
      {previewImageSrc ? (
        <img src={previewImageSrc} alt="" className="w-full h-full object-cover rounded-sm" loading="lazy" />
      ) : protectedImageSrc ? (
        <span className="text-gray-300">Loading</span>
      ) : previewText ? (
        <span className="text-gray-500 line-clamp-3 text-center px-0.5">{previewText}</span>
      ) : (
        <span className="text-gray-300">{slide.title || 'Slide'}</span>
      )}
    </div>
  );
}

export const SceneSidebar = React.memo<SceneSidebarProps>(function SceneSidebar({
  visible,
  onClose,
  onSceneSelect,
  onSceneRetry,
}) {
  const scenes = useMAICStageStore((s) => s.scenes);
  const slides = useMAICStageStore((s) => s.slides);
  const sceneSlideBounds = useMAICStageStore((s) => s.sceneSlideBounds);
  const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
  const currentSlideIndex = useMAICStageStore((s) => s.currentSlideIndex);
  const goToScene = useMAICStageStore((s) => s.goToScene);
  const failedOutlineIds = useMAICStageStore((s) => s.failedOutlineIds);
  // Lookup for O(1) "is this scene failed?" per tile. Using a Set keeps
  // the scan off the hot render path.
  const failedSet = useMemo(() => new Set(failedOutlineIds), [failedOutlineIds]);

  // Sidebar resizing
  const [sidebarWidth, setSidebarWidth] = useState(288); // 18rem default
  const [isResizing, setIsResizing] = useState(false);

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
    const startX = e.clientX;
    const startWidth = sidebarWidth;

    const onMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX;
      setSidebarWidth(Math.max(220, Math.min(450, startWidth + delta)));
    };
    const onUp = () => {
      setIsResizing(false);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }, [sidebarWidth]);

  // Build slide distribution across scenes, preferring sceneSlideBounds when available
  const sceneSlideInfo = useMemo(() => {
    const totalSlides = slides.length;
    if (scenes.length === 0 || totalSlides === 0) {
      return scenes.map(() => ({ count: 0, startIdx: -1, endIdx: -1 }));
    }

    if (sceneSlideBounds.length > 0) {
      return scenes.map((_, si) => {
        const bounds = sceneSlideBounds.find((b) => b.sceneIdx === si);
        if (bounds) {
          const count = bounds.endSlide - bounds.startSlide + 1;
          return { count, startIdx: bounds.startSlide, endIdx: bounds.endSlide };
        }
        return { count: 0, startIdx: -1, endIdx: -1 };
      });
    }

    // Fallback: distribute evenly
    const perScene = Math.max(1, Math.ceil(totalSlides / scenes.length));
    let idx = 0;
    return scenes.map((_, si) => {
      const start = idx;
      const count = si < scenes.length - 1 ? perScene : totalSlides - idx;
      idx += count;
      return { count: Math.max(count, 0), startIdx: start, endIdx: start + Math.max(count, 0) - 1 };
    });
  }, [scenes, slides.length, sceneSlideBounds]);

  const handleSceneClick = useCallback(
    (index: number) => {
      if (onSceneSelect) onSceneSelect(index);
      else goToScene(index);
    },
    [goToScene, onSceneSelect],
  );

  return (
    <div
      className={cn(
        'absolute inset-y-0 left-0 z-30 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 shadow-lg',
        'flex flex-col transition-transform duration-200 ease-in-out',
        visible ? 'translate-x-0' : '-translate-x-full',
      )}
      style={{ width: sidebarWidth }}
      role="navigation"
      aria-label="Scene list"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2.5 border-b border-gray-200 dark:border-gray-700">
        <div>
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Scenes
          </h2>
          <p className="text-[10px] text-gray-400 mt-0.5">
            {scenes.length} activit{scenes.length === 1 ? 'y' : 'ies'} &middot; {slides.length} slide screen{slides.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className={cn(
            'p-1.5 rounded-md transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-primary-500',
            'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800',
          )}
          title="Close sidebar"
          aria-label="Close scene sidebar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Scene list */}
      <ul className="flex-1 overflow-y-auto py-1">
        {scenes.map((scene: MAICScene, index: number) => {
          const isActive = index === currentSceneIndex;
          const info = sceneSlideInfo[index] || { count: 1, startIdx: 0, endIdx: 0 };
          const emoji = SCENE_EMOJI_MAP[scene.type] || SCENE_EMOJI_MAP.slide || '';
          const label = SCENE_LABEL_MAP[scene.type] ?? scene.type;
          const estMin = estimateMinutes(scene, info.count);
          // T4 — failed state: red border + optional retry button.
          const isFailed = failedSet.has(scene.id);

          // Progress: how many slides in this scene have been "viewed"
          // (simple heuristic: currentSlideIndex >= slideIdx means viewed)
          const viewedCount = Math.max(
            0,
            Math.min(info.count, currentSlideIndex - info.startIdx + 1),
          );
          const progressPct = info.count > 0 ? Math.round((viewedCount / info.count) * 100) : 0;

          return (
            <li key={scene.id} className="relative">
              <button
                type="button"
                onClick={() => handleSceneClick(index)}
                className={cn(
                  'w-full flex items-start gap-2.5 px-3 py-2.5 text-left transition-colors',
                  'focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500',
                  isFailed
                    ? 'bg-red-50 dark:bg-red-900/20 border-l-[3px] border-l-red-500'
                    : isActive
                      ? 'bg-primary-50 dark:bg-primary-900/30 border-l-[3px] border-l-primary-600 dark:border-l-primary-400'
                      : 'border-l-[3px] border-l-transparent hover:bg-gray-50 dark:hover:bg-gray-800',
                )}
                aria-current={isActive ? 'true' : undefined}
              >
                {/* Thumbnail preview */}
                <div className="shrink-0 w-16">
                  <SceneThumbnail
                    slide={info.startIdx >= 0 ? slides[info.startIdx] : undefined}
                    isActive={isActive}
                  />
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  {/* Title */}
                  <span
                    className={cn(
                      'block text-xs leading-tight truncate',
                      isActive
                        ? 'text-primary-700 font-semibold dark:text-primary-300'
                        : 'text-gray-700 font-medium dark:text-gray-300',
                    )}
                    title={scene.title}
                  >
                    {scene.title}
                  </span>

                  {/* Metadata row: type badge, slide count, duration */}
                  <div className="flex items-center gap-1.5 mt-1">
                    {/* Type badge with emoji */}
                    <span
                      className={cn(
                        'text-[9px] px-1.5 py-0.5 rounded-full font-medium',
                        isActive
                          ? 'bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-300'
                          : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
                      )}
                    >
                      {emoji} {label}
                    </span>

                    {/* Slide count badge */}
                    {info.count > 0 && (
                      <span className="text-[9px] text-gray-400 dark:text-gray-500">
                        {info.count} slide{info.count !== 1 ? 's' : ''}
                      </span>
                    )}

                    {/* Duration estimate */}
                    <span className="text-[9px] text-gray-400 dark:text-gray-500">
                      ~{estMin} min
                    </span>
                  </div>

                  {/* Progress bar */}
                  <div className="mt-1.5 h-1 w-full bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className={cn(
                        'h-full rounded-full transition-all duration-300',
                        isActive
                          ? 'bg-primary-500'
                          : progressPct >= 100
                            ? 'bg-green-400'
                            : 'bg-gray-300 dark:bg-gray-600',
                      )}
                      style={{ width: `${Math.min(progressPct, 100)}%` }}
                    />
                  </div>
                </div>

                {/* Order number */}
                <span
                  className={cn(
                    'shrink-0 flex items-center justify-center h-5 w-5 rounded text-[10px] font-medium mt-0.5',
                    isFailed
                      ? 'bg-red-500 text-white'
                      : isActive
                        ? 'bg-primary-600 text-white dark:bg-primary-500'
                        : 'bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
                  )}
                >
                  {scene.order}
                </span>
              </button>
              {/* T4 — retry affordance for failed scenes. Only rendered
                  when the caller supplied `onSceneRetry`; the button is
                  absolutely positioned at the bottom-right of the tile
                  so it doesn't mess with the tile's own click target. */}
              {isFailed && onSceneRetry && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSceneRetry(scene.id);
                  }}
                  className="absolute bottom-1.5 right-3 text-[10px] font-semibold text-red-600 hover:text-red-800 bg-white/80 hover:bg-white rounded px-1.5 py-0.5 shadow-sm border border-red-200 transition-colors"
                  aria-label={`Retry scene ${scene.order} generation`}
                >
                  Retry
                </button>
              )}
            </li>
          );
        })}
      </ul>

      {/* Resize handle */}
      <div
        className={cn(
          'absolute inset-y-0 right-0 w-1.5 cursor-col-resize hover:bg-primary-200 transition-colors z-10',
          isResizing && 'bg-primary-300',
        )}
        onMouseDown={handleResizeStart}
        title="Drag to resize"
      />
    </div>
  );
});
