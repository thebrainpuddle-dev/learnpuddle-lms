import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('../../common/Toast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

vi.mock('../../../config/featureFlags', () => ({
  featureFlags: {
    maicV2Enabled: true,
    maicGenerationUseV2: true,
  },
}));

vi.mock('../PDFUploader', () => ({
  PDFUploader: () => React.createElement('div', { 'data-testid': 'pdf-uploader' }),
}));

vi.mock('../WebSearchPanel', () => ({
  WebSearchPanel: () => React.createElement('div', { 'data-testid': 'web-search-panel' }),
}));

vi.mock('../OutlineEditor', () => ({
  OutlineEditor: () => React.createElement('div', { 'data-testid': 'outline-editor' }),
}));

vi.mock('../GenerationVisualizer', () => ({
  GenerationVisualizer: () =>
    React.createElement('div', { 'data-testid': 'generation-visualizer' }),
}));

const approvedAgents = [
  {
    id: 'agent-1',
    name: 'Asha',
    role: 'student',
    avatar: 'A',
    color: '#123456',
  },
];

vi.mock('../AgentGenerationStep', () => ({
  AgentGenerationStep: ({ onComplete }: { onComplete: (agents: typeof approvedAgents) => void }) =>
    React.createElement(
      'button',
      {
        type: 'button',
        onClick: () => onComplete(approvedAgents),
      },
      'Approve agents',
    ),
}));

const startOutlineGenerationMock = vi.fn();
const startV2GenerationMock = vi.fn().mockResolvedValue('classroom-v2');

vi.mock('../../../hooks/useMAICGeneration', () => ({
  useMAICGeneration: () => ({
    step: 'idle',
    phase: 'idle',
    currentSceneIdx: 0,
    totalScenes: 0,
    outline: null,
    progress: 0,
    error: null,
    startedAt: null,
    isTabHidden: false,
    firstSceneReadyAt: null,
    startOutlineGeneration: startOutlineGenerationMock,
    updateOutline: vi.fn(),
    startContentGeneration: vi.fn(),
    startV2Generation: startV2GenerationMock,
    retryScene: vi.fn(),
    cancel: vi.fn(),
    reset: vi.fn(),
  }),
}));

vi.mock('../../../stores/maicStageStore', () => ({
  useMAICStageStore: Object.assign(
    (selector: any) =>
      selector({
        failedOutlineIds: [],
        setSlides: vi.fn(),
        setAgents: vi.fn(),
        setScenes: vi.fn(),
        setSceneSlideBounds: vi.fn(),
      }),
    {
      getState: () => ({
        clearAllOutlineFailures: vi.fn(),
        markOutlineFailed: vi.fn(),
        clearOutlineFailure: vi.fn(),
      }),
    },
  ),
}));

vi.mock('../../../services/openmaicService', () => ({
  maicApi: {
    createClassroom: vi.fn(),
  },
}));

import { GenerationWizard } from '../GenerationWizard';

describe('GenerationWizard — v2 teacher generation handoff', () => {
  beforeEach(() => {
    window.localStorage.clear();
    startOutlineGenerationMock.mockClear();
    startV2GenerationMock.mockClear();
  });

  it('starts the v2 graph job after Step 2 instead of the legacy outline stream', async () => {
    render(<GenerationWizard />);

    fireEvent.change(screen.getByLabelText(/topic/i), {
      target: { value: 'Photosynthesis' },
    });
    fireEvent.change(screen.getByLabelText(/grade level/i), {
      target: { value: 'Grade 6' },
    });
    fireEvent.change(screen.getByLabelText(/subject/i), {
      target: { value: 'Science' },
    });

    fireEvent.click(screen.getByRole('button', { name: /meet your classroom/i }));
    fireEvent.click(await screen.findByRole('button', { name: /approve agents/i }));

    await waitFor(() => expect(startV2GenerationMock).toHaveBeenCalledTimes(1));
    expect(startOutlineGenerationMock).not.toHaveBeenCalled();
    const [config, agents] = startV2GenerationMock.mock.calls[0];
    expect(config.topic).toBe('Photosynthesis');
    expect(config.gradeLevel).toBe('Grade 6');
    expect(config.subject).toBe('Science');
    expect(config.classGuide).toContain('Photosynthesis');
    expect(config.classGuide).toContain('PBL/activity brief');
    expect(config.classGuide).toContain('Agent choreography');
    expect(agents).toEqual(approvedAgents);
  });
});
