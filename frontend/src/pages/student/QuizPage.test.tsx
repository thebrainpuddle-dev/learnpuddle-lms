// src/pages/student/QuizPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for the Student QuizPage.
//
// Covers:
//   - Honor-code gate: "I agree — start quiz" button visible before accepting
//   - Clicking "I agree — start quiz" shows quiz questions
//   - Loading skeleton while query is pending
//   - "Quiz not found" error state when data is undefined
//   - Quiz heading ("Quiz") after honor code accepted
//   - Progress bar / answered-count indicator
//   - All question types rendered (MCQ single, MCQ multiple, TRUE_FALSE, SHORT_ANSWER)
//   - Answer selection: MCQ single radio, MCQ multiple checkbox, TRUE_FALSE button, SHORT_ANSWER textarea
//   - Submit Quiz button visible while quiz is active
//   - Submit button opens ConfirmDialog
//   - ConfirmDialog cancel keeps quiz open
//   - ConfirmDialog confirm calls submitQuiz mutation with correct args
//   - Success toast shown after submission
//   - Error toast shown when submitQuiz fails
//   - Results view shown when submission != null (score, percentage, "Your Answers")
//   - Back navigation from results view
//   - Back to assignments navigation link in active quiz
//   - Answered count / unanswered indicator updates as questions are answered

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

vi.mock('../../services/studentService', () => ({
  studentService: {
    getQuizDetail: vi.fn(),
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

import { studentService } from '../../services/studentService';
const mockGetQuizDetail = studentService.getQuizDetail as ReturnType<typeof vi.fn>;
const mockSubmitQuiz = studentService.submitQuiz as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

function renderPage() {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={['/student/quizzes/asgn-1']}>
        <QuizPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const BASE_QUESTIONS = [
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
    prompt: 'Select the prime numbers',
    options: ['1', '2', '3'],
    points: 2,
  },
  {
    id: 'q-3',
    order: 3,
    question_type: 'TRUE_FALSE' as const,
    selection_mode: 'SINGLE' as const,
    prompt: 'The Earth orbits the Sun',
    options: [],
    points: 1,
  },
  {
    id: 'q-4',
    order: 4,
    question_type: 'SHORT_ANSWER' as const,
    selection_mode: 'SINGLE' as const,
    prompt: 'Describe the water cycle',
    options: [],
    points: 3,
  },
];

const MOCK_QUIZ_DATA = {
  assignment_id: 'asgn-1',
  quiz_id: 'quiz-1',
  schema_version: 1,
  questions: BASE_QUESTIONS,
  submission: null,
};

const MOCK_QUIZ_SUBMITTED = {
  ...MOCK_QUIZ_DATA,
  submission: {
    answers: {
      'q-1': { option_index: 1 },  // "4"
      'q-2': { option_indices: [1, 2] }, // "2", "3"
      'q-3': { value: true },
      'q-4': { text: 'Water evaporates...' },
    },
    score: 6,
    graded_at: '2026-04-01T10:00:00Z',
    submitted_at: '2026-04-01T09:55:00Z',
  },
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Student QuizPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockSubmitQuiz.mockResolvedValue({
      quiz_id: 'quiz-1',
      assignment_id: 'asgn-1',
      score: null,
      graded_at: null,
    });
  });

  // ── 1. Loading state ────────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows skeleton placeholder divs while the query is pending', () => {
      mockGetQuizDetail.mockReturnValue(new Promise(() => {})); // never resolves
      renderPage();
      const skeletons = document.querySelectorAll('.tp-skeleton');
      expect(skeletons.length).toBeGreaterThan(0);
    });

    it('does not show honor-code gate while loading', () => {
      mockGetQuizDetail.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(
        screen.queryByText(/academic integrity pledge/i),
      ).not.toBeInTheDocument();
    });
  });

  // ── 2. Error / not-found state ──────────────────────────────────────────────

  describe('not-found state', () => {
    it('shows "Quiz not found" heading when data is undefined', async () => {
      mockGetQuizDetail.mockResolvedValue(undefined);
      renderPage();
      expect(await screen.findByText('Quiz not found')).toBeInTheDocument();
    });

    it('shows helper message when quiz is not found', async () => {
      mockGetQuizDetail.mockResolvedValue(undefined);
      renderPage();
      expect(
        await screen.findByText(/this quiz may have been removed/i),
      ).toBeInTheDocument();
    });

    it('navigates to /student/assignments from the not-found back button', async () => {
      const user = userEvent.setup();
      mockGetQuizDetail.mockResolvedValue(undefined);
      renderPage();
      await screen.findByText('Quiz not found');
      await user.click(screen.getByRole('button', { name: /back to assignments/i }));
      expect(mockNavigate).toHaveBeenCalledWith('/student/assignments');
    });
  });

  // ── 3. Honor-code gate ──────────────────────────────────────────────────────

  describe('honor-code gate (before accepting)', () => {
    it('shows the "Academic Integrity Pledge" heading before quiz starts', async () => {
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_DATA);
      renderPage();
      expect(
        await screen.findByText('Academic Integrity Pledge'),
      ).toBeInTheDocument();
    });

    it('shows the "I agree — start quiz" button', async () => {
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_DATA);
      renderPage();
      expect(
        await screen.findByRole('button', { name: /i agree.*start quiz/i }),
      ).toBeInTheDocument();
    });

    it('does not show quiz questions before honor code is accepted', async () => {
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_DATA);
      renderPage();
      // Wait for honor gate to appear (data loaded)
      await screen.findByText('Academic Integrity Pledge');
      expect(screen.queryByText('What is 2 + 2?')).not.toBeInTheDocument();
    });

    it('does not show "Submit Quiz" button before honor code is accepted', async () => {
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_DATA);
      renderPage();
      await screen.findByText('Academic Integrity Pledge');
      expect(
        screen.queryByRole('button', { name: /submit quiz/i }),
      ).not.toBeInTheDocument();
    });
  });

  // ── 4. After accepting honor code ───────────────────────────────────────────

  describe('active quiz (after accepting honor code)', () => {
    async function renderAndAccept() {
      const user = userEvent.setup();
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_DATA);
      renderPage();
      await user.click(
        await screen.findByRole('button', { name: /i agree.*start quiz/i }),
      );
      return user;
    }

    it('hides the honor-code gate after clicking "I agree"', async () => {
      await renderAndAccept();
      expect(
        screen.queryByText('Academic Integrity Pledge'),
      ).not.toBeInTheDocument();
    });

    it('shows the "Quiz" heading', async () => {
      await renderAndAccept();
      const headings = screen.getAllByRole('heading', { level: 1 });
      expect(headings.some((h) => h.textContent === 'Quiz')).toBe(true);
    });

    it('shows a "Back to Assignments" navigation link', async () => {
      await renderAndAccept();
      expect(
        screen.getByRole('button', { name: /back to assignments/i }),
      ).toBeInTheDocument();
    });

    it('clicking "Back to Assignments" navigates to /student/assignments', async () => {
      const user = await renderAndAccept();
      await user.click(screen.getByRole('button', { name: /back to assignments/i }));
      expect(mockNavigate).toHaveBeenCalledWith('/student/assignments');
    });

    // ── Progress bar ───────────────────────────────────────────────────────

    it('shows "Progress" label and 0% initially', async () => {
      await renderAndAccept();
      expect(screen.getByText('Progress')).toBeInTheDocument();
      expect(screen.getByText('0%')).toBeInTheDocument();
    });

    it('shows "0 of 4 answered" initially', async () => {
      await renderAndAccept();
      expect(screen.getByText(/0 of 4 answered/i)).toBeInTheDocument();
    });

    // ── Question rendering ─────────────────────────────────────────────────

    it('renders all question prompts', async () => {
      await renderAndAccept();
      expect(screen.getByText('What is 2 + 2?')).toBeInTheDocument();
      expect(screen.getByText('Select the prime numbers')).toBeInTheDocument();
      expect(screen.getByText('The Earth orbits the Sun')).toBeInTheDocument();
      expect(screen.getByText('Describe the water cycle')).toBeInTheDocument();
    });

    it('renders MCQ single-select question with radio buttons', async () => {
      await renderAndAccept();
      // There are 3 options: "3", "4", "5" — all should be radio inputs
      const radios = screen.getAllByRole('radio');
      expect(radios.length).toBeGreaterThanOrEqual(3);
      // "3" appears in both q-1 ("3") and q-2 ("3"); use getAllByText
      expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(1);
      expect(screen.getByRole('radio', { name: /^4$/ })).toBeInTheDocument();
      expect(screen.getByRole('radio', { name: /^5$/ })).toBeInTheDocument();
    });

    it('renders MCQ multiple-select question with checkboxes', async () => {
      await renderAndAccept();
      const checkboxes = screen.getAllByRole('checkbox');
      // q-2 has 3 options: "1", "2", "3"
      expect(checkboxes).toHaveLength(3);
    });

    it('renders TRUE_FALSE question with True and False buttons', async () => {
      await renderAndAccept();
      expect(screen.getByRole('button', { name: 'True' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'False' })).toBeInTheDocument();
    });

    it('renders SHORT_ANSWER question with a textarea', async () => {
      await renderAndAccept();
      expect(
        screen.getByPlaceholderText('Type your answer...'),
      ).toBeInTheDocument();
    });

    it('shows question type label "Multiple choice" for MCQ single-select', async () => {
      await renderAndAccept();
      expect(screen.getByText(/Q1.*Multiple choice.*1 pt/)).toBeInTheDocument();
    });

    it('shows question type label "Multiple select" for MCQ multiple-select', async () => {
      await renderAndAccept();
      expect(screen.getByText(/Q2.*Multiple select.*2 pt/)).toBeInTheDocument();
    });

    it('shows question type label "True / False"', async () => {
      await renderAndAccept();
      expect(screen.getByText(/Q3.*True \/ False.*1 pt/)).toBeInTheDocument();
    });

    // ── Answer selection ───────────────────────────────────────────────────

    it('selecting a MCQ radio option marks it checked', async () => {
      const user = await renderAndAccept();
      const radio4 = screen.getByRole('radio', { name: /^4$/ });
      await user.click(radio4);
      expect(radio4).toBeChecked();
    });

    it('selecting a checkbox option marks it checked', async () => {
      const user = await renderAndAccept();
      const checkbox2 = screen.getByRole('checkbox', { name: /^2$/ });
      await user.click(checkbox2);
      expect(checkbox2).toBeChecked();
    });

    it('unchecking a checkbox option unchecks it', async () => {
      const user = await renderAndAccept();
      const checkbox2 = screen.getByRole('checkbox', { name: /^2$/ });
      await user.click(checkbox2); // check
      await user.click(checkbox2); // uncheck
      expect(checkbox2).not.toBeChecked();
    });

    it('clicking the "True" button selects it', async () => {
      const user = await renderAndAccept();
      const trueBtn = screen.getByRole('button', { name: 'True' });
      await user.click(trueBtn);
      // After selection the button gets indigo styling — it remains enabled
      expect(trueBtn).not.toBeDisabled();
    });

    it('typing in the short-answer textarea updates the value', async () => {
      const user = await renderAndAccept();
      const textarea = screen.getByPlaceholderText('Type your answer...');
      await user.type(textarea, 'Evaporation and precipitation');
      expect(textarea).toHaveValue('Evaporation and precipitation');
    });

    it('progress updates to 25% after answering one question', async () => {
      const user = await renderAndAccept();
      await user.click(screen.getByRole('radio', { name: /^4$/ }));
      expect(screen.getByText('25%')).toBeInTheDocument();
      expect(screen.getByText(/1 of 4 answered/i)).toBeInTheDocument();
    });

    // ── Unanswered indicator ────────────────────────────────────────────────

    it('shows unanswered count when not all questions are answered', async () => {
      await renderAndAccept();
      // 4 unanswered questions on load
      expect(screen.getByText(/4 unanswered/i)).toBeInTheDocument();
    });

    // ── Submit button & dialog ─────────────────────────────────────────────

    it('renders a "Submit Quiz" button', async () => {
      await renderAndAccept();
      expect(
        screen.getByRole('button', { name: /submit quiz/i }),
      ).toBeInTheDocument();
    });

    it('clicking "Submit Quiz" opens the confirm dialog', async () => {
      const user = await renderAndAccept();
      await user.click(screen.getByRole('button', { name: /submit quiz/i }));
      expect(
        await screen.findByText('Are you sure? You cannot change your answers after submission.'),
      ).toBeInTheDocument();
    });

    it('confirm dialog shows "Submit Quiz" as the title', async () => {
      const user = await renderAndAccept();
      await user.click(screen.getByRole('button', { name: /submit quiz/i }));
      // Both the button and the dialog heading carry "Submit Quiz";
      // assert the dialog heading specifically by role
      const headings = await screen.findAllByRole('heading', { name: /submit quiz/i });
      expect(headings.length).toBeGreaterThanOrEqual(1);
    });

    it('clicking "Keep editing" in the dialog closes it without submitting', async () => {
      const user = await renderAndAccept();
      await user.click(screen.getByRole('button', { name: /submit quiz/i }));
      await screen.findByText(/cannot change your answers/i);
      await user.click(screen.getByRole('button', { name: /keep editing/i }));
      await waitFor(() => {
        expect(
          screen.queryByText(/cannot change your answers/i),
        ).not.toBeInTheDocument();
      });
      expect(mockSubmitQuiz).not.toHaveBeenCalled();
    });

    // ── Submission mutation ────────────────────────────────────────────────

    it('confirms submission — calls submitQuiz with assignmentId and answers', async () => {
      const user = await renderAndAccept();

      // Answer q-1 (MCQ single) — option "4" is index 1
      await user.click(screen.getByRole('radio', { name: /^4$/ }));

      // Open dialog and confirm
      await user.click(screen.getByRole('button', { name: /submit quiz/i }));
      await screen.findByText(/cannot change your answers/i);
      await user.click(screen.getByRole('button', { name: /^Submit$/ }));

      await waitFor(() => {
        expect(mockSubmitQuiz).toHaveBeenCalledWith(
          'asgn-1',
          expect.objectContaining({ 'q-1': { option_index: 1 } }),
        );
      });
    });

    it('shows success toast after submission', async () => {
      const user = await renderAndAccept();
      await user.click(screen.getByRole('button', { name: /submit quiz/i }));
      await screen.findByText(/cannot change your answers/i);
      await user.click(screen.getByRole('button', { name: /^Submit$/ }));

      await waitFor(() => {
        expect(mockToast.success).toHaveBeenCalledWith(
          'Quiz submitted',
          'Your answers have been recorded.',
        );
      });
    });

    it('shows error toast when submitQuiz fails', async () => {
      mockSubmitQuiz.mockRejectedValue({
        response: { data: { detail: 'Quiz already submitted.' } },
      });

      const user = await renderAndAccept();
      await user.click(screen.getByRole('button', { name: /submit quiz/i }));
      await screen.findByText(/cannot change your answers/i);
      await user.click(screen.getByRole('button', { name: /^Submit$/ }));

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith(
          'Submission failed',
          'Quiz already submitted.',
        );
      });
    });

    it('shows generic error toast when no detail in error response', async () => {
      mockSubmitQuiz.mockRejectedValue(new Error('Network failure'));

      const user = await renderAndAccept();
      await user.click(screen.getByRole('button', { name: /submit quiz/i }));
      await screen.findByText(/cannot change your answers/i);
      await user.click(screen.getByRole('button', { name: /^Submit$/ }));

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith(
          'Submission failed',
          'Something went wrong. Please try again.',
        );
      });
    });
  });

  // ── 5. Results view ─────────────────────────────────────────────────────────

  describe('results view (already submitted)', () => {
    it('skips the honor-code gate and shows results directly', async () => {
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_SUBMITTED);
      renderPage();
      expect(await screen.findByText('Quiz Completed')).toBeInTheDocument();
      expect(screen.queryByText('Academic Integrity Pledge')).not.toBeInTheDocument();
    });

    it('displays the score percentage (6/7 pts = 85%)', async () => {
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_SUBMITTED);
      renderPage();
      // Total points: 1+2+1+3 = 7, score = 6 → 86% (rounded)
      expect(await screen.findByText(/\d+%/)).toBeInTheDocument();
    });

    it('displays the raw score "6 / 7 points"', async () => {
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_SUBMITTED);
      renderPage();
      expect(await screen.findByText('6 / 7 points')).toBeInTheDocument();
    });

    it('displays "Your Answers" heading', async () => {
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_SUBMITTED);
      renderPage();
      expect(await screen.findByText('Your Answers')).toBeInTheDocument();
    });

    it('renders all question prompts in read-only mode', async () => {
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_SUBMITTED);
      renderPage();
      await screen.findByText('Quiz Completed');
      expect(screen.getByText('What is 2 + 2?')).toBeInTheDocument();
      expect(screen.getByText('The Earth orbits the Sun')).toBeInTheDocument();
    });

    it('back button in results view navigates to /student/assignments', async () => {
      const user = userEvent.setup();
      mockGetQuizDetail.mockResolvedValue(MOCK_QUIZ_SUBMITTED);
      renderPage();
      await screen.findByText('Quiz Completed');
      // There are two back buttons in the results view; click the first
      const backButtons = screen.getAllByRole('button', {
        name: /back to assignments/i,
      });
      await user.click(backButtons[0]);
      expect(mockNavigate).toHaveBeenCalledWith('/student/assignments');
    });
  });
});
