// src/components/maic/__tests__/SlideRenderer.bodyImageRight.test.tsx
//
// F4 (P0) — Typed slide schema with role discriminator.
//
// Verifies the slot-aware `body-image-right` template renderer:
//   1. Full slots → title + body + image + footer rendered via CSS grid.
//   2. Empty image src + imagesPending → shimmer skeleton (no Unsplash).
//   3. template set but `slots` undefined → falls back to legacy
//      `elements[]` free-form renderer (backward compat).
//   4. No `template` field → legacy free-form path is used unchanged
//      (sanity check that the new code path is opt-in only).

import React from 'react';
import { describe, test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SlideRenderer } from '../SlideRenderer';
import type { MAICSlide } from '../../../types/maic';

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock('../../../stores/maicSettingsStore', () => ({
  useMAICSettingsStore: (selector: (s: { slideTransition: string }) => unknown) =>
    selector({ slideTransition: 'none' }),
}));

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('SlideRenderer — body-image-right template (F4)', () => {
  test('renders title + body + image + footer slots in a grid layout', () => {
    const slide: MAICSlide = {
      id: 'tpl-slide-1',
      title: 'Photosynthesis basics',
      elements: [],
      template: 'body-image-right',
      slots: {
        title: { text: 'How plants make food' },
        body: {
          text: 'Plants convert light into chemical energy.',
          bullets: ['Chlorophyll absorbs light', 'CO2 is fixed into sugar'],
        },
        image: {
          src: 'https://images.example.com/photosynthesis.jpg',
          alt: 'Diagram of photosynthesis',
        },
        footer: { text: 'Source: Botany 101 textbook' },
      },
    };

    render(<SlideRenderer slide={slide} />);

    // Wrapper marker so e2e tests / consumers can target the template.
    const wrapper = document.querySelector(
      '[data-testid="slide-template-body-image-right"]',
    );
    expect(wrapper).not.toBeNull();

    // Slot-level test ids exist.
    expect(
      document.querySelector('[data-testid="slide-slot-title"]'),
    ).not.toBeNull();
    expect(
      document.querySelector('[data-testid="slide-slot-body"]'),
    ).not.toBeNull();
    expect(
      document.querySelector('[data-testid="slide-slot-image"]'),
    ).not.toBeNull();
    expect(
      document.querySelector('[data-testid="slide-slot-footer"]'),
    ).not.toBeNull();

    // Text content from slots is present.
    expect(screen.getByText('How plants make food')).toBeDefined();
    expect(
      screen.getByText('Plants convert light into chemical energy.'),
    ).toBeDefined();
    expect(screen.getByText('Chlorophyll absorbs light')).toBeDefined();
    expect(screen.getByText('CO2 is fixed into sugar')).toBeDefined();
    expect(screen.getByText('Source: Botany 101 textbook')).toBeDefined();

    // Image rendered with the supplied src + alt.
    const imgs = document.querySelectorAll('img');
    expect(imgs.length).toBeGreaterThan(0);
    expect(imgs[0].getAttribute('src')).toBe(
      'https://images.example.com/photosynthesis.jpg',
    );
    expect(imgs[0].getAttribute('alt')).toBe('Diagram of photosynthesis');
  });

  test('maps backing element ids onto slot DOM nodes for action targeting', () => {
    const slide: MAICSlide = {
      id: 'tpl-targetable-slots',
      title: 'Targetable slots',
      template: 'body-image-right',
      elements: [
        { type: 'text', id: 'el-title', x: 0, y: 0, width: 100, height: 40, content: 'Title' },
        { type: 'text', id: 'el-body', x: 0, y: 50, width: 100, height: 100, content: 'Body' },
        { type: 'image', id: 'el-image', x: 100, y: 50, width: 100, height: 100, content: 'Parabola graph', src: '' },
        { type: 'text', id: 'el-footer', x: 0, y: 170, width: 100, height: 30, content: 'Footer' },
      ],
      slots: {
        title: { text: 'Quadratic launch' },
        body: { text: 'Use the graph to reason about roots.' },
        image: { src: 'https://images.example.com/graph.jpg', alt: 'Parabola graph' },
        footer: { text: 'Practice checkpoint' },
      },
    };

    render(<SlideRenderer slide={slide} />);

    expect(document.querySelector('[data-testid="slide-slot-title"]')?.id).toBe('el-title');
    expect(document.querySelector('[data-testid="slide-slot-body"]')?.id).toBe('el-body');
    expect(document.querySelector('[data-testid="slide-slot-image"]')?.id).toBe('el-image');
    expect(document.querySelector('[data-testid="slide-slot-footer"]')?.id).toBe('el-footer');
  });

  test('shows shimmer skeleton when image src is empty AND imagesPending=true', () => {
    const slide: MAICSlide = {
      id: 'tpl-slide-2',
      title: 'Pending image',
      elements: [],
      template: 'body-image-right',
      slots: {
        title: { text: 'Loading visual' },
        body: { text: 'Body text here' },
        image: { src: '', alt: 'Pending diagram' },
      },
    };

    render(<SlideRenderer slide={slide} imagesPending={true} />);

    // The slot wrapper is still rendered.
    expect(
      document.querySelector('[data-testid="slide-template-body-image-right"]'),
    ).not.toBeNull();

    // The fetching skeleton is rendered inside the image slot.
    const skeleton = document.querySelector(
      '[data-testid="image-fetching-skeleton"]',
    );
    expect(skeleton).not.toBeNull();
    expect(screen.getByText('Fetching image…')).toBeDefined();
  });

  test('falls back to legacy elements[] renderer when template is set but slots is undefined', () => {
    // template field present without `slots` — must NOT crash and must
    // render the legacy elements[] path so existing content keeps working.
    const slide: MAICSlide = {
      id: 'tpl-slide-3',
      title: 'No slots',
      template: 'body-image-right',
      // slots intentionally omitted
      elements: [
        {
          type: 'text',
          id: 'legacy-text-1',
          x: 10,
          y: 10,
          width: 400,
          height: 60,
          content: 'Legacy free-form text element',
        },
      ],
    };

    render(<SlideRenderer slide={slide} />);

    // Template wrapper must NOT be present — we fell back to free-form.
    expect(
      document.querySelector('[data-testid="slide-template-body-image-right"]'),
    ).toBeNull();

    // Legacy element content is rendered.
    expect(
      screen.getByText('Legacy free-form text element'),
    ).toBeDefined();
  });

  test('renders legacy elements[] path unchanged when slide has no template field', () => {
    const slide: MAICSlide = {
      id: 'legacy-slide-1',
      title: 'Legacy slide',
      elements: [
        {
          type: 'text',
          id: 'legacy-text-2',
          x: 10,
          y: 10,
          width: 400,
          height: 60,
          content: 'Pure free-form slide',
        },
      ],
    };

    render(<SlideRenderer slide={slide} />);

    // No new template wrapper.
    expect(
      document.querySelector('[data-testid="slide-template-body-image-right"]'),
    ).toBeNull();

    // Legacy content present.
    expect(screen.getByText('Pure free-form slide')).toBeDefined();
  });

  // ─── WAVE-6-F4-F3 — Empty-slot Unsplash bypass ───────────────────────────
  test('does NOT render Unsplash fallback or right-column track when slots.image is an empty object {}', () => {
    // Reviewer flagged that `hasImage = !!image` was true for `image: {}`,
    // so a slide with an empty image object would still allocate the right
    // column AND fall through to the random Unsplash fallback — bypassing
    // both the imageProviderDisabled honest placeholder and the spirit of
    // the slot schema (no src/alt → no image).
    const slide: MAICSlide = {
      id: 'tpl-empty-image',
      title: 'Empty image slot',
      elements: [],
      template: 'body-image-right',
      slots: {
        title: { text: 'Slot present, content absent' },
        body: { text: 'Body still renders' },
        image: {
          // empty object — no src, no alt
          meta: { imageProviderDisabled: true },
        },
      },
    };

    render(<SlideRenderer slide={slide} imagesPending={false} />);

    // The image slot itself MUST NOT be rendered — there's nothing to show.
    expect(
      document.querySelector('[data-testid="slide-slot-image"]'),
    ).toBeNull();

    // No <img> at all (no Unsplash fallback, no real src).
    expect(document.querySelectorAll('img').length).toBe(0);

    // Title + body still render.
    expect(screen.getByText('Slot present, content absent')).toBeDefined();
    expect(screen.getByText('Body still renders')).toBeDefined();
  });

  // ─── WAVE-6-F4-F6 — slide.title fallback when slots.title missing ────────
  test('falls back to slide.title when slots.title is missing', () => {
    // The generator's "Untitled" fallback flows through the outer
    // slide.title, so the slot template must honour it when the LLM omits
    // slots.title.
    const slide: MAICSlide = {
      id: 'tpl-fallback-title',
      title: 'Outer',
      elements: [],
      template: 'body-image-right',
      slots: {
        body: { text: 'Body content here' },
        // slots.title intentionally omitted
      },
    };

    render(<SlideRenderer slide={slide} />);

    // Title slot is rendered with the outer slide.title text.
    const titleEl = document.querySelector('[data-testid="slide-slot-title"]');
    expect(titleEl).not.toBeNull();
    expect(titleEl?.textContent).toBe('Outer');
  });

  test('prefers slots.title.text over slide.title when both are set', () => {
    const slide: MAICSlide = {
      id: 'tpl-prefer-slot-title',
      title: 'Outer',
      elements: [],
      template: 'body-image-right',
      slots: {
        title: { text: 'Inner' },
        body: { text: 'Body content here' },
      },
    };

    render(<SlideRenderer slide={slide} />);

    const titleEl = document.querySelector('[data-testid="slide-slot-title"]');
    expect(titleEl).not.toBeNull();
    expect(titleEl?.textContent).toBe('Inner');
  });
});
