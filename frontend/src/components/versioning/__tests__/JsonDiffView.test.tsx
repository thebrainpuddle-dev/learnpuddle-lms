// src/components/versioning/__tests__/JsonDiffView.test.tsx
//
// Tests for the JsonDiffView component.

import React from 'react';
import { render, screen } from '@testing-library/react';
import { JsonDiffView } from '../JsonDiffView';

describe('JsonDiffView', () => {
  it('shows "no differences" message when old and new values are identical', () => {
    const snap = { title: 'Hello', order: 1 };
    render(<JsonDiffView oldValue={snap} newValue={snap} />);
    expect(
      screen.getByText(/No differences — snapshot matches current state/i),
    ).toBeInTheDocument();
  });

  it('renders an added key with "+" prefix', () => {
    render(<JsonDiffView oldValue={{}} newValue={{ title: 'New Course' }} />);
    expect(screen.getByText(/\+ title:/i)).toBeInTheDocument();
    expect(screen.getByText(/"New Course"/)).toBeInTheDocument();
  });

  it('renders a removed key with "-" prefix', () => {
    render(<JsonDiffView oldValue={{ title: 'Old Course' }} newValue={{}} />);
    expect(screen.getByText(/- title:/i)).toBeInTheDocument();
    expect(screen.getByText(/"Old Course"/)).toBeInTheDocument();
  });

  it('renders a changed key with "~" prefix and shows both old and new values', () => {
    render(
      <JsonDiffView
        oldValue={{ title: 'Before' }}
        newValue={{ title: 'After' }}
      />,
    );
    expect(screen.getByText(/~ title:/i)).toBeInTheDocument();
    expect(screen.getByText(/"Before"/)).toBeInTheDocument();
    expect(screen.getByText(/"After"/)).toBeInTheDocument();
  });

  it('handles the empty / first-revision case — undefined oldValue shows all keys as added', () => {
    render(<JsonDiffView oldValue={undefined} newValue={{ foo: 'bar' }} />);
    expect(screen.getByText(/\+ foo:/i)).toBeInTheDocument();
    expect(screen.getByText(/"bar"/)).toBeInTheDocument();
  });

  it('renders nested object diffs recursively', () => {
    const oldSnap = { meta: { published: false, title: 'A' } };
    const newSnap = { meta: { published: true, title: 'A' } };
    render(<JsonDiffView oldValue={oldSnap} newValue={newSnap} />);
    expect(screen.getByText(/meta:/i)).toBeInTheDocument();
    // published changed from false → true
    expect(screen.getByText(/~ published:/i)).toBeInTheDocument();
  });

  it('handles arrays — shows added element', () => {
    render(
      <JsonDiffView
        oldValue={{ tags: ['a'] }}
        newValue={{ tags: ['a', 'b'] }}
      />,
    );
    // Second element (index 1) was added
    expect(screen.getByText(/\+ 1:/i)).toBeInTheDocument();
  });

  it('shows the legend row', () => {
    render(<JsonDiffView oldValue={{ x: 1 }} newValue={{ x: 2 }} />);
    expect(screen.getByText(/Added/i)).toBeInTheDocument();
    expect(screen.getByText(/Removed/i)).toBeInTheDocument();
    expect(screen.getByText(/Changed/i)).toBeInTheDocument();
  });

  it('accepts a custom className', () => {
    const { container } = render(
      <JsonDiffView
        oldValue={{ x: 1 }}
        newValue={{ x: 1 }}
        className="custom-diff-class"
      />,
    );
    expect(container.firstChild).toHaveClass('custom-diff-class');
  });

  it('renders null values as "null"', () => {
    render(
      <JsonDiffView
        oldValue={{ deadline: null }}
        newValue={{ deadline: '2026-12-31' }}
      />,
    );
    expect(screen.getByText(/null/)).toBeInTheDocument();
    expect(screen.getByText(/"2026-12-31"/)).toBeInTheDocument();
  });
});
