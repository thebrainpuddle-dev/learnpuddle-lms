// AgentGenerationStep.test.tsx — integration tests for the wizard's agent
// generation step. The service module is mocked so no real API calls happen.

import { beforeEach, describe, expect, test, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { AgentGenerationStep } from '../AgentGenerationStep';
import { maicApi, maicStudentApi } from '../../../services/openmaicService';
import type { MAICAgent } from '../../../types/maic';

// We manually mock the parts of the service that the component touches so
// the tests don't depend on vitest's auto-mock heuristics for object exports.
vi.mock('../../../services/openmaicService', () => ({
  maicApi: {
    generateAgentProfiles: vi.fn(),
    regenerateAgent: vi.fn(),
    ttsPreview: vi.fn(),
    listVoices: vi.fn(),
  },
  maicStudentApi: {
    generateAgentProfiles: vi.fn(),
    regenerateAgent: vi.fn(),
  },
}));

const mockAgents: MAICAgent[] = [
  {
    id: 'agent-1',
    name: 'Dr. Aarav Sharma',
    role: 'professor',
    avatar: '\u{1F468}\u200D\u{1F3EB}',
    color: '#4338CA',
    voiceId: 'en-IN-PrabhatNeural',
    voiceProvider: 'azure',
    personality: 'Patient.',
    expertise: 'Leads.',
    speakingStyle: 'Warm.',
  },
  {
    id: 'agent-2',
    name: 'Ms. Priya Iyer',
    role: 'teaching_assistant',
    avatar: '\u{1F469}\u200D\u{1F3EB}',
    color: '#DB2777',
    voiceId: 'en-IN-NeerjaNeural',
    voiceProvider: 'azure',
    personality: 'Supportive.',
    expertise: 'Guides practice.',
    speakingStyle: 'Encouraging.',
  },
];

/** Install default happy-path mocks. Individual tests override as needed. */
function installDefaultMocks() {
  vi.mocked(maicApi.generateAgentProfiles).mockResolvedValue({
    data: { agents: mockAgents },
  } as never);
  vi.mocked(maicApi.listVoices).mockResolvedValue({
    data: { voices: [] },
  } as never);
  vi.mocked(maicApi.regenerateAgent).mockResolvedValue({
    data: { agent: mockAgents[0] },
  } as never);
  vi.mocked(maicApi.ttsPreview).mockResolvedValue({
    data: new Blob(),
  } as never);
  vi.mocked(maicStudentApi.generateAgentProfiles).mockResolvedValue({
    data: { agents: mockAgents },
  } as never);
  vi.mocked(maicStudentApi.regenerateAgent).mockResolvedValue({
    data: { agent: mockAgents[0] },
  } as never);
}

describe('AgentGenerationStep', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installDefaultMocks();
  });

  test('loads agents on mount and renders the roster', async () => {
    render(
      <AgentGenerationStep
        topic="Photosynthesis"
        language="en"
        role="teacher"
        onComplete={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(screen.getByText('Dr. Aarav Sharma')).toBeInTheDocument(),
    );
    expect(screen.getByText('Ms. Priya Iyer')).toBeInTheDocument();
  });

  test('"Looks good →" calls onComplete with the current agents', async () => {
    const onComplete = vi.fn();
    render(
      <AgentGenerationStep
        topic="Photosynthesis"
        language="en"
        role="teacher"
        onComplete={onComplete}
        onBack={vi.fn()}
      />,
    );

    await waitFor(() => screen.getByText('Dr. Aarav Sharma'));
    fireEvent.click(screen.getByRole('button', { name: /Looks good/i }));
    expect(onComplete).toHaveBeenCalledWith(mockAgents);
  });

  test('"Regenerate all" shows a confirmation dialog', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    render(
      <AgentGenerationStep
        topic="Photosynthesis"
        language="en"
        role="teacher"
        onComplete={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    await waitFor(() => screen.getByText('Dr. Aarav Sharma'));
    fireEvent.click(screen.getByRole('button', { name: /Regenerate all/i }));
    expect(confirmSpy).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  test('student role uses the student API surface', async () => {
    render(
      <AgentGenerationStep
        topic="Photosynthesis"
        language="en"
        role="student"
        onComplete={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(maicStudentApi.generateAgentProfiles).toHaveBeenCalled(),
    );
    expect(maicApi.generateAgentProfiles).not.toHaveBeenCalled();
  });

  test('shows an error banner when the agent request fails', async () => {
    vi.mocked(maicApi.generateAgentProfiles).mockRejectedValue(new Error('boom'));

    render(
      <AgentGenerationStep
        topic="Photosynthesis"
        language="en"
        role="teacher"
        onComplete={vi.fn()}
        onBack={vi.fn()}
      />,
    );

    await waitFor(() =>
      expect(screen.getByText(/couldn't generate agents/i)).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
  });
});
