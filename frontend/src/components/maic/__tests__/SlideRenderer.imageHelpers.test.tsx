// src/components/maic/__tests__/SlideRenderer.imageHelpers.test.tsx
//
// WAVE-6-F4-F1 — exercises the shared image-render helpers extracted from
// the duplicated copies in `BodyImageRightTemplate` and the legacy
// `ImageElement`. The helpers are the single source of truth for:
//   - the SEC-P0-4 allow-list (`resolveImageSrc`)
//   - the shimmer "Fetching image…" skeleton
//   - the "Image unavailable" failure placeholder
//   - the "AI images disabled" honest placeholder
//   - the success-path <img>

import React from 'react';
import { describe, test, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  ImageWithFallbacks,
  resolveImageSrc,
} from '../SlideRenderer';

vi.mock('../../../stores/maicSettingsStore', () => ({
  useMAICSettingsStore: (selector: (s: { slideTransition: string }) => unknown) =>
    selector({ slideTransition: 'none' }),
}));

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

describe('resolveImageSrc — SEC-P0-4 allow-list', () => {
  test('accepts https URLs', () => {
    expect(resolveImageSrc('https://images.example.com/a.jpg')).toBe(
      'https://images.example.com/a.jpg',
    );
  });

  test('accepts http URLs', () => {
    expect(resolveImageSrc('http://images.example.com/a.jpg')).toBe(
      'http://images.example.com/a.jpg',
    );
  });

  test('accepts site-relative paths', () => {
    expect(resolveImageSrc('/media/foo.jpg')).toBe('/media/foo.jpg');
  });

  test('trims whitespace before checking', () => {
    expect(resolveImageSrc('   https://x.com/y.jpg   ')).toBe(
      'https://x.com/y.jpg',
    );
  });

  test('rejects data: URLs', () => {
    expect(resolveImageSrc('data:text/html;base64,evil')).toBeNull();
    expect(resolveImageSrc('data:image/svg+xml;base64,evil')).toBeNull();
  });

  test('rejects javascript: URLs', () => {
    expect(resolveImageSrc('javascript:alert(1)')).toBeNull();
  });

  test('rejects empty / undefined / whitespace-only', () => {
    expect(resolveImageSrc('')).toBeNull();
    expect(resolveImageSrc(undefined)).toBeNull();
    expect(resolveImageSrc('   ')).toBeNull();
  });

  test('rejects bare-string non-allow-listed input', () => {
    expect(resolveImageSrc('foo.jpg')).toBeNull();
  });
});

describe('ImageWithFallbacks — render branches', () => {
  test('renders shimmer skeleton when imagesPending=true and src is empty', () => {
    render(<ImageWithFallbacks src="" alt="x" imagesPending />);
    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).not.toBeNull();
    expect(screen.getByText('Fetching image…')).toBeDefined();
  });

  test('renders shimmer skeleton when taskStatus=pending (regardless of src)', () => {
    render(
      <ImageWithFallbacks
        src="https://x.com/a.jpg"
        alt="x"
        taskStatus="pending"
      />,
    );
    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).not.toBeNull();
    // No <img> while pending.
    expect(document.querySelector('img')).toBeNull();
  });

  test('renders shimmer skeleton when taskStatus=generating', () => {
    render(<ImageWithFallbacks src="" alt="x" taskStatus="generating" />);
    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).not.toBeNull();
  });

  test('renders "Image unavailable" placeholder when taskStatus=failed', () => {
    render(
      <ImageWithFallbacks
        src=""
        alt="x"
        taskStatus="failed"
        taskErrorCode="CONTENT_SENSITIVE"
        elementKey="2:1:0:img"
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

  test('renders honest "AI images disabled" placeholder when imageProviderDisabled and no src', () => {
    render(
      <ImageWithFallbacks
        src=""
        alt="x"
        imageProviderDisabled
      />,
    );
    expect(screen.getByText('AI images disabled')).toBeDefined();
    expect(
      screen.getByText(/Ask your admin to enable image generation/),
    ).toBeDefined();
    // No <img>, no skeleton.
    expect(document.querySelector('img')).toBeNull();
    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).toBeNull();
  });

  test('renders <img> when src resolves and no other state', () => {
    render(
      <ImageWithFallbacks
        src="https://images.example.com/a.jpg"
        alt="diagram"
      />,
    );
    const imgs = document.querySelectorAll('img');
    expect(imgs.length).toBeGreaterThan(0);
    expect(imgs[0].getAttribute('src')).toBe('https://images.example.com/a.jpg');
    expect(imgs[0].getAttribute('alt')).toBe('diagram');
  });

  test('renders <img> via suppressOnLoadShimmer (F4 template path) without on-load shimmer', () => {
    render(
      <ImageWithFallbacks
        src="https://images.example.com/a.jpg"
        alt="diagram"
        suppressOnLoadShimmer
      />,
    );
    const imgs = document.querySelectorAll('img');
    expect(imgs.length).toBe(1);
    // The success path on the F4 template uses a simpler container — no
    // pre-load shimmer overlay competing for space inside the slot.
    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).toBeNull();
  });

  test('precedence: taskStatus=pending wins over imageProviderDisabled and imagesPending', () => {
    // When the per-element task is mid-flight, the user sees the fetching
    // skeleton even if the tenant has provider disabled — the task itself
    // signals work in progress.
    render(
      <ImageWithFallbacks
        src=""
        alt="x"
        imagesPending
        imageProviderDisabled
        taskStatus="pending"
      />,
    );
    expect(
      document.querySelector('[data-testid="image-fetching-skeleton"]'),
    ).not.toBeNull();
    expect(screen.queryByText('AI images disabled')).toBeNull();
  });

  test('returns null when src is empty and no other state is active', () => {
    const { container } = render(
      <ImageWithFallbacks src="" alt="x" />,
    );
    // No skeleton, no placeholder, no <img>. Caller is expected to provide
    // a fallback (e.g. Unsplash) before invoking the helper in this case.
    expect(container.firstChild).toBeNull();
  });
});
