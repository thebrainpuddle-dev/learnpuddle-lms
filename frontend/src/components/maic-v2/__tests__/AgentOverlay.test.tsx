/**
 * Tests for src/components/maic-v2/AgentOverlay.tsx (MAIC-403.4).
 *
 * Pure presentational component — assertions cover null-agent path,
 * avatar-string interpretation (URL vs text), color application, and
 * the conditional voice-wave indicator.
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { AgentOverlay } from '../AgentOverlay';
import type { AgentSnapshot } from '../../../lib/maic-v2/scene-buffer';


function makeAgent(overrides: Partial<AgentSnapshot> = {}): AgentSnapshot {
  return {
    agentId: 'default-1',
    agentName: 'AI Teacher',
    agentAvatar: '🎓',
    agentColor: '#3b82f6',
    messageId: 'm1',
    ...overrides,
  };
}


describe('AgentOverlay', () => {
  test('renders nothing when agent is null', () => {
    const { container } = render(<AgentOverlay agent={null} speaking={false} />);
    expect(container.firstChild).toBeNull();
  });

  test('renders agent name and emoji avatar with theme color', () => {
    render(<AgentOverlay agent={makeAgent()} speaking={false} />);
    const name = screen.getByTestId('maic-v2-agent-name');
    expect(name).toHaveTextContent('AI Teacher');
    expect(name).toHaveStyle({ color: '#3b82f6' });
    expect(screen.getByTestId('maic-v2-agent-avatar')).toHaveTextContent('🎓');
  });

  test('falls back to first character of name when avatar is null', () => {
    const agent = makeAgent({ agentAvatar: null, agentName: 'Sahana' });
    render(<AgentOverlay agent={agent} speaking={false} />);
    expect(screen.getByTestId('maic-v2-agent-avatar')).toHaveTextContent('S');
  });

  test('renders an <img> when avatar is a URL', () => {
    const agent = makeAgent({ agentAvatar: 'https://cdn.example/avatar.png' });
    const { container } = render(<AgentOverlay agent={agent} speaking={false} />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img!.getAttribute('src')).toBe('https://cdn.example/avatar.png');
    expect(img!.getAttribute('alt')).toBe('AI Teacher');
  });

  test('renders an <img> for path-based avatars (starts with /)', () => {
    const agent = makeAgent({ agentAvatar: '/avatars/teacher.png' });
    const { container } = render(<AgentOverlay agent={agent} speaking={false} />);
    expect(container.querySelector('img')).not.toBeNull();
  });

  test('renders an <img> for data: avatars', () => {
    const agent = makeAgent({ agentAvatar: 'data:image/png;base64,iVBOR' });
    const { container } = render(<AgentOverlay agent={agent} speaking={false} />);
    expect(container.querySelector('img')).not.toBeNull();
  });

  test('shows the voice-wave indicator when speaking=true', () => {
    render(<AgentOverlay agent={makeAgent()} speaking={true} />);
    const wave = screen.getByTestId('maic-v2-voice-wave');
    expect(wave).toBeInTheDocument();
    expect(wave.children).toHaveLength(3);
  });

  test('hides the voice-wave indicator when speaking=false', () => {
    render(<AgentOverlay agent={makeAgent()} speaking={false} />);
    expect(screen.queryByTestId('maic-v2-voice-wave')).toBeNull();
  });
});
