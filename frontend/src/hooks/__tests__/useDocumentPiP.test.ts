// src/hooks/__tests__/useDocumentPiP.test.ts
//
// Unit tests for useDocumentPiP. We mock `window.documentPictureInPicture`
// because happy-dom doesn't implement the API (it's Chrome-only as of
// early 2026). The goal is to exercise the hook's state transitions:
//
//   1. isSupported reflects whether the API is present on window
//   2. open() sets isOpen=true, moves the stage DOM node into the PiP
//      window, and leaves a placeholder in its original parent
//   3. firing `pagehide` on the PiP window restores the stage + clears
//      isOpen back to false
//   4. close() triggers the same restore flow

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { createRef } from 'react';
import { useDocumentPiP } from '../useDocumentPiP';

type PiPHandler = (ev: Event) => void;

/** Build a fake PiP window backed by a real happy-dom Document so the
 *  hook's DOM moves behave the same way a browser would. */
function createFakePiPWindow() {
  const doc = document.implementation.createHTMLDocument('pip');
  const handlers = new Set<PiPHandler>();
  const pipWindow = {
    document: doc,
    focus: vi.fn(),
    close: vi.fn(() => {
      // Simulate the browser firing pagehide when the PiP tab closes.
      for (const h of handlers) h(new Event('pagehide'));
    }),
    addEventListener: vi.fn((type: string, handler: PiPHandler) => {
      if (type === 'pagehide') handlers.add(handler);
    }),
    removeEventListener: vi.fn((type: string, handler: PiPHandler) => {
      if (type === 'pagehide') handlers.delete(handler);
    }),
    // Test helper — lets us simulate the user closing the PiP window
    // without going through window.close() (mirrors real pagehide dispatch).
    __firePageHide: () => {
      for (const h of handlers) h(new Event('pagehide'));
    },
  };
  return pipWindow;
}

describe('useDocumentPiP', () => {
  const originalDPiP = (window as unknown as { documentPictureInPicture?: unknown })
    .documentPictureInPicture;

  beforeEach(() => {
    // Default: API is present.
    const fake = createFakePiPWindow();
    (window as unknown as { documentPictureInPicture: unknown }).documentPictureInPicture = {
      requestWindow: vi.fn(async () => fake),
      __fake: fake,
    };
  });

  afterEach(() => {
    if (originalDPiP === undefined) {
      delete (window as unknown as { documentPictureInPicture?: unknown })
        .documentPictureInPicture;
    } else {
      (window as unknown as { documentPictureInPicture: unknown }).documentPictureInPicture =
        originalDPiP;
    }
  });

  it('1. isSupported is true when documentPictureInPicture is defined', () => {
    const { result } = renderHook(() => useDocumentPiP());
    expect(result.current.isSupported).toBe(true);
    expect(result.current.isOpen).toBe(false);
  });

  it('2. isSupported is false when API is missing', () => {
    delete (window as unknown as { documentPictureInPicture?: unknown })
      .documentPictureInPicture;
    const { result } = renderHook(() => useDocumentPiP());
    expect(result.current.isSupported).toBe(false);
  });

  it('3. open() moves the stage node into the PiP window and leaves a placeholder', async () => {
    const { result } = renderHook(() => useDocumentPiP());

    const parent = document.createElement('div');
    const stage = document.createElement('div');
    stage.setAttribute('data-testid', 'stage');
    parent.appendChild(stage);
    document.body.appendChild(parent);

    const stageRef = createRef<HTMLDivElement>();
    (stageRef as { current: HTMLDivElement | null }).current = stage;

    await act(async () => {
      await result.current.open(stageRef);
    });

    expect(result.current.isOpen).toBe(true);
    // Stage is no longer a child of `parent`.
    expect(stage.parentElement).not.toBe(parent);
    // A placeholder took its place.
    const placeholder = parent.querySelector('[data-pip-placeholder]');
    expect(placeholder).not.toBeNull();
  });

  it('4. pagehide on PiP window restores the stage to its original parent', async () => {
    const { result } = renderHook(() => useDocumentPiP());

    const parent = document.createElement('div');
    const stage = document.createElement('div');
    parent.appendChild(stage);
    document.body.appendChild(parent);

    const stageRef = createRef<HTMLDivElement>();
    (stageRef as { current: HTMLDivElement | null }).current = stage;

    await act(async () => {
      await result.current.open(stageRef);
    });

    const api = (window as unknown as {
      documentPictureInPicture: { __fake: { __firePageHide: () => void } };
    }).documentPictureInPicture;

    await act(async () => {
      api.__fake.__firePageHide();
    });

    expect(result.current.isOpen).toBe(false);
    expect(stage.parentElement).toBe(parent);
    expect(parent.querySelector('[data-pip-placeholder]')).toBeNull();
  });

  it('5. close() tears down PiP and restores state', async () => {
    const { result } = renderHook(() => useDocumentPiP());

    const parent = document.createElement('div');
    const stage = document.createElement('div');
    parent.appendChild(stage);
    document.body.appendChild(parent);

    const stageRef = createRef<HTMLDivElement>();
    (stageRef as { current: HTMLDivElement | null }).current = stage;

    await act(async () => {
      await result.current.open(stageRef);
    });
    expect(result.current.isOpen).toBe(true);

    await act(async () => {
      result.current.close();
    });

    expect(result.current.isOpen).toBe(false);
    expect(stage.parentElement).toBe(parent);
  });

  it('6. open() rejects when the API is unavailable', async () => {
    delete (window as unknown as { documentPictureInPicture?: unknown })
      .documentPictureInPicture;
    const { result } = renderHook(() => useDocumentPiP());

    const stage = document.createElement('div');
    const stageRef = createRef<HTMLDivElement>();
    (stageRef as { current: HTMLDivElement | null }).current = stage;

    await expect(result.current.open(stageRef)).rejects.toThrow(/not supported/i);
  });
});
