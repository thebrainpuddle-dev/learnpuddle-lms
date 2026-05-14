import { beforeEach, describe, expect, test } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SceneSidebar } from '../SceneSidebar';
import { useMAICStageStore } from '../../../stores/maicStageStore';
import type { MAICScene } from '../../../types/maic-scenes';
import type { MAICSlide } from '../../../types/maic';

function scene(id: string, type: MAICScene['type'], order: number): MAICScene {
  return {
    id,
    type,
    title: id,
    order,
    content: type === 'slide'
      ? { type: 'slide', elements: [] }
      : type === 'quiz'
        ? { type: 'quiz', questions: [] }
        : type === 'interactive'
          ? { type: 'interactive', html: '' }
          : { type: 'pbl', projectConfig: {} },
    actions: [],
  } as MAICScene;
}

function slide(id: string): MAICSlide {
  return {
    id,
    title: id,
    elements: [{ id: `${id}-text`, type: 'text', x: 0, y: 0, width: 100, height: 20, content: id }],
    background: '#fff',
  } as MAICSlide;
}

describe('SceneSidebar mixed scenes', () => {
  beforeEach(() => {
    useMAICStageStore.getState().reset();
  });

  test('uses honest activity and slide-screen summary for sparse bounds', () => {
    useMAICStageStore.setState({
      scenes: [
        scene('Intro', 'slide', 1),
        scene('Check', 'quiz', 2),
        scene('Garden Design', 'slide', 3),
        scene('Project', 'pbl', 4),
      ],
      slides: [slide('slide-1'), slide('slide-2')],
      sceneSlideBounds: [
        { sceneIdx: 0, startSlide: 0, endSlide: 0 },
        { sceneIdx: 2, startSlide: 1, endSlide: 1 },
      ],
      currentSceneIndex: 1,
      currentSlideIndex: 0,
    });

    render(<SceneSidebar visible onClose={() => {}} />);

    expect(screen.getByText('4 activities · 2 slide screens')).toBeInTheDocument();
    expect(screen.getByText('Check')).toBeInTheDocument();
    expect(screen.getByText('Garden Design')).toBeInTheDocument();
    expect(screen.getAllByText(/1 slide/)).toHaveLength(2);
  });
});
