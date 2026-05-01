// src/pages/admin/GradeDetailPage.test.tsx
//
// FE-047: Comprehensive tests for GradeDetailPage — admin grade detail view.
//
// Coverage strategy:
//   1.  Loading state (skeleton / animate-pulse)
//   2.  Breadcrumb (School link + grade name)
//   3.  Grade header (h1, section count, student count)
//   4.  Section cards (names, teacher name, missing teacher placeholder)
//   5.  Empty state ("No sections for this grade" + "Create First Section" button)
//   6.  Add Section modal (open, fields, pre-fill, validation, success)
//   7.  Edit Section (dropdown → Edit → modal pre-filled → submit)
//   8.  Delete Section (dropdown → Delete → confirm dialog → service call)
//   9.  Error state ("Failed to load sections" + Retry button)
//  10.  Grade not found state
//  11.  Back button navigates to /admin/school
//  12.  Import CSV button disabled when sections=[]
//
// Mock notes:
//   • academicsService: all relevant methods vi.fn()
//   • useNavigate: captured mockNavigate
//   • useToast: captured for assertions
//   • usePageTitle: no-op

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { GradeDetailPage } from './GradeDetailPage';
import { ToastProvider } from '../../components/common';
import { academicsService } from '../../services/academicsService';
import type { Section, Grade, SchoolOverviewResponse } from '../../services/academicsService';

// ── Module mocks ───────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/academicsService', () => ({
  academicsService: {
    getSchoolOverview: vi.fn(),
    getSections:       vi.fn(),
    createSection:     vi.fn(),
    updateSection:     vi.fn(),
    deleteSection:     vi.fn(),
    importStudents:    vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

const mockToast = { success: vi.fn(), error: vi.fn(), warning: vi.fn() };
vi.mock('../../components/common', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/common')>();
  return { ...actual, useToast: () => mockToast };
});

// ── Fixtures ───────────────────────────────────────────────────────────────────

const GRADE_ID = 'grade-5';

const SECTION_A: Section = {
  id: 'sec-a',
  grade: GRADE_ID,
  grade_name: 'Grade 5',
  grade_short_code: 'G5',
  name: 'A',
  academic_year: '2025-2026',
  class_teacher: 'teacher-1',
  class_teacher_name: 'Alice Smith',
  student_count: 30,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

const SECTION_B: Section = {
  id: 'sec-b',
  grade: GRADE_ID,
  grade_name: 'Grade 5',
  grade_short_code: 'G5',
  name: 'B',
  academic_year: '2025-2026',
  class_teacher: null,
  class_teacher_name: null,
  student_count: 28,
  created_at: '2025-01-02T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
};

const GRADE: Grade = {
  id: GRADE_ID,
  grade_band: 'band-primary',
  grade_band_name: 'Primary',
  grade_band_short_code: 'PRI',
  name: 'Grade 5',
  short_code: 'G5',
  order: 5,
  student_count: 58,
  section_count: 2,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

const OVERVIEW: SchoolOverviewResponse = {
  school_name: 'Demo School',
  academic_year: '2025-2026',
  grade_bands: [
    {
      id: 'band-primary',
      name: 'Primary',
      short_code: 'PRI',
      order: 1,
      curriculum_framework: 'IB',
      theme_config: { accent_color: '#10B981' },
      grade_count: 1,
      created_at: '2025-01-01T00:00:00Z',
      updated_at: '2025-01-01T00:00:00Z',
      grades: [GRADE],
    },
  ],
};

// ── Typed service ref ──────────────────────────────────────────────────────────

const svc = academicsService as {
  getSchoolOverview: ReturnType<typeof vi.fn>;
  getSections:       ReturnType<typeof vi.fn>;
  createSection:     ReturnType<typeof vi.fn>;
  updateSection:     ReturnType<typeof vi.fn>;
  deleteSection:     ReturnType<typeof vi.fn>;
  importStudents:    ReturnType<typeof vi.fn>;
};

// ── Render helper ──────────────────────────────────────────────────────────────

function renderPage(gradeId = GRADE_ID) {
  const qc = new QueryClient({
    defaultOptions: {
      queries:   { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter initialEntries={[`/admin/school/grade/${gradeId}`]}>
          <Routes>
            <Route path="/admin/school/grade/:gradeId" element={<GradeDetailPage />} />
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

  // Default: overview loaded, two sections
  svc.getSchoolOverview.mockResolvedValue(OVERVIEW);
  svc.getSections.mockResolvedValue([SECTION_A, SECTION_B]);
  svc.createSection.mockResolvedValue({ ...SECTION_A, id: 'sec-new', name: 'C' });
  svc.updateSection.mockResolvedValue({ ...SECTION_A, name: 'A-Updated' });
  svc.deleteSection.mockResolvedValue(undefined);
});

// ── Tests ──────────────────────────────────────────────────────────────────────

describe('GradeDetailPage', () => {

  // ── 1. Loading state ──────────────────────────────────────────────────────

  describe('1. Loading state', () => {
    it('shows animated skeleton while queries are pending', () => {
      // Neither query resolves — page stays in loading branch
      svc.getSchoolOverview.mockReturnValue(new Promise(() => {}));
      svc.getSections.mockReturnValue(new Promise(() => {}));

      renderPage();

      // The loading branch renders animate-pulse wrappers
      const pulseElements = document.querySelectorAll('.animate-pulse');
      expect(pulseElements.length).toBeGreaterThan(0);
    });
  });

  // ── 2. Breadcrumb ─────────────────────────────────────────────────────────

  describe('2. Breadcrumb', () => {
    it('renders "School" breadcrumb link pointing to /admin/school', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('link', { name: 'School' })).toBeInTheDocument(),
      );

      const schoolLink = screen.getByRole('link', { name: 'School' });
      expect(schoolLink).toHaveAttribute('href', '/admin/school');
    });

    it('renders grade name as the active breadcrumb segment', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Grade 5', { selector: 'nav span' })).toBeInTheDocument(),
      );
    });
  });

  // ── 3. Grade header ───────────────────────────────────────────────────────

  describe('3. Grade header', () => {
    it('shows grade name "Grade 5" in h1', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('heading', { level: 1, name: 'Grade 5' })).toBeInTheDocument(),
      );
    });

    it('shows section count in subtitle', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText(/2\s+sections/i)).toBeInTheDocument(),
      );
    });

    it('shows student count in subtitle', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText(/58\s+students/i)).toBeInTheDocument(),
      );
    });
  });

  // ── 4. Section cards ──────────────────────────────────────────────────────

  describe('4. Section cards', () => {
    it('renders "Section A" card', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Section A')).toBeInTheDocument(),
      );
    });

    it('renders "Section B" card', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Section B')).toBeInTheDocument(),
      );
    });

    it('shows first name of teacher for Section A ("Alice")', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Section A')).toBeInTheDocument(),
      );

      // The card shows only the first word of class_teacher_name
      expect(screen.getByText('Alice')).toBeInTheDocument();
    });

    it('shows "--" placeholder for Section B (no teacher)', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Section B')).toBeInTheDocument(),
      );

      expect(screen.getByText('--')).toBeInTheDocument();
    });
  });

  // ── 5. Empty state ────────────────────────────────────────────────────────

  describe('5. Empty state', () => {
    beforeEach(() => {
      svc.getSections.mockResolvedValue([]);
    });

    it('shows "No sections for this grade" when sections array is empty', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('No sections for this grade')).toBeInTheDocument(),
      );
    });

    it('shows "Create First Section" button in empty state', async () => {
      renderPage();

      await waitFor(() =>
        expect(
          screen.getByRole('button', { name: /create first section/i }),
        ).toBeInTheDocument(),
      );
    });
  });

  // ── 6. Add Section modal ──────────────────────────────────────────────────

  describe('6. Add Section modal', () => {
    it('clicking "Add Section" button opens modal with heading "Add Section"', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /add section/i })).toBeInTheDocument(),
      );

      await user.click(screen.getByRole('button', { name: /add section/i }));

      await waitFor(() =>
        expect(
          screen.getByRole('heading', { name: 'Add Section' }),
        ).toBeInTheDocument(),
      );
    });

    it('modal contains a "Section Name" field', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /add section/i })).toBeInTheDocument(),
      );
      await user.click(screen.getByRole('button', { name: /add section/i }));

      await waitFor(() =>
        expect(screen.getByLabelText(/section name/i)).toBeInTheDocument(),
      );
    });

    it('Academic Year field is pre-filled with "2025-2026" from overview', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /add section/i })).toBeInTheDocument(),
      );
      await user.click(screen.getByRole('button', { name: /add section/i }));

      await waitFor(() =>
        expect(screen.getByDisplayValue('2025-2026')).toBeInTheDocument(),
      );
    });

    it('submitting with empty section name shows "Section name is required"', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /add section/i })).toBeInTheDocument(),
      );
      await user.click(screen.getByRole('button', { name: /add section/i }));

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /create section/i })).toBeInTheDocument(),
      );

      // Submit without entering a name
      await user.click(screen.getByRole('button', { name: /create section/i }));

      await waitFor(() =>
        expect(screen.getByText('Section name is required')).toBeInTheDocument(),
      );
    });

    it('valid submission calls academicsService.createSection with correct payload', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /add section/i })).toBeInTheDocument(),
      );
      await user.click(screen.getByRole('button', { name: /add section/i }));

      await waitFor(() =>
        expect(screen.getByLabelText(/section name/i)).toBeInTheDocument(),
      );

      await user.type(screen.getByLabelText(/section name/i), 'C');
      await user.click(screen.getByRole('button', { name: /create section/i }));

      await waitFor(() =>
        expect(svc.createSection).toHaveBeenCalledWith(
          expect.objectContaining({
            grade: GRADE_ID,
            name: 'C',
            academic_year: '2025-2026',
          }),
        ),
      );
    });
  });

  // ── 7. Edit Section ───────────────────────────────────────────────────────

  describe('7. Edit Section', () => {
    it('Actions dropdown for Section A contains "Edit" option', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Section A')).toBeInTheDocument(),
      );

      await user.click(
        screen.getByRole('button', { name: /actions for section a/i }),
      );

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^edit$/i })).toBeInTheDocument(),
      );
    });

    it('clicking Edit opens modal with "Edit Section" heading and name pre-filled with "A"', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Section A')).toBeInTheDocument(),
      );

      // Open the actions dropdown for Section A
      await user.click(
        screen.getByRole('button', { name: /actions for section a/i }),
      );

      // Click Edit in the dropdown
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^edit$/i })).toBeInTheDocument(),
      );
      await user.click(screen.getByRole('button', { name: /^edit$/i }));

      // Modal should open in edit mode
      await waitFor(() =>
        expect(
          screen.getByRole('heading', { name: 'Edit Section' }),
        ).toBeInTheDocument(),
      );

      // Section name field should be pre-filled
      expect(screen.getByDisplayValue('A')).toBeInTheDocument();
    });
  });

  // ── 8. Delete Section ─────────────────────────────────────────────────────

  describe('8. Delete Section', () => {
    it('Actions dropdown for Section A contains "Delete" option', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Section A')).toBeInTheDocument(),
      );

      await user.click(
        screen.getByRole('button', { name: /actions for section a/i }),
      );

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument(),
      );
    });

    it('clicking Delete opens confirmation dialog with "Delete Section" heading', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Section A')).toBeInTheDocument(),
      );

      await user.click(
        screen.getByRole('button', { name: /actions for section a/i }),
      );

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument(),
      );
      await user.click(screen.getByRole('button', { name: /^delete$/i }));

      await waitFor(() =>
        expect(
          screen.getByRole('heading', { name: 'Delete Section' }),
        ).toBeInTheDocument(),
      );
    });

    it('confirming deletion calls academicsService.deleteSection with section id', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Section A')).toBeInTheDocument(),
      );

      // Open dropdown → Delete
      await user.click(
        screen.getByRole('button', { name: /actions for section a/i }),
      );
      await waitFor(() =>
        expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument(),
      );
      await user.click(screen.getByRole('button', { name: /^delete$/i }));

      // Confirm dialog appears — click the red "Delete Section" confirm button
      await waitFor(() =>
        expect(
          screen.getByRole('heading', { name: 'Delete Section' }),
        ).toBeInTheDocument(),
      );

      // Multiple buttons may read "Delete Section"; the confirm one is inside the dialog
      const confirmButtons = screen.getAllByRole('button', { name: /delete section/i });
      // The last match is the confirm button (the dialog heading is an h3, not a button)
      const confirmBtn = confirmButtons[confirmButtons.length - 1];
      await user.click(confirmBtn);

      await waitFor(() =>
        expect(svc.deleteSection).toHaveBeenCalledWith('sec-a'),
      );
    });
  });

  // ── 9. Error state ────────────────────────────────────────────────────────

  describe('9. Error state', () => {
    beforeEach(() => {
      svc.getSections.mockRejectedValue(new Error('Network error'));
    });

    it('shows "Failed to load sections" when sections query throws', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('Failed to load sections')).toBeInTheDocument(),
      );
    });

    it('shows a "Retry" button in the error state', async () => {
      renderPage();

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument(),
      );
    });
  });

  // ── 10. Grade not found ───────────────────────────────────────────────────

  describe('10. Grade not found', () => {
    it('shows "Grade not found" when gradeId does not match any grade in overview', async () => {
      // Override getSections so the page doesn't hang in loading
      svc.getSections.mockResolvedValue([]);

      renderPage('grade-nonexistent');

      await waitFor(() =>
        expect(screen.getByText('Grade not found')).toBeInTheDocument(),
      );
    });
  });

  // ── 11. Back button ───────────────────────────────────────────────────────

  describe('11. Back button', () => {
    it('clicking back button (aria-label="Back to school overview") navigates to /admin/school', async () => {
      const user = userEvent.setup();
      renderPage();

      await waitFor(() =>
        expect(
          screen.getByRole('button', { name: /back to school overview/i }),
        ).toBeInTheDocument(),
      );

      await user.click(
        screen.getByRole('button', { name: /back to school overview/i }),
      );

      expect(mockNavigate).toHaveBeenCalledWith('/admin/school');
    });
  });

  // ── 12. Import CSV button ─────────────────────────────────────────────────

  describe('12. Import CSV button', () => {
    it('"Import CSV" button is disabled when there are no sections', async () => {
      svc.getSections.mockResolvedValue([]);
      renderPage();

      await waitFor(() =>
        expect(screen.getByText('No sections for this grade')).toBeInTheDocument(),
      );

      const importBtn = screen.getByRole('button', { name: /import csv/i });
      expect(importBtn).toBeDisabled();
    });
  });

});
