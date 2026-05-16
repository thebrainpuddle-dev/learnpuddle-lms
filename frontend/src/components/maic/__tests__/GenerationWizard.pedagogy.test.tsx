/**
 * Chunk 3b — GenerationWizard pedagogy field handoff.
 *
 * Asserts that the typed pedagogy targets (learningObjective,
 * misconceptions[], successCriteria[], pblBrief) added in Chunk 3b end
 * up in the MAICGenerationConfig passed to startV2Generation, so the
 * backend's POST /api/maic/v2/generate/ receives them and renders the
 * `## Pedagogy Targets` block (covered by Chunk 3a backend tests).
 *
 * Mirrors GenerationWizard.v2Handoff.test.tsx's mock topology so the
 * test isolates UI → config plumbing without booting the actual
 * generation hook.
 */
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
    startOutlineGeneration: vi.fn(),
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

describe('GenerationWizard — Chunk 3b typed pedagogy targets', () => {
  beforeEach(() => {
    window.localStorage.clear();
    startV2GenerationMock.mockClear();
  });

  it('forwards populated pedagogy targets into the v2 generation config', async () => {
    render(<GenerationWizard />);

    fireEvent.change(screen.getByLabelText(/topic/i), {
      target: { value: 'Photosynthesis' },
    });

    fireEvent.click(screen.getByRole('button', { name: /meet your classroom/i }));

    // Step 2 — fill the four typed pedagogy inputs.
    fireEvent.change(screen.getByTestId('maic-learning-objective'), {
      target: {
        value:
          'Students explain how leaves convert sunlight into stored chemical energy.',
      },
    });
    fireEvent.change(screen.getByTestId('maic-misconceptions'), {
      target: {
        value:
          'Plants get food from the soil.\nPhotosynthesis happens only in flowers.',
      },
    });
    fireEvent.change(screen.getByTestId('maic-success-criteria'), {
      target: {
        value:
          'Diagram the light reactions with arrows.\nPredict what happens in 48h dark.',
      },
    });
    fireEvent.change(screen.getByTestId('maic-pbl-brief'), {
      target: { value: 'Design a sealed terrarium experiment.' },
    });

    fireEvent.click(screen.getByRole('button', { name: /approve agents/i }));

    await waitFor(() => expect(startV2GenerationMock).toHaveBeenCalledTimes(1));
    const [config] = startV2GenerationMock.mock.calls[0];

    expect(config.learningObjective).toBe(
      'Students explain how leaves convert sunlight into stored chemical energy.',
    );
    expect(config.misconceptions).toEqual([
      'Plants get food from the soil.',
      'Photosynthesis happens only in flowers.',
    ]);
    expect(config.successCriteria).toEqual([
      'Diagram the light reactions with arrows.',
      'Predict what happens in 48h dark.',
    ]);
    expect(config.pblBrief).toBe('Design a sealed terrarium experiment.');
  });

  it('omits pedagogy targets from the config when inputs are blank', async () => {
    render(<GenerationWizard />);

    fireEvent.change(screen.getByLabelText(/topic/i), {
      target: { value: 'Photosynthesis' },
    });
    fireEvent.click(screen.getByRole('button', { name: /meet your classroom/i }));
    fireEvent.click(screen.getByRole('button', { name: /approve agents/i }));

    await waitFor(() => expect(startV2GenerationMock).toHaveBeenCalledTimes(1));
    const [config] = startV2GenerationMock.mock.calls[0];

    expect(config.learningObjective).toBeUndefined();
    expect(config.misconceptions).toBeUndefined();
    expect(config.successCriteria).toBeUndefined();
    expect(config.pblBrief).toBeUndefined();
  });

  it('drops blank lines and caps lists at 5 items before submit', async () => {
    render(<GenerationWizard />);

    fireEvent.change(screen.getByLabelText(/topic/i), {
      target: { value: 'Photosynthesis' },
    });
    fireEvent.click(screen.getByRole('button', { name: /meet your classroom/i }));

    // 7 lines, 2 blank → 5 real → capped at 5
    fireEvent.change(screen.getByTestId('maic-misconceptions'), {
      target: {
        value: 'one\n\ntwo\nthree\n   \nfour\nfive\nsix\nseven',
      },
    });

    fireEvent.click(screen.getByRole('button', { name: /approve agents/i }));

    await waitFor(() => expect(startV2GenerationMock).toHaveBeenCalledTimes(1));
    const [config] = startV2GenerationMock.mock.calls[0];

    expect(config.misconceptions).toEqual(['one', 'two', 'three', 'four', 'five']);
    expect(config.misconceptions).toHaveLength(5);
  });
});
