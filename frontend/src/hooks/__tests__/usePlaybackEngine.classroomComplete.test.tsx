// src/hooks/__tests__/usePlaybackEngine.classroomComplete.test.tsx
//
// SPRINT-2-BATCH-9-F10 (TEST-P0-8) — regression test for the stable
// `data-testid="classroom-complete"` terminal-state signal.
//
// Reviewer flagged that the Playwright e2e suite asserts "Scene N of N"
// in the live region after the final scene but cannot prove the engine
// reached its terminal "course complete" state. The frontend follow-up
// added a `classroomComplete` boolean to `usePlaybackEngine` plus a
// matching `<div data-testid="classroom-complete">` in `Stage.tsx`.
//
// This test validates:
//   1. On initial mount the testid is NOT in the document (terminal flag
//      starts false).
//   2. When the playback engine reaches the LAST scene's final action
//      under autoplay (i.e. `onSceneComplete` fires while
//      `currentSceneIndex === scenes.length - 1`), the testid renders.
//   3. Loading a fresh scene clears the terminal flag (testid disappears
//      on rewind/manual nav).

import React from 'react';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { useAuthStore } from '../../stores/authStore';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { usePlaybackEngine } from '../usePlaybackEngine';
import type { MAICScene } from '../../types/maic-scenes';

// The action engine talks to a TTS endpoint and an HTMLAudioElement —
// happy-dom doesn't implement them. Stub `execute` + `prefetchSpeech`
// to resolve immediately so the playback engine drives to completion
// synchronously through the .then() chain.
vi.mock('../../lib/maicActionEngine', async () => {
  const actual = await vi.importActual<typeof import('../../lib/maicActionEngine')>(
    '../../lib/maicActionEngine',
  );
  class StubActionEngine extends actual.MAICActionEngine {
    constructor(opts: any) {
      super(opts);
    }
    execute(): Promise<void> {
      return Promise.resolve();
    }
    prefetchSpeech(): undefined {
      return undefined;
    }
    unlockAudio(): void {
      /* noop */
    }
    dispose(): void {
      /* noop */
    }
  }
  return { ...actual, MAICActionEngine: StubActionEngine };
});

/**
 * Minimal harness that exposes the hook's `classroomComplete` flag in the
 * DOM so React Testing Library queries can assert presence/absence.
 * Mirrors the conditional rendering in `Stage.tsx` (the actual production
 * site of the testid).
 */
function ClassroomCompleteHarness() {
  const engine = usePlaybackEngine('teacher');
  return (
    <div>
      <span data-testid="harness-mounted">mounted</span>
      {engine.classroomComplete && (
        <div
          role="status"
          aria-live="polite"
          aria-atomic="true"
          data-testid="classroom-complete"
        >
          Class complete
        </div>
      )}
    </div>
  );
}

beforeEach(() => {
  vi.useRealTimers();
  // Auth token is required for the hook's init effect to instantiate the engines.
  useAuthStore.setState({ accessToken: 'test-token' } as any);
  useMAICStageStore.setState({
    scenes: [],
    currentSceneIndex: 0,
    slides: [],
    currentSlideIndex: 0,
    agents: [{ id: 'a1', name: 'Prof', role: 'professor' } as any],
  });
});

afterEach(() => {
  vi.useRealTimers();
  delete (window as any).__maicEngine;
});

function makeScene(id: string, title: string): MAICScene {
  return {
    id,
    title,
    type: 'lecture',
    content: { type: 'slide' } as any,
    // Single fire-and-forget action so processNext() runs once and immediately
    // exhausts the action list (currentActionIndex >= actions.length), which
    // is what triggers `onSceneComplete` in the production engine.
    actions: [{ type: 'highlight', elementId: 'x' } as any],
  } as any;
}

describe('SPRINT-2-BATCH-9-F10 — classroom-complete testid', () => {
  test('is NOT in the document on initial mount', () => {
    act(() => {
      useMAICStageStore.setState({
        scenes: [makeScene('s1', 'Intro'), makeScene('s2', 'Outro')],
        currentSceneIndex: 0,
      });
    });

    render(<ClassroomCompleteHarness />);

    expect(screen.getByTestId('harness-mounted')).toBeInTheDocument();
    expect(screen.queryByTestId('classroom-complete')).not.toBeInTheDocument();
  });

  test('appears after the last scene completes under autoplay', async () => {
    const scene = makeScene('s1', 'Only scene');
    act(() => {
      useMAICStageStore.setState({
        scenes: [scene],
        currentSceneIndex: 0,
      });
    });

    let hookApi: ReturnType<typeof usePlaybackEngine> | null = null;
    function Capture() {
      hookApi = usePlaybackEngine('teacher');
      return (
        <>
          {hookApi.classroomComplete && (
            <div data-testid="classroom-complete">Class complete</div>
          )}
        </>
      );
    }

    render(<Capture />);
    expect(screen.queryByTestId('classroom-complete')).not.toBeInTheDocument();

    // Drive the engine through a full autoplay run on a single-scene
    // classroom. In production, Stage.tsx's effect calls `loadScene` when
    // the current scene changes; in the harness we call it manually.
    // playFromCurrent() flips autoAdvanceRef=true and engine.play() →
    // processNext → exhausts the lone fire-and-forget action via
    // queueMicrotask → next processNext sees end of actions →
    // onSceneComplete fires → terminal branch (no next scene) →
    // setClassroomComplete(true).
    await act(async () => {
      hookApi!.loadScene(scene);
      hookApi!.playFromCurrent();
      // Flush microtasks + the queueMicrotask chain inside processNext.
      await Promise.resolve();
      await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.getByTestId('classroom-complete')).toBeInTheDocument();
  });

  test('disappears when a fresh scene is loaded after completion (e.g. user navigates back)', async () => {
    const scene = makeScene('s1', 'Only scene');
    act(() => {
      useMAICStageStore.setState({
        scenes: [scene],
        currentSceneIndex: 0,
      });
    });

    let hookApi: ReturnType<typeof usePlaybackEngine> | null = null;
    function Capture() {
      hookApi = usePlaybackEngine('teacher');
      return (
        <>
          {hookApi.classroomComplete && (
            <div data-testid="classroom-complete">Class complete</div>
          )}
        </>
      );
    }

    render(<Capture />);

    await act(async () => {
      hookApi!.loadScene(scene);
      hookApi!.playFromCurrent();
      await Promise.resolve();
      await Promise.resolve();
      await new Promise((resolve) => setTimeout(resolve, 0));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });

    expect(screen.getByTestId('classroom-complete')).toBeInTheDocument();

    // Now simulate the user navigating back into the classroom — loadScene
    // clears the terminal flag so the testid leaves the DOM.
    await act(async () => {
      hookApi!.loadScene(scene);
    });

    expect(screen.queryByTestId('classroom-complete')).not.toBeInTheDocument();
  });

  test('stop cancels queued startClass playback before delayed play fires', async () => {
    vi.useFakeTimers();
    const scene = makeScene('s1', 'Only scene');
    act(() => {
      useMAICStageStore.setState({
        scenes: [scene],
        currentSceneIndex: 0,
      });
    });

    let hookApi: ReturnType<typeof usePlaybackEngine> | null = null;
    function Capture() {
      hookApi = usePlaybackEngine('teacher');
      return (
        <>
          {hookApi.classroomComplete && (
            <div data-testid="classroom-complete">Class complete</div>
          )}
        </>
      );
    }

    render(<Capture />);

    await act(async () => {
      hookApi!.loadScene(scene);
      hookApi!.startClass();
      hookApi!.stop();
      vi.advanceTimersByTime(350);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(hookApi!.isClassPlaying).toBe(false);
    expect(useMAICStageStore.getState().isPlaying).toBe(false);
    expect(screen.queryByTestId('classroom-complete')).not.toBeInTheDocument();
  });

  test('access-token rotation does not recreate the active playback engines', async () => {
    let hookApi: ReturnType<typeof usePlaybackEngine> | null = null;
    function Capture() {
      hookApi = usePlaybackEngine('teacher');
      return <span data-testid="mounted">mounted</span>;
    }

    render(<Capture />);
    expect(screen.getByTestId('mounted')).toBeInTheDocument();

    const firstEngine = (window as any).__maicEngine?.actionEngine;
    expect(firstEngine).toBeTruthy();

    await act(async () => {
      useAuthStore.setState({ accessToken: 'rotated-token' } as any);
      await Promise.resolve();
    });

    const secondEngine = (window as any).__maicEngine?.actionEngine;
    expect(secondEngine).toBe(firstEngine);
    expect(hookApi).not.toBeNull();
  });
});
