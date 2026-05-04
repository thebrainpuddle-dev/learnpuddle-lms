/**
 * Tests for LiveInput (MAIC-411.3).
 *
 * Pure presentational component — no engine, no WS. Verifies the
 * input + button behavior + keyboard shortcut + empty-text guard.
 */
import { describe, expect, test, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { LiveInput } from '../LiveInput';


describe('LiveInput', () => {
  test('renders text input + Send + End Discussion buttons', () => {
    render(<LiveInput onSend={() => {}} onEnd={() => {}} />);
    expect(screen.getByTestId('maic-v2-live-input-text')).toBeInTheDocument();
    expect(screen.getByTestId('maic-v2-live-input-send')).toBeInTheDocument();
    expect(screen.getByTestId('maic-v2-live-input-end')).toBeInTheDocument();
  });

  test('Send button is disabled when input is empty', () => {
    render(<LiveInput onSend={() => {}} onEnd={() => {}} />);
    expect(screen.getByTestId('maic-v2-live-input-send')).toBeDisabled();
  });

  test('Send button is disabled when input is whitespace-only', () => {
    render(<LiveInput onSend={() => {}} onEnd={() => {}} />);
    fireEvent.change(screen.getByTestId('maic-v2-live-input-text'), {
      target: { value: '   ' },
    });
    expect(screen.getByTestId('maic-v2-live-input-send')).toBeDisabled();
  });

  test('Send button enables when non-whitespace text is entered', () => {
    render(<LiveInput onSend={() => {}} onEnd={() => {}} />);
    fireEvent.change(screen.getByTestId('maic-v2-live-input-text'), {
      target: { value: 'hi' },
    });
    expect(screen.getByTestId('maic-v2-live-input-send')).not.toBeDisabled();
  });

  test('clicking Send calls onSend with trimmed text and clears input', () => {
    const onSend = vi.fn();
    render(<LiveInput onSend={onSend} onEnd={() => {}} />);
    const input = screen.getByTestId('maic-v2-live-input-text') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '  hello world  ' } });
    fireEvent.click(screen.getByTestId('maic-v2-live-input-send'));
    expect(onSend).toHaveBeenCalledWith('hello world');
    expect(input.value).toBe('');
  });

  test('pressing Enter submits the message (single-line plain Enter)', () => {
    const onSend = vi.fn();
    render(<LiveInput onSend={onSend} onEnd={() => {}} />);
    const input = screen.getByTestId('maic-v2-live-input-text');
    fireEvent.change(input, { target: { value: 'enter test' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onSend).toHaveBeenCalledWith('enter test');
  });

  test('Shift+Enter does NOT submit (reserved for multi-line in Phase 5+)', () => {
    const onSend = vi.fn();
    render(<LiveInput onSend={onSend} onEnd={() => {}} />);
    const input = screen.getByTestId('maic-v2-live-input-text');
    fireEvent.change(input, { target: { value: 'shift enter' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(onSend).not.toHaveBeenCalled();
  });

  test('Enter on empty input does NOT submit', () => {
    const onSend = vi.fn();
    render(<LiveInput onSend={onSend} onEnd={() => {}} />);
    fireEvent.keyDown(screen.getByTestId('maic-v2-live-input-text'), {
      key: 'Enter',
    });
    expect(onSend).not.toHaveBeenCalled();
  });

  test('clicking End Discussion calls onEnd', () => {
    const onEnd = vi.fn();
    render(<LiveInput onSend={() => {}} onEnd={onEnd} />);
    fireEvent.click(screen.getByTestId('maic-v2-live-input-end'));
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  test('End Discussion is always enabled — user can bail at any time', () => {
    render(<LiveInput onSend={() => {}} onEnd={() => {}} />);
    // Even with empty input, End Discussion must work
    expect(
      screen.getByTestId('maic-v2-live-input-end'),
    ).not.toBeDisabled();
  });
});
