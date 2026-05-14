// src/pages/admin/SectionDetailPage.test.tsx
//
// FE-050: Comprehensive tests for the admin SectionDetailPage.
//
// URL: /admin/school/section/:sectionId?tab=students|teachers|courses
//
// Coverage strategy:
//   1.  Students tab default  — tab button visible, student rows rendered
//   2.  Section header info   — "Section A" and "Grade 5" present in h1
//   3.  Tab navigation        — Teachers tab, Courses tab, back to Students
//   4.  Loading state         — spinner / "Loading..." text while query pending
//   5.  Empty students state  — "No students found" + Add Student + Import CSV
//   6.  Add Student modal     — open, fields present, validation, valid submit
//   7.  Student search        — typing triggers getSectionStudents with search param
//   8.  Error state (students)— "Failed to load students" message + "Try again"
//   9.  Teachers tab          — teacher_name rendered from TeachingAssignment shape
//  10.  Courses tab           — course title rendered
//  11.  Import CSV            — button present in toolbar
//  12.  Back button           — ArrowLeft button present
//  13.  Breadcrumb            — "School" link visible
//
// Implementation notes:
//   • SectionTeachersResponse.teachers is TeachingAssignment[], not the simple
//     {first_name, last_name} shape described in the spec.  The component renders
//     assignment.teacher_name and assignment.subject_name.
//   • The h1 reads "{gradeName} - {sectionName}" (e.g. "Grade 5 - A").
//   • Section info is sourced from studentsData.section which uses the Section
//     model (has a `grade` FK field, not `grade_id`).
//   • getSectionTeachers / getSectionCourses are only called when their tab is
//     active (enabled: activeTab === 'teachers' / 'courses').

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { SectionDetailPage } from './SectionDetailPage';
import { ToastProvider } from '../../components/common';
import { academicsService } from '../../services/academicsService';
import type {
  SectionStudentsResponse,
  SectionTeachersResponse,
  SectionCoursesResponse,
  Section,
  TeachingAssignment,
} from '../../services/academicsService';

// ── Module mocks ───────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/academicsService', () => ({
  academicsService: {
    getSectionStudents: vi.fn(),
    getSectionTeachers: vi.fn(),
    getSectionCourses:  vi.fn(),
    addStudent:         vi.fn(),
    importStudents:     vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

const mockToast = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };
vi.mock('../../components/common', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/common')>();
  return { ...actual, useToast: () => mockToast };
});

// ── Typed service ref ──────────────────────────────────────────────────────────

const svc = academicsService as {
  getSectionStudents: ReturnType<typeof vi.fn>;
  getSectionTeachers: ReturnType<typeof vi.fn>;
  getSectionCourses:  ReturnType<typeof vi.fn>;
  addStudent:         ReturnType<typeof vi.fn>;
  importStudents:     ReturnType<typeof vi.fn>;
};

// ── Fixtures ───────────────────────────────────────────────────────────────────

const SECTION_ID = 'sec-a';
const GRADE_ID   = 'grade-5';

// Section shape matches the real Section model (uses `grade` FK, not `grade_id`)
const SECTION_INFO: Section = {
  id:                 SECTION_ID,
  grade:              GRADE_ID,
  grade_name:         'Grade 5',
  grade_short_code:   'G5',
  name:               'A',
  academic_year:      '2025-2026',
  class_teacher:      null,
  class_teacher_name: null,
  student_count:      2,
  created_at:         '2026-01-01T00:00:00Z',
  updated_at:         '2026-01-01T00:00:00Z',
};

const STUDENT_1 = {
  id:         'stu-1',
  first_name: 'Alice',
  last_name:  'Johnson',
  email:      'alice@school.com',
  student_id: 'STU001',
  is_active:  true,
  last_login: '2026-04-20T10:00:00Z',
  role:       'STUDENT',
};

const STUDENT_2 = {
  id:         'stu-2',
  first_name: 'Bob',
  last_name:  'Smith',
  email:      'bob@school.com',
  student_id: 'STU002',
  is_active:  false,
  last_login: null,
  role:       'STUDENT',
};

const STUDENTS_RESPONSE: SectionStudentsResponse = {
  section:  SECTION_INFO,
  students: [STUDENT_1, STUDENT_2],
  total:    2,
};

// Teachers use TeachingAssignment shape (teacher_name, teacher_email, subject_name, etc.)
const TEACHER_ASSIGNMENT: TeachingAssignment = {
  id:              'ta-1',
  teacher:         'tch-1',
  teacher_name:    'Carol Davis',
  teacher_email:   'carol@school.com',
  subject:         'sub-1',
  subject_name:    'Mathematics',
  subject_code:    'MATH',
  section_ids:     [SECTION_ID],
  section_details: [],
  academic_year:   '2025-2026',
  is_class_teacher: false,
  created_at:      '2026-01-01T00:00:00Z',
  updated_at:      '2026-01-01T00:00:00Z',
};

const TEACHERS_RESPONSE: SectionTeachersResponse = {
  section:  SECTION_INFO,
  teachers: [TEACHER_ASSIGNMENT],
};

// Courses use the shape from SectionCoursesResponse (has is_active, created_at)
const COURSE_1 = {
  id:           'crs-1',
  title:        'Algebra Basics',
  slug:         'algebra-basics',
  is_published: true,
  is_active:    true,
  created_at:   '2026-01-01T00:00:00Z',
  student_count: 2,
};

const COURSES_RESPONSE: SectionCoursesResponse = {
  section: SECTION_INFO,
  courses: [COURSE_1],
};

// ── Render helper ──────────────────────────────────────────────────────────────

function renderPage(tab?: string) {
  const qc = new QueryClient({
    defaultOptions: {
      queries:   { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const initialEntry = `/admin/school/section/${SECTION_ID}${tab ? `?tab=${tab}` : ''}`;
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[initialEntry]}>
          <Routes>
            <Route
              path="/admin/school/section/:sectionId"
              element={<SectionDetailPage />}
            />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// ── Setup ──────────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.resetAllMocks();
  mockNavigate.mockReset();
  mockToast.success.mockReset();
  mockToast.error.mockReset();
  mockToast.warning.mockReset();

  // Default: students query resolves with two students
  svc.getSectionStudents.mockResolvedValue(STUDENTS_RESPONSE);
  svc.getSectionTeachers.mockResolvedValue(TEACHERS_RESPONSE);
  svc.getSectionCourses.mockResolvedValue(COURSES_RESPONSE);
  svc.addStudent.mockResolvedValue({ id: 'stu-new' });
  svc.importStudents.mockResolvedValue({ created: 1, skipped: 0, errors: [], total_rows: 1 });
});

// ── Tests ──────────────────────────────────────────────────────────────────────

describe('SectionDetailPage', () => {

  // ── 1. Students tab default ────────────────────────────────────────────────

  describe('1. Students tab default', () => {
    it('"Students" tab button is visible by default', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /students/i })).toBeInTheDocument(),
      );
    });

    it('renders "Alice Johnson" in the students list', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Alice Johnson')).toBeInTheDocument(),
      );
    });

    it('renders "Bob Smith" in the students list', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Bob Smith')).toBeInTheDocument(),
      );
    });
  });

  // ── 2. Section header info ─────────────────────────────────────────────────

  describe('2. Section header info', () => {
    it('shows section name "A" in the page heading', async () => {
      renderPage();

      // h1 text is "{gradeName} - {sectionName}" e.g. "Grade 5 - A"
      await waitFor(() =>
        expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/\bA\b/),
      );
    });

    it('shows "Grade 5" in the page heading', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Grade 5'),
      );
    });
  });

  // ── 3. Tab navigation ──────────────────────────────────────────────────────

  describe('3. Tab navigation', () => {
    it('clicking "Teachers" tab shows Carol Davis in the teachers list', async () => {
      const user = userEvent.setup();
      renderPage();

      // Wait for initial render
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /teachers/i })).toBeInTheDocument(),
      );

      await user.click(screen.getByRole('button', { name: /teachers/i }));

      await waitFor(() =>
        expect(screen.getByText('Carol Davis')).toBeInTheDocument(),
      );
    });

    it('clicking "Courses" tab shows "Algebra Basics" in the courses list', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /courses/i })).toBeInTheDocument(),
      );

      await user.click(screen.getByRole('button', { name: /courses/i }));

      await waitFor(() =>
        expect(screen.getByText('Algebra Basics')).toBeInTheDocument(),
      );
    });

    it('clicking back to "Students" tab re-shows student names', async () => {
      const user = userEvent.setup();
      renderPage();

      // Switch to Teachers tab
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /teachers/i })).toBeInTheDocument(),
      );
      await user.click(screen.getByRole('button', { name: /teachers/i }));

      await waitFor(() =>
        expect(screen.getByText('Carol Davis')).toBeInTheDocument(),
      );

      // Switch back to Students tab
      await user.click(screen.getByRole('button', { name: /students/i }));

      await waitFor(() =>
        expect(screen.getByText('Alice Johnson')).toBeInTheDocument(),
      );
    });
  });

  // ── 4. Loading state ───────────────────────────────────────────────────────

  describe('4. Loading state', () => {
    it('shows loading indicator while students query is pending', () => {
      svc.getSectionStudents.mockReturnValue(new Promise(() => {}));
      renderPage();

      // The component renders a Spinner + "Loading..." text while the query pends
      const loadingText = document.querySelector('.animate-spin');
      expect(loadingText).toBeInTheDocument();
    });
  });

  // ── 5. Empty students state ────────────────────────────────────────────────

  describe('5. Empty students state', () => {
    beforeEach(() => {
      svc.getSectionStudents.mockResolvedValue({
        ...STUDENTS_RESPONSE,
        students: [],
        total: 0,
      });
    });

    it('shows "No students found" when students array is empty', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('No students found')).toBeInTheDocument(),
      );
    });

    it('renders "Add Student" button in the empty state', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('No students found')).toBeInTheDocument(),
      );

      // The empty state includes an Add Student button alongside the toolbar one
      const addStudentButtons = screen.getAllByRole('button', { name: /add student/i });
      expect(addStudentButtons.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 6. Add Student modal ───────────────────────────────────────────────────

  describe('6. Add Student modal', () => {
    it('"Add Student" toolbar button opens the modal', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getAllByRole('button', { name: /add student/i })[0]).toBeInTheDocument(),
      );

      // Click the toolbar Add Student button (first match)
      await user.click(screen.getAllByRole('button', { name: /add student/i })[0]);

      await waitFor(() =>
        expect(screen.getByRole('heading', { name: /add student/i })).toBeInTheDocument(),
      );
    });

    it('modal contains First name, Last name, and Email fields', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getAllByRole('button', { name: /add student/i })[0]).toBeInTheDocument(),
      );
      await user.click(screen.getAllByRole('button', { name: /add student/i })[0]);

      await waitFor(() =>
        expect(screen.getByLabelText(/first name/i)).toBeInTheDocument(),
      );

      expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    });

    it('submitting empty form shows "First name is required" error', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getAllByRole('button', { name: /add student/i })[0]).toBeInTheDocument(),
      );
      await user.click(screen.getAllByRole('button', { name: /add student/i })[0]);

      await waitFor(() =>
        expect(screen.getByLabelText(/first name/i)).toBeInTheDocument(),
      );

      // Submit without filling any fields.
      // Multiple buttons read "Add Student" (toolbar + modal submit).
      // The modal's submit button is type="submit" — pick it by that attribute.
      const submitButton = screen
        .getAllByRole('button', { name: /add student/i })
        .find((btn) => btn.getAttribute('type') === 'submit')!;
      await user.click(submitButton);

      await waitFor(() =>
        expect(screen.getByText('First name is required')).toBeInTheDocument(),
      );
    });

    it('valid submission calls academicsService.addStudent with correct payload', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getAllByRole('button', { name: /add student/i })[0]).toBeInTheDocument(),
      );
      await user.click(screen.getAllByRole('button', { name: /add student/i })[0]);

      await waitFor(() =>
        expect(screen.getByLabelText(/first name/i)).toBeInTheDocument(),
      );

      await user.type(screen.getByLabelText(/first name/i), 'Jane');
      await user.type(screen.getByLabelText(/last name/i), 'Doe');
      await user.type(screen.getByLabelText(/email/i), 'jane@school.com');

      // Use the type="submit" button inside the modal
      const submitButton = screen
        .getAllByRole('button', { name: /add student/i })
        .find((btn) => btn.getAttribute('type') === 'submit')!;
      await user.click(submitButton);

      await waitFor(() =>
        expect(svc.addStudent).toHaveBeenCalledWith(
          SECTION_ID,
          expect.objectContaining({
            first_name: 'Jane',
            last_name:  'Doe',
            email:      'jane@school.com',
          }),
        ),
      );
    });
  });

  // ── 7. Student search ──────────────────────────────────────────────────────

  describe('7. Student search', () => {
    it('typing in the search input triggers getSectionStudents with the search param', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(
          screen.getByPlaceholderText('Search students by name, email, or ID...'),
        ).toBeInTheDocument(),
      );

      const searchInput = screen.getByPlaceholderText(
        'Search students by name, email, or ID...',
      );
      await user.type(searchInput, 'Alice');

      // Debounce is 300ms — wait for the debounced call to go through
      await waitFor(
        () =>
          expect(svc.getSectionStudents).toHaveBeenCalledWith(
            SECTION_ID,
            'Alice',
          ),
        { timeout: 2000 },
      );
    });
  });

  // ── 8. Error state (students) ──────────────────────────────────────────────

  describe('8. Error state (students)', () => {
    beforeEach(() => {
      svc.getSectionStudents.mockRejectedValue(new Error('Network error'));
    });

    it('shows "Failed to load students. Please try again." when query throws', async () => {
      renderPage();

      await waitFor(() =>
        expect(
          screen.getByText('Failed to load students. Please try again.'),
        ).toBeInTheDocument(),
      );
    });

    it('shows a "Try again" button in the error state', async () => {
      renderPage();

      await waitFor(() =>
        expect(
          screen.getByText('Failed to load students. Please try again.'),
        ).toBeInTheDocument(),
      );

      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    });
  });

  // ── 9. Teachers tab ────────────────────────────────────────────────────────

  describe('9. Teachers tab', () => {
    it('switching to Teachers tab renders teacher name "Carol Davis"', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /teachers/i })).toBeInTheDocument(),
      );

      await user.click(screen.getByRole('button', { name: /teachers/i }));

      await waitFor(() =>
        expect(screen.getByText('Carol Davis')).toBeInTheDocument(),
      );
    });

    it('"Carol" is visible in the teacher row after switching to Teachers tab', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /teachers/i })).toBeInTheDocument(),
      );

      await user.click(screen.getByRole('button', { name: /teachers/i }));

      await waitFor(() =>
        expect(screen.getByText('Carol Davis')).toBeInTheDocument(),
      );

      // teacher_name starts with "Carol" — the avatar uses the first letter
      expect(screen.getByText('C')).toBeInTheDocument();
    });
  });

  // ── 10. Courses tab ────────────────────────────────────────────────────────

  describe('10. Courses tab', () => {
    it('switching to Courses tab renders "Algebra Basics"', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /courses/i })).toBeInTheDocument(),
      );

      await user.click(screen.getByRole('button', { name: /courses/i }));

      await waitFor(() =>
        expect(screen.getByText('Algebra Basics')).toBeInTheDocument(),
      );
    });

    it('"Algebra Basics" course is shown in the courses table', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /courses/i })).toBeInTheDocument(),
      );

      await user.click(screen.getByRole('button', { name: /courses/i }));

      await waitFor(() => {
        const courseTitles = screen.getAllByText('Algebra Basics');
        expect(courseTitles.length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  // ── 11. Import CSV ─────────────────────────────────────────────────────────

  describe('11. Import CSV', () => {
    it('"Import CSV" button is present in the students tab toolbar', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /import csv/i })).toBeInTheDocument(),
      );
    });
  });

  // ── 12. Back button ────────────────────────────────────────────────────────

  describe('12. Back button', () => {
    it('ArrowLeft back button is present on the page', async () => {
      renderPage();

      // The back button has title="Back to grade" and contains an ArrowLeftIcon
      await waitFor(() =>
        expect(screen.getByTitle('Back to grade')).toBeInTheDocument(),
      );
    });
  });

  // ── 13. Breadcrumb ─────────────────────────────────────────────────────────

  describe('13. Breadcrumb', () => {
    it('"School" breadcrumb link is visible', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('link', { name: 'School' })).toBeInTheDocument(),
      );
    });
  });

});
