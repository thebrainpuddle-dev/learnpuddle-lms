// src/components/maic/SlideNavigator.tsx
//
// Bottom navigation bar with slides grouped by scene. Shows slide dots
// organized under scene labels with accent-colored active indicator,
// scene boundary dividers, prev/next buttons, and a scene dropdown for
// quick scene-level jumping.

import React, { useRef, useEffect, useMemo, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Play, Pause, ChevronDown } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import type { MAICScene, SceneSlideBounds } from '../../types/maic-scenes';
import { cn } from '../../lib/utils';

/** Build scene-to-slide mapping from scenes and slides arrays, using
 *  sceneSlideBounds when available for accurate multi-slide grouping. */
function buildSceneGroups(
  scenes: MAICScene[],
  totalSlides: number,
  sceneSlideBounds: SceneSlideBounds[],
) {
  if (scenes.length === 0) {
    // No scenes — treat every slide as its own group
    return Array.from({ length: totalSlides }, (_, i) => ({
      sceneIndex: i,
      sceneTitle: `Slide ${i + 1}`,
      slideIndices: [i],
    }));
  }

  // Use sceneSlideBounds for precise mapping if available
  if (sceneSlideBounds.length > 0) {
    return sceneSlideBounds.map((bounds) => {
      const indices: number[] = [];
      for (let s = bounds.startSlide; s <= bounds.endSlide && s < totalSlides; s++) {
        indices.push(s);
      }
      return {
        sceneIndex: bounds.sceneIdx,
        sceneTitle: scenes[bounds.sceneIdx]?.title || `Scene ${bounds.sceneIdx + 1}`,
        slideIndices: indices,
      };
    });
  }

  // Fallback: distribute slides evenly across scenes (legacy 1:1 behavior)
  const groups: { sceneIndex: number; sceneTitle: string; slideIndices: number[] }[] = [];
  const slidesPerScene = Math.max(1, Math.ceil(totalSlides / scenes.length));
  let slideIdx = 0;

  for (let si = 0; si < scenes.length; si++) {
    const indices: number[] = [];
    const count = si < scenes.length - 1 ? slidesPerScene : totalSlides - slideIdx;
    for (let j = 0; j < count && slideIdx < totalSlides; j++, slideIdx++) {
      indices.push(slideIdx);
    }
    if (indices.length > 0) {
      groups.push({
        sceneIndex: si,
        sceneTitle: scenes[si].title,
        slideIndices: indices,
      });
    }
  }

  // If we have leftover slides with no scene, add them
  while (slideIdx < totalSlides) {
    const lastGroup = groups[groups.length - 1];
    if (lastGroup) {
      lastGroup.slideIndices.push(slideIdx);
    }
    slideIdx++;
  }

  return groups;
}

/**
 * Props for SlideNavigator.
 *
 * - `onSlideClick`: optional callback invoked when the user clicks a slide
 *   thumbnail that resolves to the CURRENT scene. Called with the
 *   **scene-relative** slide index (matching `TransitionAction.slideIndex`)
 *   so the parent can invoke `playbackEngine.seekToSlide(rel)` directly.
 *   For cross-scene clicks the component always falls back to the stage
 *   store's `goToSlide(absoluteIdx)` — a scene change, not a within-scene
 *   seek. When the prop is absent, the component resolves the seek via the
 *   dev-only `window.__maicEngine` handle if available.
 */
export interface SlideNavigatorProps {
  onSlideClick?: (relativeSlideIndex: number) => void;
}

export const SlideNavigator = React.memo(function SlideNavigator({
  onSlideClick,
}: SlideNavigatorProps = {}) {
  const slides = useMAICStageStore((s) => s.slides);
  const scenes = useMAICStageStore((s) => s.scenes);
  const sceneSlideBounds = useMAICStageStore((s) => s.sceneSlideBounds);
  const currentSlideIndex = useMAICStageStore((s) => s.currentSlideIndex);
  const goToSlide = useMAICStageStore((s) => s.goToSlide);
  const nextSlide = useMAICStageStore((s) => s.nextSlide);
  const prevSlide = useMAICStageStore((s) => s.prevSlide);
  const goToScene = useMAICStageStore((s) => s.goToScene);
  const isPlaying = useMAICStageStore((s) => s.isPlaying);
  const setPlaying = useMAICStageStore((s) => s.setPlaying);

  // Delegate thumbnail clicks. The clicked `absoluteIdx` is an absolute
  // slide index (0-based across all scenes). We route as follows:
  //
  //   A. Click is WITHIN the current scene:
  //      a1. `onSlideClick` prop present → call it with the SCENE-RELATIVE
  //          index (so Stage can call playbackEngine.seekToSlide(rel)).
  //      a2. Otherwise try dev-only `window.__maicEngine` for the seek.
  //      a3. Otherwise fall back to pure goToSlide(absoluteIdx).
  //
  //   B. Click is in a DIFFERENT scene:
  //      → always goToSlide(absoluteIdx). This updates `currentSceneIndex`,
  //        Stage's scene-change useEffect observes and calls `loadScene()`,
  //        which internally calls stop() → abortCurrentAction → token bump.
  //        No-audio-overlap guarantee still holds.
  const handleSlideClick = useCallback(
    (absoluteIdx: number) => {
      // Locate the scene this slide belongs to, and its relative offset.
      const bounds = sceneSlideBounds.find(
        (b) => absoluteIdx >= b.startSlide && absoluteIdx <= b.endSlide,
      );
      const targetSceneIdx = bounds?.sceneIdx ?? -1;
      const relativeSlideIdx = bounds ? absoluteIdx - bounds.startSlide : -1;
      const sameScene =
        targetSceneIdx === useMAICStageStore.getState().currentSceneIndex &&
        relativeSlideIdx >= 0;

      if (sameScene) {
        if (onSlideClick) {
          onSlideClick(relativeSlideIdx);
          return;
        }
        // Dev/test fallback via exposed engine handle.
        const engine =
          typeof window !== 'undefined'
            ? (window as any).__maicEngine?.playbackEngine
            : undefined;
        if (engine && typeof engine.seekToSlide === 'function') {
          engine.seekToSlide(relativeSlideIdx);
          return;
        }
      }

      // Cross-scene click, or no engine available — defer to the store.
      goToSlide(absoluteIdx);
    },
    [onSlideClick, goToSlide, sceneSlideBounds],
  );

  const totalSlides = slides.length;
  const totalCount = Math.max(totalSlides, scenes.length);

  const sceneGroups = useMemo(
    () => buildSceneGroups(scenes, totalSlides, sceneSlideBounds),
    [scenes, totalSlides, sceneSlideBounds],
  );

  // Determine active scene index from current slide index
  const activeSceneIdx = useMemo(() => {
    for (const group of sceneGroups) {
      if (group.slideIndices.includes(currentSlideIndex)) {
        return group.sceneIndex;
      }
    }
    return 0;
  }, [sceneGroups, currentSlideIndex]);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const thumbnailRefs = useRef<Map<number, HTMLButtonElement>>(new Map());
  const [sceneDropdownOpen, setSceneDropdownOpen] = React.useState(false);

  // Scroll active thumbnail into view
  useEffect(() => {
    const thumb = thumbnailRefs.current.get(currentSlideIndex);
    if (thumb) {
      thumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  }, [currentSlideIndex]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!sceneDropdownOpen) return;
    const handleClick = () => setSceneDropdownOpen(false);
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [sceneDropdownOpen]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        prevSlide();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        nextSlide();
      } else if (e.key === ' ') {
        e.preventDefault();
        setPlaying(!isPlaying);
      }
    },
    [prevSlide, nextSlide, isPlaying, setPlaying],
  );

  if (totalCount === 0) return null;

  return (
    <div
      className="flex items-center gap-2 px-3 py-2 bg-white border-t border-gray-200"
      role="navigation"
      aria-label="Slide navigation"
      onKeyDown={handleKeyDown}
    >
      {/* Previous button */}
      <button
        type="button"
        onClick={prevSlide}
        disabled={currentSlideIndex === 0}
        className={cn(
          'shrink-0 p-1.5 rounded-lg transition-colors',
          'text-gray-500 hover:bg-gray-100 hover:text-gray-700',
          'disabled:opacity-30 disabled:cursor-not-allowed',
          'focus:outline-none focus:ring-2 focus:ring-primary-500',
        )}
        aria-label="Previous slide"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      {/* Play/Pause */}
      <button
        type="button"
        onClick={() => setPlaying(!isPlaying)}
        className={cn(
          'shrink-0 p-1.5 rounded-lg transition-colors',
          'text-gray-600 hover:bg-gray-100 hover:text-gray-800',
          'focus:outline-none focus:ring-2 focus:ring-primary-500',
        )}
        aria-label={isPlaying ? 'Pause playback' : 'Start playback'}
      >
        {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </button>

      {/* Slide indicator */}
      <span className="shrink-0 text-xs text-gray-500 min-w-[4.5rem] text-center tabular-nums">
        Slide {currentSlideIndex + 1} of {totalCount}
      </span>

      {/* Scene dropdown for quick jump */}
      {scenes.length > 1 && (
        <div className="relative shrink-0">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setSceneDropdownOpen((prev) => !prev);
            }}
            className={cn(
              'flex items-center gap-1 px-2 py-1 rounded-md text-xs transition-colors',
              'text-gray-600 hover:bg-gray-100 hover:text-gray-800',
              'focus:outline-none focus:ring-2 focus:ring-primary-500',
              'border border-gray-200',
            )}
            aria-label="Jump to scene"
          >
            <span className="max-w-[8rem] truncate">
              {scenes[activeSceneIdx]?.title || `Scene ${activeSceneIdx + 1}`}
            </span>
            <ChevronDown className="h-3 w-3" />
          </button>
          {sceneDropdownOpen && (
            <div className="absolute bottom-full mb-1 left-0 w-56 bg-white border border-gray-200 rounded-lg shadow-lg py-1 z-50 max-h-60 overflow-y-auto">
              {scenes.map((scene, idx) => (
                <button
                  key={scene.id}
                  type="button"
                  onClick={() => {
                    goToScene(idx);
                    setSceneDropdownOpen(false);
                  }}
                  className={cn(
                    'w-full text-left px-3 py-1.5 text-xs transition-colors',
                    idx === activeSceneIdx
                      ? 'bg-primary-50 text-primary-700 font-medium'
                      : 'text-gray-700 hover:bg-gray-50',
                  )}
                >
                  <span className="text-gray-400 mr-1.5">{idx + 1}.</span>
                  {scene.title}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Slide thumbnails grouped by scene */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-x-auto flex items-center gap-0.5 px-1 scrollbar-thin scrollbar-thumb-gray-300"
        role="tablist"
        aria-label="Slide thumbnails"
      >
        {sceneGroups.map((group, groupIdx) => (
          <React.Fragment key={group.sceneIndex}>
            {/* Scene divider (between groups) */}
            {groupIdx > 0 && (
              <div className="shrink-0 w-px h-6 bg-gray-200 mx-1.5" aria-hidden="true" />
            )}

            {/* Scene group */}
            <div className="shrink-0 flex flex-col items-center gap-0.5">
              {/* Scene label (only when multiple scenes) */}
              {scenes.length > 1 && (
                <span
                  className={cn(
                    'text-[8px] leading-none font-medium truncate max-w-[8rem] px-0.5',
                    group.sceneIndex === activeSceneIdx
                      ? 'text-primary-600'
                      : 'text-gray-400',
                  )}
                  title={group.sceneTitle}
                >
                  {group.sceneTitle}
                </span>
              )}

              {/* Slide dots/thumbnails for this scene */}
              <div className="flex items-center gap-1">
                {group.slideIndices.map((slideIdx) => {
                  const slide = slides[slideIdx];
                  const isActive = slideIdx === currentSlideIndex;
                  const bg = slide?.background || '#ffffff';

                  return (
                    <button
                      key={slide?.id || slideIdx}
                      ref={(el) => {
                        if (el) thumbnailRefs.current.set(slideIdx, el);
                        else thumbnailRefs.current.delete(slideIdx);
                      }}
                      type="button"
                      role="tab"
                      data-testid="slide-thumbnail"
                      aria-selected={isActive}
                      aria-label={`Slide ${slideIdx + 1}: ${slide?.title || ''}`}
                      onClick={() => handleSlideClick(slideIdx)}
                      className={cn(
                        'shrink-0 w-14 h-10 rounded border-2 transition-all overflow-hidden',
                        'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1',
                        isActive
                          ? 'border-primary-500 shadow-sm scale-110'
                          : 'border-gray-200 hover:border-gray-300 opacity-60 hover:opacity-100',
                      )}
                      style={{ background: bg }}
                    >
                      <div className="h-full w-full flex items-center justify-center">
                        <span
                          className={cn(
                            'text-[9px] font-medium',
                            isActive ? 'text-primary-600' : 'text-gray-400',
                          )}
                        >
                          {slideIdx + 1}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </React.Fragment>
        ))}
      </div>

      {/* Next button */}
      <button
        type="button"
        onClick={nextSlide}
        disabled={currentSlideIndex >= totalCount - 1}
        className={cn(
          'shrink-0 p-1.5 rounded-lg transition-colors',
          'text-gray-500 hover:bg-gray-100 hover:text-gray-700',
          'disabled:opacity-30 disabled:cursor-not-allowed',
          'focus:outline-none focus:ring-2 focus:ring-primary-500',
        )}
        aria-label="Next slide"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
});
