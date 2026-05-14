import { beforeEach, describe, expect, test } from 'vitest';
import { useMAICStageStore } from '../maicStageStore';
import type { MAICScene } from '../../types/maic-scenes';
import type { MAICSlide } from '../../types/maic';

function scene(id: string, type: MAICScene['type']): MAICScene {
  return {
    id,
    type,
    title: id,
    order: Number(id.replace(/\D/g, '')) || 1,
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
  return { id, title: id, elements: [], background: '#fff' };
}

describe('maicStageStore scene bounds', () => {
  beforeEach(() => {
    useMAICStageStore.getState().reset();
  });

  test('goToScene resolves sparse bounds by sceneIdx instead of array index', () => {
    useMAICStageStore.setState({
      scenes: [scene('s1', 'slide'), scene('s2', 'quiz'), scene('s3', 'slide')],
      slides: [slide('slide-0'), slide('slide-1'), slide('slide-2'), slide('slide-3')],
      sceneSlideBounds: [
        { sceneIdx: 0, startSlide: 0, endSlide: 1 },
        { sceneIdx: 2, startSlide: 2, endSlide: 3 },
      ],
      currentSceneIndex: 0,
      currentSlideIndex: 0,
    });

    useMAICStageStore.getState().goToScene(2);

    const state = useMAICStageStore.getState();
    expect(state.currentSceneIndex).toBe(2);
    expect(state.currentSlideIndex).toBe(2);
    expect(state.getCurrentSceneSlides().map((s) => s.id)).toEqual(['slide-2', 'slide-3']);
  });

  test('goToScene keeps non-slide scenes active without borrowing another scene slide', () => {
    useMAICStageStore.setState({
      scenes: [scene('s1', 'slide'), scene('s2', 'pbl'), scene('s3', 'slide')],
      slides: [slide('slide-0'), slide('slide-1')],
      sceneSlideBounds: [
        { sceneIdx: 0, startSlide: 0, endSlide: 0 },
        { sceneIdx: 2, startSlide: 1, endSlide: 1 },
      ],
      currentSceneIndex: 0,
      currentSlideIndex: 0,
    });

    useMAICStageStore.getState().goToScene(1);

    const state = useMAICStageStore.getState();
    expect(state.currentSceneIndex).toBe(1);
    expect(state.currentSlideIndex).toBe(0);
    expect(state.getCurrentSceneSlides()).toEqual([]);
  });

  test('goToSlide maps back to the owning sceneIdx for sparse bounds', () => {
    useMAICStageStore.setState({
      scenes: [scene('s1', 'slide'), scene('s2', 'quiz'), scene('s3', 'slide')],
      slides: [slide('slide-0'), slide('slide-1'), slide('slide-2'), slide('slide-3')],
      sceneSlideBounds: [
        { sceneIdx: 0, startSlide: 0, endSlide: 1 },
        { sceneIdx: 2, startSlide: 2, endSlide: 3 },
      ],
      currentSceneIndex: 0,
      currentSlideIndex: 0,
    });

    useMAICStageStore.getState().goToSlide(3);

    const state = useMAICStageStore.getState();
    expect(state.currentSceneIndex).toBe(2);
    expect(state.currentSlideIndex).toBe(3);
  });

  test('setSceneSlideBounds drops stale fake bounds for non-slide scenes', () => {
    useMAICStageStore.setState({
      scenes: [scene('s1', 'slide'), scene('s2', 'quiz'), scene('s3', 'interactive'), scene('s4', 'pbl')],
      slides: [slide('slide-0')],
      currentSceneIndex: 0,
      currentSlideIndex: 0,
    });

    useMAICStageStore.getState().setSceneSlideBounds([
      { sceneIdx: 0, startSlide: 0, endSlide: 0 },
      { sceneIdx: 1, startSlide: 0, endSlide: 0 },
      { sceneIdx: 2, startSlide: 0, endSlide: 0 },
      { sceneIdx: 3, startSlide: 0, endSlide: 0 },
    ]);

    expect(useMAICStageStore.getState().sceneSlideBounds).toEqual([
      { sceneIdx: 0, startSlide: 0, endSlide: 0 },
    ]);
  });
});
