// AgentCard.test.tsx — unit tests for the per-agent card used in the wizard's
// agent generation step.

import { describe, expect, test, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AgentCard } from '../AgentCard';
import type { MAICAgent } from '../../../types/maic';

const agent: MAICAgent = {
  id: 'agent-1',
  name: 'Dr. Aarav Sharma',
  role: 'professor',
  avatar: '\u{1F468}\u200D\u{1F3EB}', // 👨‍🏫
  color: '#4338CA',
  voiceId: 'en-IN-PrabhatNeural',
  voiceProvider: 'azure',
  personality: 'Patient.',
  expertise: 'Leads.',
  speakingStyle: 'Warm.',
};

describe('AgentCard', () => {
  test('renders name, role, voice, avatar', () => {
    render(
      <AgentCard
        agent={agent}
        onEdit={() => {}}
        onRegenerate={() => {}}
        onPreviewVoice={() => {}}
        isPreviewing={false}
      />,
    );
    expect(screen.getByText('Dr. Aarav Sharma')).toBeInTheDocument();
    expect(screen.getByText(/professor/i)).toBeInTheDocument();
    expect(screen.getByText(/Prabhat/i)).toBeInTheDocument();
    expect(screen.getByText('\u{1F468}\u200D\u{1F3EB}')).toBeInTheDocument();
  });

  test('fires onEdit when edit button clicked', () => {
    const onEdit = vi.fn();
    render(
      <AgentCard
        agent={agent}
        onEdit={onEdit}
        onRegenerate={() => {}}
        onPreviewVoice={() => {}}
        isPreviewing={false}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    expect(onEdit).toHaveBeenCalledWith(agent);
  });

  test('fires onPreviewVoice with voiceId', () => {
    const onPreviewVoice = vi.fn();
    render(
      <AgentCard
        agent={agent}
        onEdit={() => {}}
        onRegenerate={() => {}}
        onPreviewVoice={onPreviewVoice}
        isPreviewing={false}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /preview voice/i }));
    expect(onPreviewVoice).toHaveBeenCalledWith('en-IN-PrabhatNeural');
  });

  test('shows pause icon when isPreviewing is true', () => {
    const { rerender } = render(
      <AgentCard
        agent={agent}
        onEdit={() => {}}
        onRegenerate={() => {}}
        onPreviewVoice={() => {}}
        isPreviewing={false}
      />,
    );
    expect(
      screen.getByRole('button', { name: /preview voice/i }).getAttribute('data-playing'),
    ).toBe('false');

    rerender(
      <AgentCard
        agent={agent}
        onEdit={() => {}}
        onRegenerate={() => {}}
        onPreviewVoice={() => {}}
        isPreviewing={true}
      />,
    );
    expect(
      screen.getByRole('button', { name: /preview voice/i }).getAttribute('data-playing'),
    ).toBe('true');
  });

  test('shows regenerating overlay when isRegenerating is true', () => {
    render(
      <AgentCard
        agent={agent}
        onEdit={() => {}}
        onRegenerate={() => {}}
        onPreviewVoice={() => {}}
        isPreviewing={false}
        isRegenerating={true}
      />,
    );
    expect(screen.getByText(/regenerating/i)).toBeInTheDocument();
  });

  test('fires onRegenerate with agent id', () => {
    const onRegenerate = vi.fn();
    render(
      <AgentCard
        agent={agent}
        onEdit={() => {}}
        onRegenerate={onRegenerate}
        onPreviewVoice={() => {}}
        isPreviewing={false}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /regen/i }));
    expect(onRegenerate).toHaveBeenCalledWith('agent-1');
  });
});
