import React from 'react';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useStudentMAICGeneration } from '../useStudentMAICGeneration';
import { useAuthStore } from '../../stores/authStore';
import type { MAICAgent, MAICGenerationConfig } from '../../types/maic';

vi.mock('../../lib/maicSSE', () => ({
  streamMAIC: vi.fn(),
}));

vi.mock('../../lib/maicDb', () => ({
  saveClassroom: vi.fn().mockResolvedValue(undefined),
}));

const validateTopicMock = vi.fn();
const generateV2ClassroomMock = vi.fn();
const getV2GenerationJobMock = vi.fn();

vi.mock('../../services/openmaicService', () => ({
  maicStudentApi: {
    validateTopic: (...args: unknown[]) => validateTopicMock(...args),
    generateV2Classroom: (...args: unknown[]) => generateV2ClassroomMock(...args),
    getV2GenerationJob: (...args: unknown[]) => getV2GenerationJobMock(...args),
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
  current: ReturnType<typeof useStudentMAICGeneration>;
}

function renderHook() {
  const handle: HookHandle = { current: undefined as unknown as HookHandle['current'] };
  function Probe() {
    handle.current = useStudentMAICGeneration();
    return null;
  }
  render(<Probe />);
  return handle;
}

const config: MAICGenerationConfig = {
  topic: 'Algebra misconceptions',
  language: 'en',
  agentCount: 2,
  sceneCount: 5,
  enableTTS: true,
  enableImages: true,
  pdfText: 'Student uploaded revision notes.',
  enableWebSearch: true,
};

const agents: MAICAgent[] = [
  {
    id: 'agent-1',
    name: 'Asha',
    role: 'student',
    avatar: 'A',
    color: '#123456',
  },
  {
    id: 'agent-2',
    name: 'Kabir',
    role: 'student',
    avatar: 'K',
    color: '#654321',
  },
];

describe('useStudentMAICGeneration — v2 generation handoff', () => {
  beforeEach(() => {
    validateTopicMock.mockReset();
    generateV2ClassroomMock.mockReset();
    getV2GenerationJobMock.mockReset();
    useAuthStore.setState({ accessToken: 'test-token' } as never);
    validateTopicMock.mockResolvedValue({
      data: {
        allowed: true,
        is_educational: true,
        subject_area: 'mathematics',
        confidence: 1,
        reason: 'Approved',
      },
    });
    generateV2ClassroomMock.mockResolvedValue({
      data: {
        job_id: 'student-job-123',
        ws_url: 'ws://test/ws/maic/generation/student-job-123/',
        tenant_id: 1,
      },
    });
    getV2GenerationJobMock.mockResolvedValue({
      data: {
        job_id: 'student-job-123',
        status: 'succeeded',
        step: 3,
        progress: {
          stage: 3,
          completed: 5,
          total: 5,
          message: 'Generation complete!',
        },
        result: {
          classroomId: 'classroom-student-123',
          studentUrl: '/student/ai-classroom/classroom-student-123',
          scenesCount: 5,
        },
        done: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    });
  });

  it('validates the topic and submits student classrooms through the v2 private path', async () => {
    const handle = renderHook();
    let result: Awaited<ReturnType<typeof handle.current.startV2Generation>> | null = null;

    await act(async () => {
      result = await handle.current.startV2Generation(config, agents);
    });

    expect(result).toEqual({ classroomId: 'classroom-student-123', rejected: false });
    expect(validateTopicMock).toHaveBeenCalledWith({
      topic: 'Algebra misconceptions',
      pdfText: 'Student uploaded revision notes.',
    });
    expect(generateV2ClassroomMock).toHaveBeenCalledTimes(1);
    const body = generateV2ClassroomMock.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(body.topic).toBe('Algebra misconceptions');
    expect(body.sceneCount).toBe(5);
    expect(body.agentCount).toBe(2);
    expect(body.agents).toEqual(agents);
    expect(body.pdfText).toBe('Student uploaded revision notes.');
    expect(body.enablePBL).toBe(true);
    expect(body.enableImageGeneration).toBe(true);
    expect(body.isPublic).toBe(false);
    expect(body.courseId).toBeUndefined();
    expect(body.moduleId).toBeUndefined();
    expect(String(body.specifications)).toContain('student self-study AI classroom');
    expect(getV2GenerationJobMock).toHaveBeenCalledWith('student-job-123');
    expect(handle.current.step).toBe('complete');
    expect(handle.current.progress).toBe(100);
  }, 10000);

  it('does not enqueue v2 generation when validation rejects the topic', async () => {
    validateTopicMock.mockResolvedValueOnce({
      data: {
        allowed: false,
        is_educational: false,
        subject_area: 'general',
        confidence: 0.1,
        reason: 'Please enter an educational topic.',
      },
    });
    const handle = renderHook();
    let result: Awaited<ReturnType<typeof handle.current.startV2Generation>> | null = null;

    await act(async () => {
      result = await handle.current.startV2Generation(config, agents);
    });

    expect(result).toEqual({ classroomId: null, rejected: true });
    expect(generateV2ClassroomMock).not.toHaveBeenCalled();
    expect(handle.current.step).toBe('error');
    expect(handle.current.error).toContain('educational topic');
  });
});
