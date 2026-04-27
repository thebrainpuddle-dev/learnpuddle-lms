// useMAICGeneration.gradeMeta.test.tsx
//
// FULL-1 — Asserts the network boundary contract: when the wizard config
// includes `gradeLevel` / `subject` / `syllabusBoard`, `streamMAIC` is
// invoked with snake_case body fields (`grade_level`, `subject`,
// `syllabus_board`). When those fields are blank/undefined, the keys are
// omitted entirely so the backend's "Generic / no grade" defaults apply.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render } from '@testing-library/react';
import { useMAICGeneration } from '../useMAICGeneration';
import { useAuthStore } from '../../stores/authStore';
import type { MAICGenerationConfig } from '../../types/maic';

// ── Module mocks ──────────────────────────────────────────────────────────────

const streamMAICMock = vi.fn(async () => undefined);
vi.mock('../../lib/maicSSE', () => ({
  streamMAIC: (...args: unknown[]) => streamMAICMock(...args),
}));

vi.mock('../../lib/maicDb', () => ({
  saveClassroom: vi.fn().mockResolvedValue(undefined),
}));

vi.mock('../../services/openmaicService', () => ({
  maicApi: {
    pingClassroomProgress: vi.fn().mockResolvedValue({}),
    updateClassroom: vi.fn().mockResolvedValue({}),
    generateSceneContent: vi.fn().mockResolvedValue({ data: { slides: [] } }),
    generateSceneActions: vi.fn().mockResolvedValue({ data: { actions: [] } }),
  },
}));

vi.mock('../../utils/generationLock', () => ({
  setGenerationActive: vi.fn(),
}));

vi.mock('../../utils/authSession', () => ({
  setLastActivityTimestamp: vi.fn(),
}));

vi.mock('../../stores/maicStageStore', () => {
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
  return {
    useMAICStageStore: Object.assign(
      (selector?: any) => (selector ? selector(noopStore) : noopStore),
      { getState: () => noopStore },
    ),
  };
});

// ── Helpers ───────────────────────────────────────────────────────────────────

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

const baseConfig: MAICGenerationConfig = {
  topic: 'Photosynthesis',
  language: 'en',
  agentCount: 2,
  sceneCount: 4,
  enableTTS: true,
  enableImages: true,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('useMAICGeneration — FULL-1 grade-aware body mapping', () => {
  beforeEach(() => {
    streamMAICMock.mockClear();
    useAuthStore.setState({ accessToken: 'test-token' } as never);
  });

  it('maps gradeLevel/subject/syllabusBoard → snake_case body keys', async () => {
    const handle = renderHook();

    await act(async () => {
      await handle.current.startOutlineGeneration({
        ...baseConfig,
        gradeLevel: 'Grade 9',
        subject: 'Mathematics',
        syllabusBoard: 'CBSE',
      });
    });

    expect(streamMAICMock).toHaveBeenCalledTimes(1);
    const args = streamMAICMock.mock.calls[0]?.[0] as {
      url: string;
      body: Record<string, unknown>;
    };
    expect(args.url).toBe('/api/v1/teacher/maic/generate/outlines/');
    expect(args.body.grade_level).toBe('Grade 9');
    expect(args.body.subject).toBe('Mathematics');
    expect(args.body.syllabus_board).toBe('CBSE');
    // Sanity: legacy fields still flow through.
    expect(args.body.topic).toBe('Photosynthesis');
    expect(args.body.language).toBe('en');
  });

  it('omits snake_case keys when grade fields are missing', async () => {
    const handle = renderHook();

    await act(async () => {
      await handle.current.startOutlineGeneration({ ...baseConfig });
    });

    expect(streamMAICMock).toHaveBeenCalledTimes(1);
    const body = (streamMAICMock.mock.calls[0]?.[0] as { body: Record<string, unknown> }).body;
    expect(body).not.toHaveProperty('grade_level');
    expect(body).not.toHaveProperty('subject');
    expect(body).not.toHaveProperty('syllabus_board');
  });

  it('omits snake_case keys when grade fields are whitespace-only', async () => {
    const handle = renderHook();

    await act(async () => {
      await handle.current.startOutlineGeneration({
        ...baseConfig,
        gradeLevel: '   ',
        subject: '\t',
        syllabusBoard: '',
      });
    });

    const body = (streamMAICMock.mock.calls[0]?.[0] as { body: Record<string, unknown> }).body;
    expect(body).not.toHaveProperty('grade_level');
    expect(body).not.toHaveProperty('subject');
    expect(body).not.toHaveProperty('syllabus_board');
  });
});
