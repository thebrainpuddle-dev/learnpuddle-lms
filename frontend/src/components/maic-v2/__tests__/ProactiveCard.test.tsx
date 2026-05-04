/**
 * Tests for ProactiveCard (MAIC-411.1).
 *
 * Pure presentational component — no engine, no WS, no state machine.
 * Just verify the visual contract + button wiring.
 */
import { describe, expect, test, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import { ProactiveCard } from '../ProactiveCard';
import type { TriggerEvent } from '../../../lib/maic-v2/playback-types';


function makeTrigger(overrides: Partial<TriggerEvent> = {}): TriggerEvent {
  return {
    id: 'd1',
    question: 'What are fractions?',
    ...overrides,
  };
}


describe('ProactiveCard', () => {
  test('renders the trigger question', () => {
    render(
      <ProactiveCard
        trigger={makeTrigger({ question: 'Photosynthesis vs respiration?' })}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    expect(
      screen.getByTestId('maic-v2-proactive-card-question'),
    ).toHaveTextContent('Photosynthesis vs respiration?');
  });

  test('renders the prompt when present', () => {
    render(
      <ProactiveCard
        trigger={makeTrigger({
          prompt: 'Discuss the energy flow direction in each.',
        })}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    expect(
      screen.getByTestId('maic-v2-proactive-card-prompt'),
    ).toHaveTextContent('Discuss the energy flow direction in each.');
  });

  test('omits the prompt block when prompt is undefined', () => {
    render(
      <ProactiveCard
        trigger={makeTrigger({ prompt: undefined })}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    expect(
      screen.queryByTestId('maic-v2-proactive-card-prompt'),
    ).toBeNull();
  });

  test('clicking Join calls onJoin (and not onSkip)', () => {
    const onJoin = vi.fn();
    const onSkip = vi.fn();
    render(
      <ProactiveCard
        trigger={makeTrigger()}
        onJoin={onJoin}
        onSkip={onSkip}
      />,
    );
    fireEvent.click(screen.getByTestId('maic-v2-proactive-card-join'));
    expect(onJoin).toHaveBeenCalledTimes(1);
    expect(onSkip).not.toHaveBeenCalled();
  });

  test('clicking Skip calls onSkip (and not onJoin)', () => {
    const onJoin = vi.fn();
    const onSkip = vi.fn();
    render(
      <ProactiveCard
        trigger={makeTrigger()}
        onJoin={onJoin}
        onSkip={onSkip}
      />,
    );
    fireEvent.click(screen.getByTestId('maic-v2-proactive-card-skip'));
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onJoin).not.toHaveBeenCalled();
  });

  test('exposes the trigger id via data-attribute', () => {
    render(
      <ProactiveCard
        trigger={makeTrigger({ id: 'd-photosynthesis' })}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    expect(
      screen.getByTestId('maic-v2-proactive-card'),
    ).toHaveAttribute('data-trigger-id', 'd-photosynthesis');
  });

  test('applies the entry-animation class', () => {
    // Locks the contract: a CSS class drives the entry; if a future
    // refactor swaps to inline style or motion, this test catches it.
    render(
      <ProactiveCard
        trigger={makeTrigger()}
        onJoin={() => {}}
        onSkip={() => {}}
      />,
    );
    const card = screen.getByTestId('maic-v2-proactive-card');
    expect(card.className).toContain('proactive-card-enter');
  });
});
