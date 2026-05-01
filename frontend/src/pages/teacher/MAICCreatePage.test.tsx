// src/pages/teacher/MAICCreatePage.test.tsx
//
// FE-060: Tests for the Teacher New AI Classroom (MAICCreatePage).
// Covers: page header ("New AI Classroom"), subtitle text, back button
//         navigates to /teacher/ai-classroom, GenerationWizard is rendered,
//         onComplete callback navigates to /teacher/ai-classroom/:id.
//
// Mocking strategy:
//   - GenerationWizard stubbed to expose an onComplete trigger button
//   - useNavigate mocked via importOriginal spread
//   - usePageTitle stubbed

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MAICCreatePage } from './MAICCreatePage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

// Stub GenerationWizard — exposes a "Complete" button that fires onComplete
vi.mock('../../components/maic/GenerationWizard', () => ({
  GenerationWizard: ({ onComplete }: { onComplete: (id: string) => void }) => (
    <div data-testid="generation-wizard">
      <button onClick={() => onComplete('classroom-42')}>Complete Wizard</button>
    </div>
  ),
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderPage() {
  return render(
    <MemoryRouter>
      <MAICCreatePage />
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('MAICCreatePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders "New AI Classroom" heading', () => {
    renderPage();
    expect(
      screen.getByRole('heading', { level: 1, name: /new ai classroom/i }),
    ).toBeInTheDocument();
  });

  it('renders subtitle text about AI-powered interactive classroom', () => {
    renderPage();
    expect(
      screen.getByText(/configure and generate an ai-powered interactive classroom/i),
    ).toBeInTheDocument();
  });

  it('renders the GenerationWizard component', () => {
    renderPage();
    expect(screen.getByTestId('generation-wizard')).toBeInTheDocument();
  });

  it('navigates back to /teacher/ai-classroom when back button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    // Back button is the only button that doesn't come from the wizard
    const buttons = screen.getAllByRole('button');
    // The back button is the first button (before the wizard's "Complete Wizard" button)
    const backButton = buttons[0];
    await user.click(backButton);
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/ai-classroom');
  });

  it('navigates to /teacher/ai-classroom/:id when wizard completes', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(screen.getByRole('button', { name: /complete wizard/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/ai-classroom/classroom-42');
  });
});
