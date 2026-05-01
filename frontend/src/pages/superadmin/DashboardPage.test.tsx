import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { SuperAdminDashboardPage } from './DashboardPage';
import { superAdminService } from '../../services/superAdminService';

// ─── Module mocks ────────────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('../../services/superAdminService', () => ({
  superAdminService: {
    getStats: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ─── Mock data ────────────────────────────────────────────────────────────────

const MOCK_STATS = {
  total_tenants: 12,
  active_tenants: 10,
  trial_tenants: 3,
  total_users: 450,
  total_teachers: 380,
  plan_distribution: { FREE: 2, STARTER: 5, PRO: 3, ENTERPRISE: 2 },
  recent_onboards: [
    {
      id: 'school-1',
      name: 'Riverside Academy',
      subdomain: 'riverside',
      created_at: '2026-04-25T00:00:00Z',
    },
    {
      id: 'school-2',
      name: 'Lakewood High',
      subdomain: 'lakewood',
      created_at: '2026-04-20T00:00:00Z',
    },
  ],
  schools_near_limits: [
    { id: 'school-3', name: 'Valley Prep', resource: 'teachers', used: 48, limit: 50 },
  ],
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
    },
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <SuperAdminDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

const mockGetStats = superAdminService.getStats as ReturnType<typeof vi.fn>;

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('SuperAdminDashboardPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockGetStats.mockResolvedValue(MOCK_STATS);
  });

  // ── 1. Heading ──────────────────────────────────────────────────────────────

  it('renders Platform Dashboard heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { name: /Platform Dashboard/i }),
    ).toBeInTheDocument();
  });

  // ── 2. Subtitle ─────────────────────────────────────────────────────────────

  it('renders subtitle text', async () => {
    renderPage();
    expect(
      await screen.findByText(/Overview of all schools on the platform/i),
    ).toBeInTheDocument();
  });

  // ── 3. Onboard School button renders ────────────────────────────────────────

  it('renders Onboard School button', async () => {
    renderPage();
    expect(
      await screen.findByRole('button', { name: /Onboard School/i }),
    ).toBeInTheDocument();
  });

  // ── 4. Onboard School button navigation ─────────────────────────────────────

  it('Onboard School button navigates correctly', async () => {
    const user = userEvent.setup();
    renderPage();

    const btn = await screen.findByRole('button', { name: /Onboard School/i });
    await user.click(btn);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/super-admin/schools?onboard=true');
  });

  // ── 5. Loading skeleton ──────────────────────────────────────────────────────

  it('shows loading skeleton while loading', async () => {
    // Never resolves so the component stays in loading state
    mockGetStats.mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();

    // Five animate-pulse skeleton cards should be present
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThanOrEqual(5);
  });

  // ── 6. Stat card labels ──────────────────────────────────────────────────────

  it('renders stat card labels', async () => {
    renderPage();

    await screen.findByText('Total Schools');
    expect(screen.getByText('Active Schools')).toBeInTheDocument();
    expect(screen.getByText('Trial Schools')).toBeInTheDocument();
    expect(screen.getByText('Total Users')).toBeInTheDocument();
    expect(screen.getByText('Total Teachers')).toBeInTheDocument();
  });

  // ── 7. Stat card values ──────────────────────────────────────────────────────

  it('renders stat card values', async () => {
    renderPage();

    // Wait for data to load
    await screen.findByText('Total Schools');

    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('450')).toBeInTheDocument();
    expect(screen.getByText('380')).toBeInTheDocument();
  });

  // ── 8. Plan Distribution section heading ────────────────────────────────────

  it('renders plan distribution section heading', async () => {
    renderPage();
    expect(await screen.findByText('Plan Distribution')).toBeInTheDocument();
  });

  // ── 9. Plan labels in distribution ──────────────────────────────────────────

  it('shows plan labels in distribution', async () => {
    renderPage();

    // Wait for the plan rows to appear (they only render once stats resolves)
    expect(await screen.findByText('FREE')).toBeInTheDocument();
    expect(await screen.findByText('STARTER')).toBeInTheDocument();
    expect(await screen.findByText('PRO')).toBeInTheDocument();
    expect(await screen.findByText('ENTERPRISE')).toBeInTheDocument();
  });

  // ── 10. School counts in plan distribution ───────────────────────────────────

  it('shows school counts in plan distribution', async () => {
    renderPage();

    // STARTER = 5 → "5 schools" (plural); wait for it to appear
    expect(await screen.findByText('5 schools')).toBeInTheDocument();
    // PRO = 3 → "3 schools"
    expect(screen.getByText('3 schools')).toBeInTheDocument();
    // FREE = 2, ENTERPRISE = 2 → "2 schools" (appears twice)
    const twoSchools = screen.getAllByText('2 schools');
    expect(twoSchools).toHaveLength(2);
  });

  it('shows singular "school" label when count is 1', async () => {
    mockGetStats.mockResolvedValue({
      ...MOCK_STATS,
      plan_distribution: { FREE: 1, STARTER: 5, PRO: 3, ENTERPRISE: 2 },
    });
    renderPage();

    // Wait for plan rows to render (data-dependent)
    expect(await screen.findByText('1 school')).toBeInTheDocument();
  });

  // ── 11. Recently Onboarded section heading ───────────────────────────────────

  it('renders Recently Onboarded section heading', async () => {
    renderPage();
    expect(await screen.findByText('Recently Onboarded')).toBeInTheDocument();
  });

  // ── 12. Recently onboarded school names ─────────────────────────────────────

  it('shows recently onboarded school names', async () => {
    renderPage();

    expect(await screen.findByText('Riverside Academy')).toBeInTheDocument();
    expect(await screen.findByText('Lakewood High')).toBeInTheDocument();
  });

  // ── 13. Clicking recent onboard navigates to school detail ───────────────────

  it('clicking school in recent onboards navigates to school detail', async () => {
    const user = userEvent.setup();
    renderPage();

    const btn = await screen.findByRole('button', { name: /Riverside Academy/i });
    await user.click(btn);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/super-admin/schools/school-1');
  });

  // ── 14. Empty state when recent_onboards is empty ────────────────────────────

  it('shows "No schools yet" empty state when recent_onboards is empty', async () => {
    mockGetStats.mockResolvedValue({ ...MOCK_STATS, recent_onboards: [] });
    renderPage();

    await screen.findByText('Recently Onboarded');
    expect(await screen.findByText('No schools yet')).toBeInTheDocument();
  });

  // ── 15. Near Limits section heading ─────────────────────────────────────────

  it('renders Near Limits section heading', async () => {
    renderPage();
    expect(await screen.findByText('Near Limits')).toBeInTheDocument();
  });

  // ── 16. Near-limits school with resource usage ───────────────────────────────

  it('shows near-limits school with resource usage', async () => {
    renderPage();

    // Wait for data-dependent content
    expect(await screen.findByText('Valley Prep')).toBeInTheDocument();
    expect(screen.getByText('teachers: 48/50')).toBeInTheDocument();
  });

  // ── 17. Clicking near-limits school navigates to school detail ───────────────

  it('clicking near-limits school navigates to school detail', async () => {
    const user = userEvent.setup();
    renderPage();

    const btn = await screen.findByRole('button', { name: /Valley Prep/i });
    await user.click(btn);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/super-admin/schools/school-3');
  });

  // ── 18. Empty state when schools_near_limits is empty ────────────────────────

  it('shows "All schools within limits" when schools_near_limits is empty', async () => {
    mockGetStats.mockResolvedValue({ ...MOCK_STATS, schools_near_limits: [] });
    renderPage();

    await screen.findByText('Near Limits');
    expect(await screen.findByText('All schools within limits')).toBeInTheDocument();
  });

  // ── 19. Loading state does NOT show stat cards ───────────────────────────────

  it('does not render stat cards while loading', () => {
    mockGetStats.mockReturnValue(new Promise(() => {}));
    renderPage();

    expect(screen.queryByText('Total Schools')).not.toBeInTheDocument();
    expect(screen.queryByText('Active Schools')).not.toBeInTheDocument();
  });

  // ── 20. Plan Distribution "Loading..." fallback ──────────────────────────────

  it('shows "Loading..." in plan distribution section before data arrives', () => {
    mockGetStats.mockReturnValue(new Promise(() => {}));
    renderPage();

    // The plan distribution fallback text appears when stats is undefined
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  // ── 21. getStats is called once on mount ────────────────────────────────────

  it('calls superAdminService.getStats on mount', async () => {
    renderPage();

    await waitFor(() => {
      expect(mockGetStats).toHaveBeenCalledTimes(1);
    });
  });

  // ── 22. data-tour attributes are present ────────────────────────────────────

  it('renders data-tour attribute on the dashboard wrapper', async () => {
    const { container } = renderPage();

    await screen.findByText('Platform Dashboard');

    expect(
      container.querySelector('[data-tour="superadmin-dashboard-page"]'),
    ).toBeInTheDocument();
  });

  it('renders data-tour attribute on the Onboard School button', async () => {
    const { container } = renderPage();

    await screen.findByText('Platform Dashboard');

    expect(
      container.querySelector('[data-tour="superadmin-dashboard-onboard"]'),
    ).toBeInTheDocument();
  });
});
