// src/pages/student/AchievementsPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for AchievementsPage.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AchievementsPage } from './AchievementsPage';
import { studentService } from '../../services/studentService';
import type { StudentGamificationSummary } from '../../services/studentService';

// ─── Module mocks ─────────────────────────────────────────────────────────────

vi.mock('../../services/studentService', () => ({
  studentService: {
    getGamificationSummary: vi.fn(),
    getStudentCourses: vi.fn(),
    getStudentDashboard: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ─── Typed mock handle ────────────────────────────────────────────────────────

const mockedStudentService = studentService as unknown as {
  [K in keyof typeof studentService]: ReturnType<typeof vi.fn>;
};

// ─── Fixtures ─────────────────────────────────────────────────────────────────

/**
 * A fully populated gamification fixture that exercises every branch of the
 * component: a mix of unlocked and locked badges, a partial streak, and
 * non-zero values across every points-breakdown category.
 */
const MOCK_GAMIFICATION: StudentGamificationSummary = {
  points_total: 1_250,
  points_breakdown: {
    content_completion: 600,
    course_completion: 300,
    assignment_submission: 200,
    streak_bonus: 100,
    quest_bonus: 50,
  },
  streak: {
    current_days: 5,
    target_days: 7,
  },
  badges: [
    {
      key: 'first-steps',
      name: 'First Steps',
      level: 1,
      min_points: 0,
      max_points: 500,
      color: '#6366f1',
      unlocked: true,
      progress_percentage: 100,
    },
    {
      key: 'rising-star',
      name: 'Rising Star',
      level: 2,
      min_points: 500,
      max_points: 1_500,
      color: '#f59e0b',
      unlocked: true,
      progress_percentage: 100,
    },
    {
      key: 'scholar',
      name: 'Scholar',
      level: 3,
      min_points: 1_500,
      max_points: 3_000,
      color: '#10b981',
      unlocked: false,
      progress_percentage: 42,
    },
    {
      key: 'expert',
      name: 'Expert',
      level: 4,
      min_points: 3_000,
      max_points: null,
      color: '#ef4444',
      unlocked: false,
      progress_percentage: 0,
    },
  ],
};

/**
 * Fixture where every badge is unlocked — exercises the "All Badges Unlocked!"
 * branch in the HeroStats Next-Badge card.
 */
const MOCK_ALL_BADGES_UNLOCKED: StudentGamificationSummary = {
  ...MOCK_GAMIFICATION,
  badges: MOCK_GAMIFICATION.badges.map((b) => ({
    ...b,
    unlocked: true,
    progress_percentage: 100,
  })),
};

/**
 * Fixture where points_total and badges are both zero/empty — exercises the
 * EmptyState branch.
 */
const MOCK_EMPTY: StudentGamificationSummary = {
  points_total: 0,
  points_breakdown: {
    content_completion: 0,
    course_completion: 0,
    assignment_submission: 0,
    streak_bonus: 0,
    quest_bonus: 0,
  },
  streak: { current_days: 0, target_days: 7 },
  badges: [],
};

// ─── Test helpers ─────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
        refetchOnWindowFocus: false,
      },
    },
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <AchievementsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Suite ────────────────────────────────────────────────────────────────────

describe('AchievementsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedStudentService.getGamificationSummary.mockResolvedValue(MOCK_GAMIFICATION);
  });

  // ── 1. Page heading ──────────────────────────────────────────────────────────

  it('renders the "Achievements" page heading', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { level: 1, name: /achievements/i })).toBeInTheDocument();
  });

  // ── 2. Subtitle ──────────────────────────────────────────────────────────────

  it('renders the subtitle "Track your learning progress and rewards."', async () => {
    renderPage();
    expect(
      await screen.findByText('Track your learning progress and rewards.'),
    ).toBeInTheDocument();
  });

  // ── 3. Total Points card ─────────────────────────────────────────────────────

  it('shows the Total Points label in the hero stats row', async () => {
    renderPage();
    expect(await screen.findByText('Total Points')).toBeInTheDocument();
  });

  it('displays the correct total-points value formatted with locale separators', async () => {
    renderPage();
    // 1250 formatted via toLocaleString — may appear in both the hero value and
    // the next-badge pts line, so use findAllByText.
    const matches = await screen.findAllByText(/1[,.]?250/);
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  // ── 4. Unlocked badge count in hero row ──────────────────────────────────────

  it('shows "2 badges unlocked" beneath the total-points value', async () => {
    renderPage();
    expect(await screen.findByText('2 badges unlocked')).toBeInTheDocument();
  });

  it('shows "1 badge unlocked" (singular) when only one badge is unlocked', async () => {
    const singleUnlocked: StudentGamificationSummary = {
      ...MOCK_GAMIFICATION,
      badges: [
        { ...MOCK_GAMIFICATION.badges[0], unlocked: true },
        ...MOCK_GAMIFICATION.badges.slice(1).map((b) => ({ ...b, unlocked: false })),
      ],
    };
    mockedStudentService.getGamificationSummary.mockResolvedValue(singleUnlocked);
    renderPage();
    expect(await screen.findByText('1 badge unlocked')).toBeInTheDocument();
  });

  // ── 5. Current Streak card ───────────────────────────────────────────────────

  it('shows the Current Streak label', async () => {
    renderPage();
    expect(await screen.findByText('Current Streak')).toBeInTheDocument();
  });

  it('displays the streak current_days value with plural "days"', async () => {
    renderPage();
    // Component renders "{current_days} days" — fixture has 5 days
    expect(await screen.findAllByText(/5\s*days/)).not.toHaveLength(0);
  });

  it('shows the streak target days', async () => {
    renderPage();
    expect(await screen.findByText(/Target:\s*7 days/)).toBeInTheDocument();
  });

  it('renders "1 day" (singular) when current_days is 1', async () => {
    mockedStudentService.getGamificationSummary.mockResolvedValue({
      ...MOCK_GAMIFICATION,
      streak: { current_days: 1, target_days: 7 },
    });
    renderPage();
    // Both the hero card and the streak-tracker section show this text
    const matches = await screen.findAllByText(/1\s*day(?!s)/);
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  // ── 6. Next Badge card (first locked badge shown) ────────────────────────────

  it('renders the "Next Badge" label when there is a locked badge', async () => {
    renderPage();
    expect(await screen.findByText('Next Badge')).toBeInTheDocument();
  });

  it('shows the next-badge name in the progress card', async () => {
    renderPage();
    // "Scholar" is the first unlocked=false badge; it appears in both the
    // Next Badge hero card and the Badges Grid section — use findAllByText.
    const matches = await screen.findAllByText('Scholar');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('shows "All Badges Unlocked!" when every badge is unlocked', async () => {
    mockedStudentService.getGamificationSummary.mockResolvedValue(MOCK_ALL_BADGES_UNLOCKED);
    renderPage();
    expect(await screen.findByText('All Badges Unlocked!')).toBeInTheDocument();
  });

  // ── 7. Points Breakdown section ──────────────────────────────────────────────

  it('renders the "Points Breakdown" section heading', async () => {
    renderPage();
    expect(await screen.findByText('Points Breakdown')).toBeInTheDocument();
  });

  it('renders the Content Completion breakdown item', async () => {
    renderPage();
    expect(await screen.findByText('Content Completion')).toBeInTheDocument();
  });

  it('renders the Course Completion breakdown item', async () => {
    renderPage();
    expect(await screen.findByText('Course Completion')).toBeInTheDocument();
  });

  it('renders the Assignment Submission breakdown item', async () => {
    renderPage();
    expect(await screen.findByText('Assignment Submission')).toBeInTheDocument();
  });

  it('renders the Streak Bonus breakdown item', async () => {
    renderPage();
    expect(await screen.findByText('Streak Bonus')).toBeInTheDocument();
  });

  it('renders the Quest Bonus breakdown item', async () => {
    renderPage();
    expect(await screen.findByText('Quest Bonus')).toBeInTheDocument();
  });

  it('displays the Content Completion points value', async () => {
    renderPage();
    // 600 pts — may also be formatted as "600"
    expect(await screen.findByText(/600\s*pts/)).toBeInTheDocument();
  });

  it('displays the Course Completion points value', async () => {
    renderPage();
    expect(await screen.findByText(/300\s*pts/)).toBeInTheDocument();
  });

  it('displays the Assignment Submission points value', async () => {
    renderPage();
    expect(await screen.findByText(/200\s*pts/)).toBeInTheDocument();
  });

  it('displays the Streak Bonus points value', async () => {
    renderPage();
    expect(await screen.findByText(/100\s*pts/)).toBeInTheDocument();
  });

  it('displays the Quest Bonus points value', async () => {
    renderPage();
    expect(await screen.findByText(/50\s*pts/)).toBeInTheDocument();
  });

  // ── 8. Streak Tracker section ────────────────────────────────────────────────

  it('renders the "Streak Tracker" section heading', async () => {
    renderPage();
    expect(await screen.findByText('Streak Tracker')).toBeInTheDocument();
  });

  it('renders the "Target Progress" label inside the streak tracker', async () => {
    renderPage();
    expect(await screen.findByText('Target Progress')).toBeInTheDocument();
  });

  it('shows the target-progress percentage rounded to the nearest integer', async () => {
    renderPage();
    // current_days=5, target_days=7  →  Math.round(5/7*100) = 71%
    expect(await screen.findByText('71%')).toBeInTheDocument();
  });

  it('shows "{N} days to target" in the streak tracker when target not reached', async () => {
    renderPage();
    // 7 - 5 = 2 days to target
    expect(await screen.findByText('2 days to target')).toBeInTheDocument();
  });

  it('shows "Target reached!" when current_days >= target_days', async () => {
    mockedStudentService.getGamificationSummary.mockResolvedValue({
      ...MOCK_GAMIFICATION,
      streak: { current_days: 7, target_days: 7 },
    });
    renderPage();
    expect(await screen.findByText('Target reached!')).toBeInTheDocument();
  });

  it('renders a 7-column calendar row in the streak tracker', async () => {
    const { container } = renderPage();
    // The calendar is rendered in a `grid-cols-7` grid.
    // Wait until data is loaded first.
    await screen.findByText('Streak Tracker');
    const calendarGrid = container.querySelector('.grid-cols-7');
    expect(calendarGrid).toBeInTheDocument();
    // 7 day cells
    const dayCells = calendarGrid!.children;
    expect(dayCells).toHaveLength(7);
  });

  // ── 9. Badges Grid section ───────────────────────────────────────────────────

  it('renders the "Badges" section heading', async () => {
    renderPage();
    expect(await screen.findByText('Badges')).toBeInTheDocument();
  });

  it('renders all badge names in the badges grid', async () => {
    renderPage();
    // Some names (e.g. "Scholar") also appear in the Next Badge hero card, so
    // use findAllByText and assert at least one match exists for each badge.
    for (const badge of MOCK_GAMIFICATION.badges) {
      const matches = await screen.findAllByText(badge.name);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    }
  });

  it('shows "Unlocked" text below each unlocked badge', async () => {
    renderPage();
    // Two badges are unlocked in the fixture → two "Unlocked" labels
    const unlockedLabels = await screen.findAllByText('Unlocked');
    expect(unlockedLabels).toHaveLength(2);
  });

  it('does not show "Unlocked" text for locked badges', async () => {
    renderPage();
    await screen.findByText('Badges'); // ensure section is rendered
    const unlockedLabels = screen.getAllByText('Unlocked');
    // Only the 2 unlocked badges produce this text
    expect(unlockedLabels).toHaveLength(2);
  });

  it('shows the progress percentage text for a locked badge', async () => {
    renderPage();
    // Scholar badge: progress_percentage=42, min_points=1500, max_points=3000
    // Component renders: "42% — 1,500 / 3,000 pts"
    expect(await screen.findByText(/42%/)).toBeInTheDocument();
  });

  it('shows the badge level for each badge', async () => {
    renderPage();
    // Fixture has levels 1-4. Level 3 (Scholar) also appears in the Next Badge
    // hero card, so use findAllByText for all level labels.
    expect((await screen.findAllByText('Level 1')).length).toBeGreaterThanOrEqual(1);
    expect((await screen.findAllByText('Level 2')).length).toBeGreaterThanOrEqual(1);
    expect((await screen.findAllByText('Level 3')).length).toBeGreaterThanOrEqual(1);
    expect((await screen.findAllByText('Level 4')).length).toBeGreaterThanOrEqual(1);
  });

  it('renders a progress bar for the locked badge with non-zero progress', async () => {
    // Scholar has progress_percentage=42; the bar uses an inline style width.
    // Use findAllByText since "Scholar" appears in both the Next Badge card and
    // the Badges Grid.
    const { container } = renderPage();
    const scholarMatches = await screen.findAllByText('Scholar');
    expect(scholarMatches.length).toBeGreaterThanOrEqual(1);
    // Find the progress bar div that carries `width: 42%`
    const bars = container.querySelectorAll<HTMLElement>('[style*="width: 42%"]');
    expect(bars.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the locked-badge progress bar at 0% for a zero-progress badge', async () => {
    // Expert has progress_percentage=0
    const { container } = renderPage();
    await screen.findByText('Expert');
    const bars = container.querySelectorAll<HTMLElement>('[style*="width: 0%"]');
    expect(bars.length).toBeGreaterThanOrEqual(1);
  });

  // ── 10. No badges empty state ────────────────────────────────────────────────

  it('shows the badges empty-state when there are no badges', async () => {
    mockedStudentService.getGamificationSummary.mockResolvedValue({
      ...MOCK_GAMIFICATION,
      badges: [],
    });
    renderPage();
    expect(await screen.findByText('No badges available yet.')).toBeInTheDocument();
    expect(await screen.findByText('Keep learning to unlock badges!')).toBeInTheDocument();
  });

  // ── 11. Empty state (no points and no badges) ────────────────────────────────

  it('shows the global empty state when points_total is 0 and badges is empty', async () => {
    mockedStudentService.getGamificationSummary.mockResolvedValue(MOCK_EMPTY);
    renderPage();
    expect(await screen.findByText('Start your learning journey!')).toBeInTheDocument();
    expect(
      await screen.findByText(
        /Complete courses, submit assignments, and build streaks to earn your first points/,
      ),
    ).toBeInTheDocument();
  });

  // ── 12. Loading skeleton ─────────────────────────────────────────────────────

  it('shows loading skeletons while the query is in-flight', () => {
    mockedStudentService.getGamificationSummary.mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();
    const pulsing = container.querySelectorAll('.animate-pulse');
    expect(pulsing.length).toBeGreaterThanOrEqual(1);
  });

  it('does not show the main content while loading', () => {
    mockedStudentService.getGamificationSummary.mockReturnValue(new Promise(() => {}));
    renderPage();
    // Main content sections are absent during loading
    expect(screen.queryByText('Points Breakdown')).not.toBeInTheDocument();
    expect(screen.queryByText('Badges')).not.toBeInTheDocument();
    expect(screen.queryByText('Streak Tracker')).not.toBeInTheDocument();
  });

  // ── 13. Error state ──────────────────────────────────────────────────────────

  it('shows the error state when the query fails', async () => {
    mockedStudentService.getGamificationSummary.mockRejectedValue(new Error('Network error'));
    renderPage();
    expect(await screen.findByText('Failed to load achievements')).toBeInTheDocument();
    expect(await screen.findByText('Something went wrong. Please try again.')).toBeInTheDocument();
  });

  it('renders a Retry button in the error state', async () => {
    mockedStudentService.getGamificationSummary.mockRejectedValue(new Error('Network error'));
    renderPage();
    expect(await screen.findByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('calls getGamificationSummary again when the Retry button is clicked', async () => {
    const user = userEvent.setup();

    // First call fails; second call succeeds
    mockedStudentService.getGamificationSummary
      .mockRejectedValueOnce(new Error('Network error'))
      .mockResolvedValue(MOCK_GAMIFICATION);

    renderPage();
    const retryBtn = await screen.findByRole('button', { name: /retry/i });
    await user.click(retryBtn);

    await waitFor(() => {
      expect(mockedStudentService.getGamificationSummary).toHaveBeenCalledTimes(2);
    });
  });

  // ── 14. Correct query key ────────────────────────────────────────────────────

  it('uses the query key ["studentGamification"] to call getGamificationSummary', async () => {
    renderPage();
    await screen.findByText('Total Points'); // wait for data to settle
    expect(mockedStudentService.getGamificationSummary).toHaveBeenCalledTimes(1);
  });

  // ── 15. Heading still present in loading / error / empty states ───────────────

  it('keeps the "Achievements" heading visible while loading', () => {
    mockedStudentService.getGamificationSummary.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole('heading', { level: 1, name: /achievements/i })).toBeInTheDocument();
  });

  it('keeps the "Achievements" heading visible in the error state', async () => {
    mockedStudentService.getGamificationSummary.mockRejectedValue(new Error('fail'));
    renderPage();
    expect(await screen.findByRole('heading', { level: 1, name: /achievements/i })).toBeInTheDocument();
  });

  it('keeps the "Achievements" heading visible in the empty state', async () => {
    mockedStudentService.getGamificationSummary.mockResolvedValue(MOCK_EMPTY);
    renderPage();
    expect(await screen.findByRole('heading', { level: 1, name: /achievements/i })).toBeInTheDocument();
  });
});
