// useMAICGeneration.persistPartial.test.tsx
//
// CG-P0-4 — startContentGeneration must PATCH `content` to the server
// after EACH scene completes, not only at the end. Without this, a
// browser navigation mid-generation orphans the classroom on
// `status=GENERATING` with empty `content`. See
// incidents/2026-04-25-classroom-generation-orphan.md.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render } from '@testing-library/react';
import { useMAICGeneration } from '../useMAICGeneration';
import { useAuthStore } from '../../stores/authStore';
import type { MAICSSEEvent } from '../../types/maic';

const streamMAICMock = vi.fn(async ({ onEvent, onDone }: {
  onEvent: (e: MAICSSEEvent) => void;
  onDone: () => void;
}) => {
  onEvent({
    type: 'outline',
    data: {
      topic: 'Test Topic',
      language: 'en',
      totalMinutes: 30,
      agents: [
        { id: 'a1', name: 'Alice', voiceId: 'v1', personality: 'curious', avatar: '🦊' },
        { id: 'a2', name: 'Bob', voiceId: 'v2', personality: 'patient', avatar: '🐢' },
      ],
      scenes: [
        { id: 's0', title: 'Scene 0', description: '', type: 'lecture', durationMinutes: 5, agentIds: ['a1', 'a2'] },
        { id: 's1', title: 'Scene 1', description: '', type: 'lecture', durationMinutes: 5, agentIds: ['a1', 'a2'] },
      ],
    },
  } as MAICSSEEvent);
  onDone();
});
vi.mock('../../lib/maicSSE', () => ({
  streamMAIC: (args: unknown) => streamMAICMock(args as Parameters<typeof streamMAICMock>[0]),
}));

const updateClassroomMock = vi.fn().mockResolvedValue({ data: {} });
const generateSceneContentMock = vi.fn().mockResolvedValue({
  data: {
    slides: [
      {
        id: 'slide-1',
        title: 'Slide 1',
        elements: [{ id: 'el-1', type: 'text', content: 'Hello', x: 0, y: 0, w: 100, h: 100 }],
        background: '#fff',
        speakerScript: 'hello world',
        duration: 30,
      },
    ],
  },
});
const generateSceneActionsMock = vi.fn().mockResolvedValue({
  data: { actions: [{ type: 'speech', agentId: 'a1', text: 'hello' }] },
});
const pingClassroomProgressMock = vi.fn().mockResolvedValue({});

vi.mock('../../services/openmaicService', () => ({
  maicApi: {
    pingClassroomProgress: (...args: unknown[]) => pingClassroomProgressMock(...args),
    updateClassroom: (...args: unknown[]) => updateClassroomMock(...args),
    generateSceneContent: (...args: unknown[]) => generateSceneContentMock(...args),
    generateSceneActions: (...args: unknown[]) => generateSceneActionsMock(...args),
  },
}));

vi.mock('../../lib/maicDb', () => ({
  saveClassroom: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../utils/generationLock', () => ({ setGenerationActive: vi.fn() }));
vi.mock('../../utils/authSession', () => ({ setLastActivityTimestamp: vi.fn() }));

const noopStore = {
  setSlides: vi.fn(),
  setAgents: vi.fn(),
  setScenes: vi.fn(),
  setSceneSlideBounds: vi.fn(),
  clearAllOutlineFailures: vi.fn(),
  markOutlineFailed: vi.fn(),
  clearOutlineFailure: vi.fn(),
  scenes: [],
};
vi.mock('../../stores/maicStageStore', () => ({
  useMAICStageStore: Object.assign(
    (selector?: (s: typeof noopStore) => unknown) => (selector ? selector(noopStore) : noopStore),
    { getState: () => noopStore },
  ),
}));

interface HookHandle {
  current: ReturnType<typeof useMAICGeneration>;
}

function renderHook() {
  const handle: HookHandle = { current: undefined as unknown as HookHandle['current'] };
  function Probe() {
    handle.current = useMAICGeneration();
    return null;
  }
  render(<Probe />);
  return handle;
}

describe('useMAICGeneration — CG-P0-4 incremental content persistence', () => {
  beforeEach(() => {
    streamMAICMock.mockClear();
    updateClassroomMock.mockClear();
    generateSceneContentMock.mockClear();
    generateSceneActionsMock.mockClear();
    pingClassroomProgressMock.mockClear();
    useAuthStore.setState({ accessToken: 'test-token' } as never);
  });

  it('PATCHes `content` to the server after each scene completes, not only at end', async () => {
    const handle = renderHook();

    await act(async () => {
      await handle.current.startOutlineGeneration({
        topic: 'Test',
        language: 'en',
        agentCount: 2,
        sceneCount: 2,
        enableTTS: true,
        enableImages: true,
      });
    });

    await act(async () => {
      await handle.current.startContentGeneration('classroom-123');
    });

    // Every PATCH that ships a `content` field is a partial-or-final save.
    // 2 scenes × (1 after content + 1 after actions) + 1 final = 5 calls
    // with `content`. We require AT LEAST 2 to prove incremental persistence
    // (not just the single end-of-flow save).
    const callsWithContent = updateClassroomMock.mock.calls.filter(
      ([, body]: unknown[]) => Boolean((body as { content?: unknown })?.content),
    );
    expect(callsWithContent.length).toBeGreaterThanOrEqual(2);

    // The first content-bearing PATCH must arrive BEFORE the final READY
    // status flip — proves it's a true partial save, not the closing one.
    const finalCallIdx = updateClassroomMock.mock.calls.findIndex(
      ([, body]: unknown[]) => (body as { status?: string })?.status === 'READY',
    );
    expect(finalCallIdx).toBeGreaterThan(0);

    const firstContentCallIdx = updateClassroomMock.mock.calls.findIndex(
      ([, body]: unknown[]) => Boolean((body as { content?: unknown })?.content),
    );
    expect(firstContentCallIdx).toBeLessThan(finalCallIdx);
  });

  it('partial save during content-loop includes fallback actions for scenes whose actions have not run yet', async () => {
    // Capture the FIRST partial PATCH and inspect: scenes already in the
    // payload but whose `actions` array is empty (because the actions loop
    // hasn't started for them) must be augmented with deterministic fallback
    // actions, so a navigation here still leaves a playable classroom.
    const handle = renderHook();
    await act(async () => {
      await handle.current.startOutlineGeneration({
        topic: 'Test',
        language: 'en',
        agentCount: 2,
        sceneCount: 2,
        enableTTS: true,
        enableImages: true,
      });
    });
    await act(async () => {
      await handle.current.startContentGeneration('classroom-123');
    });

    // The first content-bearing PATCH lands right after scene 0's content
    // (before scene 0 actions run). At that moment, scenes[0].actions is empty,
    // and persistPartial must fill it with fallback actions.
    const firstContentCall = updateClassroomMock.mock.calls.find(
      ([, body]: unknown[]) => Boolean((body as { content?: unknown })?.content),
    );
    expect(firstContentCall).toBeDefined();
    const content = (firstContentCall![1] as {
      content: { scenes: Array<{ id: string; actions: unknown[] }> };
    }).content;
    expect(content.scenes.length).toBeGreaterThan(0);
    // First scene at first-PATCH time has no real actions yet → must be
    // backfilled with fallback actions (length > 0).
    expect(content.scenes[0].actions.length).toBeGreaterThan(0);
  });
});
