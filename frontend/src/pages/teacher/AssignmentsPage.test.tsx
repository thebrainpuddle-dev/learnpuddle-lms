// src/pages/teacher/AssignmentsPage.test.tsx
// FE-052
//
// Comprehensive tests for the Teacher Assessments (Assignments) page.
// Covers: header, tabs, assignment list, status badges, tab filtering,
//         course title display, submit action, view submission modal,
//         empty state, and score display.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AssignmentsPage } from './AssignmentsPage';
import { teacherService, TeacherAssignmentListItem } from '../../services/teacherService';
import { ToastProvider } from '../../components/common';

// ── Mocks ─────────────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/teacherService', () => ({
  teacherService: {
    listAssignments: vi.fn(),
    submitAssignment: vi.fn(),
    getSubmission: vi.fn(),
  },
}));

vi.mock('../../components/teacher/SubmissionModal', () => ({
  SubmissionModal: ({
    isOpen,
    onClose,
  }: {
    isOpen: boolean;
    onClose: () => void;
  }) =>
    isOpen ? (
      <div data-testid="submission-modal">
        <button onClick={onClose}>Close Modal</button>
      </div>
    ) : null,
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

const mockToast = { success: vi.fn(), error: vi.fn() };
vi.mock('../../components/common', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/common')>();
  return { ...actual, useToast: () => mockToast };
});

// ── Fixtures ──────────────────────────────────────────────────────────────────

const PENDING_ASSIGNMENT: TeacherAssignmentListItem = {
  id: 'asgn-1',
  title: 'Chapter 3 Assessment',
  description: 'Complete the chapter assessment',
  instructions: '',
  course_id: 'c-1',
  course_title: 'Algebra Fundamentals',
  due_date: '2026-05-01T23:59:00Z',
  submission_status: 'PENDING',
  score: null,
  max_score: '100',
  passing_score: '60',
  is_mandatory: true,
  is_active: true,
  feedback: '',
  is_quiz: false,
};

const PENDING_QUIZ_ASSIGNMENT: TeacherAssignmentListItem = {
  id: 'asgn-quiz-1',
  title: 'Chapter 3 Quiz',
  description: 'Complete the chapter quiz',
  instructions: '',
  course_id: 'c-1',
  course_title: 'Algebra Fundamentals',
  due_date: '2026-05-01T23:59:00Z',
  submission_status: 'PENDING',
  score: null,
  max_score: '100',
  passing_score: '60',
  is_mandatory: true,
  is_active: true,
  feedback: '',
  is_quiz: true,
};

const SUBMITTED_ASSIGNMENT: TeacherAssignmentListItem = {
  id: 'asgn-2',
  title: 'IB PYP Reflection',
  description: 'Write a reflection on PYP units',
  instructions: '',
  course_id: 'c-2',
  course_title: 'IB PYP Framework',
  due_date: '2026-04-15T23:59:00Z',
  submission_status: 'SUBMITTED',
  score: null,
  max_score: '50',
  passing_score: '30',
  is_mandatory: false,
  is_active: true,
  feedback: '',
  is_quiz: false,
};

const GRADED_ASSIGNMENT: TeacherAssignmentListItem = {
  id: 'asgn-3',
  title: 'Classroom Management Quiz',
  description: 'Test on classroom management techniques',
  instructions: '',
  course_id: 'c-3',
  course_title: 'Classroom Management',
  due_date: '2026-04-10T23:59:00Z',
  submission_status: 'GRADED',
  score: 42,
  max_score: '50',
  passing_score: '30',
  is_mandatory: false,
  is_active: true,
  feedback: 'Well done.',
  is_quiz: false,
};

const ALL_ASSIGNMENTS = [PENDING_ASSIGNMENT, SUBMITTED_ASSIGNMENT, GRADED_ASSIGNMENT];

// ── Render helper ─────────────────────────────────────────────────────────────

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <AssignmentsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// ── Setup ─────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.resetAllMocks();
  (teacherService.listAssignments as ReturnType<typeof vi.fn>).mockResolvedValue(
    ALL_ASSIGNMENTS,
  );
  (teacherService.getSubmission as ReturnType<typeof vi.fn>).mockResolvedValue({
    id: 'sub-1',
    assignment_id: 'asgn-2',
    submission_text: 'My answer',
    file_url: '',
    status: 'SUBMITTED',
    score: null,
    feedback: '',
    submitted_at: '2026-04-16T10:00:00Z',
    updated_at: '2026-04-16T10:00:00Z',
  });
  (teacherService.submitAssignment as ReturnType<typeof vi.fn>).mockResolvedValue({
    id: 'sub-new',
    assignment_id: 'asgn-1',
    submission_text: 'My submission',
    file_url: '',
    status: 'SUBMITTED',
    score: null,
    feedback: '',
    submitted_at: '2026-04-27T09:00:00Z',
    updated_at: '2026-04-27T09:00:00Z',
  });
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('AssignmentsPage', () => {
  // ── 1. Page header ──────────────────────────────────────────────────────────

  describe('Page header', () => {
    it('renders the "Assessments" heading', async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByRole('heading', { name: /assessments/i }),
        ).toBeInTheDocument();
      });
    });
  });

  // ── 2. Tab buttons ──────────────────────────────────────────────────────────

  describe('Tab buttons', () => {
    it('renders the "All" tab button', async () => {
      renderPage();
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^all/i })).toBeInTheDocument(),
      );
    });

    it('renders the "Pending" tab button', async () => {
      renderPage();
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^pending/i })).toBeInTheDocument(),
      );
    });

    it('renders "Submitted" and "Graded" tab buttons', async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /^submitted/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole('button', { name: /^graded/i }),
        ).toBeInTheDocument();
      });
    });
  });

  // ── 3. Assignment list ──────────────────────────────────────────────────────

  describe('Assignment list', () => {
    it('renders "Chapter 3 Assessment" in the default All tab', async () => {
      renderPage();
      expect(await screen.findByText('Chapter 3 Assessment')).toBeInTheDocument();
    });

    it('renders "IB PYP Reflection" in the default All tab', async () => {
      renderPage();
      expect(await screen.findByText('IB PYP Reflection')).toBeInTheDocument();
    });

    it('renders "Classroom Management Quiz" in the default All tab', async () => {
      renderPage();
      expect(await screen.findByText('Classroom Management Quiz')).toBeInTheDocument();
    });
  });

  // ── 4. Status badges ────────────────────────────────────────────────────────

  describe('Status badges', () => {
    it('shows the PENDING status badge for a pending assignment', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      // The badge renders submission_status text directly (uppercased)
      const badges = screen.getAllByText('PENDING');
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });

    it('shows the SUBMITTED status badge for a submitted assignment', async () => {
      renderPage();
      await screen.findByText('IB PYP Reflection');
      const badges = screen.getAllByText('SUBMITTED');
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });

    it('shows the GRADED status badge for a graded assignment', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');
      const badges = screen.getAllByText('GRADED');
      expect(badges.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 5. Tab filtering ────────────────────────────────────────────────────────

  describe('Tab filtering', () => {
    beforeEach(() => {
      (teacherService.listAssignments as ReturnType<typeof vi.fn>).mockImplementation(
        (status?: string) => {
          if (status === 'PENDING') return Promise.resolve([PENDING_ASSIGNMENT]);
          if (status === 'SUBMITTED') return Promise.resolve([SUBMITTED_ASSIGNMENT]);
          if (status === 'GRADED') return Promise.resolve([GRADED_ASSIGNMENT]);
          return Promise.resolve(ALL_ASSIGNMENTS);
        },
      );
    });

    it('clicking "Pending" tab shows only the pending assignment', async () => {
      renderPage();
      // Wait for initial render
      await screen.findByText('Chapter 3 Assessment');

      await userEvent.click(screen.getByRole('button', { name: /^pending/i }));

      await waitFor(() => {
        expect(screen.getByText('Chapter 3 Assessment')).toBeInTheDocument();
      });
      expect(screen.queryByText('IB PYP Reflection')).not.toBeInTheDocument();
      expect(screen.queryByText('Classroom Management Quiz')).not.toBeInTheDocument();
    });

    it('clicking "Submitted" tab shows only the submitted assignment', async () => {
      renderPage();
      await screen.findByText('IB PYP Reflection');

      await userEvent.click(screen.getByRole('button', { name: /^submitted/i }));

      await waitFor(() => {
        expect(screen.getByText('IB PYP Reflection')).toBeInTheDocument();
      });
      expect(screen.queryByText('Chapter 3 Assessment')).not.toBeInTheDocument();
      expect(screen.queryByText('Classroom Management Quiz')).not.toBeInTheDocument();
    });

    it('clicking "Graded" tab shows only the graded assignment', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');

      await userEvent.click(screen.getByRole('button', { name: /^graded/i }));

      await waitFor(() => {
        expect(screen.getByText('Classroom Management Quiz')).toBeInTheDocument();
      });
      expect(screen.queryByText('Chapter 3 Assessment')).not.toBeInTheDocument();
      expect(screen.queryByText('IB PYP Reflection')).not.toBeInTheDocument();
    });
  });

  // ── 6. Course title display ──────────────────────────────────────────────────

  describe('Course title display', () => {
    it('shows "Algebra Fundamentals" course title in the assignment row', async () => {
      renderPage();
      expect(await screen.findByText('Algebra Fundamentals')).toBeInTheDocument();
    });
  });

  // ── 7. Submit action ─────────────────────────────────────────────────────────

  describe('Submit action for PENDING text assignment', () => {
    it('renders a "Submit" button for a PENDING non-quiz assignment', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      // PENDING + !is_quiz → "Submit" button
      const submitButtons = screen.getAllByRole('button', { name: /^submit$/i });
      expect(submitButtons.length).toBeGreaterThanOrEqual(1);
    });

    it('clicking "Submit" opens the submission textarea modal', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      const submitButton = screen.getAllByRole('button', { name: /^submit$/i })[0];
      await userEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/type your answer or reflection here/i)).toBeInTheDocument();
      });
    });
  });

  describe('Submit action for PENDING quiz assignment', () => {
    beforeEach(() => {
      (teacherService.listAssignments as ReturnType<typeof vi.fn>).mockResolvedValue([
        PENDING_QUIZ_ASSIGNMENT,
      ]);
    });

    it('renders a "Start Quiz" button for a PENDING quiz assignment', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /start quiz/i })).toBeInTheDocument();
    });

    it('clicking "Start Quiz" navigates to the quiz route', async () => {
      renderPage();
      const btn = await screen.findByRole('button', { name: /start quiz/i });
      await userEvent.click(btn);
      expect(mockNavigate).toHaveBeenCalledWith(`/teacher/quizzes/${PENDING_QUIZ_ASSIGNMENT.id}`);
    });
  });

  // ── 8. View submission ───────────────────────────────────────────────────────

  describe('View submission', () => {
    it('renders a "View" button for SUBMITTED and GRADED assignments', async () => {
      renderPage();
      await screen.findByText('IB PYP Reflection');
      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      // One for SUBMITTED, one for GRADED
      expect(viewButtons.length).toBeGreaterThanOrEqual(2);
    });

    it('clicking "View" for a non-quiz SUBMITTED assignment opens the SubmissionModal', async () => {
      renderPage();
      await screen.findByText('IB PYP Reflection');

      // Find the View button next to the SUBMITTED assignment
      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      // Click the first View button (SUBMITTED assignment)
      await userEvent.click(viewButtons[0]);

      await waitFor(() => {
        expect(screen.getByTestId('submission-modal')).toBeInTheDocument();
      });
    });

    it('clicking "Close Modal" inside SubmissionModal closes it', async () => {
      renderPage();
      await screen.findByText('IB PYP Reflection');

      const viewButtons = screen.getAllByRole('button', { name: /^view$/i });
      await userEvent.click(viewButtons[0]);

      await waitFor(() =>
        expect(screen.getByTestId('submission-modal')).toBeInTheDocument(),
      );

      await userEvent.click(screen.getByRole('button', { name: /close modal/i }));

      await waitFor(() =>
        expect(screen.queryByTestId('submission-modal')).not.toBeInTheDocument(),
      );
    });
  });

  // ── 9. Empty state ───────────────────────────────────────────────────────────

  describe('Empty state', () => {
    it('shows "No assessments found" when the query returns an empty array', async () => {
      (teacherService.listAssignments as ReturnType<typeof vi.fn>).mockResolvedValue([]);
      renderPage();
      expect(await screen.findByText(/no assessments found/i)).toBeInTheDocument();
    });

    it('shows the empty state description for the ALL tab', async () => {
      (teacherService.listAssignments as ReturnType<typeof vi.fn>).mockResolvedValue([]);
      renderPage();
      expect(
        await screen.findByText(/you don't have any assessments yet/i),
      ).toBeInTheDocument();
    });
  });

  // ── 10. Score display ────────────────────────────────────────────────────────

  describe('Score display', () => {
    it('shows the score "42/50" for a GRADED assignment with a score', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');
      expect(screen.getByText('42/50')).toBeInTheDocument();
    });

    it('renders the "Score" label beneath the numeric score for a GRADED assignment', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');
      // The label below the score value
      expect(screen.getByText(/^score$/i)).toBeInTheDocument();
    });
  });

  // ── 11. Submit mutation ───────────────────────────────────────────────────────

  describe('Submit mutation', () => {
    it('calls submitAssignment with the correct id and submission_text on confirm', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      // Open the submit modal for the text assignment
      const submitButton = screen.getAllByRole('button', { name: /^submit$/i })[0];
      await userEvent.click(submitButton);

      const textarea = await screen.findByPlaceholderText(/type your answer or reflection here/i);
      await userEvent.type(textarea, 'My detailed answer');

      // Click the confirm Submit button inside the modal
      const confirmButtons = screen.getAllByRole('button', { name: /^submit$/i });
      // The last Submit button should be the modal confirm button
      await userEvent.click(confirmButtons[confirmButtons.length - 1]);

      await waitFor(() => {
        expect(teacherService.submitAssignment).toHaveBeenCalledWith('asgn-1', {
          submission_text: 'My detailed answer',
        });
      });
    });

    it('shows success toast and closes modal after successful submission', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      const submitButton = screen.getAllByRole('button', { name: /^submit$/i })[0];
      await userEvent.click(submitButton);

      const textarea = await screen.findByPlaceholderText(/type your answer or reflection here/i);
      await userEvent.type(textarea, 'My answer');

      const confirmButtons = screen.getAllByRole('button', { name: /^submit$/i });
      await userEvent.click(confirmButtons[confirmButtons.length - 1]);

      await waitFor(() => {
        expect(mockToast.success).toHaveBeenCalledWith(
          'Submitted',
          'Your assessment has been submitted.',
        );
      });

      // Modal should be closed
      await waitFor(() => {
        expect(
          screen.queryByPlaceholderText(/type your answer or reflection here/i),
        ).not.toBeInTheDocument();
      });
    });

    it('shows error toast when submission fails', async () => {
      (teacherService.submitAssignment as ReturnType<typeof vi.fn>).mockRejectedValue(
        new Error('Network error'),
      );
      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      const submitButton = screen.getAllByRole('button', { name: /^submit$/i })[0];
      await userEvent.click(submitButton);

      const textarea = await screen.findByPlaceholderText(/type your answer or reflection here/i);
      await userEvent.type(textarea, 'Some text');

      const confirmButtons = screen.getAllByRole('button', { name: /^submit$/i });
      await userEvent.click(confirmButtons[confirmButtons.length - 1]);

      await waitFor(() => {
        expect(mockToast.error).toHaveBeenCalledWith(
          'Failed',
          'Could not submit. Please try again.',
        );
      });
    });

    it('cancelling the submit modal closes it without calling submitAssignment', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      const submitButton = screen.getAllByRole('button', { name: /^submit$/i })[0];
      await userEvent.click(submitButton);

      await screen.findByPlaceholderText(/type your answer or reflection here/i);

      await userEvent.click(screen.getByRole('button', { name: /cancel/i }));

      await waitFor(() => {
        expect(
          screen.queryByPlaceholderText(/type your answer or reflection here/i),
        ).not.toBeInTheDocument();
      });

      expect(teacherService.submitAssignment).not.toHaveBeenCalled();
    });
  });

  // ── 12. Tab counts from allAssignments ───────────────────────────────────────

  describe('Tab counts', () => {
    it('shows the total count from allAssignments in the All tab badge', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      // ALL_ASSIGNMENTS has 3 items → All tab should show 3
      const allTabButton = screen.getByRole('button', { name: /^all/i });
      expect(allTabButton).toHaveTextContent('3');
    });
  });
});
