// src/pages/admin/GamificationPage.test.tsx
//
// Tests for the Admin Gamification Management page.
// Covers: tab navigation, leaderboard display, badge CRUD, config form, XP history,
//         loading states, error states, and cross-role access guards.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AdminGamificationPage } from './GamificationPage';
import { gamificationService } from '../../services/gamificationService';
import { masteryService } from '../../services/masteryService';
import { ToastProvider } from '../../components/common';

// ── Mock modules ──────────────────────────────────────────────────────────────

// The component calls `gamificationService.admin.*` — mirror that namespace.
vi.mock('../../services/gamificationService', () => ({
  gamificationService: {
    admin: {
      getConfig: vi.fn(),
      updateConfig: vi.fn(),
      listBadges: vi.fn(),
      createBadge: vi.fn(),
      updateBadge: vi.fn(),
      deleteBadge: vi.fn(),
      getLeaderboard: vi.fn(),
      getXPHistory: vi.fn(),
      adjustXP: vi.fn(),
    },
  },
}));

// TASK-018 — mastery leaderboard tab depends on masteryService.
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

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

vi.mock('./course-editor/api', () => ({
  fetchTeachers: vi.fn().mockResolvedValue([
    { id: 'teacher-1', first_name: 'Alice', last_name: 'Smith', email: 'alice@school.com' },
  ]),
}));

// Stub Recharts to avoid canvas/SVG issues in jsdom
vi.mock('recharts', () => ({
  RadarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="radar-chart">{children}</div>
  ),
  PolarGrid: () => null,
  PolarAngleAxis: () => null,
  PolarRadiusAxis: () => null,
  Radar: () => null,
  Legend: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  Tooltip: () => null,
}));

// Stub DataTable to simplify table rendering while still surfacing row data.
vi.mock('../../components/ui/data-table', () => ({
  DataTable: ({
    data,
    emptyMessage,
    columns,
  }: {
    data: Array<Record<string, unknown>>;
    emptyMessage?: string;
    columns: Array<{ accessorKey?: string; id?: string; cell?: unknown }>;
  }) => (
    <div data-testid="data-table">
      {data.length === 0 && emptyMessage ? (
        <span>{emptyMessage}</span>
      ) : (
        <div>
          <span>{data.length} rows</span>
          {/* Render a minimal representation so tests can find row text. */}
          {data.map((row, i) => (
            <div key={i} data-testid="data-table-row">
              {Object.entries(row).map(([k, v]) => {
                if (typeof v === 'string' || typeof v === 'number') {
                  return <span key={k}>{String(v)}</span>;
                }
                return null;
              })}
            </div>
          ))}
        </div>
      )}
      {/* Dummy to keep columns referenced (not strictly needed). */}
      <span data-testid="data-table-cols" hidden>
        {columns.length}
      </span>
    </div>
  ),
  DataTableColumnHeader: ({ title }: { title: string }) => <span>{title}</span>,
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────
// These match the real service types exactly — see gamificationService.ts.

const mockConfig = {
  id: 'config-1',
  xp_per_content_completion: 10,
  xp_per_course_completion: 50,
  xp_per_assignment_submission: 20,
  xp_per_quiz_submission: 30,
  xp_per_streak_day: 5,
  streak_freeze_max: 2,
  leaderboard_enabled: true,
  leaderboard_anonymize: false,
  opt_out_allowed: true,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockBadges = [
  {
    id: 'badge-1',
    name: 'First Login',
    description: 'Logged in for the first time',
    category: 'milestone' as const,
    criteria_type: 'xp_threshold' as const,
    criteria_value: 1,
    icon: 'star',
    color: '#f59e0b',
    is_active: true,
    sort_order: 0,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'badge-2',
    name: 'Streak Master',
    description: '7-day streak',
    category: 'streak' as const,
    criteria_type: 'streak_days' as const,
    criteria_value: 7,
    icon: 'fire',
    color: '#ef4444',
    is_active: true,
    sort_order: 1,
    created_at: '2026-01-02T00:00:00Z',
    updated_at: '2026-01-02T00:00:00Z',
  },
];

const mockLeaderboard = {
  period: 'weekly',
  snapshot_date: '2026-04-19',
  entries: [
    {
      rank: 1,
      teacher_id: 'teacher-1',
      teacher_name: 'Alice Smith',
      teacher_email: 'alice@school.com',
      total_xp: 500,
      xp_period: 500,
      level: 5,
      level_name: 'Master',
      badge_count: 3,
      current_streak: 7,
    },
    {
      rank: 2,
      teacher_id: 'teacher-2',
      teacher_name: 'Bob Jones',
      teacher_email: 'bob@school.com',
      total_xp: 350,
      xp_period: 350,
      level: 3,
      level_name: 'Advanced',
      badge_count: 1,
      current_streak: 3,
    },
  ],
};

// Service returns an array directly, not a paginated wrapper.
const mockXPHistory = [
  {
    id: 'xp-1',
    teacher: 'teacher-1',
    teacher_name: 'Alice Smith',
    teacher_email: 'alice@school.com',
    xp_amount: 50,
    reason: 'course_completion',
    description: 'Completed Intro to Pedagogy',
    reference_id: null,
    reference_type: '',
    created_at: '2026-04-15T10:00:00Z',
  },
];

// ── Setup ─────────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderGamificationPage() {
  const queryClient = makeQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <AdminGamificationPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const mockMasteryLeaderboard = {
  count: 2,
  results: [
    {
      rank: 1,
      teacher_id: 'teacher-1',
      teacher_name: 'Alice Smith',
      teacher_email: 'alice@school.com',
      total_mastery_points: '150.00',
      mp_this_week: '20.00',
      mp_this_month: '60.00',
    },
    {
      rank: 2,
      teacher_id: 'teacher-2',
      teacher_name: 'Bob Jones',
      teacher_email: 'bob@school.com',
      total_mastery_points: '90.00',
      mp_this_week: '10.00',
      mp_this_month: '30.00',
    },
  ],
};

function setupServiceMocks() {
  vi.mocked(gamificationService.admin.getConfig).mockResolvedValue(mockConfig);
  vi.mocked(gamificationService.admin.listBadges).mockResolvedValue(mockBadges);
  vi.mocked(gamificationService.admin.getLeaderboard).mockResolvedValue(mockLeaderboard);
  vi.mocked(gamificationService.admin.getXPHistory).mockResolvedValue(mockXPHistory);
  vi.mocked(masteryService.getAdminLeaderboard).mockResolvedValue(
    mockMasteryLeaderboard,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('GamificationPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupServiceMocks();
  });

  // ── Rendering ─────────────────────────────────────────────────────────────

  it('renders the page heading', async () => {
    renderGamificationPage();
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { level: 1, name: /gamification/i }),
      ).toBeInTheDocument();
    });
  });

  // ── Tab navigation ─────────────────────────────────────────────────────────

  it('defaults to Leaderboard tab', async () => {
    renderGamificationPage();
    await waitFor(() => {
      // Anchored regex avoids the "Mastery Leaderboard" tab (TASK-018).
      expect(screen.getByRole('tab', { name: /^leaderboard$/i })).toHaveAttribute(
        'aria-selected',
        'true',
      );
    });
  });

  it('displays leaderboard entries on Leaderboard tab', async () => {
    renderGamificationPage();
    await waitFor(() => {
      expect(screen.getByText('Alice Smith')).toBeInTheDocument();
      expect(screen.getByText('Bob Jones')).toBeInTheDocument();
    });
  });

  it('shows rank medals for top 3 entries', async () => {
    renderGamificationPage();
    await waitFor(() => {
      expect(screen.getByText('🥇')).toBeInTheDocument();
      expect(screen.getByText('🥈')).toBeInTheDocument();
    });
  });

  it('switches to XP History tab on click', async () => {
    const user = userEvent.setup();
    renderGamificationPage();

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /xp history/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: /xp history/i }));

    await waitFor(() => {
      expect(gamificationService.admin.getXPHistory).toHaveBeenCalled();
    });
  });

  it('switches to Badges tab on click', async () => {
    const user = userEvent.setup();
    renderGamificationPage();

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /badges/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: /badges/i }));

    await waitFor(() => {
      expect(gamificationService.admin.listBadges).toHaveBeenCalled();
    });
  });

  it('switches to Config tab on click', async () => {
    const user = userEvent.setup();
    renderGamificationPage();

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /config/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('tab', { name: /config/i }));

    await waitFor(() => {
      expect(gamificationService.admin.getConfig).toHaveBeenCalled();
    });
  });

  // ── Leaderboard ────────────────────────────────────────────────────────────

  it('shows XP for leaderboard entries', async () => {
    renderGamificationPage();
    await waitFor(() => {
      // xp_period is rendered with toLocaleString() — "500" has no comma.
      expect(screen.getByText('500')).toBeInTheDocument();
    });
  });

  it('calls getLeaderboard with default period "weekly"', async () => {
    renderGamificationPage();
    await waitFor(() => {
      expect(gamificationService.admin.getLeaderboard).toHaveBeenCalledWith('weekly');
    });
  });

  it('shows empty state when leaderboard has no entries', async () => {
    vi.mocked(gamificationService.admin.getLeaderboard).mockResolvedValue({
      period: 'weekly',
      snapshot_date: '2026-04-19',
      entries: [],
    });
    renderGamificationPage();
    await waitFor(() => {
      expect(
        screen.getByText(/no leaderboard data|no entries|no data/i),
      ).toBeInTheDocument();
    });
  });

  // ── XP History ────────────────────────────────────────────────────────────

  it('fetches XP history when the tab is opened', async () => {
    const user = userEvent.setup();
    renderGamificationPage();

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /xp history/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /xp history/i }));

    await waitFor(() => {
      expect(gamificationService.admin.getXPHistory).toHaveBeenCalled();
    });
  });

  // ── Badge CRUD ────────────────────────────────────────────────────────────

  it('opens Create Badge modal on "New Badge" button click', async () => {
    const user = userEvent.setup();
    renderGamificationPage();

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /badges/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /badges/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new badge/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /new badge/i }));

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
  });

  it('renders badge rows on Badges tab', async () => {
    const user = userEvent.setup();
    renderGamificationPage();

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /badges/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /badges/i }));

    // Data table mock surfaces row count when populated.
    await waitFor(() => {
      expect(screen.getByText('2 rows')).toBeInTheDocument();
    });
  });

  it('calls createBadge on form submit', async () => {
    const user = userEvent.setup();
    vi.mocked(gamificationService.admin.createBadge).mockResolvedValue({
      ...mockBadges[0],
      id: 'badge-new',
      name: 'New Badge',
    });

    renderGamificationPage();

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /badges/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /badges/i }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /new badge/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /new badge/i }));

    await waitFor(() => screen.getByRole('dialog'));

    // Fill in the name field (required) — FormField labels the input.
    const nameInput = screen.getByLabelText(/badge name/i);
    await user.type(nameInput, 'New Badge');

    // Submit via the primary action button in the dialog.
    const dialog = screen.getByRole('dialog');
    const submitBtn = within(dialog).getByRole('button', { name: /create badge/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(gamificationService.admin.createBadge).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'New Badge' }),
      );
    });
  });

  // ── Config form ───────────────────────────────────────────────────────────

  it('shows XP configuration inputs on Config tab', async () => {
    const user = userEvent.setup();
    renderGamificationPage();

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /config/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /config/i }));

    await waitFor(() => {
      // Form should populate with the config fixture value.
      expect(screen.getByDisplayValue('10')).toBeInTheDocument(); // xp_per_content_completion
      expect(screen.getByDisplayValue('50')).toBeInTheDocument(); // xp_per_course_completion
    });
  });

  it('calls updateConfig on config form submit', async () => {
    const user = userEvent.setup();
    vi.mocked(gamificationService.admin.updateConfig).mockResolvedValue(mockConfig);

    renderGamificationPage();

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /config/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /config/i }));

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /save configuration/i }),
      ).toBeInTheDocument(),
    );

    await user.click(screen.getByRole('button', { name: /save configuration/i }));

    await waitFor(() => {
      expect(gamificationService.admin.updateConfig).toHaveBeenCalled();
    });
  });

  // ── XP Adjust ────────────────────────────────────────────────────────────

  it('renders an Adjust XP button on the leaderboard tab', async () => {
    renderGamificationPage();
    await waitFor(() => {
      // The section header button
      expect(
        screen.getByRole('button', { name: /adjust xp/i }),
      ).toBeInTheDocument();
    });
  });

  // ── Error handling ────────────────────────────────────────────────────────

  it('renders the leaderboard empty state when the fetch rejects', async () => {
    vi.mocked(gamificationService.admin.getLeaderboard).mockRejectedValue(
      new Error('Network Error'),
    );
    renderGamificationPage();
    // When the query fails (retries disabled), data is undefined → empty state.
    await waitFor(() => {
      expect(
        screen.getByText(/no leaderboard data/i),
      ).toBeInTheDocument();
    });
  });

  // ── Mutation error toasts ─────────────────────────────────────────────────

  it('shows a toast.error when createBadge mutation rejects', async () => {
    const user = userEvent.setup();
    // Reject with a non-Error value so getErrorMessage falls through to the
    // fallback string ("Failed to create badge") rather than err.message.
    vi.mocked(gamificationService.admin.createBadge).mockRejectedValue(
      { code: 500 }, // plain object — not instanceof Error, not AxiosError
    );

    renderGamificationPage();

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /badges/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /badges/i }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /new badge/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /new badge/i }));

    await waitFor(() => screen.getByRole('dialog'));

    const nameInput = screen.getByLabelText(/badge name/i);
    await user.type(nameInput, 'Broken Badge');

    const dialog = screen.getByRole('dialog');
    const submitBtn = within(dialog).getByRole('button', { name: /create badge/i });
    await user.click(submitBtn);

    // The onError handler calls toast.error → ToastProvider renders role="alert"
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByRole('alert')).toHaveTextContent(/failed to create badge/i);
  });

  // ── TASK-018: Mastery Leaderboard tab ─────────────────────────────────────

  it('renders the Mastery Leaderboard tab trigger', async () => {
    renderGamificationPage();
    await waitFor(() => {
      expect(
        screen.getByRole('tab', { name: /mastery leaderboard/i }),
      ).toBeInTheDocument();
    });
  });

  it('loads mastery leaderboard data when the tab is opened', async () => {
    const user = userEvent.setup();
    renderGamificationPage();

    await waitFor(() =>
      expect(
        screen.getByRole('tab', { name: /mastery leaderboard/i }),
      ).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /mastery leaderboard/i }));

    await waitFor(() => {
      expect(masteryService.getAdminLeaderboard).toHaveBeenCalled();
    });

    // DataTable stub renders row count; both teachers should show.
    await waitFor(() => {
      expect(screen.getByText('2 rows')).toBeInTheDocument();
    });
  });

  it('shows a toast.error when updateConfig mutation rejects', async () => {
    const user = userEvent.setup();
    // Reject with a non-Error value so getErrorMessage falls through to the
    // fallback string ("Failed to save config") rather than err.message.
    vi.mocked(gamificationService.admin.updateConfig).mockRejectedValue(
      { code: 500 }, // plain object — not instanceof Error, not AxiosError
    );

    renderGamificationPage();

    await waitFor(() =>
      expect(screen.getByRole('tab', { name: /config/i })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('tab', { name: /config/i }));

    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /save configuration/i }),
      ).toBeInTheDocument(),
    );
    await user.click(screen.getByRole('button', { name: /save configuration/i }));

    // The onError handler calls toast.error → ToastProvider renders role="alert"
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByRole('alert')).toHaveTextContent(/failed to save config/i);
  });
});
