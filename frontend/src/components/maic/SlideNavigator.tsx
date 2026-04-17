// src/components/maic/SlideNavigator.tsx
//
// Bottom navigation bar — **scenes only** (OpenMAIC style). Each classroom
// topic is a scene; the scene owns its slides internally. The user jumps
// between scenes here; slides within a scene auto-advance as the engine
// plays through the scene's transition actions.
//
// Controls:
//   - ◀ / ▶       prev / next scene
//   - ▶ / ⏸       play / pause (single canonical control, engine-aware)
//   - scene chips — one per scene, shows title + position, click to jump
//   - progress   — "Scene N of M · slide X of Y"

import React, { useRef, useEffect, useMemo, useCallback } from 'react';
import { ChevronLeft, ChevronRight, Play, Pause } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { cn } from '../../lib/utils';

export interface SlideNavigatorProps {
  /** Engine-aware play/pause handler wired by Stage. The bottom play
   *  button is the single canonical control; StageToolbar no longer
   *  renders one. */
  onPlayPause?: () => void;
  /** Engine-aware scene seek handler wired by Stage. Stops the engine
   *  and updates the store atomically so pressing Play after clicking a
   *  chip always starts from action 0 of the new scene — no stale
   *  audio from the previous scene can leak across. Falls back to the
   *  store's goToScene when not provided (legacy pre-Chunk-10 callers). */
  onSeekToScene?: (sceneIndex: number) => void;
  /** Deprecated — we no longer expose a per-slide seek surface. Left in
   *  the prop shape for backward compat with existing Stage wiring;
   *  never invoked from this component. */
  onSlideClick?: (relativeSlideIndex: number) => void;
}

export const SlideNavigator = React.memo(function SlideNavigator({
  onPlayPause,
  onSeekToScene,
}: SlideNavigatorProps = {}) {
  const scenes = useMAICStageStore((s) => s.scenes);
  const sceneSlideBounds = useMAICStageStore((s) => s.sceneSlideBounds);
  const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
  const currentSlideIndex = useMAICStageStore((s) => s.currentSlideIndex);
  const goToScene = useMAICStageStore((s) => s.goToScene);
  const nextScene = useMAICStageStore((s) => s.nextScene);
  const isPlaying = useMAICStageStore((s) => s.isPlaying);
  const setPlaying = useMAICStageStore((s) => s.setPlaying);

  // Scenes that actually contribute playable slides. Quiz/empty scenes
  // are hidden from the strip — they'd be unclickable chips otherwise.
  // A scene's bounds entry means the generation pipeline produced slides
  // for it (see useMAICGeneration.ts).
  const navScenes = useMemo(() => {
    return sceneSlideBounds.map((bounds) => {
      const scene = scenes[bounds.sceneIdx];
      if (!scene) return null;
      const slideCount = bounds.endSlide - bounds.startSlide + 1;
      return {
        sceneIndex: bounds.sceneIdx,
        title: scene.title,
        slideCount,
        startSlide: bounds.startSlide,
        endSlide: bounds.endSlide,
      };
    }).filter(Boolean) as Array<{
      sceneIndex: number;
      title: string;
      slideCount: number;
      startSlide: number;
      endSlide: number;
    }>;
  }, [scenes, sceneSlideBounds]);

  // Which scene does the current slide belong to?
  const activeSceneIdx = useMemo(() => {
    const match = sceneSlideBounds.find(
      (b) => currentSlideIndex >= b.startSlide && currentSlideIndex <= b.endSlide,
    );
    return match ? match.sceneIdx : currentSceneIndex;
  }, [sceneSlideBounds, currentSlideIndex, currentSceneIndex]);

  // Current scene position labels (e.g., "slide 2 of 4 within the active scene")
  const activeScene = useMemo(() => {
    return navScenes.find((s) => s.sceneIndex === activeSceneIdx) ?? null;
  }, [navScenes, activeSceneIdx]);

  const slideInScene = activeScene
    ? Math.max(0, currentSlideIndex - activeScene.startSlide) + 1
    : 0;

  // Jump to scene by index. Prefer the engine-aware seek provided by
  // Stage (stops the engine atomically before the store update) so
  // pressing Play right after a chip click always plays from action 0
  // of the target scene, not stale state from the prior one.
  const handleSceneClick = useCallback(
    (sceneIdx: number) => {
      if (onSeekToScene) onSeekToScene(sceneIdx);
      else goToScene(sceneIdx);
    },
    [goToScene, onSeekToScene],
  );

  const handlePrev = useCallback(() => {
    if (activeSceneIdx <= 0) return;
    const target = activeSceneIdx - 1;
    if (onSeekToScene) onSeekToScene(target);
    else goToScene(target);
  }, [activeSceneIdx, goToScene, onSeekToScene]);

  const handleNext = useCallback(() => {
    const last = navScenes[navScenes.length - 1]?.sceneIndex ?? -1;
    if (activeSceneIdx >= last) return;
    if (onSeekToScene) onSeekToScene(activeSceneIdx + 1);
    else nextScene();
  }, [activeSceneIdx, navScenes, nextScene, onSeekToScene]);

  // Scroll active chip into view when scene changes.
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  const chipRefs = useRef<Map<number, HTMLButtonElement>>(new Map());

  useEffect(() => {
    const el = chipRefs.current.get(activeSceneIdx);
    if (el && scrollContainerRef.current) {
      const container = scrollContainerRef.current;
      const { offsetLeft, offsetWidth } = el;
      const targetScroll = offsetLeft - container.clientWidth / 2 + offsetWidth / 2;
      container.scrollTo({ left: Math.max(0, targetScroll), behavior: 'smooth' });
    }
  }, [activeSceneIdx]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        e.preventDefault();
        handlePrev();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        handleNext();
      } else if (e.key === ' ') {
        e.preventDefault();
        if (onPlayPause) onPlayPause();
        else setPlaying(!isPlaying);
      }
    },
    [handlePrev, handleNext, isPlaying, setPlaying, onPlayPause],
  );

  if (navScenes.length === 0) return null;

  const isFirstScene = activeSceneIdx <= (navScenes[0]?.sceneIndex ?? 0);
  const isLastScene = activeSceneIdx >= (navScenes[navScenes.length - 1]?.sceneIndex ?? 0);

  return (
    <div
      className="flex items-center gap-3 px-3 py-2 bg-white border-t border-gray-200"
      role="navigation"
      aria-label="Scene navigation"
      onKeyDown={handleKeyDown}
    >
      {/* Prev scene */}
      <button
        type="button"
        onClick={handlePrev}
        disabled={isFirstScene}
        className={cn(
          'shrink-0 p-1.5 rounded-lg transition-colors',
          'text-gray-500 hover:bg-gray-100 hover:text-gray-700',
          'disabled:opacity-30 disabled:cursor-not-allowed',
          'focus:outline-none focus:ring-2 focus:ring-primary-500',
        )}
        aria-label="Previous scene"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>

      {/* Play/Pause — single canonical control */}
      <button
        type="button"
        onClick={onPlayPause ?? (() => setPlaying(!isPlaying))}
        data-testid="play-button"
        className={cn(
          'shrink-0 flex items-center justify-center rounded-full transition-all',
          'h-10 w-10 shadow-sm',
          isPlaying
            ? 'bg-primary-600 text-white hover:bg-primary-700'
            : 'bg-gray-900 text-white hover:bg-gray-700',
          'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
        )}
        aria-label={isPlaying ? 'Pause playback' : 'Start playback'}
        title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
      >
        {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4 ml-0.5" />}
      </button>

      {/* Position label */}
      <div className="shrink-0 text-xs text-gray-500 tabular-nums min-w-[8rem]">
        <div className="font-medium text-gray-700 truncate max-w-[12rem]">
          {activeScene ? activeScene.title : 'Classroom'}
        </div>
        <div className="text-[10px] text-gray-400">
          Scene {activeSceneIdx + 1} of {navScenes.length}
          {activeScene && activeScene.slideCount > 1 && (
            <> · slide {slideInScene} of {activeScene.slideCount}</>
          )}
        </div>
      </div>

      {/* Scene chips — horizontal scroll */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-x-auto flex items-center gap-1.5 px-1 scrollbar-thin scrollbar-thumb-gray-300"
        role="tablist"
        aria-label="Scenes"
      >
        {navScenes.map((scene) => {
          const isActive = scene.sceneIndex === activeSceneIdx;
          return (
            <button
              key={scene.sceneIndex}
              ref={(el) => {
                if (el) chipRefs.current.set(scene.sceneIndex, el);
                else chipRefs.current.delete(scene.sceneIndex);
              }}
              type="button"
              role="tab"
              data-testid="scene-chip"
              aria-selected={isActive}
              onClick={() => handleSceneClick(scene.sceneIndex)}
              className={cn(
                'shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs transition-all',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1',
                isActive
                  ? 'bg-primary-600 text-white shadow-sm scale-105'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200 hover:text-gray-800',
              )}
              title={scene.title}
            >
              <span
                className={cn(
                  'flex items-center justify-center h-4 w-4 rounded-full text-[9px] font-bold tabular-nums',
                  isActive ? 'bg-white/25' : 'bg-gray-300 text-gray-600',
                )}
              >
                {scene.sceneIndex + 1}
              </span>
              <span className="font-medium truncate max-w-[10rem]">{scene.title}</span>
            </button>
          );
        })}
      </div>

      {/* Next scene */}
      <button
        type="button"
        onClick={handleNext}
        disabled={isLastScene}
        className={cn(
          'shrink-0 p-1.5 rounded-lg transition-colors',
          'text-gray-500 hover:bg-gray-100 hover:text-gray-700',
          'disabled:opacity-30 disabled:cursor-not-allowed',
          'focus:outline-none focus:ring-2 focus:ring-primary-500',
        )}
        aria-label="Next scene"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </div>
  );
});
