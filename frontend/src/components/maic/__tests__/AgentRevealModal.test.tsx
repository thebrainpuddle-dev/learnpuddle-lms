import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AgentRevealModal } from '../AgentRevealModal';
import type { MAICAgent } from '../../../types/maic';

const agents: MAICAgent[] = [
  {
    id: 'agent-1',
    name: 'Dr. Asha Rao',
    role: 'professor',
    avatar: 'A',
    color: '#4F46E5',
    personality: 'Clear and practical.',
  },
];

describe('AgentRevealModal', () => {
  it('focuses and dismisses after the real reveal timing completes', async () => {
    const onContinue = vi.fn();

    render(<AgentRevealModal agents={agents} open onContinue={onContinue} />);

    const continueButton = screen.getByTestId('agent-reveal-continue');
    expect(continueButton).toBeDisabled();

    await waitFor(() => expect(continueButton).toBeEnabled(), { timeout: 2500 });
    expect(continueButton).toHaveFocus();

    fireEvent.click(continueButton);

    expect(onContinue).toHaveBeenCalledTimes(1);
  });

  it('supports Enter as a keyboard handoff after the reveal completes', async () => {
    const onContinue = vi.fn();

    render(<AgentRevealModal agents={agents} open onContinue={onContinue} />);

    await waitFor(() => expect(screen.getByTestId('agent-reveal-continue')).toBeEnabled(), {
      timeout: 2500,
    });

    fireEvent.keyDown(screen.getByRole('dialog', { name: 'Meet your classroom agents' }), {
      key: 'Enter',
    });

    expect(onContinue).toHaveBeenCalledTimes(1);
  });
});
