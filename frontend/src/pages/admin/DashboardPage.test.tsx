import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
import { useTenantStore } from '../../stores/tenantStore';
import { useAuthStore } from '../../stores/authStore';
import { adminService } from '../../services/adminService';

// Mock modules
vi.mock('../../stores/tenantStore');
vi.mock('../../stores/authStore');
vi.mock('../../services/adminService', () => ({
  adminService: {
    getTenantStats: vi.fn(),
    getTenantAnalytics: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

vi.mock('../../components/dashboard/PlanBadge', () => ({
  PlanBadge: () => <span data-testid="plan-badge">Plan</span>,
}));

const mockedUseNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockedUseNavigate,
  };
});

const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;
const mockedAdminService = adminService as unknown as {
  getTenantStats: ReturnType<typeof vi.fn>;
  getTenantAnalytics: ReturnType<typeof vi.fn>;
};

const MOCK_STATS = {
  total_teachers: 25,
  active_teachers: 20,
  inactive_teachers: 5,
  total_students: 10,
  total_admins: 3,
  total_courses: 10,
  published_courses: 8,
  total_content_items: 50,
  avg_completion_pct: 72,
  course_completions: 40,
  courses_in_progress: 15,
  content_completions: 120,
  total_assignments: 30,
  total_submissions: 25,
  graded_submissions: 20,
  pending_review: 7,
  cert_compliance: { fully_compliant: 5, compliance_pct: 80, total_teachers: 25, partially_compliant: 10, non_compliant: 10, expiring_certs: 2, expired_certs: 1 },
  weekly_trend: [],
  upcoming_deadlines: [],
  top_teachers: [{ name: 'Alice Smith', completed_courses: 8 }],
  recent_activity: [
    {
      teacher_name: 'Alice Smith',
      course_title: 'Math 101',
      content_title: 'Lesson 1',
      completed_at: new Date().toISOString(),
    },
  ],
};

const MOCK_ANALYTICS = {
  teacher_engagement: null,
  student_engagement: null,
  student_course_progress: null,
  student_performance: null,
  student_overview: null,
  course_breakdown: [],
};

describe('DashboardPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    mockedUseTenantStore.mockReturnValue({
      plan: 'STARTER',
      usage: { teachers: { used: 20, limit: 50 }, courses: { used: 8, limit: 20 }, storage_mb: { used: 100, limit: 500 } },
      limits: { max_teachers: 50, max_courses: 20, max_storage_mb: 500, max_video_duration_minutes: 60 },
      theme: { name: 'Test School', primary_color: '#4f46e5' },
      features: {},
      hasFeature: vi.fn(() => false),
    });

    mockedUseAuthStore.mockReturnValue({
      user: { first_name: 'Admin' },
    });

    mockedAdminService.getTenantStats.mockResolvedValue(MOCK_STATS);
    mockedAdminService.getTenantAnalytics.mockResolvedValue(MOCK_ANALYTICS);
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>
    );

  it('renders the hero heading', async () => {
    renderPage();
    expect(await screen.findByText(/Welcome back, Admin/)).toBeInTheDocument();
  });

  it('displays the school name from tenant store', async () => {
    renderPage();
    expect(await screen.findByText(/Test School/)).toBeInTheDocument();
  });

  it('displays total teachers stat', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Total Teachers')).toBeInTheDocument();
    });
  });

  it('displays published courses stat', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Active Courses')).toBeInTheDocument();
    });
  });

  it('displays average completion percentage', async () => {
    renderPage();
    await waitFor(() => {
      // 72% appears in both the stat header and the completion bar
      expect(screen.getAllByText(/72%/).length).toBeGreaterThanOrEqual(1);
    });
  });

  it('displays completion stats section', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Completion Stats')).toBeInTheDocument();
    });
  });

  it('displays recent activity entry', async () => {
    renderPage();
    // Alice Smith appears in both Recent Activity and Top Performers
    const matches = await screen.findAllByText('Alice Smith');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('navigates to create course on button click', async () => {
    renderPage();
    const createButton = await screen.findByRole('button', { name: /New Course/i });
    await userEvent.click(createButton);
    expect(mockedUseNavigate).toHaveBeenCalledWith('/admin/courses/new');
  });

  it('shows loading skeleton before data arrives', () => {
    mockedAdminService.getTenantStats.mockReturnValue(new Promise(() => {})); // Never resolves
    mockedAdminService.getTenantAnalytics.mockReturnValue(new Promise(() => {})); // Never resolves
    renderPage();
    // While loading, the skeleton shimmer divs should be rendered
    const shimmerDivs = document.querySelectorAll('.animate-pulse');
    expect(shimmerDivs.length).toBeGreaterThanOrEqual(1);
  });

  it('displays stat card labels', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Total Teachers')).toBeInTheDocument();
      expect(screen.getByText('Active Courses')).toBeInTheDocument();
      expect(screen.getByText('Total Students')).toBeInTheDocument();
      expect(screen.getByText('Certifications')).toBeInTheDocument();
    });
  });

  it('displays empty activity message when no activity', async () => {
    mockedAdminService.getTenantStats.mockResolvedValue({
      ...MOCK_STATS,
      recent_activity: [],
    });
    renderPage();
    expect(await screen.findByText(/No recent activity/i)).toBeInTheDocument();
  });

  it('renders gracefully when getTenantStats rejects with an error', async () => {
    mockedAdminService.getTenantStats.mockRejectedValue(new Error('Network Error'));
    mockedAdminService.getTenantAnalytics.mockRejectedValue(new Error('Network Error'));
    renderPage();

    // The page should still render its heading and structural elements
    expect(await screen.findByText(/Welcome back, Admin/)).toBeInTheDocument();
  });

  it('shows the New Course button even on API error', async () => {
    mockedAdminService.getTenantStats.mockRejectedValue(new Error('500 Internal Server Error'));
    mockedAdminService.getTenantAnalytics.mockRejectedValue(new Error('500 Internal Server Error'));
    renderPage();

    // Wait for both queries to settle and the full page to render
    const createButton = await screen.findByRole('button', { name: /New Course/i });
    expect(createButton).toBeInTheDocument();
  });
});
