import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FishEvolutionWidget, getFishStageFromPoints, getSliderFromPoints } from './FishEvolutionWidget';

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: jest.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      addListener: jest.fn(),
      removeListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
}

describe('FishEvolutionWidget', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockMatchMedia(false);
  });

  it('maps points to stage boundaries', () => {
    expect(getFishStageFromPoints(0).key).toBe('PUDDLE');
    expect(getFishStageFromPoints(200).key).toBe('POND');
    expect(getFishStageFromPoints(600).key).toBe('LAKE');
    expect(getFishStageFromPoints(1200).key).toBe('RIVER');
    expect(getFishStageFromPoints(2500).key).toBe('OCEAN');
    expect(getSliderFromPoints(2500)).toBe(100);
  });

  it('supports slider and play interaction', async () => {
    render(<FishEvolutionWidget pointsTotal={340} />);

    expect(screen.getByRole('img', { name: /live fish and puddle animation/i })).toBeInTheDocument();
    expect(screen.getByRole('listitem', { name: 'Pond state' })).toHaveClass('is-current');

    await userEvent.click(screen.getByRole('listitem', { name: 'Ocean state' }));
    expect(screen.getByRole('listitem', { name: 'Ocean state' })).toHaveClass('is-muted');
    expect(screen.getByRole('listitem', { name: 'Ocean state' })).toHaveClass('is-preview');

    await userEvent.click(screen.getByRole('button', { name: /play animation/i }));
    expect(screen.getByRole('button', { name: /pause animation/i })).toBeInTheDocument();
  });

  it('disables animation controls for reduced motion users', () => {
    mockMatchMedia(true);
    render(<FishEvolutionWidget pointsTotal={340} />);

    const button = screen.getByRole('button', { name: /play animation/i });
    expect(button).toBeDisabled();
    expect(button).toHaveTextContent('Animation Off');
  });
});
