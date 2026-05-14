/**
 * Tests for Phase3LiveModeDemo (MAIC-418.1).
 *
 * Smoke-level component test — verifies the demo renders, mounts the
 * engine on Start, surfaces the trigger 3s after Start, and records
 * the would-be WS frames onto data-last-sent-action via real local
 * handlers (NOT mocks).
 *
 * The full live-mode flow (Join → Send → End) is also covered by the
 * Stage integration tests in Stage.test.tsx (MAIC-411.2/411.3) and by
 * the headless Chromium smoke (MAIC-418.3). This test focuses on the
 * demo wiring itself.
 */
import { describe, expect, test, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';

import Phase3LiveModeDemo from '../Phase3LiveModeDemo';


describe('Phase3LiveModeDemo', () => {
  test('renders the demo root with idle mode and empty data-last-sent-action', () => {
    render(<Phase3LiveModeDemo />);
    const root = screen.getByTestId('phase3-live-mode');
    expect(root).toHaveAttribute('data-engine-mode', 'idle');
    expect(root.getAttribute('data-last-sent-action')).toBe('');
  });

  test('exposes the documented testids', () => {
    render(<Phase3LiveModeDemo />);
    expect(screen.getByTestId('phase3-live-mode-start')).toBeInTheDocument();
    expect(screen.getByTestId('phase3-live-mode-mode')).toHaveTextContent('idle');
  });

  test('clicking Start advances engine into playing then triggers ProactiveCard after 3s', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      render(<Phase3LiveModeDemo />);
      fireEvent.click(screen.getByTestId('phase3-live-mode-start'));
      // Engine starts processing — discussion action is consumed and
      // schedules a 3s delay before currentTrigger is set.
      expect(screen.queryByTestId('maic-v2-proactive-card')).toBeNull();

      act(() => {
        vi.advanceTimersByTime(3000);
      });
      // ProactiveCard now visible
      expect(screen.getByTestId('maic-v2-proactive-card')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  test('Join → live mode → LiveInput visible', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      const { container } = render(<Phase3LiveModeDemo />);
      fireEvent.click(screen.getByTestId('phase3-live-mode-start'));
      act(() => {
        vi.advanceTimersByTime(3000);
      });
      fireEvent.click(screen.getByTestId('maic-v2-proactive-card-join'));
      const root = container.querySelector('[data-testid="phase3-live-mode"]')!;
      expect(root.getAttribute('data-engine-mode')).toBe('live');
      expect(screen.getByTestId('maic-v2-live-input')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  test('Send records data-last-sent-action with user_message JSON shape', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      const { container } = render(<Phase3LiveModeDemo />);
      fireEvent.click(screen.getByTestId('phase3-live-mode-start'));
      act(() => {
        vi.advanceTimersByTime(3000);
      });
      fireEvent.click(screen.getByTestId('maic-v2-proactive-card-join'));

      const input = screen.getByTestId('maic-v2-live-input-text');
      fireEvent.change(input, { target: { value: 'edge case question?' } });
      fireEvent.click(screen.getByTestId('maic-v2-live-input-send'));

      const root = container.querySelector('[data-testid="phase3-live-mode"]')!;
      const raw = root.getAttribute('data-last-sent-action');
      expect(raw).toBeTruthy();
      const parsed = JSON.parse(raw!);
      expect(parsed).toEqual({
        action: 'user_message',
        data: { text: 'edge case question?' },
      });
    } finally {
      vi.useRealTimers();
    }
  });

  test('End Discussion records resume frame and exits live mode', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    try {
      const { container } = render(<Phase3LiveModeDemo />);
      fireEvent.click(screen.getByTestId('phase3-live-mode-start'));
      act(() => {
        vi.advanceTimersByTime(3000);
      });
      fireEvent.click(screen.getByTestId('maic-v2-proactive-card-join'));
      fireEvent.click(screen.getByTestId('maic-v2-live-input-end'));

      const root = container.querySelector('[data-testid="phase3-live-mode"]')!;
      const parsed = JSON.parse(root.getAttribute('data-last-sent-action')!);
      expect(parsed).toEqual({ action: 'resume' });
      // Mode out of `live` (engine reaches idle after exhausting
      // the single discussion action).
      expect(root.getAttribute('data-engine-mode')).not.toBe('live');
    } finally {
      vi.useRealTimers();
    }
  });
});
