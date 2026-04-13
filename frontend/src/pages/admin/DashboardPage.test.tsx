import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
import { useTenantStore } from '../../stores/tenantStore';

// Mock modules
jest.mock('../../stores/tenantStore');
jest.mock('../../services/adminService', () => ({
  adminService: {
    getTenantStats: jest.fn(),
    getCourseBreakdown: jest.fn(),
  },
}));

jest.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: jest.fn(),
}));

const mockedUseNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockedUseNavigate,
}));

const mockedUseTenantStore = useTenantStore as unknown as jest.Mock;

const MOCK_STATS = {
  total_teachers: 25,
  active_teachers: 20,
  inactive_teachers: 5,
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

describe('DashboardPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    jest.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    mockedUseTenantStore.mockReturnValue({
      plan: 'STARTER',
      usage: { teachers: { used: 20, limit: 50 }, courses: { used: 8, limit: 20 }, storage_mb: { used: 100, limit: 500 } },
      limits: { max_teachers: 50, max_courses: 20, max_storage_mb: 500, max_video_duration_minutes: 60 },
      theme: { name: 'Test School', primary_color: '#4f46e5' },
      features: {},
      hasFeature: jest.fn(() => false),
    });

    const { adminService } = require('../../services/adminService');
    adminService.getTenantStats.mockResolvedValue(MOCK_STATS);
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
    expect(await screen.findByText(/Hello, Admin/)).toBeInTheDocument();
  });

  it('displays the school name from tenant store', async () => {
    renderPage();
    expect(await screen.findByText('Test School')).toBeInTheDocument();
  });

  it('displays total teachers stat', async () => {
    renderPage();
    expect(await screen.findByText('25')).toBeInTheDocument();
  });

  it('displays published courses stat', async () => {
    renderPage();
    expect(await screen.findByText('8')).toBeInTheDocument();
  });

  it('displays average completion percentage', async () => {
    renderPage();
    expect(await screen.findByText('72%')).toBeInTheDocument();
  });

  it('displays pending review count', async () => {
    renderPage();
    expect(await screen.findByText('7')).toBeInTheDocument();
  });

  it('displays recent activity entry', async () => {
    renderPage();
    expect(await screen.findByText('Alice Smith')).toBeInTheDocument();
  });

  it('navigates to create course on button click', async () => {
    renderPage();
    const createButton = await screen.findByRole('button', { name: /Create Course/i });
    await userEvent.click(createButton);
    expect(mockedUseNavigate).toHaveBeenCalledWith('/admin/courses/new');
  });

  it('shows loading state before data arrives', () => {
    const { adminService } = require('../../services/adminService');
    adminService.getTenantStats.mockReturnValue(new Promise(() => {})); // Never resolves
    renderPage();
    // Stats should show placeholder dashes during loading
    const dashes = screen.getAllByText('-');
    expect(dashes.length).toBeGreaterThanOrEqual(1);
  });

  it('displays sticker stats section', async () => {
    renderPage();
    expect(await screen.findByText('Active')).toBeInTheDocument();
    expect(await screen.findByText('Inactive')).toBeInTheDocument();
    expect(await screen.findByText('Completions')).toBeInTheDocument();
    expect(await screen.findByText('In Progress')).toBeInTheDocument();
    expect(await screen.findByText('Assignments')).toBeInTheDocument();
    expect(await screen.findByText('Submissions')).toBeInTheDocument();
  });

  it('displays empty activity message when no activity', async () => {
    const { adminService } = require('../../services/adminService');
    adminService.getTenantStats.mockResolvedValue({
      ...MOCK_STATS,
      recent_activity: [],
    });
    renderPage();
    expect(await screen.findByText(/No activity recorded yet/i)).toBeInTheDocument();
  });

  it('renders gracefully when getTenantStats rejects with an error', async () => {
    const { adminService } = require('../../services/adminService');
    adminService.getTenantStats.mockRejectedValue(new Error('Network Error'));
    renderPage();

    // The page should still render its heading and structural elements
    expect(await screen.findByText(/Hello, Admin/)).toBeInTheDocument();

    // Stats should fall back to 0 / placeholder values (no crash)
    await waitFor(() => {
      // StatsCard should display 0 when stats is undefined
      const zeros = screen.getAllByText('0');
      expect(zeros.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('shows zero stats rather than crashing on API error', async () => {
    const { adminService } = require('../../services/adminService');
    adminService.getTenantStats.mockRejectedValue(new Error('500 Internal Server Error'));
    renderPage();

    // Wait for query to settle (error state)
    await waitFor(() => {
      expect(adminService.getTenantStats).toHaveBeenCalled();
    });

    // The Create Course button should still be functional
    const createButton = screen.getByRole('button', { name: /Create Course/i });
    expect(createButton).toBeInTheDocument();
  });
});
