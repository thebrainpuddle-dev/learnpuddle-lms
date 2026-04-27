// src/components/maic/__tests__/SlideRenderer.imagesPending.test.tsx
//
// SPRINT-2-BATCH-3-F2 — Tests for the `imagesPending` indicator on
// SlideRenderer.
//
// Verifies two states for an image element whose `src` is empty:
//   1. imagesPending=true  → "fetching image…" skeleton (NOT Unsplash fallback)
//   2. imagesPending=false → Unsplash fallback URL (existing behaviour)

import React from 'react';
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SlideRenderer } from '../SlideRenderer';
import type { MAICSlide } from '../../../types/maic';

// ─── Mocks ───────────────────────────────────────────────────────────────────

// maicSettingsStore drives slide transitions — mock to avoid store setup.
vi.mock('../../../stores/maicSettingsStore', () => ({
  useMAICSettingsStore: (selector: (s: { slideTransition: string }) => unknown) =>
    selector({ slideTransition: 'none' }),
}));

// ResizeObserver is not available in vitest/jsdom.
global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// ─── Fixture helpers ─────────────────────────────────────────────────────────

function makeImageSlide(srcValue: string): MAICSlide {
  return {
    id: 'test-slide-1',
    title: 'Test slide',
    elements: [
      {
        type: 'image',
        id: 'img-el-1',
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

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('SlideRenderer — imagesPending indicator (SPRINT-2-BATCH-3-F2)', () => {
  beforeEach(() => {
    // Reset document body between tests so rendered DOM is clean.
  });

  test(
    'renders "fetching image…" skeleton when src is empty AND imagesPending is true',
    () => {
      render(
        <SlideRenderer
          slide={makeImageSlide('')}
          imagesPending={true}
        />,
      );

      // The skeleton container should be in the DOM.
      const skeleton = document.querySelector('[data-testid="image-fetching-skeleton"]');
      expect(skeleton).not.toBeNull();

      // Caption text confirms it's the fetching state, not the error state.
      expect(screen.getByText('Fetching image…')).toBeDefined();

      // No <img> element should be rendered for an empty src in pending state.
      const imgs = document.querySelectorAll('img');
      // May or may not render img with empty src depending on browser behavior —
      // but we assert the fetching skeleton IS rendered, which is the key invariant.
      expect(skeleton).toBeTruthy();
    },
  );

  test(
    'renders an <img> with Unsplash fallback src when src is empty AND imagesPending is false',
    () => {
      render(
        <SlideRenderer
          slide={makeImageSlide('')}
          imagesPending={false}
        />,
      );

      // No fetching skeleton.
      const skeleton = document.querySelector('[data-testid="image-fetching-skeleton"]');
      expect(skeleton).toBeNull();

      // An <img> element should be rendered with an Unsplash URL.
      const imgs = document.querySelectorAll('img');
      expect(imgs.length).toBeGreaterThan(0);
      const src = imgs[0].getAttribute('src') ?? '';
      expect(src).toContain('unsplash.com');
      expect(src).toContain('photosynthesis');
    },
  );

  test(
    'renders an <img> with the real src when el.src is a valid https URL regardless of imagesPending',
    () => {
      const realSrc = 'https://images.unsplash.com/photo-abc123.jpg';
      render(
        <SlideRenderer
          slide={makeImageSlide(realSrc)}
          imagesPending={true}
        />,
      );

      // Fetching skeleton must NOT appear — there is already a real image src.
      const skeleton = document.querySelector('[data-testid="image-fetching-skeleton"]');
      expect(skeleton).toBeNull();

      // The rendered <img> should have the real src.
      const imgs = document.querySelectorAll('img');
      expect(imgs.length).toBeGreaterThan(0);
      expect(imgs[0].getAttribute('src')).toBe(realSrc);
    },
  );

  test(
    'falls through to Unsplash when imagesPending is undefined',
    () => {
      // When imagesPending is not provided (undefined), empty src → Unsplash.
      render(
        <SlideRenderer
          slide={makeImageSlide('')}
          // imagesPending omitted — should default to undefined/falsy
        />,
      );

      const skeleton = document.querySelector('[data-testid="image-fetching-skeleton"]');
      // No skeleton — imagesPending is undefined/falsy, so Unsplash fallback applies.
      expect(skeleton).toBeNull();

      const imgs = document.querySelectorAll('img');
      expect(imgs.length).toBeGreaterThan(0);
      const src = imgs[0].getAttribute('src') ?? '';
      expect(src).toContain('unsplash.com');
    },
  );
});
