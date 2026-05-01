// src/pages/teacher/QuizPlayerPage.test.tsx
//
// FE-067: Tests for the Teacher Quiz Player page.
// Covers: bootstrapping (Loading), no-questions state, live quiz rendering
//         (prompt, type label, MCQ choices, question counter, Previous disabled
//         on Q1, Submit Quiz button on last Q), answer selection, submit flow,
//         ResultView (passed heading, score, Done button).
//
// Mocking strategy:
//   - assessmentService (startAttempt, submitAttempt) via vi.mock
//   - useQuizAttemptStore → dynamic mockStore object, mutated per test
//   - useToast / Loading via vi.mock('../../components/common')
//   - useNavigate via importOriginal spread
//   - usePageTitle stubbed
//
// Route param: `:contentId` — provided via MemoryRouter + Routes + Route.
// "Reuse" path (live quiz): mockStore pre-populated with attemptId + questions
// matching the route contentId — triggers immediate `bootstrapping=false`.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QuizPlayerPage } from './QuizPlayerPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  showToast: vi.fn(),
};

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/assessmentService', () => ({
  assessmentService: {
    startAttempt: vi.fn(),
    submitAttempt: vi.fn(),
  },
}));

// Dynamic store — mutate fields in beforeEach/test body before render.
const mockStore = {
  attemptId: null as string | null,
  contentId: null as string | null,
  questions: [] as Array<{
    id: string;
    type: string;
    prompt: string;
    points: number;
    difficulty: string;
    choices: Array<{ id: string; text: string; order: number }>;
  }>,
  answers: {} as Record<string, unknown>,
  currentIndex: 0,
  endAtMs: null as number | null,
  startedAtMs: null as number | null,
  maxScore: 10,
  start: vi.fn(),
  setAnswer: vi.fn(),
  setCurrentIndex: vi.fn(),
  next: vi.fn(),
  prev: vi.fn(),
  remainingSeconds: vi.fn(() => null as number | null),
  elapsedSeconds: vi.fn(() => 0),
  clear: vi.fn(),
};

vi.mock('../../stores/quizAttemptStore', () => ({
  useQuizAttemptStore: () => mockStore,
}));

vi.mock('../../components/common', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../components/common')>();
  return {
    ...actual,
    useToast: () => mockToast,
    Loading: () => <div data-testid="loading-spinner">Loading…</div>,
  };
});

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { assessmentService } from '../../services/assessmentService';

const mockStartAttempt = assessmentService.startAttempt as ReturnType<typeof vi.fn>;
const mockSubmitAttempt = assessmentService.submitAttempt as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage(contentId = 'content-1') {
  const path = `/teacher/quiz/${contentId}`;
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/teacher/quiz/:contentId"
            element={<QuizPlayerPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeMCQQuestion(overrides: Record<string, unknown> = {}) {
  return {
    id: 'q1',
    type: 'MCQ',
    prompt: 'What is the powerhouse of the cell?',
    points: 2,
    difficulty: 'easy',
    choices: [
      { id: 'c1', text: 'Nucleus', order: 0 },
      { id: 'c2', text: 'Mitochondria', order: 1 },
      { id: 'c3', text: 'Ribosome', order: 2 },
    ],
    ...overrides,
  };
}

function makeStartResponse(questions = [makeMCQQuestion()]) {
  return {
    id: 'attempt-1',
    attempt_number: 1,
    status: 'IN_PROGRESS',
    started_at: new Date().toISOString(),
    time_limit_seconds: 0, // unlimited
    max_score: 10,
    questions,
  };
}

function makeSubmitResponse(passed = true) {
  return {
    id: 'attempt-1',
    status: 'SUBMITTED',
    score: 8,
    max_score: 10,
    score_percent: 80,
    passed,
    time_spent_seconds: 45,
    submitted_at: new Date().toISOString(),
    questions: [makeMCQQuestion()],
    answers: {},
  };
}

/** Reset mockStore to a "live quiz" state with pre-loaded questions. */
function setLiveQuizStore(
  questions = [makeMCQQuestion()],
  currentIndex = 0,
) {
  mockStore.attemptId = 'attempt-1';
  mockStore.contentId = 'content-1';
  mockStore.questions = questions as typeof mockStore.questions;
  mockStore.answers = {};
  mockStore.currentIndex = currentIndex;
  mockStore.endAtMs = null;
  mockStore.startedAtMs = Date.now();
  mockStore.maxScore = 10;
}

/** Reset mockStore to initial (empty) state. */
function resetStore() {
  mockStore.attemptId = null;
  mockStore.contentId = null;
  mockStore.questions = [];
  mockStore.answers = {};
  mockStore.currentIndex = 0;
  mockStore.endAtMs = null;
  mockStore.startedAtMs = null;
  mockStore.maxScore = 10;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('QuizPlayerPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetStore();
    mockStartAttempt.mockResolvedValue(makeStartResponse());
    mockSubmitAttempt.mockResolvedValue(makeSubmitResponse());
    // Reset mock function implementations (cleared by clearAllMocks)
    mockStore.remainingSeconds = vi.fn(() => null);
    mockStore.elapsedSeconds = vi.fn(() => 0);
    mockStore.start = vi.fn();
    mockStore.setAnswer = vi.fn();
    mockStore.setCurrentIndex = vi.fn();
    mockStore.next = vi.fn();
    mockStore.prev = vi.fn();
    mockStore.clear = vi.fn();
  });

  // ── Bootstrapping state ───────────────────────────────────────────────────

  it('shows Loading spinner while attempt is bootstrapping', () => {
    mockStartAttempt.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
  });

  // ── No questions state ────────────────────────────────────────────────────

  it('shows "No questions available." after start with empty questions', async () => {
    // startAttempt resolves, store.start is called (no-op mock), questions stay []
    mockStartAttempt.mockResolvedValue(makeStartResponse([]));
    renderPage();
    expect(
      await screen.findByText('No questions available.'),
    ).toBeInTheDocument();
  });

  // ── Live quiz: rendering ──────────────────────────────────────────────────

  it('renders question prompt', async () => {
    setLiveQuizStore();
    renderPage();
    expect(
      await screen.findByTestId('quiz-prompt'),
    ).toHaveTextContent('What is the powerhouse of the cell?');
  });

  it('renders question type label "Single Choice" for MCQ', async () => {
    setLiveQuizStore();
    renderPage();
    await screen.findByTestId('quiz-prompt');
    expect(screen.getByText(/single choice/i)).toBeInTheDocument();
  });

  it('renders MCQ answer choices', async () => {
    setLiveQuizStore();
    renderPage();
    await screen.findByTestId('quiz-prompt');
    expect(screen.getByText('Nucleus')).toBeInTheDocument();
    expect(screen.getByText('Mitochondria')).toBeInTheDocument();
    expect(screen.getByText('Ribosome')).toBeInTheDocument();
  });

  it('renders question counter "Question 1 of 1"', async () => {
    setLiveQuizStore([makeMCQQuestion()], 0);
    renderPage();
    await screen.findByTestId('quiz-prompt');
    expect(screen.getByText(/question 1 of 1/i)).toBeInTheDocument();
  });

  it('renders question counter "Question 2 of 2" on second question', async () => {
    const q2 = makeMCQQuestion({ id: 'q2', prompt: 'Second question' });
    setLiveQuizStore([makeMCQQuestion(), q2], 1);
    renderPage();
    await screen.findByText('Second question');
    expect(screen.getByText(/question 2 of 2/i)).toBeInTheDocument();
  });

  // ── Live quiz: navigation ─────────────────────────────────────────────────

  it('Previous button is disabled on first question (index 0)', async () => {
    setLiveQuizStore([makeMCQQuestion()], 0);
    renderPage();
    await screen.findByTestId('quiz-prompt');
    const prevBtn = screen.getByRole('button', { name: /previous/i });
    expect(prevBtn).toBeDisabled();
  });

  it('shows Submit Quiz button (not Next) on last question', async () => {
    setLiveQuizStore([makeMCQQuestion()], 0); // 1 question at index 0 = last
    renderPage();
    await screen.findByTestId('quiz-prompt');
    expect(screen.getByRole('button', { name: /submit quiz/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^next$/i })).not.toBeInTheDocument();
  });

  it('shows Next button when not on last question', async () => {
    const q2 = makeMCQQuestion({ id: 'q2', prompt: 'Q2' });
    setLiveQuizStore([makeMCQQuestion(), q2], 0); // 2 questions, at index 0
    renderPage();
    await screen.findByTestId('quiz-prompt');
    expect(screen.getByRole('button', { name: /^next$/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /submit quiz/i })).not.toBeInTheDocument();
  });

  // ── Live quiz: answer selection ────────────────────────────────────────────

  it('clicking MCQ choice calls setAnswer with choice id', async () => {
    const user = userEvent.setup();
    setLiveQuizStore();
    renderPage();
    await screen.findByTestId('quiz-prompt');
    const radio = screen.getAllByRole('radio');
    await user.click(radio[1]); // click "Mitochondria" (c2)
    expect(mockStore.setAnswer).toHaveBeenCalledWith('q1', 'c2');
  });

  // ── Submit ────────────────────────────────────────────────────────────────

  it('clicking Submit Quiz calls submitAttempt', async () => {
    const user = userEvent.setup();
    setLiveQuizStore([makeMCQQuestion()], 0);
    renderPage();
    await screen.findByTestId('quiz-prompt');
    await user.click(screen.getByRole('button', { name: /submit quiz/i }));
    await waitFor(() => expect(mockSubmitAttempt).toHaveBeenCalledTimes(1));
  });

  // ── ResultView ────────────────────────────────────────────────────────────

  it('shows "You passed!" heading after successful submission', async () => {
    const user = userEvent.setup();
    setLiveQuizStore([makeMCQQuestion()], 0);
    mockSubmitAttempt.mockResolvedValue(makeSubmitResponse(true));
    renderPage();
    await screen.findByTestId('quiz-prompt');
    await user.click(screen.getByRole('button', { name: /submit quiz/i }));
    expect(
      await screen.findByRole('heading', { level: 2, name: /you passed!/i }),
    ).toBeInTheDocument();
  });

  it('shows "Not quite there" heading when failed', async () => {
    const user = userEvent.setup();
    setLiveQuizStore([makeMCQQuestion()], 0);
    mockSubmitAttempt.mockResolvedValue(makeSubmitResponse(false));
    renderPage();
    await screen.findByTestId('quiz-prompt');
    await user.click(screen.getByRole('button', { name: /submit quiz/i }));
    expect(
      await screen.findByRole('heading', { level: 2, name: /not quite there/i }),
    ).toBeInTheDocument();
  });

  it('shows score on result screen', async () => {
    const user = userEvent.setup();
    setLiveQuizStore([makeMCQQuestion()], 0);
    renderPage();
    await screen.findByTestId('quiz-prompt');
    await user.click(screen.getByRole('button', { name: /submit quiz/i }));
    // Result: score=8, max_score=10, pct=80%
    await screen.findByRole('heading', { level: 2, name: /you passed!/i });
    expect(screen.getByText(/\(80%\)/)).toBeInTheDocument();
  });

  it('Done button on result screen calls store.clear and navigates', async () => {
    const user = userEvent.setup();
    setLiveQuizStore([makeMCQQuestion()], 0);
    renderPage();
    await screen.findByTestId('quiz-prompt');
    await user.click(screen.getByRole('button', { name: /submit quiz/i }));
    await screen.findByRole('heading', { level: 2, name: /you passed!/i });
    await user.click(screen.getByRole('button', { name: /done/i }));
    expect(mockStore.clear).toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/assignments');
  });
});
