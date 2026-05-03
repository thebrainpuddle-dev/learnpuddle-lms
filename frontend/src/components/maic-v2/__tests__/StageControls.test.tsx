/**
 * Tests for src/components/maic-v2/StageControls.tsx (MAIC-403.6).
 *
 * Verifies mode → button visibility mapping, canStart gate, and
 * callback fan-out (each click calls the matching prop exactly once).
 */
import { describe, test, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { StageControls } from '../StageControls';
import type { StageControlsProps } from '../StageControls';
import type { EngineMode } from '../../../lib/maic-v2/playback-types';


function defaults(overrides: Partial<StageControlsProps> = {}): StageControlsProps {
  return {
    mode: 'idle',
    canStart: true,
    onStart: vi.fn(),
    onPause: vi.fn(),
    onResume: vi.fn(),
    onStop: vi.fn(),
    ...overrides,
  };
}


describe('StageControls — visibility per mode', () => {
  test.each<[EngineMode, string[]]>([
    ['idle', ['maic-v2-control-start']],
    ['playing', ['maic-v2-control-pause', 'maic-v2-control-stop']],
    ['paused', ['maic-v2-control-resume', 'maic-v2-control-stop']],
    ['live', ['maic-v2-control-stop']],
  ])('mode=%s exposes %j', (mode, expected) => {
    render(<StageControls {...defaults({ mode })} />);
    for (const id of expected) {
      expect(screen.getByTestId(id)).toBeInTheDocument();
    }
    // Other control test-ids should NOT be present.
    const all = [
      'maic-v2-control-start',
      'maic-v2-control-pause',
      'maic-v2-control-resume',
      'maic-v2-control-stop',
    ];
    for (const id of all) {
      if (!expected.includes(id)) {
        expect(screen.queryByTestId(id)).toBeNull();
      }
    }
  });
});


describe('StageControls — canStart gate', () => {
  test('Start is disabled when canStart=false', () => {
    render(<StageControls {...defaults({ mode: 'idle', canStart: false })} />);
    const btn = screen.getByTestId('maic-v2-control-start') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  test('Start is enabled when canStart=true', () => {
    render(<StageControls {...defaults({ mode: 'idle', canStart: true })} />);
    const btn = screen.getByTestId('maic-v2-control-start') as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });
});


describe('StageControls — callback fan-out', () => {
  test('Start click fires onStart exactly once', () => {
    const onStart = vi.fn();
    render(<StageControls {...defaults({ mode: 'idle', onStart })} />);
    fireEvent.click(screen.getByTestId('maic-v2-control-start'));
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  test('Pause click fires onPause exactly once', () => {
    const onPause = vi.fn();
    render(<StageControls {...defaults({ mode: 'playing', onPause })} />);
    fireEvent.click(screen.getByTestId('maic-v2-control-pause'));
    expect(onPause).toHaveBeenCalledTimes(1);
  });

  test('Resume click fires onResume exactly once', () => {
    const onResume = vi.fn();
    render(<StageControls {...defaults({ mode: 'paused', onResume })} />);
    fireEvent.click(screen.getByTestId('maic-v2-control-resume'));
    expect(onResume).toHaveBeenCalledTimes(1);
  });

  test('Stop click fires onStop exactly once (visible in playing/paused/live)', () => {
    const onStop = vi.fn();
    render(<StageControls {...defaults({ mode: 'playing', onStop })} />);
    fireEvent.click(screen.getByTestId('maic-v2-control-stop'));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  test('disabled Start does not fire onStart when clicked', () => {
    const onStart = vi.fn();
    render(<StageControls {...defaults({ mode: 'idle', canStart: false, onStart })} />);
    fireEvent.click(screen.getByTestId('maic-v2-control-start'));
    expect(onStart).not.toHaveBeenCalled();
  });
});
