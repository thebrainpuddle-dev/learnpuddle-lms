// src/pages/teacher/QuizPage.test.tsx
//
// FE-057: Tests for the Teacher Quiz Page.
// Covers: loading spinner, "Quiz not found" state, page header, back navigation,
//         question types (MCQ single/multiple, TRUE_FALSE, SHORT_ANSWER),
//         question metadata labels, answer selection state, submit button,
//         submit mutation (correct args), submit success navigation, submit error toast.
//
// Mocking strategy:
//   - teacherService (getQuiz, submitQuiz) via vi.mock
//   - useNavigate and useParams mocked via importOriginal spread
//   - useToast mocked via importOriginal spread on ../../components/common
//   - usePageTitle stubbed

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QuizPage } from './QuizPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ assignmentId: 'asgn-1' }),
  };
});

vi.mock('../../services/teacherService', () => ({
  teacherService: {
    getQuiz: vi.fn(),
    submitQuiz: vi.fn(),
  },
}));

const mockToast = { error: vi.fn(), success: vi.fn(), info: vi.fn() };
vi.mock('../../components/common', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/common')>();
  return { ...actual, useToast: () => mockToast };
});

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { teacherService } from '../../services/teacherService';
const mockGetQuiz = teacherService.getQuiz as ReturnType<typeof vi.fn>;
const mockSubmitQuiz = teacherService.submitQuiz as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>
        <QuizPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const mockQuizData = {
  assignment_id: 'asgn-1',
  quiz_id: 'quiz-1',
  schema_version: 1,
  questions: [
    {
      id: 'q-1',
      order: 1,
      question_type: 'MCQ' as const,
      selection_mode: 'SINGLE' as const,
      prompt: 'What is 2 + 2?',
      options: ['3', '4', '5'],
      points: 1,
    },
    {
      id: 'q-2',
      order: 2,
      question_type: 'MCQ' as const,
      selection_mode: 'MULTIPLE' as const,
      prompt: 'Select even numbers',
      options: ['1', '2', '4'],
      points: 2,
    },
    {
      id: 'q-3',
      order: 3,
      question_type: 'TRUE_FALSE' as const,
      selection_mode: 'SINGLE' as const,
      prompt: 'The sky is blue',
      options: [],
      points: 1,
    },
    {
      id: 'q-4',
      order: 4,
      question_type: 'SHORT_ANSWER' as const,
      selection_mode: 'SINGLE' as const,
      prompt: 'Explain photosynthesis',
      options: [],
      points: 3,
    },
  ],
  submission: null,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('QuizPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSubmitQuiz.mockResolvedValue({ quiz_id: 'quiz-1', assignment_id: 'asgn-1', score: null, graded_at: null });
  });

  // ── Loading ─────────────────────────────────────────────────────────────────

  it('shows loading spinner while query is pending', () => {
    mockGetQuiz.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  // ── Quiz not found ──────────────────────────────────────────────────────────

  it('shows "Quiz not found" when getQuiz returns undefined/null-like', async () => {
    mockGetQuiz.mockResolvedValue(undefined);
    renderPage();
    expect(await screen.findByText('Quiz not found')).toBeInTheDocument();
  });

  // ── Page structure ──────────────────────────────────────────────────────────

  it('renders "Quiz" heading', async () => {
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    // h1 with "Quiz" — findAllByRole since there's also "Quiz" text elsewhere
    const headings = await screen.findAllByRole('heading', { level: 1 });
    expect(headings.some((h) => h.textContent === 'Quiz')).toBe(true);
  });

  it('renders back to assignments navigation link', async () => {
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    expect(
      await screen.findByRole('button', { name: /back to assignments/i }),
    ).toBeInTheDocument();
  });

  it('navigates to /teacher/assignments when back button clicked', async () => {
    const user = userEvent.setup();
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await user.click(await screen.findByRole('button', { name: /back to assignments/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/assignments');
  });

  // ── Question rendering ──────────────────────────────────────────────────────

  it('renders question prompts', async () => {
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    expect(await screen.findByText('What is 2 + 2?')).toBeInTheDocument();
    expect(screen.getByText('Select even numbers')).toBeInTheDocument();
    expect(screen.getByText('The sky is blue')).toBeInTheDocument();
    expect(screen.getByText('Explain photosynthesis')).toBeInTheDocument();
  });

  it('renders MCQ single-select question with radio buttons', async () => {
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await screen.findByText('What is 2 + 2?');
    // MCQ SINGLE renders radio inputs for each option
    const radios = screen.getAllByRole('radio');
    // Includes "3", "4", "5" radios (and True/False radios for q-3)
    expect(radios.length).toBeGreaterThan(2);
    // Option text visible — note '4' also appears in Q2 options ['1','2','4'],
    // so use getAllByText to avoid the "multiple elements" error.
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getAllByText('4').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('renders MCQ multiple-select question with checkboxes', async () => {
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await screen.findByText('Select even numbers');
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(3); // options "1", "2", "4"
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('renders TRUE_FALSE question with True and False radio options', async () => {
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await screen.findByText('The sky is blue');
    expect(screen.getByText('True')).toBeInTheDocument();
    expect(screen.getByText('False')).toBeInTheDocument();
  });

  it('renders SHORT_ANSWER question with textarea', async () => {
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await screen.findByText('Explain photosynthesis');
    expect(screen.getByPlaceholderText('Type your answer...')).toBeInTheDocument();
  });

  it('shows question metadata: order, type label, and points', async () => {
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    // Q1: "Q1 • Multiple choice • 1 pt"
    expect(await screen.findByText(/Q1.*Multiple choice.*1 pt/)).toBeInTheDocument();
    // Q2: "Q2 • Multiple select • 2 pt"
    expect(screen.getByText(/Q2.*Multiple select.*2 pt/)).toBeInTheDocument();
    // Q3: "Q3 • True / False • 1 pt"
    expect(screen.getByText(/Q3.*True \/ False.*1 pt/)).toBeInTheDocument();
  });

  // ── Answer selection ────────────────────────────────────────────────────────

  it('selecting MCQ radio option checks it', async () => {
    const user = userEvent.setup();
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await screen.findByText('What is 2 + 2?');
    const option4Radio = screen.getByRole('radio', { name: /^4$/ });
    await user.click(option4Radio);
    expect(option4Radio).toBeChecked();
  });

  it('selecting multiple checkboxes checks them', async () => {
    const user = userEvent.setup();
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await screen.findByText('Select even numbers');
    const checkbox2 = screen.getByRole('checkbox', { name: /^2$/ });
    await user.click(checkbox2);
    expect(checkbox2).toBeChecked();
  });

  it('typing in short answer textarea updates value', async () => {
    const user = userEvent.setup();
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await screen.findByText('Explain photosynthesis');
    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'Plants use sunlight');
    expect(textarea).toHaveValue('Plants use sunlight');
  });

  // ── Submit ──────────────────────────────────────────────────────────────────

  it('renders "Submit quiz" button', async () => {
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    expect(await screen.findByRole('button', { name: /submit quiz/i })).toBeInTheDocument();
  });

  it('calls submitQuiz with assignmentId and current answers on submit', async () => {
    const user = userEvent.setup();
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await screen.findByText('What is 2 + 2?');
    // Select option "4" for q-1
    await user.click(screen.getByRole('radio', { name: /^4$/ }));
    await user.click(screen.getByRole('button', { name: /submit quiz/i }));
    await waitFor(() => {
      expect(mockSubmitQuiz).toHaveBeenCalledWith('asgn-1', expect.objectContaining({ 'q-1': { option_index: 1 } }));
    });
  });

  it('navigates to /teacher/assignments after successful submit', async () => {
    const user = userEvent.setup();
    mockGetQuiz.mockResolvedValue(mockQuizData);
    renderPage();
    await screen.findByText('What is 2 + 2?');
    await user.click(screen.getByRole('button', { name: /submit quiz/i }));
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/teacher/assignments');
    });
  });

  it('shows error toast when submit fails', async () => {
    const user = userEvent.setup();
    mockGetQuiz.mockResolvedValue(mockQuizData);
    mockSubmitQuiz.mockRejectedValue(new Error('Server error'));
    renderPage();
    await screen.findByText('What is 2 + 2?');
    await user.click(screen.getByRole('button', { name: /submit quiz/i }));
    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'Submission failed',
        'Could not submit quiz. Please try again.',
      );
    });
  });

  // ── Pre-filled answers from existing submission ─────────────────────────────

  it('pre-fills answers from existing submission', async () => {
    const dataWithSubmission = {
      ...mockQuizData,
      submission: {
        answers: { 'q-1': { option_index: 2 } }, // "5" selected
        score: null,
        graded_at: null,
        submitted_at: '2024-01-01T12:00:00Z',
      },
    };
    mockGetQuiz.mockResolvedValue(dataWithSubmission);
    renderPage();
    await screen.findByText('What is 2 + 2?');
    // The radio for option "5" (index 2) should be checked
    const option5Radio = screen.getByRole('radio', { name: /^5$/ });
    expect(option5Radio).toBeChecked();
  });
});
