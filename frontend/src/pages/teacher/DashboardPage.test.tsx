import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
import { teacherService } from '../../services/teacherService';
import { notificationService } from '../../services/notificationService';
import { useAuthStore } from '../../stores/authStore';

jest.mock('../../stores/authStore');
jest.mock('../../services/teacherService', () => ({
  teacherService: {
    getDashboard: jest.fn(),
    getCalendar: jest.fn(),
    getGamificationSummary: jest.fn(),
  },
}));
jest.mock('../../services/notificationService', () => ({
  notificationService: {
    getNotifications: jest.fn(),
    markAsRead: jest.fn(),
  },
}));

const mockedUseAuthStore = useAuthStore as unknown as jest.Mock;
const mockedTeacherService = teacherService as jest.Mocked<typeof teacherService>;
const mockedNotificationService = notificationService as jest.Mocked<typeof notificationService>;

describe('DashboardPage essentials layout', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockedUseAuthStore.mockReturnValue({
      user: { first_name: 'Rakesh' },
    });

    mockedTeacherService.getDashboard.mockResolvedValue({
      stats: {
        overall_progress: 48,
        total_courses: 4,
        completed_courses: 1,
        pending_assignments: 2,
      },
      continue_learning: {
        course_id: 'course-1',
        course_title: 'Course A',
        content_id: 'content-1',
        content_title: 'Lesson A',
        progress_percentage: 25,
      },
      deadlines: [{ id: 'course-1', type: 'course', title: 'Course A', days_left: 2 }],
    } as any);

    mockedTeacherService.getCalendar.mockResolvedValue({
      window: { start_date: '2026-02-22', end_date: '2026-02-26', days: 5 },
      days: [
        { date: '2026-02-22', weekday: 'Sunday', short_weekday: 'Sun', day: 22, month: 'Feb', is_today: true, task_count: 1, total_minutes: 45 },
        { date: '2026-02-23', weekday: 'Monday', short_weekday: 'Mon', day: 23, month: 'Feb', is_today: false, task_count: 1, total_minutes: 60 },
        { date: '2026-02-24', weekday: 'Tuesday', short_weekday: 'Tue', day: 24, month: 'Feb', is_today: false, task_count: 0, total_minutes: 0 },
        { date: '2026-02-25', weekday: 'Wednesday', short_weekday: 'Wed', day: 25, month: 'Feb', is_today: false, task_count: 0, total_minutes: 0 },
        { date: '2026-02-26', weekday: 'Thursday', short_weekday: 'Thu', day: 26, month: 'Feb', is_today: false, task_count: 0, total_minutes: 0 },
      ],
      events: [
        {
          id: 'event-1',
          type: 'assignment_due',
          title: 'Usability Heuristics',
          subtitle: 'Course A',
          date: '2026-02-22',
          start_time: '10:00',
          end_time: '10:45',
          color: 'rose',
          route: '/teacher/assignments',
        },
      ],
    } as any);

    mockedTeacherService.getGamificationSummary.mockResolvedValue({
      points_total: 320,
      points_breakdown: {
        content_completion: 120,
        course_completion: 40,
        assignment_submission: 100,
        streak_bonus: 55,
        quest_bonus: 5,
      },
      streak: { current_days: 5, target_days: 5 },
      quest: {
        key: 'streak_5_days',
        title: 'Log in 5 days straight',
        description: 'Complete a five day streak',
        reward_points: 5,
        progress_current: 5,
        progress_target: 5,
        completed: true,
        claimable: true,
        claimed_today: false,
      },
      badge_current: {
        level: 2,
        key: 'certified_teacher',
        name: 'Certified Teacher',
        ripple_range: '200-600',
        min_points: 200,
        max_points: 599,
        color: '#45B7D1',
        style: 'glass_3d',
      },
      badges: [
        {
          level: 1,
          key: 'associate_educator',
          name: 'Associate Educator',
          ripple_range: '0-200',
          min_points: 0,
          max_points: 199,
          color: '#4ECDC4',
          unlocked: true,
          progress_percentage: 100,
          style: 'glass_3d',
        },
        {
          level: 2,
          key: 'certified_teacher',
          name: 'Certified Teacher',
          ripple_range: '200-600',
          min_points: 200,
          max_points: 599,
          color: '#45B7D1',
          unlocked: true,
          progress_percentage: 61,
          style: 'glass_3d',
        },
      ],
    } as any);

    mockedNotificationService.getNotifications.mockResolvedValue([
      {
        id: 'notif-1',
        notification_type: 'ASSIGNMENT_DUE',
        title: 'Assignment due',
        message: 'Submit by tonight',
        is_read: false,
        is_actionable: true,
        created_at: '2026-02-22T10:00:00Z',
      },
    ] as any);
    mockedNotificationService.markAsRead.mockResolvedValue(undefined as any);
  });

  const renderPage = () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/teacher/dashboard']}>
          <Routes>
            <Route path="/teacher/dashboard" element={<DashboardPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  };

  it('renders lean essentials and removes legacy clutter', async () => {
    renderPage();

    expect(await screen.findByText(/welcome back, rakesh/i)).toBeInTheDocument();
    expect(await screen.findByText('Current State')).toBeInTheDocument();
    expect(await screen.findByText('5-Day Planner')).toBeInTheDocument();
    expect(await screen.findByText('To Do')).toBeInTheDocument();
    expect((await screen.findAllByText('Continue Learning')).length).toBeGreaterThan(0);

    expect(screen.queryByText('Daily Quest')).not.toBeInTheDocument();
    expect(screen.queryByText('Ripple Badges')).not.toBeInTheDocument();
    expect(screen.queryByText(/calm/i)).not.toBeInTheDocument();
  });

  it('marks actionable item as read from to-do list', async () => {
    renderPage();

    const markDoneButtons = await screen.findAllByTitle('Mark as done');
    await userEvent.click(markDoneButtons[0]);

    await waitFor(() => {
      expect(mockedNotificationService.markAsRead).toHaveBeenCalledWith('notif-1', expect.anything());
    });
  });
});
