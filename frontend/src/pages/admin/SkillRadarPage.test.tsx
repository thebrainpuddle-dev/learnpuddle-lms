// src/pages/admin/SkillRadarPage.test.tsx
//
// Tests for the Admin Skill Radar page.
// Covers: loading, empty state, summary stats, radar rendering,
// top gap list, table breakdown, category filter, and error handling.

import React from 'react';
import {
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { SkillRadarPage } from './SkillRadarPage';
import { skillsService } from '../../services/skillsService';
import { ToastProvider } from '../../components/common';

// ── Mocks ────────────────────────────────────────────────────────────────

vi.mock('../../services/skillsService', () => ({
  skillsService: {
    overview: vi.fn(),
    categories: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

// jsdom has no SVG layout — stub Recharts.
vi.mock('recharts', () => ({
  RadarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="radar-chart">{children}</div>
  ),
  PolarGrid: () => null,
  PolarAngleAxis: () => null,
  PolarRadiusAxis: () => null,
  Radar: ({ name }: { name: string }) => (
    <div data-testid={`radar-series-${name}`}>{name}</div>
  ),
  Legend: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

// ── Fixtures ─────────────────────────────────────────────────────────────

const mockedOverview = vi.mocked(skillsService.overview);
const mockedCategories = vi.mocked(skillsService.categories);

const FIXTURE = {
  results: [
    {
      skill_id: 'sk-1',
      skill_name: 'Differentiated Instruction',
      skill_category: 'Pedagogy',
      level_required: 4,
      teachers_assessed: 10,
      at_or_above_target: 3,
      below_target: 7,
      avg_current_level: 2.4,
      avg_target_level: 4.0,
      teacher_details: [],
    },
    {
      skill_id: 'sk-2',
      skill_name: 'Formative Assessment',
      skill_category: 'Pedagogy',
      level_required: 3,
      teachers_assessed: 10,
      at_or_above_target: 10,
      below_target: 0,
      avg_current_level: 3.2,
      avg_target_level: 3.0,
      teacher_details: [],
    },
    {
      skill_id: 'sk-3',
      skill_name: 'Classroom Tech',
      skill_category: 'Technology',
      level_required: 3,
      teachers_assessed: 10,
      at_or_above_target: 5,
      below_target: 5,
      avg_current_level: 2.7,
      avg_target_level: 3.5,
      teacher_details: [],
    },
  ],
  summary: {
    total_skills_tracked: 3,
    total_teacher_skill_gaps: 14,
    total_teachers: 10,
  },
};

// ── Harness ──────────────────────────────────────────────────────────────

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ToastProvider>
          <SkillRadarPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('SkillRadarPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedCategories.mockResolvedValue({
      data: ['Pedagogy', 'Technology'],
    } as unknown as Awaited<ReturnType<typeof skillsService.categories>>);
  });

  it('renders summary stats, radar chart, and table when data loads', async () => {
    mockedOverview.mockResolvedValue(FIXTURE);

    renderPage();

    // Wait for data to resolve
    await waitFor(() =>
      expect(screen.getByTestId('stat-skills-tracked')).toHaveTextContent('3'),
    );
    expect(screen.getByTestId('stat-teachers')).toHaveTextContent('10');
    expect(screen.getByTestId('stat-gaps')).toHaveTextContent('14');

    // Radar chart wrapper + both series mounted
    expect(screen.getByTestId('radar-chart')).toBeInTheDocument();
    expect(screen.getByTestId('radar-series-Avg current')).toBeInTheDocument();
    expect(screen.getByTestId('radar-series-Avg target')).toBeInTheDocument();

    // Table has all 3 skills
    const table = screen.getByTestId('skill-table');
    expect(
      within(table).getByText('Differentiated Instruction'),
    ).toBeInTheDocument();
    expect(within(table).getByText('Formative Assessment')).toBeInTheDocument();
    expect(within(table).getByText('Classroom Tech')).toBeInTheDocument();
  });

  it('lists the biggest gap skill first in Focus areas', async () => {
    mockedOverview.mockResolvedValue(FIXTURE);

    renderPage();

    const focusList = await screen.findByTestId('focus-list');
    const items = within(focusList).getAllByRole('listitem');
    // Biggest gap is Differentiated Instruction (target 4.0 − current 2.4 = 1.6)
    expect(items[0]).toHaveTextContent('Differentiated Instruction');
    // Next biggest is Classroom Tech (3.5 − 2.7 = 0.8)
    expect(items[1]).toHaveTextContent('Classroom Tech');
    // Formative Assessment is at/above target — should be filtered out
    expect(within(focusList).queryByText('Formative Assessment')).toBeNull();
  });

  it('shows empty radar + empty table message when no skills are tracked', async () => {
    mockedOverview.mockResolvedValue({
      results: [],
      summary: {
        total_skills_tracked: 0,
        total_teacher_skill_gaps: 0,
        total_teachers: 0,
      },
    });

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('radar-empty')).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/No skills have been mapped for your team yet/i),
    ).toBeInTheDocument();
    // Focus-areas card shows its own empty copy
    expect(
      screen.getByText(/No skill gaps right now/i),
    ).toBeInTheDocument();
  });

  it('refetches with category param when filter changes', async () => {
    const user = userEvent.setup();
    mockedOverview.mockResolvedValue(FIXTURE);

    renderPage();

    await waitFor(() =>
      expect(mockedOverview).toHaveBeenCalledWith(undefined),
    );

    // Wait for the filter options to populate
    await screen.findByRole('option', { name: 'Pedagogy' });

    const select = screen.getByLabelText(/Category/i);
    await user.selectOptions(select, 'Pedagogy');

    await waitFor(() =>
      expect(mockedOverview).toHaveBeenCalledWith({ category: 'Pedagogy' }),
    );
  });

  it('renders a recoverable error state when the API fails', async () => {
    mockedOverview.mockRejectedValue(new Error('boom'));

    renderPage();

    await waitFor(() =>
      expect(
        screen.getByText(/Could not load skills overview/i),
      ).toBeInTheDocument(),
    );
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
  });
});
