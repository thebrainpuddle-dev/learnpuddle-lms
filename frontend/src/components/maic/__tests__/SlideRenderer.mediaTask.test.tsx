// src/components/maic/__tests__/SlideRenderer.mediaTask.test.tsx
//
// F2 (P0) — verifies per-element media-task store integration in
// SlideRenderer. Specifically:
//   - task `done` overrides el.src (server URL takes precedence);
//   - task `pending`/`generating` shows the shimmer skeleton;
//   - task `failed` shows the "Image unavailable" placeholder + retry;
//   - missing task (legacy callers / classrooms generated before F2) falls
//     through to `imagesPending` or an honest unavailable placeholder.

import React from 'react';
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SlideRenderer } from '../SlideRenderer';
import { useMaicMediaGenerationStore } from '../../../stores/maicMediaGenerationStore';
import type { MAICSlide } from '../../../types/maic';

vi.mock('../../../stores/maicSettingsStore', () => ({
  useMAICSettingsStore: (selector: (s: { slideTransition: string }) => unknown) =>
    selector({ slideTransition: 'none' }),
}));

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const SCENE_IDX = 2;
const SLIDE_IDX = 1;
const ELEMENT_IDX = 0;
const ELEMENT_ID = 'img-el-1';
const ELEMENT_KEY = `${SCENE_IDX}:${SLIDE_IDX}:${ELEMENT_IDX}:${ELEMENT_ID}`;
const CR = 'classroom-uuid-1';

function makeImageSlide(srcValue: string): MAICSlide {
  return {
    id: 'test-slide-1',
    title: 'Test slide',
    elements: [
      {
        type: 'image',
        id: ELEMENT_ID,
        x: 0,
        y: 0,
        width: 400,
        height: 225,
        content: 'photosynthesis',
        src: srcValue,
      },
    ],
  };
}

beforeEach(() => {
  useMaicMediaGenerationStore.getState().resetAll();
});

describe('SlideRenderer — F2 per-element media task', () => {
  test('task `done` overrides el.src with task.src', () => {
    useMaicMediaGenerationStore.getState().hydrateFromMap(CR, {
      [ELEMENT_KEY]: {
        status: 'done',
        src: 'https://cdn.example/from-task.jpg',
        updated_at: '2026-04-28T12:00:00Z',
      },
    });

    render(
      <SlideRenderer
        slide={makeImageSlide('https://cdn.example/old-from-el.jpg')}
        sceneIndex={SCENE_IDX}
        slideIndex={SLIDE_IDX}
      />,
    );

    const imgs = document.querySelectorAll('img');
    expect(imgs.length).toBeGreaterThan(0);
    expect(imgs[0].getAttribute('src')).toBe('https://cdn.example/from-task.jpg');
  });

  test('task `pending` shows shimmer skeleton (regardless of el.src or imagesPending)', () => {
    useMaicMediaGenerationStore.getState().hydrateFromMap(CR, {
      [ELEMENT_KEY]: { status: 'pending', updated_at: '2026-04-28T12:00:00Z' },
    });

    render(
      <SlideRenderer
        slide={makeImageSlide('https://cdn.example/already.jpg')}
        sceneIndex={SCENE_IDX}
        slideIndex={SLIDE_IDX}
        imagesPending={false}
      />,
    );

    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).not.toBeNull();
    expect(screen.getByText('Fetching image…')).toBeDefined();
    // No <img> tag in pending state.
    expect(document.querySelector('img')).toBeNull();
  });

  test('task `generating` shows shimmer skeleton', () => {
    useMaicMediaGenerationStore.getState().hydrateFromMap(CR, {
      [ELEMENT_KEY]: { status: 'generating' },
    });

    render(
      <SlideRenderer
        slide={makeImageSlide('')}
        sceneIndex={SCENE_IDX}
        slideIndex={SLIDE_IDX}
      />,
    );

    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).not.toBeNull();
  });

  test('task `failed` shows Image unavailable placeholder with disabled retry button', () => {
    useMaicMediaGenerationStore.getState().hydrateFromMap(CR, {
      [ELEMENT_KEY]: {
        status: 'failed',
        error_code: 'CONTENT_SENSITIVE',
        updated_at: '2026-04-28T12:00:00Z',
      },
    });

    render(
      <SlideRenderer
        slide={makeImageSlide('')}
        sceneIndex={SCENE_IDX}
        slideIndex={SLIDE_IDX}
      />,
    );

    expect(
      document.querySelector('[data-testid="image-failed-placeholder"]'),
    ).not.toBeNull();
    expect(screen.getByText('Image unavailable')).toBeDefined();
    const btn = document.querySelector(
      '[data-testid="image-retry-button"]',
    ) as HTMLButtonElement | null;
    expect(btn).not.toBeNull();
    expect(btn?.disabled).toBe(true);
  });

  test('legacy fallback — no task entry, no sceneIndex → falls through to imagesPending path', () => {
    // Hydrate the store WITHOUT this element_key so the lookup misses.
    useMaicMediaGenerationStore.getState().hydrateFromMap(CR, {
      'unrelated-key': { status: 'done', src: 'https://other' },
    });

    render(
      <SlideRenderer
        slide={makeImageSlide('')}
        // sceneIndex/slideIndex omitted — legacy caller
        imagesPending={true}
      />,
    );

    // imagesPending=true → fetching skeleton (legacy behaviour) still shown.
    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).not.toBeNull();
  });

  test('sceneIndex/slideIndex supplied but no task entry → empty placeholder when not pending', () => {
    // Empty store but sceneIndex+slideIndex provided.
    render(
      <SlideRenderer
        slide={makeImageSlide('')}
        sceneIndex={SCENE_IDX}
        slideIndex={SLIDE_IDX}
        imagesPending={false}
      />,
    );

    // No skeleton (imagesPending=false), no random remote fallback.
    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).toBeNull();
    expect(
      document.querySelector('[data-testid="image-empty-placeholder"]'),
    ).not.toBeNull();
    expect(document.querySelector('img')).toBeNull();
  });

  test('task `done` with a non-allowlisted src is rejected, falls through to el.src', () => {
    useMaicMediaGenerationStore.getState().hydrateFromMap(CR, {
      [ELEMENT_KEY]: {
        status: 'done',
        src: 'data:text/html;base64,evil', // SEC-P0-4 block
      },
    });

    render(
      <SlideRenderer
        slide={makeImageSlide('https://cdn.example/safe.jpg')}
        sceneIndex={SCENE_IDX}
        slideIndex={SLIDE_IDX}
      />,
    );

    const imgs = document.querySelectorAll('img');
    expect(imgs.length).toBeGreaterThan(0);
    expect(imgs[0].getAttribute('src')).toBe('https://cdn.example/safe.jpg');
  });
});
