// SlideNavigator.test.tsx — counter null-state UX (BUNDLE-2026-04-29-FX-3)
//
// SlideNavigator renders the bottom scene strip with a "Scene N of M" counter.
// When the active scene isn't a slide-bearing scene (e.g. quiz / pbl /
// interactive), `activeNavPosition` is null and showing a stale counter
// like "Scene – of N" is confusing — the navigator should hide entirely.
//
// Cases covered:
//   1. Renders normally when activeSceneIdx matches a navScenes entry.
//   2. Returns null when navScenes is empty (no slide-bearing scenes).
//   3. Returns null when activeSceneIdx doesn't match any navScenes entry
//      (user is on a non-slide scene like quiz/pbl/interactive).

import { describe, expect, test, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SlideNavigator } from '../SlideNavigator';
import { useMAICStageStore } from '../../../stores/maicStageStore';
import type { MAICScene, SceneSlideBounds } from '../../../types/maic-scenes';

function makeScene(overrides: Partial<MAICScene> = {}): MAICScene {
  return {
    id: 'scene-x',
    title: 'Scene X',
    type: 'lecture',
    actions: [],
    ...overrides,
  } as MAICScene;
}

describe('SlideNavigator — null-state UX', () => {
  beforeEach(() => {
    // Reset store between cases so leaked state from one test can't mask
    // the rendering decisions in the next.
    useMAICStageStore.setState({
      scenes: [],
      sceneSlideBounds: [],
      currentSceneIndex: 0,
      currentSlideIndex: 0,
      isPlaying: false,
    });
  });

  test('renders normally when active scene is a slide-bearing scene', () => {
    const scenes: MAICScene[] = [
      makeScene({ id: 's1', title: 'Intro', type: 'lecture' }),
      makeScene({ id: 's2', title: 'Deep Dive', type: 'lecture' }),
    ];
    const sceneSlideBounds: SceneSlideBounds[] = [
      { sceneIdx: 0, startSlide: 0, endSlide: 1 },
      { sceneIdx: 1, startSlide: 2, endSlide: 3 },
    ];
    useMAICStageStore.setState({
      scenes,
      sceneSlideBounds,
      currentSceneIndex: 0,
      currentSlideIndex: 0,
    });

    const { container } = render(<SlideNavigator />);
    // Navigator is mounted (non-empty) and shows the position label.
    expect(container.firstChild).not.toBeNull();
    expect(screen.getByRole('navigation', { name: /scene navigation/i })).toBeInTheDocument();
    // Counter shows real "Scene N of M", not the en-dash placeholder.
    expect(screen.getByText(/Scene 1 of 2/)).toBeInTheDocument();
  });

  test('returns null when navScenes is empty (no slide-bearing scenes)', () => {
    // No bounds at all — every scene is non-slide-bearing or generation
    // hasn't produced slides yet.
    useMAICStageStore.setState({
      scenes: [makeScene({ id: 's1', title: 'Quiz', type: 'quiz' })],
      sceneSlideBounds: [],
      currentSceneIndex: 0,
      currentSlideIndex: 0,
    });

    const { container } = render(<SlideNavigator />);
    expect(container.firstChild).toBeNull();
  });

  test('returns null when active scene is not in navScenes (quiz / pbl / interactive)', () => {
    // Three scenes — slide-bearing ones at index 0 and 2; index 1 is a
    // non-slide scene (e.g. quiz). The user is currently on the quiz scene.
    const scenes: MAICScene[] = [
      makeScene({ id: 's1', title: 'Intro', type: 'lecture' }),
      makeScene({ id: 's2', title: 'Quiz', type: 'quiz' }),
      makeScene({ id: 's3', title: 'Outro', type: 'lecture' }),
    ];
    const sceneSlideBounds: SceneSlideBounds[] = [
      { sceneIdx: 0, startSlide: 0, endSlide: 1 },
      { sceneIdx: 2, startSlide: 2, endSlide: 3 },
    ];
    useMAICStageStore.setState({
      scenes,
      sceneSlideBounds,
      currentSceneIndex: 1, // quiz scene — no bounds entry
      currentSlideIndex: -1, // outside any bounds range
    });

    const { container } = render(<SlideNavigator />);
    expect(container.firstChild).toBeNull();
  });
});
