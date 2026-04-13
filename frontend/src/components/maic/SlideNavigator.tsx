// src/components/maic/SlideNavigator.tsx
//
// Bottom navigation bar with horizontal scrollable slide thumbnails,
// current slide indicator, play/pause button, and prev/next arrows.

import React, { useRef, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Play, Pause } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { cn } from '../../lib/utils';

export const SlideNavigator = React.memo(function SlideNavigator() {
  const slides = useMAICStageStore((s) => s.slides);
  const scenes = useMAICStageStore((s) => s.scenes);
  const currentSlideIndex = useMAICStageStore((s) => s.currentSlideIndex);
  const goToSlide = useMAICStageStore((s) => s.goToSlide);
  const nextSlide = useMAICStageStore((s) => s.nextSlide);
  const prevSlide = useMAICStageStore((s) => s.prevSlide);
  const isPlaying = useMAICStageStore((s) => s.isPlaying);
  const setPlaying = useMAICStageStore((s) => s.setPlaying);

  // Use scenes count when scenes exist, otherwise slides count
  const totalCount = scenes.length > 0 ? scenes.length : slides.length;

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const thumbnailRefs = useRef<Map<number, HTMLButtonElement>>(new Map());

  // Scroll active thumbnail into view
  useEffect(() => {
    const thumb = thumbnailRefs.current.get(currentSlideIndex);
    if (thumb) {
      thumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }
  }, [currentSlideIndex]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
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
  };

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

      {/* Thumbnail strip */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-x-auto flex items-center gap-1.5 px-1 scrollbar-thin scrollbar-thumb-gray-300"
        role="tablist"
        aria-label="Slide thumbnails"
      >
        {Array.from({ length: totalCount }, (_, index) => {
          const slide = slides[index];
          const scene = scenes[index];
          const isActive = index === currentSlideIndex;
          const title = scene?.title || slide?.title || `Slide ${index + 1}`;
          const bg = slide?.background || '#ffffff';
          return (
            <button
              key={scene?.id || slide?.id || index}
              ref={(el) => {
                if (el) thumbnailRefs.current.set(index, el);
                else thumbnailRefs.current.delete(index);
              }}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-label={`Slide ${index + 1}: ${title}`}
              onClick={() => goToSlide(index)}
              className={cn(
                'shrink-0 w-16 h-10 rounded border-2 transition-all overflow-hidden',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1',
                isActive
                  ? 'border-primary-500 shadow-sm'
                  : 'border-gray-200 hover:border-gray-300 opacity-70 hover:opacity-100',
              )}
              style={{ background: bg }}
            >
              <div className="h-full w-full flex items-center justify-center">
                <span className="text-[8px] text-gray-400 font-medium truncate px-0.5">
                  {index + 1}
                </span>
              </div>
            </button>
          );
        })}
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
