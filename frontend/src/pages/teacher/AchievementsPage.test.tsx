// src/pages/teacher/AchievementsPage.test.tsx
//
// Tests for the Teacher Achievements (Gamification) page.
// Covers: loading, hero stats, badges with rarity, XP trend chart, streak freeze,
//         opted-out state, and error-safe empty state.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AchievementsPage } from './AchievementsPage';
import { gamificationService } from '../../services/gamificationService';
import { masteryService } from '../../services/masteryService';
import { coinsService } from '../../services/coinsService';
import { ToastProvider } from '../../components/common';

// ── Mock the service ──────────────────────────────────────────────────────────

vi.mock('../../services/gamificationService', () => ({
  gamificationService: {
    getSummary: vi.fn(),
    getMyBadges: vi.fn(),
    getBadgeDefinitions: vi.fn(),
    getXPHistory: vi.fn(),
    getLeaderboard: vi.fn(),
    useStreakFreeze: vi.fn(),
    getStreakFreezeInventory: vi.fn(),
    getCurrentLeague: vi.fn(),
  },
}));

// TASK-018 — mock masteryService so the new MP card can render.
vi.mock('../../services/masteryService', async () => {
  const actual = await vi.importActual<typeof import('../../services/masteryService')>(
    '../../services/masteryService',
  );
  return {
    ...actual,
    masteryService: {
      getTeacherSummary: vi.fn(),
      getTeacherHistory: vi.fn(),
      getAdminLeaderboard: vi.fn(),
    },
  };
});

// TASK-019 / FE-014 — mock coinsService for wallet pill + buy-freeze.
vi.mock('../../services/coinsService', async () => {
  const actual = await vi.importActual<typeof import('../../services/coinsService')>(
    '../../services/coinsService',
  );
  return {
    ...actual,
    coinsService: {
      getBalance: vi.fn(),
      getHistory: vi.fn(),
      purchaseStreakFreeze: vi.fn(),
    },
  };
});

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

// Stub Recharts — canvas/SVG breaks in jsdom and its measurements are irrelevant here.
vi.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  CartesianGrid: () => null,
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const mockSummary = {
  total_xp: 420,
  level: 3,
  level_name: 'Mentor',
  xp_this_month: 260,
  xp_this_week: 90,
  current_streak: 5,
  longest_streak: 12,
  last_xp_at: '2026-04-19T09:00:00Z',
  opted_out: false,
  badges: [],
  next_level_xp: 600,
  xp_to_next_level: 180,
};

const mockBadgeDefs = [
  {
    id: 'badge-common',
    name: 'First Step',
    description: 'Earn your first 10 XP',
    icon: 'star',
    color: '#3b82f6',
    category: 'milestone' as const,
    criteria_type: 'xp_threshold' as const,
    criteria_value: 10,
    is_active: true,
    sort_order: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'badge-legendary',
    name: 'XP Legend',
    description: 'Reach 5,000 XP',
    icon: 'star',
    color: '#f59e0b',
    category: 'milestone' as const,
    criteria_type: 'xp_threshold' as const,
    criteria_value: 5000,
    is_active: true,
    sort_order: 1,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

const mockMyBadges = [
  {
    id: 'award-1',
    badge: mockBadgeDefs[0],
    awarded_at: '2026-04-10T12:00:00Z',
    awarded_reason: 'Auto',
  },
];

const mockXPHistory = [
  {
    id: 'xp-1',
    teacher: 'me',
    teacher_name: 'Me',
    teacher_email: 'me@school.com',
    xp_amount: 30,
    reason: 'content_completion',
    description: 'Watched intro video',
    reference_id: null,
    reference_type: '',
    created_at: '2026-04-19T09:00:00Z',
  },
  {
    id: 'xp-2',
    teacher: 'me',
    teacher_name: 'Me',
    teacher_email: 'me@school.com',
    xp_amount: 20,
    reason: 'quiz_submission',
    description: 'Submitted a quiz',
    reference_id: null,
    reference_type: '',
    created_at: '2026-04-18T09:00:00Z',
  },
];

const mockInventory = {
  token_count: 2,
  max_inventory: 3,
  earn_every_n_days: 7,
  expires_days: 30,
  tokens: [],
  weekend_mode_enabled: false,
  weekend_mode_available: true,
  grace_period_hours: 3,
  in_grace_period: false,
  grace_period_ends_at: null,
  current_streak: 5,
  longest_streak: 12,
};

const mockCurrentLeague = {
  tier_code: 'silver_2',
  tier_name: 'Silver II',
  tier_rank: 5,
  week_start_date: '2026-04-20',
  members: [
    {
      teacher_id: 'me',
      teacher_name: 'Me',
      teacher_email: 'me@school.com',
      weekly_xp: 90,
      final_rank: null,
    },
  ],
  promote_count: 7,
  demote_count: 7,
  cohort_size: 30,
};

const mockMasterySummary = {
  teacher_id: 'me',
  teacher_name: 'Me',
  teacher_email: 'me@school.com',
  total_mastery_points: '48.00',
  mp_this_month: '12.00',
  mp_this_week: '5.00',
  last_mp_at: '2026-04-19T10:00:00Z',
};

const mockMasteryHistoryPage = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 'mp-1',
      teacher: 'me',
      teacher_name: 'Me',
      teacher_email: 'me@school.com',
      amount: '12.00',
      reason: 'quiz_mastery' as const,
      description: 'Algebra Quiz',
      reference_id: 'sub-1',
      reference_type: 'quiz_submission',
      skill_code: '',
      created_at: '2026-04-18T09:00:00Z',
    },
    {
      id: 'mp-2',
      teacher: 'me',
      teacher_name: 'Me',
      teacher_email: 'me@school.com',
      amount: '36.00',
      reason: 'course_mastery_bonus' as const,
      description: 'Course bonus',
      reference_id: 'c-1',
      reference_type: 'course',
      skill_code: '',
      created_at: '2026-04-15T09:00:00Z',
    },
  ],
};

const mockLeaderboard = {
  period: 'weekly',
  snapshot_date: '2026-04-19',
  entries: [
    {
      rank: 1,
      teacher_id: 'other',
      teacher_name: 'Alice',
      teacher_email: 'a@s.com',
      total_xp: 900,
      xp_period: 900,
      level: 5,
      level_name: 'Sage',
      badge_count: 4,
      current_streak: 14,
    },
    {
      rank: 2,
      teacher_id: 'me',
      teacher_name: 'Me',
      teacher_email: 'me@school.com',
      total_xp: 420,
      xp_period: 90,
      level: 3,
      level_name: 'Mentor',
      badge_count: 1,
      current_streak: 5,
    },
  ],
};

// ── Setup ─────────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderPage() {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <AchievementsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

function setupMocks(overrides: Partial<Record<keyof typeof gamificationService, unknown>> = {}) {
  vi.mocked(gamificationService.getSummary).mockResolvedValue(
    (overrides.getSummary as typeof mockSummary) ?? mockSummary,
  );
  vi.mocked(gamificationService.getMyBadges).mockResolvedValue(
    (overrides.getMyBadges as typeof mockMyBadges) ?? mockMyBadges,
  );
  vi.mocked(gamificationService.getBadgeDefinitions).mockResolvedValue(
    (overrides.getBadgeDefinitions as typeof mockBadgeDefs) ?? mockBadgeDefs,
  );
  vi.mocked(gamificationService.getXPHistory).mockResolvedValue(
    (overrides.getXPHistory as typeof mockXPHistory) ?? mockXPHistory,
  );
  vi.mocked(gamificationService.getLeaderboard).mockResolvedValue(
    (overrides.getLeaderboard as typeof mockLeaderboard) ?? mockLeaderboard,
  );
  vi.mocked(gamificationService.getStreakFreezeInventory).mockResolvedValue(
    (overrides.getStreakFreezeInventory as typeof mockInventory) ?? mockInventory,
  );
  vi.mocked(gamificationService.getCurrentLeague).mockResolvedValue(
    (overrides.getCurrentLeague as typeof mockCurrentLeague) ?? mockCurrentLeague,
  );

  vi.mocked(masteryService.getTeacherSummary).mockResolvedValue(
    mockMasterySummary,
  );
  vi.mocked(masteryService.getTeacherHistory).mockResolvedValue(
    mockMasteryHistoryPage,
  );

  // Default coin balance — 250 coins, price 100 → affordable.
  vi.mocked(coinsService.getBalance).mockResolvedValue({
    teacher_id: 'me',
    balance: 250,
    lifetime_earned: 400,
    lifetime_spent: 150,
    last_txn_at: '2026-04-19T10:00:00Z',
    updated_at: '2026-04-19T10:00:00Z',
    price_streak_freeze: 100,
  });
  vi.mocked(coinsService.purchaseStreakFreeze).mockResolvedValue({
    balance: {
      teacher_id: 'me',
      balance: 150,
      lifetime_earned: 400,
      lifetime_spent: 250,
      last_txn_at: '2026-04-20T10:00:00Z',
      updated_at: '2026-04-20T10:00:00Z',
      price_streak_freeze: 100,
    },
    transaction: {
      id: 'tx-buy',
      teacher: 'me',
      amount: -100,
      reason: 'purchase_streak_freeze',
      description: 'Purchased streak-freeze token',
      reference_id: null,
      reference_type: 'streak_freeze_purchase',
      created_at: '2026-04-20T10:00:00Z',
    },
    token: { id: 't-1', source: 'purchase', expires_at: null },
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('AchievementsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupMocks();
  });

  it('renders the level hero with name and XP progress', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: /my achievements/i })).toBeInTheDocument();
    });
    expect(await screen.findByText(/mentor/i)).toBeInTheDocument();
    expect(screen.getByText(/level 3/i)).toBeInTheDocument();
    // 420 XP · 180 to next level
    expect(screen.getByText(/420 xp/i)).toBeInTheDocument();
    expect(screen.getByText(/180 to next level/i)).toBeInTheDocument();

    const bar = screen.getByRole('progressbar', { name: /progress to next level/i });
    // 420 / 600 = 70%
    expect(bar).toHaveAttribute('aria-valuenow', '70');
  });

  it('shows streak, weekly XP, badge count, and league rank stat cards', async () => {
    renderPage();
    await screen.findByText(/mentor/i);

    expect(screen.getByText(/xp this week/i)).toBeInTheDocument();
    expect(screen.getByText('90')).toBeInTheDocument();

    expect(screen.getByText(/current streak/i)).toBeInTheDocument();
    expect(screen.getByText('5d')).toBeInTheDocument();
    expect(screen.getByText(/longest: 12d/i)).toBeInTheDocument();

    expect(screen.getByText(/badges earned/i)).toBeInTheDocument();
    expect(screen.getByText('1/2')).toBeInTheDocument();

    // Current-league card replaced the old "#N" placeholder with the tier name.
    const leagueCard = screen.getByTestId('achievements-league-card');
    expect(leagueCard).toBeInTheDocument();
    expect(leagueCard).toHaveTextContent(/silver ii/i);
  });

  it('renders every badge with earned/locked state and rarity metadata', async () => {
    renderPage();
    await screen.findByText(/mentor/i);

    const common = await screen.findByTestId('badge-card-badge-common');
    expect(common).toHaveAttribute('data-earned', 'true');
    expect(common).toHaveAttribute('data-rarity', 'common');

    const legendary = screen.getByTestId('badge-card-badge-legendary');
    expect(legendary).toHaveAttribute('data-earned', 'false');
    expect(legendary).toHaveAttribute('data-rarity', 'legendary');

    // Rarity chip labels
    expect(screen.getByText(/^Common$/)).toBeInTheDocument();
    expect(screen.getByText(/^Legendary$/)).toBeInTheDocument();
  });

  it('renders the XP trend chart', async () => {
    renderPage();
    await screen.findByText(/mentor/i);
    // With TASK-018, the MP sparkline also uses LineChart. We assert
    // at-least-one rather than exactly-one.
    const charts = await screen.findAllByTestId('line-chart');
    expect(charts.length).toBeGreaterThanOrEqual(1);
  });

  it('lists recent XP activity', async () => {
    renderPage();
    await screen.findByText(/mentor/i);
    expect(screen.getByText(/watched intro video/i)).toBeInTheDocument();
    expect(screen.getByText('+30')).toBeInTheDocument();
    expect(screen.getByText('+20')).toBeInTheDocument();
  });

  it('uses a streak freeze after the user confirms', async () => {
    vi.mocked(gamificationService.useStreakFreeze).mockResolvedValue({
      success: true,
      freezes_remaining: 1,
    });
    renderPage();
    await screen.findByText(/mentor/i);

    await userEvent.click(screen.getByRole('button', { name: /use freeze/i }));
    // Confirm dialog has its own "Use freeze" button; click the primary one.
    const confirmButtons = await screen.findAllByRole('button', { name: /use freeze/i });
    // The dialog button is the second instance.
    await userEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() => {
      expect(gamificationService.useStreakFreeze).toHaveBeenCalledTimes(1);
    });
  });

  it('shows the opt-out state when the teacher has opted out', async () => {
    setupMocks({
      getSummary: { ...mockSummary, opted_out: true },
    });
    renderPage();
    expect(
      await screen.findByText(/you've opted out of gamification/i),
    ).toBeInTheDocument();
    // Hero/stat cards should not render in the opt-out state.
    expect(screen.queryByText(/xp this week/i)).not.toBeInTheDocument();
  });

  // ── FE-012 additions ──────────────────────────────────────────────────────

  it('disables the freeze button and shows "No tokens" when inventory is empty', async () => {
    setupMocks({
      getStreakFreezeInventory: { ...mockInventory, token_count: 0 },
    });
    renderPage();
    await screen.findByText(/mentor/i);
    const btn = await screen.findByTestId('streak-freeze-button');
    await waitFor(() => {
      expect(btn).toBeDisabled();
    });
    expect(btn).toHaveTextContent(/no tokens/i);
  });

  // ── TASK-018: Mastery Points card ─────────────────────────────────────────

  it('renders the Mastery Points stat card with total MP and a link to history', async () => {
    renderPage();
    await screen.findByText(/mentor/i);

    const card = await screen.findByTestId('achievements-mastery-card');
    expect(card).toHaveAttribute('href', '/teacher/mastery');
    expect(card).toHaveTextContent(/mastery points/i);

    const total = await screen.findByTestId('achievements-mp-total');
    // total_mastery_points: '48.00' → rendered as 48.00
    expect(total).toHaveTextContent('48.00');
  });

  it('counts MP transactions per source in the breakdown icons', async () => {
    renderPage();
    await screen.findByText(/mentor/i);

    // Fixture has 1 quiz_mastery and 1 course_mastery_bonus, 0 assignment.
    const quiz = await screen.findByTestId('mp-breakdown-quiz');
    expect(quiz).toHaveTextContent('1');
    const assignment = screen.getByTestId('mp-breakdown-assignment');
    expect(assignment).toHaveTextContent('0');
    const course = screen.getByTestId('mp-breakdown-course');
    expect(course).toHaveTextContent('1');
  });

  it('renders the real current-league card', async () => {
    // 2026-04-23: Wallet / Challenges / Leagues pages removed from teacher
    // portal. The league-card visual remains (status indicator only); its
    // outbound link-target was removed along with the Leagues route.
    renderPage();
    await screen.findByText(/mentor/i);
    const leagueCard = await screen.findByTestId('achievements-league-card');
    expect(leagueCard).toHaveTextContent(/silver ii/i);
    expect(leagueCard).toHaveTextContent(/1 in cohort/i);

    const tokenCount = await screen.findByTestId('streak-freeze-token-count');
    expect(tokenCount).toHaveTextContent(/2 tokens/i);
  });

  it('opens the buy-freeze confirm modal when the streak is active and tokens = 0', async () => {
    setupMocks({
      getStreakFreezeInventory: { ...mockInventory, token_count: 0 },
    });
    renderPage();
    await screen.findByText(/mentor/i);

    const buyBtn = await screen.findByTestId('buy-freeze-button');
    await userEvent.click(buyBtn);

    // ConfirmDialog surfaces the price + balance in its body text.
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /buy streak freeze token/i }),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/spend 100 coins/i)).toBeInTheDocument();
    expect(screen.getByText(/you have 250 coins/i)).toBeInTheDocument();
  });
});
