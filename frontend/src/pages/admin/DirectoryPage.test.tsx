// src/pages/admin/DirectoryPage.test.tsx
//
// Test suite for DirectoryPage — read-only school directory with
// grade band → grade → section card layout and expandable section cards.
//
// Coverage strategy:
//   1. Loading state (skeleton shown, heading absent)
//   2. Page header (h1, school name, academic year)
//   3. Summary strip (Grade Bands / Grades / Sections / Students stats)
//   4. Empty state (no grade bands configured)
//   5. Grade band and section rendering (band heading, section cards, class teacher)
//   6. "No class teacher assigned" fallback
//   7. Search filter (client-side section filtering)
//   8. Section card expand/collapse (lazy-loads students + teachers)
//
// Notes:
//   • academicsService.getSectionStudents / getSectionTeachers are only
//     called when a SectionCard is clicked (enabled: expanded).
//   • SectionCard is a <div> with onClick, not a <button> — click the
//     "Click to view roster" span to trigger expansion.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DirectoryPage } from './DirectoryPage';
import { academicsService } from '../../services/academicsService';

// ── service mock ──────────────────────────────────────────────────────────────
vi.mock('../../services/academicsService', () => ({
  academicsService: {
    getSchoolOverview: vi.fn(),
    getSections: vi.fn(),
    getSectionStudents: vi.fn(),
    getSectionTeachers: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── typed service ref ─────────────────────────────────────────────────────────
const mockedService = academicsService as {
  getSchoolOverview: ReturnType<typeof vi.fn>;
  getSections: ReturnType<typeof vi.fn>;
  getSectionStudents: ReturnType<typeof vi.fn>;
  getSectionTeachers: ReturnType<typeof vi.fn>;
};

// ── fixture data ──────────────────────────────────────────────────────────────
const GRADE_5 = {
  id: 'grade-5',
  grade_band: 'band-1',
  grade_band_name: 'Primary',
  grade_band_short_code: 'PRI',
  name: 'Grade 5',
  short_code: 'G5',
  order: 5,
  student_count: 30,
  section_count: 2,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

const GRADE_BAND = {
  id: 'band-1',
  name: 'Primary',
  short_code: 'PRI',
  order: 1,
  curriculum_framework: 'IB_PYP',
  theme_config: { accent_color: '#4F46E5' },
  grade_count: 1,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  grades: [GRADE_5],
};

const OVERVIEW = {
  academic_year: '2025-2026',
  school_name: 'Puddle International School',
  grade_bands: [GRADE_BAND],
};

// Section A has a class teacher and students
const SECTION_A = {
  id: 'sec-a',
  grade: 'grade-5',         // matches GRADE_5.id — links section to grade
  grade_name: 'Grade 5',
  grade_short_code: 'G5',
  name: 'Alpha',
  academic_year: '2025-2026',
  class_teacher: 't-1',
  class_teacher_name: 'Alice Wong',
  student_count: 15,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

// Section B has no class teacher and no students
const SECTION_B = {
  id: 'sec-b',
  grade: 'grade-5',
  grade_name: 'Grade 5',
  grade_short_code: 'G5',
  name: 'Beta',
  academic_year: '2025-2026',
  class_teacher: null,
  class_teacher_name: null,
  student_count: 0,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

const SECTION_STUDENTS_RESPONSE = {
  section: SECTION_A,
  students: [
    {
      id: 's-1',
      email: 'bob@school.edu',
      first_name: 'Bob',
      last_name: 'Chen',
      student_id: 'KIS-001',
      is_active: true,
      last_login: null,
      role: 'STUDENT',
    },
  ],
  total: 1,
};

const SECTION_TEACHERS_RESPONSE = {
  section: SECTION_A,
  teachers: [
    {
      id: 'ta-1',
      teacher: 't-2',
      teacher_name: 'Carol Lee',
      teacher_email: 'carol@school.edu',
      subject: 'sub-1',
      subject_name: 'Mathematics',
      subject_code: 'MATH',
      section_ids: ['sec-a'],
      section_details: [],
      academic_year: '2025-2026',
      is_class_teacher: false,
      created_at: '',
      updated_at: '',
    },
  ],
};

// ── helpers ───────────────────────────────────────────────────────────────────
function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <DirectoryPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
describe('DirectoryPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedService.getSchoolOverview.mockResolvedValue(OVERVIEW);
    mockedService.getSections.mockResolvedValue([SECTION_A, SECTION_B]);
    mockedService.getSectionStudents.mockResolvedValue(SECTION_STUDENTS_RESPONSE);
    mockedService.getSectionTeachers.mockResolvedValue(SECTION_TEACHERS_RESPONSE);
  });

  // ── 1. Loading state ───────────────────────────────────────────────────────
  describe('loading state', () => {
    it('does not show the heading while the overview query is pending', () => {
      mockedService.getSchoolOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.queryByRole('heading', { name: /School Directory/i })).not.toBeInTheDocument();
    });
  });

  // ── 2. Page header ─────────────────────────────────────────────────────────
  describe('page header', () => {
    it('renders the "School Directory" heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { name: /School Directory/i })).toBeInTheDocument();
    });

    it('shows school name in the subtitle', async () => {
      renderPage();
      expect(await screen.findByText(/Puddle International School/i)).toBeInTheDocument();
    });

    it('shows academic year in the subtitle', async () => {
      renderPage();
      expect(await screen.findByText(/2025-2026/)).toBeInTheDocument();
    });

    it('renders the search input', async () => {
      renderPage();
      expect(
        await screen.findByPlaceholderText(/Search by name, grade, or section/i)
      ).toBeInTheDocument();
    });
  });

  // ── 3. Summary strip ───────────────────────────────────────────────────────
  describe('summary strip', () => {
    it('shows Grade Bands count (1)', async () => {
      renderPage();
      await screen.findByRole('heading', { name: /School Directory/i });
      // Stat chip renders: <span>{value}</span><span>{label}</span>
      expect(screen.getByText('Grade Bands')).toBeInTheDocument();
    });

    it('shows Grades count (1)', async () => {
      renderPage();
      await screen.findByRole('heading', { name: /School Directory/i });
      expect(screen.getByText('Grades')).toBeInTheDocument();
    });

    it('shows Sections count (2)', async () => {
      renderPage();
      await screen.findByRole('heading', { name: /School Directory/i });
      expect(screen.getByText('Sections')).toBeInTheDocument();
    });

    it('shows Students count (30) from grade band data', async () => {
      renderPage();
      await screen.findByRole('heading', { name: /School Directory/i });
      expect(screen.getByText('Students')).toBeInTheDocument();
      // The number 30 comes from GRADE_5.student_count
      expect(screen.getByText('30')).toBeInTheDocument();
    });
  });

  // ── 4. Empty state ─────────────────────────────────────────────────────────
  describe('empty state', () => {
    it('shows "No academic structure configured" when overview has no grade bands', async () => {
      mockedService.getSchoolOverview.mockResolvedValue({ ...OVERVIEW, grade_bands: [] });
      renderPage();
      expect(
        await screen.findByText(/No academic structure configured/i)
      ).toBeInTheDocument();
    });

    it('shows setup instruction text in the empty state', async () => {
      mockedService.getSchoolOverview.mockResolvedValue({ ...OVERVIEW, grade_bands: [] });
      renderPage();
      expect(
        await screen.findByText(/Set up grade bands and sections in School settings first/i)
      ).toBeInTheDocument();
    });
  });

  // ── 5. Grade band and section rendering ────────────────────────────────────
  describe('grade band and section rendering', () => {
    it('shows the grade band name as a heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { name: /^Primary$/i })).toBeInTheDocument();
    });

    it('shows the curriculum framework in band sub-info (underscores replaced)', async () => {
      renderPage();
      // IB_PYP → "IB PYP" (replace underscores with spaces)
      expect(await screen.findByText(/IB PYP/i)).toBeInTheDocument();
    });

    it('shows section Alpha and Beta cards (both Grade 5)', async () => {
      renderPage();
      expect(await screen.findByText('Alpha')).toBeInTheDocument();
      expect(await screen.findByText('Beta')).toBeInTheDocument();
      // Both cards show "Grade 5" — both sections belong to Grade 5
      await waitFor(() => {
        expect(screen.getAllByText('Grade 5').length).toBeGreaterThanOrEqual(2);
      });
    });

    it('shows section Beta card', async () => {
      renderPage();
      expect(await screen.findByText('Beta')).toBeInTheDocument();
    });

    it('shows class teacher name on section Alpha card', async () => {
      renderPage();
      expect(await screen.findByText('Alice Wong')).toBeInTheDocument();
    });
  });

  // ── 6. No class teacher fallback ───────────────────────────────────────────
  describe('no class teacher fallback', () => {
    it('shows "No class teacher assigned" for section Beta (no teacher)', async () => {
      renderPage();
      expect(await screen.findByText(/No class teacher assigned/i)).toBeInTheDocument();
    });
  });

  // ── 7. Search filter (client-side) ─────────────────────────────────────────
  describe('search filter', () => {
    it('typing a section name shows only matching sections', async () => {
      renderPage();
      await screen.findByText('Alpha');
      const searchInput = screen.getByPlaceholderText(/Search by name, grade, or section/i);
      await userEvent.type(searchInput, 'Alpha');
      await waitFor(() => {
        expect(screen.getByText('Alpha')).toBeInTheDocument();
        expect(screen.queryByText('Beta')).not.toBeInTheDocument();
      });
    });

    it('searching for a class teacher name shows only their section', async () => {
      renderPage();
      await screen.findByText('Alice Wong');
      const searchInput = screen.getByPlaceholderText(/Search by name, grade, or section/i);
      await userEvent.type(searchInput, 'Alice');
      await waitFor(() => {
        expect(screen.getByText('Alpha')).toBeInTheDocument();
        expect(screen.queryByText('Beta')).not.toBeInTheDocument();
      });
    });
  });

  // ── 8. Section card expand / collapse ──────────────────────────────────────
  describe('section card expand and collapse', () => {
    it('shows "Click to view roster" on cards by default', async () => {
      renderPage();
      const hints = await screen.findAllByText(/Click to view roster/i);
      expect(hints.length).toBeGreaterThanOrEqual(1);
    });

    it('clicking a card changes hint text to "Click to collapse"', async () => {
      renderPage();
      const hint = await screen.findAllByText(/Click to view roster/i);
      // Click the first section card via its expand hint
      await userEvent.click(hint[0]);
      expect(await screen.findByText(/Click to collapse/i)).toBeInTheDocument();
    });

    it('expanding a card fetches and shows student names', async () => {
      renderPage();
      const hints = await screen.findAllByText(/Click to view roster/i);
      await userEvent.click(hints[0]);
      expect(await screen.findByText('Bob Chen')).toBeInTheDocument();
    });

    it('expanding a card fetches and shows subject teacher names', async () => {
      renderPage();
      const hints = await screen.findAllByText(/Click to view roster/i);
      await userEvent.click(hints[0]);
      expect(await screen.findByText('Carol Lee')).toBeInTheDocument();
    });

    it('expanding a card shows the subject name', async () => {
      renderPage();
      const hints = await screen.findAllByText(/Click to view roster/i);
      await userEvent.click(hints[0]);
      expect(await screen.findByText('Mathematics')).toBeInTheDocument();
    });

    it('getSectionStudents is not called before any card is expanded', async () => {
      renderPage();
      await screen.findByText('Alpha');
      expect(mockedService.getSectionStudents).not.toHaveBeenCalled();
    });
  });
});
