// src/pages/student/AssignmentsPage.test.tsx
//
// Comprehensive Vitest + RTL tests for the Student AssignmentsPage.
// Covers: heading, stat cards, tabs, loading state, empty states per tab,
//         assignment list rendering, quiz vs text distinction, status badges,
//         due-date / overdue indicator, graded score + feedback, submit modal
//         (open / form fields / submit / cancel), submit mutation, toast
//         notifications, and "Start Quiz" navigation.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AssignmentsPage } from './AssignmentsPage';
import { studentService, StudentAssignmentListItem } from '../../services/studentService';
import { ToastProvider } from '../../components/common';

// ── Mocks ──────────────────────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

vi.mock('../../services/studentService', () => ({
  studentService: {
    getStudentAssignments: vi.fn(),
    submitAssignment: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Fixtures ───────────────────────────────────────────────────────────────────

/** Far-future due date so tests don't become overdue-sensitive */
const FUTURE_DATE = '2099-12-31T23:59:00Z';
/** Past due date for overdue tests */
const PAST_DATE = '2020-01-01T00:00:00Z';

const PENDING_ASSIGNMENT: StudentAssignmentListItem = {
  id: 'asgn-1',
  course_id: 'c-1',
  course_title: 'Algebra Fundamentals',
  title: 'Chapter 3 Assessment',
  description: 'Complete the chapter assessment.',
  instructions: 'Answer all questions in full sentences.',
  due_date: FUTURE_DATE,
  max_score: '100',
  passing_score: '60',
  is_mandatory: true,
  is_active: true,
  submission_status: 'PENDING',
  score: null,
  feedback: '',
  is_quiz: false,
};

const PENDING_QUIZ: StudentAssignmentListItem = {
  id: 'asgn-quiz-1',
  course_id: 'c-1',
  course_title: 'Algebra Fundamentals',
  title: 'Chapter 3 Quiz',
  description: 'Complete the chapter quiz.',
  instructions: '',
  due_date: FUTURE_DATE,
  max_score: '20',
  passing_score: '12',
  is_mandatory: false,
  is_active: true,
  submission_status: 'PENDING',
  score: null,
  feedback: '',
  is_quiz: true,
};

const SUBMITTED_ASSIGNMENT: StudentAssignmentListItem = {
  id: 'asgn-2',
  course_id: 'c-2',
  course_title: 'IB PYP Framework',
  title: 'IB PYP Reflection',
  description: 'Write a reflection on PYP units.',
  instructions: '',
  due_date: FUTURE_DATE,
  max_score: '50',
  passing_score: '30',
  is_mandatory: false,
  is_active: true,
  submission_status: 'SUBMITTED',
  score: null,
  feedback: '',
  is_quiz: false,
};

const GRADED_ASSIGNMENT: StudentAssignmentListItem = {
  id: 'asgn-3',
  course_id: 'c-3',
  course_title: 'Classroom Management',
  title: 'Classroom Management Quiz',
  description: 'Test on classroom management techniques.',
  instructions: '',
  due_date: FUTURE_DATE,
  max_score: '50',
  passing_score: '30',
  is_mandatory: false,
  is_active: true,
  submission_status: 'GRADED',
  score: 42,
  feedback: 'Well done — very thorough answers.',
  is_quiz: false,
};

const OVERDUE_ASSIGNMENT: StudentAssignmentListItem = {
  id: 'asgn-overdue',
  course_id: 'c-4',
  course_title: 'Science Basics',
  title: 'Overdue Lab Report',
  description: 'A lab report that is overdue.',
  instructions: '',
  due_date: PAST_DATE,
  max_score: '40',
  passing_score: '24',
  is_mandatory: true,
  is_active: true,
  submission_status: 'PENDING',
  score: null,
  feedback: '',
  is_quiz: false,
};

const ALL_ASSIGNMENTS: StudentAssignmentListItem[] = [
  PENDING_ASSIGNMENT,
  SUBMITTED_ASSIGNMENT,
  GRADED_ASSIGNMENT,
];

// ── Helpers ────────────────────────────────────────────────────────────────────

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
      <ToastProvider>
        <MemoryRouter>
          <AssignmentsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const mockedStudentService = studentService as unknown as {
  [K in keyof typeof studentService]: ReturnType<typeof vi.fn>;
};

// ── Setup ──────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.resetAllMocks();

  // Both "all" query and filtered query default to ALL_ASSIGNMENTS
  mockedStudentService.getStudentAssignments.mockResolvedValue(ALL_ASSIGNMENTS);
  mockedStudentService.submitAssignment.mockResolvedValue({
    id: 'sub-new',
    assignment_id: 'asgn-1',
    submission_text: 'My answer',
    file_url: '',
    status: 'SUBMITTED',
    score: null,
    feedback: '',
    submitted_at: '2026-04-27T09:00:00Z',
    updated_at: '2026-04-27T09:00:00Z',
  });
});

// ── Tests ──────────────────────────────────────────────────────────────────────

describe('Student AssignmentsPage', () => {

  // ── 1. Page heading ──────────────────────────────────────────────────────────

  describe('Page heading', () => {
    it('renders the "Assignments" heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { name: /assignments/i })).toBeInTheDocument();
    });

    it('shows assignment count in subtitle when assignments exist', async () => {
      renderPage();
      expect(await screen.findByText(/3 assignments across your courses/i)).toBeInTheDocument();
    });

    it('shows generic subtitle when there are no assignments', async () => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([]);
      renderPage();
      expect(await screen.findByText(/your course assignments/i)).toBeInTheDocument();
    });
  });

  // ── 2. Stat cards ────────────────────────────────────────────────────────────

  describe('Stat cards', () => {
    it('renders the "Pending" stat label', async () => {
      renderPage();
      const pendingLabels = await screen.findAllByText('Pending');
      expect(pendingLabels.length).toBeGreaterThanOrEqual(1);
    });

    it('renders the "Avg Score" stat label', async () => {
      renderPage();
      expect(await screen.findByText('Avg Score')).toBeInTheDocument();
    });

    it('renders the "Completed" stat label', async () => {
      renderPage();
      expect(await screen.findByText('Completed')).toBeInTheDocument();
    });

    it('shows correct pending count (1) in stat card', async () => {
      renderPage();
      // Wait for data to load
      await screen.findByText('Chapter 3 Assessment');
      // The stat card with "Pending" label is a grid cell div containing two <p> tags
      // Use getAllByText since "Pending" also appears in the tab button
      const pendingLabels = screen.getAllByText('Pending');
      // The stat-card label is the one that is NOT a button descendant
      const statCardLabel = pendingLabels.find(
        (el) => el.closest('button') === null,
      ) as HTMLElement;
      expect(statCardLabel).toBeDefined();
      // The numeric count sits in the sibling <p> before the label
      const statCard = statCardLabel.closest('div') as HTMLElement;
      expect(within(statCard).getByText('1')).toBeInTheDocument();
    });

    it('shows average score for graded assignments', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');
      // GRADED_ASSIGNMENT.score = 42, only one graded → avg = 42%
      expect(screen.getByText('42%')).toBeInTheDocument();
    });

    it('shows em dash for avg score when no assignments are graded', async () => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([
        PENDING_ASSIGNMENT,
        SUBMITTED_ASSIGNMENT,
      ]);
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 3. Tabs ──────────────────────────────────────────────────────────────────

  describe('Tab buttons', () => {
    it('renders all four tab buttons: All, Pending, Submitted, Graded', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      expect(screen.getByRole('button', { name: /^all/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^pending/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^submitted/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^graded/i })).toBeInTheDocument();
    });

    it('All tab shows count badge matching total assignments', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      const allTab = screen.getByRole('button', { name: /^all/i });
      expect(allTab).toHaveTextContent('3');
    });
  });

  // ── 4. Loading state ─────────────────────────────────────────────────────────

  describe('Loading state', () => {
    it('renders skeleton placeholders while assignments are fetching', () => {
      mockedStudentService.getStudentAssignments.mockReturnValue(new Promise(() => {}));
      const { container } = renderPage();
      const skeletons = container.querySelectorAll('.tp-skeleton');
      expect(skeletons.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 5. Empty state ───────────────────────────────────────────────────────────

  describe('Empty state — All tab', () => {
    it('shows "No assignments yet" when all assignments list is empty', async () => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([]);
      renderPage();
      expect(await screen.findByText('No assignments yet')).toBeInTheDocument();
    });

    it('shows the correct subtitle for empty All tab', async () => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([]);
      renderPage();
      expect(
        await screen.findByText(/Assignments from your courses will appear here\./),
      ).toBeInTheDocument();
    });
  });

  describe('Empty state — Pending tab', () => {
    beforeEach(() => {
      mockedStudentService.getStudentAssignments.mockImplementation((status?: string) => {
        if (!status) return Promise.resolve(ALL_ASSIGNMENTS);
        return Promise.resolve([]);
      });
    });

    it('shows "All caught up!" when Pending tab has no items', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getByRole('button', { name: /^pending/i }));
      expect(await screen.findByText("All caught up!")).toBeInTheDocument();
    });
  });

  describe('Empty state — Submitted tab', () => {
    beforeEach(() => {
      mockedStudentService.getStudentAssignments.mockImplementation((status?: string) => {
        if (!status) return Promise.resolve(ALL_ASSIGNMENTS);
        return Promise.resolve([]);
      });
    });

    it('shows "Nothing submitted" when Submitted tab is empty', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getByRole('button', { name: /^submitted/i }));
      expect(await screen.findByText('Nothing submitted')).toBeInTheDocument();
    });
  });

  describe('Empty state — Graded tab', () => {
    beforeEach(() => {
      mockedStudentService.getStudentAssignments.mockImplementation((status?: string) => {
        if (!status) return Promise.resolve(ALL_ASSIGNMENTS);
        return Promise.resolve([]);
      });
    });

    it('shows "No graded assignments" when Graded tab is empty', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getByRole('button', { name: /^graded/i }));
      expect(await screen.findByText('No graded assignments')).toBeInTheDocument();
    });
  });

  // ── 6. Assignment list rendering ─────────────────────────────────────────────

  describe('Assignment list rendering', () => {
    it('renders all assignment titles in the default All tab', async () => {
      renderPage();
      expect(await screen.findByText('Chapter 3 Assessment')).toBeInTheDocument();
      expect(await screen.findByText('IB PYP Reflection')).toBeInTheDocument();
      expect(await screen.findByText('Classroom Management Quiz')).toBeInTheDocument();
    });

    it('renders course titles for each assignment card', async () => {
      renderPage();
      expect(await screen.findByText('Algebra Fundamentals')).toBeInTheDocument();
      expect(await screen.findByText('IB PYP Framework')).toBeInTheDocument();
      expect(await screen.findByText('Classroom Management')).toBeInTheDocument();
    });

    it('renders status badge text for each assignment', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      expect(screen.getAllByText('PENDING').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('SUBMITTED').length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText('GRADED').length).toBeGreaterThanOrEqual(1);
    });

    it('renders the due date for assignments that have one', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      // FUTURE_DATE = 2099-12-31 → "Dec 31" formatted
      const dateLabelElements = screen.getAllByText(/Dec 31/i);
      expect(dateLabelElements.length).toBeGreaterThanOrEqual(1);
    });

    it('shows a "Quiz" badge for is_quiz assignments', async () => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([PENDING_QUIZ]);
      renderPage();
      await screen.findByText('Chapter 3 Quiz');
      // The QUIZ badge text
      const quizBadges = screen.getAllByText('Quiz');
      expect(quizBadges.length).toBeGreaterThanOrEqual(1);
    });

    it('shows "Required" indicator for mandatory assignments', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      expect(screen.getAllByText('Required').length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 7. Overdue indicator ─────────────────────────────────────────────────────

  describe('Overdue indicator', () => {
    beforeEach(() => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([OVERDUE_ASSIGNMENT]);
    });

    it('renders overdue text in due-date area when assignment is overdue', async () => {
      renderPage();
      await screen.findByText('Overdue Lab Report');
      // formatDueLabel returns e.g. "2310d overdue" inside a <span>
      const overdueSpans = screen.getAllByText(/overdue/i);
      expect(overdueSpans.length).toBeGreaterThanOrEqual(1);
    });

    it('renders an overdue border on the card (border-red-200)', async () => {
      const { container } = renderPage();
      await screen.findByText('Overdue Lab Report');
      // The card's outer div should have the red border class
      const card = container.querySelector('.border-red-200');
      expect(card).toBeInTheDocument();
    });
  });

  // ── 8. Graded assignment — score and feedback ────────────────────────────────

  describe('Graded assignment details', () => {
    beforeEach(() => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([GRADED_ASSIGNMENT]);
    });

    it('shows the numeric score "42/50" for a graded assignment', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');
      expect(screen.getByText('42/50')).toBeInTheDocument();
    });

    it('shows the passing score label', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');
      expect(screen.getByText(/pass: 30/i)).toBeInTheDocument();
    });

    it('renders the "View feedback" toggle button', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');
      expect(screen.getByRole('button', { name: /view feedback/i })).toBeInTheDocument();
    });

    it('expands feedback text when "View feedback" is clicked', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');
      await userEvent.click(screen.getByRole('button', { name: /view feedback/i }));
      expect(
        await screen.findByText('Well done — very thorough answers.'),
      ).toBeInTheDocument();
    });

    it('collapses feedback when "Hide feedback" is clicked', async () => {
      renderPage();
      await screen.findByText('Classroom Management Quiz');

      await userEvent.click(screen.getByRole('button', { name: /view feedback/i }));
      await screen.findByText('Well done — very thorough answers.');

      await userEvent.click(screen.getByRole('button', { name: /hide feedback/i }));
      await waitFor(() => {
        expect(
          screen.queryByText('Well done — very thorough answers.'),
        ).not.toBeInTheDocument();
      });
    });
  });

  // ── 9. Tab filtering ─────────────────────────────────────────────────────────

  describe('Tab filtering', () => {
    beforeEach(() => {
      mockedStudentService.getStudentAssignments.mockImplementation(
        (status?: 'PENDING' | 'SUBMITTED' | 'GRADED') => {
          if (status === 'PENDING') return Promise.resolve([PENDING_ASSIGNMENT]);
          if (status === 'SUBMITTED') return Promise.resolve([SUBMITTED_ASSIGNMENT]);
          if (status === 'GRADED') return Promise.resolve([GRADED_ASSIGNMENT]);
          return Promise.resolve(ALL_ASSIGNMENTS);
        },
      );
    });

    it('clicking Pending tab shows only the pending assignment', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      await userEvent.click(screen.getByRole('button', { name: /^pending/i }));

      await waitFor(() => {
        expect(screen.getByText('Chapter 3 Assessment')).toBeInTheDocument();
      });
      expect(screen.queryByText('IB PYP Reflection')).not.toBeInTheDocument();
      expect(screen.queryByText('Classroom Management Quiz')).not.toBeInTheDocument();
    });

    it('clicking Submitted tab shows only the submitted assignment', async () => {
      renderPage();
      await screen.findByText('IB PYP Reflection');

      await userEvent.click(screen.getByRole('button', { name: /^submitted/i }));

      await waitFor(() => {
        expect(screen.getByText('IB PYP Reflection')).toBeInTheDocument();
      });
      expect(screen.queryByText('Chapter 3 Assessment')).not.toBeInTheDocument();
      expect(screen.queryByText('Classroom Management Quiz')).not.toBeInTheDocument();
    });

    it('clicking Graded tab shows only the graded assignment', async () => {
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

  // ── 10. Submit modal — open ───────────────────────────────────────────────────

  describe('Submit modal — open', () => {
    beforeEach(() => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([PENDING_ASSIGNMENT]);
    });

    it('renders a "Submit" button for a pending text assignment', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      const submitBtns = screen.getAllByRole('button', { name: /^submit$/i });
      expect(submitBtns.length).toBeGreaterThanOrEqual(1);
    });

    it('clicking Submit opens the modal with the "Submit Assignment" heading', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      expect(await screen.findByText('Submit Assignment')).toBeInTheDocument();
    });

    it('modal shows the assignment title as subtitle', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      // Title appears both in the list and as modal subtitle
      const matches = await screen.findAllByText('Chapter 3 Assessment');
      expect(matches.length).toBeGreaterThanOrEqual(2);
    });

    it('modal shows the Instructions block when assignment has instructions', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      expect(await screen.findByText('Instructions')).toBeInTheDocument();
      expect(
        await screen.findByText('Answer all questions in full sentences.'),
      ).toBeInTheDocument();
    });
  });

  // ── 11. Submit modal — form fields ───────────────────────────────────────────

  describe('Submit modal — form fields', () => {
    beforeEach(async () => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([PENDING_ASSIGNMENT]);
    });

    it('renders the "Your Answer" textarea', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      expect(
        await screen.findByPlaceholderText('Type your submission here...'),
      ).toBeInTheDocument();
    });

    it('renders the optional "File URL" input', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      expect(await screen.findByPlaceholderText('https://...')).toBeInTheDocument();
    });

    it('Submit button inside modal is disabled when both fields are empty', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);

      await screen.findByText('Submit Assignment');
      const modalSubmitBtn = screen.getAllByRole('button', { name: /^submit$/i }).pop()!;
      expect(modalSubmitBtn).toBeDisabled();
    });
  });

  // ── 12. Submit modal — cancel ─────────────────────────────────────────────────

  describe('Submit modal — cancel', () => {
    beforeEach(() => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([PENDING_ASSIGNMENT]);
    });

    it('clicking Cancel closes the modal without submitting', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      await screen.findByText('Submit Assignment');

      await userEvent.click(screen.getByRole('button', { name: /cancel/i }));

      await waitFor(() => {
        expect(screen.queryByText('Submit Assignment')).not.toBeInTheDocument();
      });
      expect(studentService.submitAssignment).not.toHaveBeenCalled();
    });

    it('clicking the X close button in the modal header closes the modal', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      await screen.findByText('Submit Assignment');

      // The header close button is inside the fixed overlay — it is the only
      // button that is NOT "Cancel" and NOT "Submit" in the modal
      const fixedContainer = document.querySelector('.fixed');
      expect(fixedContainer).toBeInTheDocument();
      const allBtnsInModal = Array.from(
        (fixedContainer as HTMLElement).querySelectorAll('button'),
      );
      // Header X button: first button in the modal (top-right close icon)
      const headerCloseBtn = allBtnsInModal.find(
        (btn) =>
          !btn.textContent?.trim().toLowerCase().includes('cancel') &&
          !btn.textContent?.trim().toLowerCase().includes('submit') &&
          !btn.textContent?.trim().toLowerCase().includes('submitting'),
      ) as HTMLElement;
      expect(headerCloseBtn).toBeDefined();
      await userEvent.click(headerCloseBtn);

      await waitFor(() => {
        expect(screen.queryByText('Submit Assignment')).not.toBeInTheDocument();
      });
    });
  });

  // ── 13. Submit mutation ───────────────────────────────────────────────────────

  describe('Submit mutation', () => {
    beforeEach(() => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([PENDING_ASSIGNMENT]);
    });

    it('calls submitAssignment with the assignment id and submission_text', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      await screen.findByText('Submit Assignment');

      const textarea = screen.getByPlaceholderText('Type your submission here...');
      await userEvent.type(textarea, 'My detailed answer');

      const allSubmitBtns = screen.getAllByRole('button', { name: /^submit$/i });
      const modalSubmitBtn = allSubmitBtns[allSubmitBtns.length - 1];
      await userEvent.click(modalSubmitBtn);

      await waitFor(() => {
        expect(studentService.submitAssignment).toHaveBeenCalledWith('asgn-1', {
          submission_text: 'My detailed answer',
          file_url: undefined,
        });
      });
    });

    it('also passes file_url when provided', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      await screen.findByText('Submit Assignment');

      await userEvent.type(
        screen.getByPlaceholderText('Type your submission here...'),
        'Answer text',
      );
      await userEvent.type(
        screen.getByPlaceholderText('https://...'),
        'https://drive.google.com/file',
      );

      const allSubmitBtns = screen.getAllByRole('button', { name: /^submit$/i });
      await userEvent.click(allSubmitBtns[allSubmitBtns.length - 1]);

      await waitFor(() => {
        expect(studentService.submitAssignment).toHaveBeenCalledWith('asgn-1', {
          submission_text: 'Answer text',
          file_url: 'https://drive.google.com/file',
        });
      });
    });

    it('closes the modal after a successful submission', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      await screen.findByText('Submit Assignment');

      await userEvent.type(
        screen.getByPlaceholderText('Type your submission here...'),
        'My answer',
      );

      const allSubmitBtns = screen.getAllByRole('button', { name: /^submit$/i });
      await userEvent.click(allSubmitBtns[allSubmitBtns.length - 1]);

      await waitFor(() => {
        expect(screen.queryByText('Submit Assignment')).not.toBeInTheDocument();
      });
    });

    it('shows an error toast when the mutation fails', async () => {
      mockedStudentService.submitAssignment.mockRejectedValue(new Error('Network error'));

      renderPage();
      await screen.findByText('Chapter 3 Assessment');

      await userEvent.click(screen.getAllByRole('button', { name: /^submit$/i })[0]);
      await screen.findByText('Submit Assignment');

      await userEvent.type(
        screen.getByPlaceholderText('Type your submission here...'),
        'My answer',
      );

      const allSubmitBtns = screen.getAllByRole('button', { name: /^submit$/i });
      await userEvent.click(allSubmitBtns[allSubmitBtns.length - 1]);

      // The real ToastProvider renders two elements: the title and the body.
      // Use findAllByText with the regex and assert at least one matched.
      const toastMessages = await screen.findAllByText(/submission failed|could not submit/i);
      expect(toastMessages.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 14. Quiz navigation ───────────────────────────────────────────────────────

  describe('Quiz navigation', () => {
    it('renders "Start Quiz" button for a pending quiz assignment', async () => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([PENDING_QUIZ]);
      renderPage();
      expect(await screen.findByRole('button', { name: /start quiz/i })).toBeInTheDocument();
    });

    it('clicking "Start Quiz" navigates to /student/quizzes/:id', async () => {
      mockedStudentService.getStudentAssignments.mockResolvedValue([PENDING_QUIZ]);
      renderPage();
      const btn = await screen.findByRole('button', { name: /start quiz/i });
      await userEvent.click(btn);
      expect(mockedUseNavigate).toHaveBeenCalledWith(
        `/student/quizzes/${PENDING_QUIZ.id}`,
      );
    });

    it('renders "View Quiz" button for a submitted quiz assignment', async () => {
      const submittedQuiz: StudentAssignmentListItem = {
        ...PENDING_QUIZ,
        id: 'asgn-quiz-sub',
        submission_status: 'SUBMITTED',
      };
      mockedStudentService.getStudentAssignments.mockResolvedValue([submittedQuiz]);
      renderPage();
      expect(await screen.findByRole('button', { name: /view quiz/i })).toBeInTheDocument();
    });

    it('clicking "View Quiz" navigates to /student/quizzes/:id', async () => {
      const submittedQuiz: StudentAssignmentListItem = {
        ...PENDING_QUIZ,
        id: 'asgn-quiz-sub',
        submission_status: 'SUBMITTED',
      };
      mockedStudentService.getStudentAssignments.mockResolvedValue([submittedQuiz]);
      renderPage();
      const btn = await screen.findByRole('button', { name: /view quiz/i });
      await userEvent.click(btn);
      expect(mockedUseNavigate).toHaveBeenCalledWith(
        `/student/quizzes/asgn-quiz-sub`,
      );
    });

    it('renders "Review Quiz" button for a graded quiz assignment', async () => {
      const gradedQuiz: StudentAssignmentListItem = {
        ...PENDING_QUIZ,
        id: 'asgn-quiz-graded',
        submission_status: 'GRADED',
        score: 18,
        feedback: 'Great job.',
      };
      mockedStudentService.getStudentAssignments.mockResolvedValue([gradedQuiz]);
      renderPage();
      expect(await screen.findByRole('button', { name: /review quiz/i })).toBeInTheDocument();
    });
  });

  // ── 15. getStudentAssignments call signature ──────────────────────────────────

  describe('Service call signatures', () => {
    it('calls getStudentAssignments without a filter for the ALL tab', async () => {
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      // Called at least once without a status argument (the "all" query)
      expect(mockedStudentService.getStudentAssignments).toHaveBeenCalledWith();
    });

    it('calls getStudentAssignments with "PENDING" when Pending tab is clicked', async () => {
      mockedStudentService.getStudentAssignments.mockImplementation(
        (status?: string) => {
          if (status === 'PENDING') return Promise.resolve([PENDING_ASSIGNMENT]);
          return Promise.resolve(ALL_ASSIGNMENTS);
        },
      );
      renderPage();
      await screen.findByText('Chapter 3 Assessment');
      await userEvent.click(screen.getByRole('button', { name: /^pending/i }));
      await waitFor(() => {
        expect(mockedStudentService.getStudentAssignments).toHaveBeenCalledWith('PENDING');
      });
    });
  });
});
