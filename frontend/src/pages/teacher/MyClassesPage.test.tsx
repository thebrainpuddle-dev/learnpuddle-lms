// src/pages/teacher/MyClassesPage.test.tsx
//
// FE-053: Tests for the Teacher My Classes page.
// Covers: page header, academic year badge, loading skeleton, error state,
//         empty state, subject group rendering, section card display (grade/name,
//         student/course counts, Class Teacher badge, grade_band_name),
//         navigation on card click, and summary stats.
//
// Mocking strategy:
//   - academicsService.getMyClasses is mocked as a vi.fn()
//   - useNavigate is replaced with a stable mockNavigate spy
//   - usePageTitle is stubbed to avoid side-effects

import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MyClassesPage } from './MyClassesPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/academicsService', () => ({
  academicsService: { getMyClasses: vi.fn() },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helper ─────────────────────────────────────────────────────────

import { academicsService } from '../../services/academicsService';
const mockGetMyClasses = academicsService.getMyClasses as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MyClassesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const sectionA = {
  id: 'sec-1',
  name: 'A',
  grade_name: 'Grade 5',
  grade_band_name: 'Primary School',
  student_count: 28,
  course_count: 3,
  is_class_teacher: true,
};

const sectionB = {
  id: 'sec-2',
  name: 'B',
  grade_name: 'Grade 6',
  grade_band_name: null,
  student_count: 1,
  course_count: 1,
  is_class_teacher: false,
};

const mathAssignment = {
  assignment_id: 'asgn-1',
  subject: { name: 'Mathematics', code: 'MATH101', department: 'STEM' },
  sections: [sectionA],
};

const englishAssignment = {
  assignment_id: 'asgn-2',
  subject: { name: 'English', code: 'ENG101', department: null },
  sections: [sectionB],
};

const mockResponse = {
  assignments: [mathAssignment, englishAssignment],
  total_sections: 2,
  academic_year: '2025-2026',
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('MyClassesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // ── Page header ─────────────────────────────────────────────────────────────

  it('renders "My Classes" heading', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /my classes/i }),
    ).toBeInTheDocument();
  });

  it('shows academic year badge when present', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('2025-2026')).toBeInTheDocument();
  });

  it('does not show academic year badge when absent', async () => {
    mockGetMyClasses.mockResolvedValue({ ...mockResponse, academic_year: '' });
    renderPage();
    await screen.findByRole('heading', { level: 1, name: /my classes/i });
    expect(screen.queryByText('2025-2026')).not.toBeInTheDocument();
  });

  // ── Loading ─────────────────────────────────────────────────────────────────

  it('shows animate-pulse skeleton while loading', () => {
    mockGetMyClasses.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  // ── Error ───────────────────────────────────────────────────────────────────

  it('shows error message when query fails', async () => {
    mockGetMyClasses.mockRejectedValue(new Error('Network error'));
    renderPage();
    expect(
      await screen.findByText('Failed to load your classes. Please try again.'),
    ).toBeInTheDocument();
  });

  // ── Empty state ─────────────────────────────────────────────────────────────

  it('shows "No teaching assignments" heading when no data', async () => {
    mockGetMyClasses.mockResolvedValue({
      assignments: [],
      total_sections: 0,
      academic_year: '',
    });
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 3, name: /no teaching assignments/i }),
    ).toBeInTheDocument();
  });

  it('shows empty state description text', async () => {
    mockGetMyClasses.mockResolvedValue({
      assignments: [],
      total_sections: 0,
      academic_year: '',
    });
    renderPage();
    expect(
      await screen.findByText(/contact your admin to set up teaching assignments/i),
    ).toBeInTheDocument();
  });

  it('does not show stats cards when assignments are empty', async () => {
    mockGetMyClasses.mockResolvedValue({
      assignments: [],
      total_sections: 0,
      academic_year: '',
    });
    renderPage();
    await screen.findByRole('heading', { level: 3, name: /no teaching assignments/i });
    expect(screen.queryByText(/total sections?/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^subjects?$/i)).not.toBeInTheDocument();
  });

  // ── Subject groups ──────────────────────────────────────────────────────────

  it('renders subject group heading', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 2, name: /mathematics/i }),
    ).toBeInTheDocument();
  });

  it('renders subject code badge', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('MATH101')).toBeInTheDocument();
  });

  it('renders department badge when department is set', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('STEM')).toBeInTheDocument();
  });

  it('renders multiple subject groups', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 2, name: /mathematics/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 2, name: /english/i }),
    ).toBeInTheDocument();
  });

  // ── Section card ────────────────────────────────────────────────────────────

  it('renders grade and section name on card', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    // "Grade 5 · Section A" rendered in section card
    expect(await screen.findByText(/grade 5/i)).toBeInTheDocument();
  });

  it('shows grade_band_name when present', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('Primary School')).toBeInTheDocument();
  });

  it('shows student count (plural)', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('28 students')).toBeInTheDocument();
  });

  it('shows student count (singular)', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('1 student')).toBeInTheDocument();
  });

  it('shows course count (plural)', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('3 courses')).toBeInTheDocument();
  });

  it('shows course count (singular)', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('1 course')).toBeInTheDocument();
  });

  it('shows "Class Teacher" badge for is_class_teacher section', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('Class Teacher')).toBeInTheDocument();
  });

  it('does not show "Class Teacher" badge when is_class_teacher is false', async () => {
    mockGetMyClasses.mockResolvedValue({
      ...mockResponse,
      assignments: [
        {
          ...mathAssignment,
          sections: [{ ...sectionA, is_class_teacher: false }],
        },
      ],
    });
    renderPage();
    await screen.findByRole('heading', { level: 2, name: /mathematics/i });
    expect(screen.queryByText('Class Teacher')).not.toBeInTheDocument();
  });

  // ── Navigation ──────────────────────────────────────────────────────────────

  it('navigates to section dashboard when card is clicked', async () => {
    const user = userEvent.setup();
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    // SectionCard is a <button> whose accessible name includes the grade text
    const card = await screen.findByRole('button', { name: /grade 5.*section a/i });
    await user.click(card);
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/my-classes/section/sec-1');
  });

  it('navigates to correct section for second section card', async () => {
    const user = userEvent.setup();
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    const card = await screen.findByRole('button', { name: /grade 6.*section b/i });
    await user.click(card);
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/my-classes/section/sec-2');
  });

  // ── Stats ───────────────────────────────────────────────────────────────────

  it('shows Total Sections stat label (plural)', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('Total Sections')).toBeInTheDocument();
  });

  it('shows singular "Total Section" when count is 1', async () => {
    mockGetMyClasses.mockResolvedValue({
      ...mockResponse,
      assignments: [mathAssignment],
      total_sections: 1,
    });
    renderPage();
    expect(await screen.findByText('Total Section')).toBeInTheDocument();
  });

  it('shows Subjects stat label (plural)', async () => {
    mockGetMyClasses.mockResolvedValue(mockResponse);
    renderPage();
    expect(await screen.findByText('Subjects')).toBeInTheDocument();
  });

  it('shows singular "Subject" label when there is 1 assignment', async () => {
    mockGetMyClasses.mockResolvedValue({
      ...mockResponse,
      assignments: [mathAssignment],
      total_sections: 1,
    });
    renderPage();
    expect(await screen.findByText('Subject')).toBeInTheDocument();
  });
});
