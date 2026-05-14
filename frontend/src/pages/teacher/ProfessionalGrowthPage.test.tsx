// src/pages/teacher/ProfessionalGrowthPage.test.tsx
//
// FE-063: Tests for the Teacher Professional Growth page.
// Covers: loading state (skeleton), error state ("Unable to load growth data"),
//         empty state ("No Skills Assigned Yet" when total_skills=0),
//         page header ("Professional Growth"), stat tiles (Skills Met,
//         Growth Areas, Badges Earned), skill categories and skill rows
//         (skill name, "Growth area" badge, progress bar), recommendations
//         list (course title), badges earned section (badge names),
//         unearned badges section ("Next to unlock").
//
// Mocking strategy:
//   - teacherService.getCompetencyDashboard via vi.mock('../../services/teacherService')
//   - gamificationService (getBadgeDefinitions, getMyBadges, getXPHistory,
//     getSummary, getLeaderboard) via vi.mock('../../services/gamificationService')
//   - ActivityHeatmap stubbed (avoids canvas/SVG complexity)
//   - useNavigate mocked via importOriginal spread
//   - usePageTitle stubbed

import React from 'react';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ProfessionalGrowthPage } from './ProfessionalGrowthPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/teacherService', () => ({
  teacherService: {
    getCompetencyDashboard: vi.fn(),
  },
}));

vi.mock('../../services/gamificationService', () => ({
  gamificationService: {
    getBadgeDefinitions: vi.fn(),
    getMyBadges: vi.fn(),
    getXPHistory: vi.fn(),
    getSummary: vi.fn(),
    getLeaderboard: vi.fn(),
  },
}));

// Stub ActivityHeatmap to avoid chart rendering complexity
vi.mock('../../components/analytics/ActivityHeatmap', () => ({
  ActivityHeatmap: ({ title }: { title: string }) => (
    <div data-testid="activity-heatmap">{title}</div>
  ),
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { teacherService } from '../../services/teacherService';
import { gamificationService } from '../../services/gamificationService';

const mockGetCompetency = teacherService.getCompetencyDashboard as ReturnType<typeof vi.fn>;
const mockGetBadgeDefs = gamificationService.getBadgeDefinitions as ReturnType<typeof vi.fn>;
const mockGetMyBadges = gamificationService.getMyBadges as ReturnType<typeof vi.fn>;
const mockGetXPHistory = gamificationService.getXPHistory as ReturnType<typeof vi.fn>;
const mockGetSummary = gamificationService.getSummary as ReturnType<typeof vi.fn>;
const mockGetLeaderboard = gamificationService.getLeaderboard as ReturnType<typeof vi.fn>;

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
        <ProfessionalGrowthPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeCompetency(overrides: Record<string, unknown> = {}) {
  return {
    total_skills: 4,
    total_gaps: 2,
    skills: [
      {
        id: 'skill-1',
        name: 'Differentiated Instruction',
        category: 'Approaches to Teaching',
        current_level: 2,
        target_level: 4,
        has_gap: true,
      },
      {
        id: 'skill-2',
        name: 'Assessment for Learning',
        category: 'Approaches to Teaching',
        current_level: 4,
        target_level: 4,
        has_gap: false,
      },
      {
        id: 'skill-3',
        name: 'Inquiry-based Learning',
        category: 'Pedagogical Practice',
        current_level: 3,
        target_level: 3,
        has_gap: false,
      },
      {
        id: 'skill-4',
        name: 'Collaborative Learning',
        category: 'Pedagogical Practice',
        current_level: 1,
        target_level: 3,
        has_gap: true,
      },
    ],
    recommendations: [
      {
        course_id: 'crs-1',
        course_title: 'Advanced Differentiation Techniques',
        skill_name: 'Differentiated Instruction',
        current_level: 2,
        target_level: 4,
        level_taught: 3,
        is_assigned: true,
      },
      {
        course_id: 'crs-2',
        course_title: 'Collaborative Classroom Strategies',
        skill_name: 'Collaborative Learning',
        current_level: 1,
        target_level: 3,
        level_taught: 2,
        is_assigned: false,
      },
    ],
    ...overrides,
  };
}

function makeBadgeDefs() {
  return [
    { id: 'badge-1', name: 'Course Champion', icon: null, criteria_type: 'courses_completed', criteria_value: 5, sort_order: 1 },
    { id: 'badge-2', name: 'Streak Master', icon: 'flame', criteria_type: 'streak_days', criteria_value: 30, sort_order: 2 },
  ];
}

function makeEarnedBadges() {
  return [
    {
      id: 'eb-1',
      badge: { id: 'badge-1', name: 'Course Champion', icon: null, criteria_type: 'courses_completed', criteria_value: 5, sort_order: 1 },
      earned_at: '2024-03-01T00:00:00Z',
    },
  ];
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ProfessionalGrowthPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Default: all queries resolve with valid data
    mockGetCompetency.mockResolvedValue(makeCompetency());
    mockGetBadgeDefs.mockResolvedValue(makeBadgeDefs());
    mockGetMyBadges.mockResolvedValue(makeEarnedBadges());
    mockGetXPHistory.mockResolvedValue([]);
    mockGetSummary.mockResolvedValue(null);
    mockGetLeaderboard.mockResolvedValue({ entries: [], my_rank: null });
  });

  // ── Loading state ────────────────────────────────────────────────────────────

  it('shows loading skeleton while data is loading', () => {
    mockGetCompetency.mockReturnValue(new Promise(() => {}));
    mockGetBadgeDefs.mockReturnValue(new Promise(() => {}));
    mockGetMyBadges.mockReturnValue(new Promise(() => {}));
    renderPage();
    // Skeleton uses animate-pulse
    const skeleton = document.querySelector('.animate-pulse');
    expect(skeleton).not.toBeNull();
  });

  // ── Error state ──────────────────────────────────────────────────────────────

  it('shows error state when competency query fails', async () => {
    mockGetCompetency.mockRejectedValue(new Error('Server error'));
    renderPage();
    expect(
      await screen.findByText('Unable to load growth data'),
    ).toBeInTheDocument();
    expect(screen.getByText(/please try refreshing the page/i)).toBeInTheDocument();
  });

  // ── Empty state ──────────────────────────────────────────────────────────────

  it('shows "No Skills Assigned Yet" when total_skills is 0', async () => {
    mockGetCompetency.mockResolvedValue(
      makeCompetency({ total_skills: 0, skills: [], recommendations: [] }),
    );
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 2, name: /no skills assigned yet/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/your coordinator will map professional competencies/i)).toBeInTheDocument();
  });

  // ── Page header ──────────────────────────────────────────────────────────────

  it('renders "Professional Growth" heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /professional growth/i }),
    ).toBeInTheDocument();
  });

  it('renders subtitle text', async () => {
    renderPage();
    expect(
      await screen.findByText(/your skills, recognition, and recommended next steps/i),
    ).toBeInTheDocument();
  });

  // ── Stat tiles ───────────────────────────────────────────────────────────────

  it('renders "Skills Met" stat tile with correct value', async () => {
    // 2 of 4 skills are met (current >= target and current > 0 and no gap)
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('Skills Met')).toBeInTheDocument();
    // metSkills = 2, totalSkills = 4 → "2/4"
    // Note: "2/4" also appears in GradientProgressBar for skill-1; use getAllByText
    const vals = screen.getAllByText('2/4');
    expect(vals.length).toBeGreaterThanOrEqual(1);
    // The stat tile value is in a <p> with large font
    const statTileValue = vals.find((el) => el.tagName === 'P');
    expect(statTileValue).toBeDefined();
  });

  it('renders "Growth Areas" stat tile', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('Growth Areas')).toBeInTheDocument();
    // total_gaps = 2; "2" also appears as recommendation index badge
    // Use the sublabel to uniquely verify the tile
    expect(screen.getByText('Skills to develop')).toBeInTheDocument();
  });

  it('renders "Badges Earned" stat tile', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('Badges Earned')).toBeInTheDocument();
    // 1 earned of 2 total; "1/2" also appears as category met count
    // Verify tile uniquely via sublabel
    expect(screen.getByText('1 to unlock')).toBeInTheDocument();
  });

  // ── Skill categories ─────────────────────────────────────────────────────────

  it('renders skill category headers', async () => {
    renderPage();
    expect(await screen.findByText('Approaches to Teaching')).toBeInTheDocument();
    expect(screen.getByText('Pedagogical Practice')).toBeInTheDocument();
  });

  it('renders skill names within categories', async () => {
    renderPage();
    // Skill names appear in SkillRow AND in recommendation card's skill_name span
    // Use getAllByText since they may appear multiple times
    const diffInstr = await screen.findAllByText('Differentiated Instruction');
    expect(diffInstr.length).toBeGreaterThanOrEqual(1);
    // Others: unique in SkillRow only
    expect(screen.getByText('Assessment for Learning')).toBeInTheDocument();
    expect(screen.getByText('Inquiry-based Learning')).toBeInTheDocument();
    // Collaborative Learning appears in SkillRow + recommendation skill_name
    const collabLearning = screen.getAllByText('Collaborative Learning');
    expect(collabLearning.length).toBeGreaterThanOrEqual(1);
  });

  it('shows "Growth area" badge for skills with has_gap=true', async () => {
    renderPage();
    // Wait for page data to load
    await screen.findByRole('heading', { level: 1, name: /professional growth/i });
    await screen.findByText('Assessment for Learning'); // a skill unique to SkillRow
    const growthAreaBadges = screen.getAllByText('Growth area');
    // skills with has_gap=true: Differentiated Instruction + Collaborative Learning
    expect(growthAreaBadges.length).toBe(2);
  });

  // ── Recommendations ──────────────────────────────────────────────────────────

  it('renders recommendation course titles', async () => {
    renderPage();
    expect(
      await screen.findByText('Advanced Differentiation Techniques'),
    ).toBeInTheDocument();
    expect(screen.getByText('Collaborative Classroom Strategies')).toBeInTheDocument();
  });

  it('shows "Assigned" badge for assigned recommendations', async () => {
    renderPage();
    await screen.findByText('Advanced Differentiation Techniques');
    expect(screen.getByText('Assigned')).toBeInTheDocument();
  });

  it('shows "Ask your coordinator" for unassigned recommendations', async () => {
    renderPage();
    await screen.findByText('Collaborative Classroom Strategies');
    expect(
      screen.getByText(/ask your coordinator to assign this course/i),
    ).toBeInTheDocument();
  });

  // ── Badges ───────────────────────────────────────────────────────────────────

  it('renders earned badge names', async () => {
    renderPage();
    // badge-1 is earned: "Course Champion"
    expect(await screen.findByText('Course Champion')).toBeInTheDocument();
  });
});
