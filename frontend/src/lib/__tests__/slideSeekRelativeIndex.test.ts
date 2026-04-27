// slideSeekRelativeIndex.test.ts
//
// CG-P0-9: when the user manually clicks a slide, Stage converts the
// store's absolute `currentSlideIndex` to a SCENE-RELATIVE index using
// `sceneSlideBounds` and calls `engine.seekToSlidePaused(relative)`.
//
// `TransitionAction.slideIndex` is documented as scene-relative, so the
// engine's `resolveSlideSeekTarget` matches against scene-relative values.
// Passing the absolute index would never match → engine falls back to
// action 0 → audio always restarts from the scene intro regardless of
// which slide the user clicked.
//
// This test locks in the conversion logic that lives inline in Stage.tsx.
// Pure-function shape so we can verify it without rendering the whole
// Stage component.

import { describe, it, expect } from 'vitest';
import type { SceneSlideBounds } from '../../types/maic-scenes';

/** Mirror of the inline conversion in Stage.tsx — kept here so the
 *  contract is unit-testable. If you tweak the inline version, mirror it. */
function absoluteToSceneRelativeSlideIndex(
  absoluteSlideIndex: number,
  sceneSlideBounds: SceneSlideBounds[],
): number {
  const bound = sceneSlideBounds.find(
    (b) => absoluteSlideIndex >= b.startSlide && absoluteSlideIndex <= b.endSlide,
  );
  return bound ? absoluteSlideIndex - bound.startSlide : absoluteSlideIndex;
}

describe('CG-P0-9 — absolute → scene-relative slide index conversion', () => {
  // Realistic OpenClaw-style layout: 3 scenes, 4 slides each, total 12.
  const bounds: SceneSlideBounds[] = [
    { sceneIdx: 0, startSlide: 0, endSlide: 3 },
    { sceneIdx: 1, startSlide: 4, endSlide: 7 },
    { sceneIdx: 2, startSlide: 8, endSlide: 11 },
  ];

  it('first slide of first scene maps to relative 0', () => {
    expect(absoluteToSceneRelativeSlideIndex(0, bounds)).toBe(0);
  });

  it('mid-scene slide maps to its within-scene offset', () => {
    expect(absoluteToSceneRelativeSlideIndex(2, bounds)).toBe(2);
  });

  it('first slide of a non-first scene maps to relative 0', () => {
    // Absolute 4 = scene 1 startSlide → relative 0
    expect(absoluteToSceneRelativeSlideIndex(4, bounds)).toBe(0);
  });

  it('mid-scene slide of a non-first scene maps to within-scene offset', () => {
    // Absolute 6 = scene 1 startSlide(4) + 2 → relative 2
    expect(absoluteToSceneRelativeSlideIndex(6, bounds)).toBe(2);
  });

  it('last slide of last scene maps to within-scene offset', () => {
    // Absolute 11 = scene 2 startSlide(8) + 3 → relative 3
    expect(absoluteToSceneRelativeSlideIndex(11, bounds)).toBe(3);
  });

  it('falls back to absolute index when sceneSlideBounds is empty (legacy 1:1)', () => {
    expect(absoluteToSceneRelativeSlideIndex(7, [])).toBe(7);
  });

  it('falls back to absolute index when no bound contains the slide (out-of-range)', () => {
    expect(absoluteToSceneRelativeSlideIndex(99, bounds)).toBe(99);
  });

  it('CRITICAL: absolute index does NOT equal scene-relative for non-first scenes', () => {
    // The whole point of this conversion. Pre-fix, Stage was calling
    // seekToSlidePaused(absolute) and the engine never found a matching
    // transition (transitions store scene-relative slideIndex). Lock in
    // that distinction so a future "simplification" doesn't regress.
    const abs = 9; // scene 2's slide 1
    expect(abs).not.toBe(absoluteToSceneRelativeSlideIndex(abs, bounds));
    expect(absoluteToSceneRelativeSlideIndex(abs, bounds)).toBe(1);
  });
});
