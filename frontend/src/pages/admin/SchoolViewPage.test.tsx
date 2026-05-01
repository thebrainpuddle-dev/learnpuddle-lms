// src/pages/admin/SchoolViewPage.test.tsx
//
// FE-048: Tests for the Admin SchoolViewPage — Level 1 School Overview.
//
// Coverage strategy:
//   1. Loading state  — animate-pulse skeleton visible while query is pending
//   2. Page header    — school name in h1, academic year badge, settings button
//   3. Grade bands    — band headings rendered, grade count in sub-label
//   4. Grade cards    — individual grade cards rendered with correct data
//   5. Navigation     — grade card click, settings button click, empty-state CTA
//   6. Empty state    — shown when grade_bands is empty (no bands configured)
//   7. Error state    — shown when getSchoolOverview rejects; retry triggers refetch
//   8. Section count  — section count shown on grade card
//
// Mock strategy:
//   • academicsService.getSchoolOverview — vi.fn() (controls loading/success/error)
//   • usePageTitle — no-op stub
//   • react-router-dom useNavigate — captured mockNavigate
//
// Notes on the actual source vs the task spec:
//   • Empty-state button text is "Configure Academic Structure" (not "Set Up School Structure")
//   • Empty-state h3 text is "No academic structure configured"
//   • Error-state h3 text is "Failed to load school data"
//   • Academic year appears as a pill badge (not "Academic Year: <year>")
//   • There are NO summary stats (total grades/sections/students) in the real component
//   • Each GradeBandSection shows "<N> grades" in the sub-label row alongside curriculum and student totals

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { SchoolViewPage } from './SchoolViewPage';
import {
  academicsService,
  type SchoolOverviewResponse,
  type Grade,
} from '../../services/academicsService';

// ── Module mocks ───────────────────────────────────────────────────────────────

vi.mock('../../services/academicsService', () => ({
  academicsService: { getSchoolOverview: vi.fn() },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

// ── Typed mock refs ────────────────────────────────────────────────────────────

const mockedGetSchoolOverview = vi.mocked(academicsService.getSchoolOverview);

// ── Fixtures ───────────────────────────────────────────────────────────────────

const BASE_GRADE_FIELDS = {
  grade_band: 'band-primary',
  grade_band_name: 'Primary Band',
  grade_band_short_code: 'PRI',
  short_code: 'G5',
  order: 1,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
};

const GRADE_5: Grade = {
  ...BASE_GRADE_FIELDS,
  id: 'grade-5',
  name: 'Grade 5',
  student_count: 58,
  section_count: 2,
};

const GRADE_6: Grade = {
  ...BASE_GRADE_FIELDS,
  id: 'grade-6',
  name: 'Grade 6',
  short_code: 'G6',
  student_count: 45,
  section_count: 2,
};

const GRADE_7: Grade = {
  ...BASE_GRADE_FIELDS,
  id: 'grade-7',
  name: 'Grade 7',
  grade_band: 'band-middle',
  grade_band_name: 'Middle School Band',
  grade_band_short_code: 'MID',
  short_code: 'G7',
  order: 1,
  student_count: 30,
  section_count: 1,
};

const BASE_BAND_FIELDS = {
  short_code: 'PRI',
  order: 1,
  curriculum_framework: 'NATIONAL',
  grade_count: 2,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  theme_config: { accent_color: '#6366f1' },
};

const OVERVIEW: SchoolOverviewResponse = {
  school_name: 'Demo School',
  academic_year: '2025-2026',
  grade_bands: [
    {
      ...BASE_BAND_FIELDS,
      id: 'band-primary',
      name: 'Primary Band',
      grades: [GRADE_5, GRADE_6],
    },
    {
      ...BASE_BAND_FIELDS,
      id: 'band-middle',
      name: 'Middle School Band',
      short_code: 'MID',
      grade_count: 1,
      grades: [GRADE_7],
    },
  ],
};

// ── Render helper ──────────────────────────────────────────────────────────────

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SchoolViewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Global setup ───────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.resetAllMocks();
  mockNavigate.mockReset();
  mockedGetSchoolOverview.mockResolvedValue(OVERVIEW);
});

// ── Tests ──────────────────────────────────────────────────────────────────────

describe('SchoolViewPage', () => {
  // ── 1. Loading state ───────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows animate-pulse skeleton elements while the query is pending', () => {
      // Return a promise that never resolves so the page stays in loading state
      mockedGetSchoolOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      const skeletonEls = document.querySelectorAll('.animate-pulse');
      expect(skeletonEls.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 2. Page header ─────────────────────────────────────────────────────────

  describe('page header', () => {
    it('renders school name in the h1', async () => {
      renderPage();
      const heading = await screen.findByRole('heading', { level: 1, name: 'Demo School' });
      expect(heading).toBeInTheDocument();
    });

    it('renders the academic year badge', async () => {
      renderPage();
      // Academic year displayed as a pill badge (not a labelled sentence)
      expect(await screen.findByText('2025-2026')).toBeInTheDocument();
    });

    it('renders the settings button with correct aria-label', async () => {
      renderPage();
      await screen.findByRole('heading', { level: 1 });
      expect(
        screen.getByRole('button', { name: /school settings/i }),
      ).toBeInTheDocument();
    });
  });

  // ── 3. Grade bands ─────────────────────────────────────────────────────────

  describe('grade bands', () => {
    it('shows "Primary Band" heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { level: 2, name: 'Primary Band' })).toBeInTheDocument();
    });

    it('shows "Middle School Band" heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { level: 2, name: 'Middle School Band' })).toBeInTheDocument();
    });

    it('shows "2 grades" sub-label for Primary Band', async () => {
      renderPage();
      await screen.findByRole('heading', { level: 2, name: 'Primary Band' });
      // The GradeBandSection renders "{n} grades" in the sub-label row
      const gradeLabelEls = screen.getAllByText(/2 grades/i);
      expect(gradeLabelEls.length).toBeGreaterThanOrEqual(1);
    });

    it('shows "1 grade" sub-label for Middle School Band', async () => {
      renderPage();
      await screen.findByRole('heading', { level: 2, name: 'Middle School Band' });
      const gradeLabelEls = screen.getAllByText(/1 grade/i);
      expect(gradeLabelEls.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 4. Grade cards ─────────────────────────────────────────────────────────

  describe('grade cards', () => {
    it('renders Grade 5 card', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /grade 5/i })).toBeInTheDocument();
    });

    it('renders Grade 6 card', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /grade 6/i })).toBeInTheDocument();
    });

    it('renders Grade 7 card', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /grade 7/i })).toBeInTheDocument();
    });

    it('Grade 5 card shows "58 students"', async () => {
      renderPage();
      await screen.findByRole('button', { name: /grade 5/i });
      expect(screen.getByText('58 students')).toBeInTheDocument();
    });

    it('Grade 5 card shows "2 sections"', async () => {
      renderPage();
      await screen.findByRole('button', { name: /grade 5/i });
      // section count appears multiple times (once per band sub-label + once in card)
      const sectionEls = screen.getAllByText(/2 sections/i);
      expect(sectionEls.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 5. Navigation ──────────────────────────────────────────────────────────

  describe('navigation', () => {
    it('clicking Grade 5 card navigates to /admin/school/grade/grade-5', async () => {
      const user = userEvent.setup();
      renderPage();
      const grade5Btn = await screen.findByRole('button', { name: /grade 5/i });
      await user.click(grade5Btn);
      expect(mockNavigate).toHaveBeenCalledWith('/admin/school/grade/grade-5');
    });

    it('clicking the settings button navigates to /admin/settings', async () => {
      const user = userEvent.setup();
      renderPage();
      await screen.findByRole('heading', { level: 1 });
      const settingsBtn = screen.getByRole('button', { name: /school settings/i });
      await user.click(settingsBtn);
      expect(mockNavigate).toHaveBeenCalledWith('/admin/settings');
    });

    it('clicking the empty-state CTA navigates to /admin/settings', async () => {
      const user = userEvent.setup();
      mockedGetSchoolOverview.mockResolvedValue({
        school_name: 'Demo School',
        academic_year: '2025-2026',
        grade_bands: [],
      });
      renderPage();
      const ctaBtn = await screen.findByRole('button', { name: /configure academic structure/i });
      await user.click(ctaBtn);
      expect(mockNavigate).toHaveBeenCalledWith('/admin/settings');
    });
  });

  // ── 6. Empty state ─────────────────────────────────────────────────────────

  describe('empty state', () => {
    it('shows empty state when grade_bands is an empty array', async () => {
      mockedGetSchoolOverview.mockResolvedValue({
        school_name: 'Demo School',
        academic_year: '2025-2026',
        grade_bands: [],
      });
      renderPage();
      expect(
        await screen.findByText('No academic structure configured'),
      ).toBeInTheDocument();
    });

    it('renders "Configure Academic Structure" CTA button in the empty state', async () => {
      mockedGetSchoolOverview.mockResolvedValue({
        school_name: 'Demo School',
        academic_year: '2025-2026',
        grade_bands: [],
      });
      renderPage();
      expect(
        await screen.findByRole('button', { name: /configure academic structure/i }),
      ).toBeInTheDocument();
    });
  });

  // ── 7. Error state ─────────────────────────────────────────────────────────

  describe('error state', () => {
    it('shows error state when getSchoolOverview rejects', async () => {
      mockedGetSchoolOverview.mockRejectedValue(new Error('Network Error'));
      renderPage();
      expect(
        await screen.findByText('Failed to load school data'),
      ).toBeInTheDocument();
    });

    it('renders a "Try Again" retry button in the error state', async () => {
      mockedGetSchoolOverview.mockRejectedValue(new Error('Network Error'));
      renderPage();
      await screen.findByText('Failed to load school data');
      expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
    });

    it('clicking "Try Again" triggers a refetch call to getSchoolOverview', async () => {
      const user = userEvent.setup();
      // First call rejects, second resolves so the component can re-render
      mockedGetSchoolOverview
        .mockRejectedValueOnce(new Error('Network Error'))
        .mockResolvedValueOnce(OVERVIEW);
      renderPage();
      const retryBtn = await screen.findByRole('button', { name: /try again/i });
      await user.click(retryBtn);
      await waitFor(() =>
        expect(mockedGetSchoolOverview).toHaveBeenCalledTimes(2),
      );
    });
  });
});
