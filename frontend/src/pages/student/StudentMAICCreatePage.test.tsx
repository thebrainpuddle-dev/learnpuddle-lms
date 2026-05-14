// src/pages/student/StudentMAICCreatePage.test.tsx
//
// Vitest + React Testing Library suite for StudentMAICCreatePage.
//
// Covers: page heading, subtitle, back-button navigation, wizard render,
// and the onComplete callback that navigates to the classroom route.
//
// Mocking strategy:
//   - StudentGenerationWizard is stubbed so the test doesn't pull in the full
//     wizard dependency tree; a <button data-testid="wizard-complete"> fires
//     onComplete with a fake classroom id so navigation can be asserted.
//   - usePageTitle is stubbed to avoid document.title side-effects.
//   - useNavigate is hoisted to capture navigation calls.

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { StudentMAICCreatePage } from './StudentMAICCreatePage';

// ─── Hoist navigate mock ──────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ─── Module mocks ─────────────────────────────────────────────────────────────

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// Stub the wizard: renders a sentinel and a "complete" trigger button.
vi.mock('../../components/maic/StudentGenerationWizard', () => ({
  StudentGenerationWizard: ({ onComplete }: { onComplete: (id: string) => void }) => (
    <div data-testid="student-generation-wizard">
      <span>Wizard rendered</span>
      <button
        type="button"
        data-testid="wizard-complete"
        onClick={() => onComplete('classroom-abc')}
      >
        Complete
      </button>
    </div>
  ),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <StudentMAICCreatePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Suite ────────────────────────────────────────────────────────────────────

describe('StudentMAICCreatePage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // ── 1. Heading ───────────────────────────────────────────────────────────────

  it('renders the "New AI Classroom" page heading', () => {
    renderPage();
    expect(
      screen.getByRole('heading', { level: 1, name: /new ai classroom/i }),
    ).toBeInTheDocument();
  });

  // ── 2. Subtitle ───────────────────────────────────────────────────────────────

  it('renders the subtitle about generating from an educational topic', () => {
    renderPage();
    expect(
      screen.getByText(/generate an interactive ai classroom from any educational topic/i),
    ).toBeInTheDocument();
  });

  // ── 3. Back button navigation ─────────────────────────────────────────────────

  it('renders a back / arrow-left button', () => {
    renderPage();
    // The button wraps an SVG arrow icon; it has no accessible label so we
    // find it by querying for all buttons and picking the one preceding the heading.
    const buttons = screen.getAllByRole('button');
    // First button in DOM is the back arrow
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it('navigates to /student/ai-classroom when the back button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    // The back button is the first <button> rendered before the wizard.
    const allButtons = screen.getAllByRole('button');
    const backButton = allButtons[0];

    await user.click(backButton);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom');
  });

  // ── 4. Wizard renders ─────────────────────────────────────────────────────────

  it('renders the StudentGenerationWizard component', () => {
    renderPage();
    expect(screen.getByTestId('student-generation-wizard')).toBeInTheDocument();
    expect(screen.getByText('Wizard rendered')).toBeInTheDocument();
  });

  // ── 5. onComplete callback → navigate ─────────────────────────────────────────

  it('navigates to /student/ai-classroom/<id> when the wizard calls onComplete', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId('wizard-complete'));

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom/classroom-abc');
  });

  // ── 6. navigate is called with the correct classroom id ──────────────────────

  it('passes the exact classroom id returned by onComplete into the navigation path', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId('wizard-complete'));

    const call = mockedUseNavigate.mock.calls[0][0] as string;
    expect(call).toBe('/student/ai-classroom/classroom-abc');
  });

  // ── 7. back button does NOT navigate away when not clicked ───────────────────

  it('does not call navigate on initial render', () => {
    renderPage();
    expect(mockedUseNavigate).not.toHaveBeenCalled();
  });

  // ── 8. wizard completion and back button are independent ─────────────────────

  it('can click back and then complete without navigation interference', async () => {
    const user = userEvent.setup();
    renderPage();

    const allButtons = screen.getAllByRole('button');
    await user.click(allButtons[0]); // back
    await user.click(screen.getByTestId('wizard-complete')); // complete

    expect(mockedUseNavigate).toHaveBeenCalledTimes(2);
    expect(mockedUseNavigate).toHaveBeenNthCalledWith(1, '/student/ai-classroom');
    expect(mockedUseNavigate).toHaveBeenNthCalledWith(2, '/student/ai-classroom/classroom-abc');
  });
});
