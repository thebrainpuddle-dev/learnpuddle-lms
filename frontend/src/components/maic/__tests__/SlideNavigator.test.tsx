// SlideNavigator.test.tsx — scene navigation for mixed classrooms
//
// SlideNavigator renders the bottom scene strip with a "Scene N of M" counter.
// Mixed v2 classrooms include slide, quiz, interactive, and PBL scenes.
// The navigator must keep every scene reachable even when only some scenes
// own slide screens.
//
// Cases covered:
//   1. Renders normally when activeSceneIdx matches a navScenes entry.
//   2. Returns null only when there are no scenes.
//   3. Renders non-slide scenes without a stale "Scene –" counter.

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

describe('SlideNavigator — mixed scene UX', () => {
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

  test('returns null when there are no scenes', () => {
    useMAICStageStore.setState({
      scenes: [],
      sceneSlideBounds: [],
      currentSceneIndex: 0,
      currentSlideIndex: 0,
    });

    const { container } = render(<SlideNavigator />);
    expect(container.firstChild).toBeNull();
  });

  test('renders non-slide active scenes as first-class navigation targets', () => {
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
    expect(container.firstChild).not.toBeNull();
    expect(screen.getByRole('navigation', { name: /scene navigation/i })).toBeInTheDocument();
    expect(screen.getByText(/Scene 2 of 3/)).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /2\s*Quiz/i })).toHaveAttribute('aria-selected', 'true');
  });
});
