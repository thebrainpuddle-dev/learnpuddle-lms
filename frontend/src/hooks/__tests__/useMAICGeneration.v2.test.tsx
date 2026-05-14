import React from 'react';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useMAICGeneration } from '../useMAICGeneration';
import { useAuthStore } from '../../stores/authStore';
import type { MAICAgent, MAICGenerationConfig } from '../../types/maic';

vi.mock('../../lib/maicSSE', () => ({
  streamMAIC: vi.fn(),
}));

vi.mock('../../lib/maicDb', () => ({
  saveClassroom: vi.fn().mockResolvedValue(undefined),
}));

const generateV2ClassroomMock = vi.fn();
const getV2GenerationJobMock = vi.fn();

vi.mock('../../services/openmaicService', () => ({
  maicApi: {
    generateV2Classroom: (...args: unknown[]) => generateV2ClassroomMock(...args),
    getV2GenerationJob: (...args: unknown[]) => getV2GenerationJobMock(...args),
    pingClassroomProgress: vi.fn().mockResolvedValue({}),
    updateClassroom: vi.fn().mockResolvedValue({}),
    generateSceneContent: vi.fn(),
    generateSceneActions: vi.fn(),
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

const config: MAICGenerationConfig = {
  topic: 'Photosynthesis',
  language: 'en',
  agentCount: 1,
  sceneCount: 6,
  enableTTS: true,
  enableImages: true,
  courseId: 'course-1',
  gradeLevel: 'Grade 6',
  subject: 'Science',
  syllabusBoard: 'CBSE',
  classGuide: 'Open with a plant mystery and include a misconception check.',
  pdfText: 'Teacher guide PDF notes.',
  enableWebSearch: true,
  webSearchContext: 'Recent source: leaf starch demo.',
};

const agents: MAICAgent[] = [
  {
    id: 'agent-1',
    name: 'Asha',
    role: 'student',
    avatar: 'A',
    color: '#123456',
  },
];

describe('useMAICGeneration — v2 teacher generation handoff', () => {
  beforeEach(() => {
    generateV2ClassroomMock.mockReset();
    getV2GenerationJobMock.mockReset();
    useAuthStore.setState({ accessToken: 'test-token' } as never);
    generateV2ClassroomMock.mockResolvedValue({
      data: {
        job_id: 'job-123',
        ws_url: 'ws://test/ws/maic/generation/job-123/',
        tenant_id: 1,
      },
    });
    getV2GenerationJobMock.mockResolvedValue({
      data: {
        job_id: 'job-123',
        status: 'succeeded',
        step: 3,
        progress: {
          stage: 3,
          completed: 6,
          total: 6,
          message: 'Generation complete!',
        },
        result: {
          classroomId: 'classroom-123',
          url: '/teacher/ai-classroom/classroom-123',
          scenesCount: 6,
        },
        done: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });
  });

  it('submits class-guide context to v2 and returns the materialized classroom id', async () => {
    const handle = renderHook();
    let classroomId: string | null = null;

    await act(async () => {
      classroomId = await handle.current.startV2Generation(config, agents);
    });

    expect(classroomId).toBe('classroom-123');
    expect(generateV2ClassroomMock).toHaveBeenCalledTimes(1);
    const body = generateV2ClassroomMock.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(body.topic).toBe('Photosynthesis');
    expect(body.sceneCount).toBe(6);
    expect(body.courseId).toBe('course-1');
    expect(body.gradeLevel).toBe('Grade 6');
    expect(body.subject).toBe('Science');
    expect(body.syllabusBoard).toBe('CBSE');
    expect(body.classGuide).toContain('plant mystery');
    expect(body.pdfText).toBe('Teacher guide PDF notes.');
    expect(body.researchContext).toBe('Recent source: leaf starch demo.');
    expect(body.agents).toEqual(agents);
    expect(body.enablePBL).toBe(true);
    expect(body.enableImageGeneration).toBe(true);
    expect(String(body.specifications)).toContain('production-ready teacher-led AI classroom');
    expect(String(body.specifications)).toContain('roles, deliverable, constraints, and success criteria');
    expect(String(body.specifications)).toContain('point first, then speak');
    expect(getV2GenerationJobMock).toHaveBeenCalledWith('job-123');
    expect(handle.current.step).toBe('complete');
    expect(handle.current.progress).toBe(100);
  }, 10000);

  it('surfaces local provider timeouts as teacher-readable errors', async () => {
    getV2GenerationJobMock.mockResolvedValueOnce({
      data: {
        job_id: 'job-123',
        status: 'failed',
        step: 1,
        progress: {
          stage: 1,
          completed: 0,
          total: 0,
          message: 'Generating scene outlines...',
        },
        error: "RuntimeError: LLM call failed: ollama: request timed out after 180s for model 'llama3.2:3b'",
        result: {},
        done: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });
    const handle = renderHook();
    let classroomId: string | null = 'not-null';

    await act(async () => {
      classroomId = await handle.current.startV2Generation(config, agents);
    });

    expect(classroomId).toBeNull();
    expect(handle.current.step).toBe('error');
    expect(handle.current.error).toContain('AI provider took too long');
    expect(handle.current.error).not.toContain('RuntimeError');
  }, 10000);

  it('surfaces backend MAIC v2 gate failures instead of raw HTTP status text', async () => {
    generateV2ClassroomMock.mockRejectedValueOnce({
      response: {
        status: 403,
        data: {
          detail: 'MAIC v2 is disabled for this deployment',
        },
      },
    });
    const handle = renderHook();
    let classroomId: string | null = 'not-null';

    await act(async () => {
      classroomId = await handle.current.startV2Generation(config, agents);
    });

    expect(classroomId).toBeNull();
    expect(handle.current.step).toBe('error');
    expect(handle.current.error).toContain('AI Classroom v2 is disabled for this deployment');
    expect(handle.current.error).not.toContain('Request failed with status code 403');
    expect(getV2GenerationJobMock).not.toHaveBeenCalled();
  }, 10000);

  it('keeps polling through a transient network error', async () => {
    getV2GenerationJobMock
      .mockRejectedValueOnce(new Error('Network Error'))
      .mockResolvedValueOnce({
        data: {
          job_id: 'job-123',
          status: 'succeeded',
          step: 3,
          progress: {
            stage: 3,
            completed: 6,
            total: 6,
            message: 'Generation complete!',
          },
          result: {
            classroomId: 'classroom-123',
            url: '/teacher/ai-classroom/classroom-123',
            scenesCount: 6,
          },
          done: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      });

    const handle = renderHook();
    let classroomId: string | null = null;

    await act(async () => {
      classroomId = await handle.current.startV2Generation(config, agents);
    });

    expect(classroomId).toBe('classroom-123');
    expect(getV2GenerationJobMock).toHaveBeenCalledTimes(2);
    expect(handle.current.step).toBe('complete');
    expect(handle.current.error).toBeNull();
  }, 12000);
});
