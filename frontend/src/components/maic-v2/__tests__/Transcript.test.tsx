/**
 * Tests for src/components/maic-v2/Transcript.tsx (MAIC-403.5).
 *
 * Pure presentational — assertions cover ordered rendering, thinking
 * hint, cue_user line, error state, and empty-bucket skipping.
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Transcript } from '../Transcript';
import type { TranscriptProps } from '../Transcript';


function defaults(overrides: Partial<TranscriptProps> = {}): TranscriptProps {
  return {
    textByMessageId: {},
    messageOrder: [],
    status: 'idle',
    thinkingStage: null,
    cueingUser: false,
    ...overrides,
  };
}


describe('Transcript', () => {
  test('renders nothing-of-substance when buffer is empty and idle', () => {
    render(<Transcript {...defaults()} />);
    expect(screen.getByTestId('maic-v2-transcript')).toBeInTheDocument();
    expect(screen.queryByTestId('maic-v2-thinking')).toBeNull();
    expect(screen.queryByTestId('maic-v2-cue-user')).toBeNull();
  });

  test('shows the thinking hint with stage label when status=thinking', () => {
    render(
      <Transcript
        {...defaults({ status: 'thinking', thinkingStage: 'agent_loading' })}
      />,
    );
    const hint = screen.getByTestId('maic-v2-thinking');
    expect(hint).toBeInTheDocument();
    expect(hint).toHaveTextContent('agent_loading');
  });

  test('falls back to "Thinking…" when stage is null', () => {
    render(<Transcript {...defaults({ status: 'thinking', thinkingStage: null })} />);
    expect(screen.getByTestId('maic-v2-thinking')).toHaveTextContent('Thinking…');
  });

  test('renders text lines in messageOrder', () => {
    render(
      <Transcript
        {...defaults({
          status: 'streaming',
          messageOrder: ['m1', 'm2'],
          textByMessageId: { m1: 'First line.', m2: 'Second line.' },
        })}
      />,
    );
    const m1 = screen.getByTestId('maic-v2-transcript-line-m1');
    const m2 = screen.getByTestId('maic-v2-transcript-line-m2');
    expect(m1).toHaveTextContent('First line.');
    expect(m2).toHaveTextContent('Second line.');

    const transcript = screen.getByTestId('maic-v2-transcript');
    const lines = transcript.querySelectorAll('p[data-testid^="maic-v2-transcript-line-"]');
    expect(Array.from(lines).map((p) => p.getAttribute('data-testid'))).toEqual([
      'maic-v2-transcript-line-m1',
      'maic-v2-transcript-line-m2',
    ]);
  });

  test('renders agent identity for each message when metadata is present', () => {
    render(
      <Transcript
        {...defaults({
          status: 'streaming',
          messageOrder: ['m1'],
          textByMessageId: { m1: 'Teacher line.' },
          agentsByMessageId: {
            m1: {
              agentId: 'teacher',
              agentName: 'Math Coach',
              agentAvatar: null,
              agentColor: '#2563eb',
              messageId: 'm1',
            },
          },
        })}
      />,
    );
    expect(screen.getByTestId('maic-v2-transcript-agent-m1')).toHaveTextContent(
      'Math Coach',
    );
    expect(screen.getByTestId('maic-v2-transcript-row-m1')).toHaveStyle(
      'border-left: 4px solid #2563eb',
    );
  });

  test('skips messageIds with empty text', () => {
    render(
      <Transcript
        {...defaults({
          status: 'streaming',
          messageOrder: ['m1', 'm2'],
          textByMessageId: { m1: '', m2: 'Real content.' },
        })}
      />,
    );
    expect(screen.queryByTestId('maic-v2-transcript-line-m1')).toBeNull();
    expect(screen.getByTestId('maic-v2-transcript-line-m2')).toBeInTheDocument();
  });

  test('renders the cue-user line when cueingUser=true', () => {
    render(<Transcript {...defaults({ status: 'completed', cueingUser: true })} />);
    expect(screen.getByTestId('maic-v2-cue-user')).toHaveTextContent(
      /Your turn/i,
    );
  });

  test('renders error fallback only when status=error AND no text yet', () => {
    render(<Transcript {...defaults({ status: 'error' })} />);
    expect(screen.getByTestId('maic-v2-transcript-error')).toBeInTheDocument();
  });

  test('hides the error fallback when text is already on screen', () => {
    render(
      <Transcript
        {...defaults({
          status: 'error',
          messageOrder: ['m1'],
          textByMessageId: { m1: 'Partial output before failure.' },
        })}
      />,
    );
    expect(screen.queryByTestId('maic-v2-transcript-error')).toBeNull();
    expect(screen.getByTestId('maic-v2-transcript-line-m1')).toBeInTheDocument();
  });
});
