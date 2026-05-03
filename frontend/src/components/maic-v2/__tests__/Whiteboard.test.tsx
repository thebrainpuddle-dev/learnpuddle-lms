/**
 * Tests for src/components/maic-v2/Whiteboard.tsx (MAIC-210.1).
 *
 * Pure presentational — verifies open/closed visibility, the 1000×562
 * aspect ratio, and that children render inside the frame container so
 * downstream renderers (TextElement, ShapeElement, etc.) have a stable
 * mounting point with predictable absolute-positioning coordinates.
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Whiteboard } from '../Whiteboard';


describe('Whiteboard surface', () => {
  test('renders nothing when isOpen=false', () => {
    const { container } = render(<Whiteboard isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });

  test('renders the surface when isOpen=true', () => {
    render(<Whiteboard isOpen={true} />);
    expect(screen.getByTestId('maic-v2-whiteboard')).toBeInTheDocument();
    expect(screen.getByTestId('maic-v2-whiteboard-frame')).toBeInTheDocument();
  });

  test('exposes data-whiteboard-open attribute when open', () => {
    render(<Whiteboard isOpen={true} />);
    expect(screen.getByTestId('maic-v2-whiteboard')).toHaveAttribute(
      'data-whiteboard-open',
      'true',
    );
  });

  test('uses 1000×562 aspect ratio for responsive scaling', () => {
    render(<Whiteboard isOpen={true} />);
    const surface = screen.getByTestId('maic-v2-whiteboard');
    expect(surface).toHaveStyle({ aspectRatio: '1000 / 562' });
  });

  test('renders children inside the frame', () => {
    render(
      <Whiteboard isOpen={true}>
        <div data-testid="probe-child">x</div>
      </Whiteboard>,
    );
    const frame = screen.getByTestId('maic-v2-whiteboard-frame');
    const child = screen.getByTestId('probe-child');
    expect(frame.contains(child)).toBe(true);
  });

  test('mount is binary — false→true→false adds and removes from DOM', () => {
    const { rerender, container } = render(<Whiteboard isOpen={false} />);
    expect(container.firstChild).toBeNull();
    rerender(<Whiteboard isOpen={true} />);
    expect(screen.getByTestId('maic-v2-whiteboard')).toBeInTheDocument();
    rerender(<Whiteboard isOpen={false} />);
    expect(container.firstChild).toBeNull();
  });
});
