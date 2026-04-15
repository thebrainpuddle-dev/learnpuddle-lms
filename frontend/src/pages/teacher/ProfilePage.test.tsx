import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ProfilePage } from './ProfilePage';
import { teacherService } from '../../services/teacherService';
import { useAuthStore } from '../../stores/authStore';

vi.mock('../../stores/authStore');
vi.mock('../../services/teacherService', () => ({
  teacherService: {
    getGamificationSummary: vi.fn(),
    claimQuestReward: vi.fn(),
  },
}));
vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    patch: vi.fn(),
  },
}));
vi.mock('../../components/tour', () => ({
  useGuidedTour: () => ({ startTour: vi.fn() }),
}));
vi.mock('../../components/common', async () => {
  const actual = await vi.importActual('../../components/common');
  return {
    ...actual,
    useToast: () => ({
      success: vi.fn(),
      error: vi.fn(),
    }),
  };
});

const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;
const mockedTeacherService = teacherService as unknown as { [K in keyof typeof teacherService]: ReturnType<typeof vi.fn> };

describe('ProfilePage achievements tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });

    mockedUseAuthStore.mockReturnValue({
      user: {
        first_name: 'Rakesh',
        last_name: 'Reddy',
        email: 'rakesh@example.com',
        role: 'TEACHER',
        subjects: [],
        grades: [],
      },
      setUser: vi.fn(),
    });

    mockedTeacherService.getGamificationSummary.mockResolvedValue({
      points_total: 340,
      points_breakdown: {
        content_completion: 100,
        course_completion: 80,
        assignment_submission: 100,
        streak_bonus: 55,
        quest_bonus: 5,
      },
      streak: { current_days: 5, target_days: 5 },
      quest: {
        key: 'streak_5_days',
        title: 'Log in 5 days straight',
        description: 'Consistency challenge',
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
        ripple_range: '200-600 RP',
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
          ripple_range: '0-200 RP',
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
          ripple_range: '200-600 RP',
          min_points: 200,
          max_points: 599,
          color: '#45B7D1',
          unlocked: true,
          progress_percentage: 52,
          style: 'glass_3d',
        },
      ],
    } as any);

    mockedTeacherService.claimQuestReward.mockResolvedValue({} as any);
  });

  const renderPage = () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    return render(
      <QueryClientProvider client={queryClient}>
        <ProfilePage />
      </QueryClientProvider>,
    );
  };

  it('renders achievements content when section is selected', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: 'Achievements' }));

    expect(await screen.findByText(/live journey sync/i)).toBeInTheDocument();
    expect(await screen.findByText(/fish \+ puddle state/i)).toBeInTheDocument();
    expect(await screen.findByLabelText(/learning state fish/i)).toBeInTheDocument();
    expect(screen.queryByText(/ripple badges/i)).not.toBeInTheDocument();
  });

  it('claims quest reward from achievements tab', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: 'Achievements' }));
    await userEvent.click(await screen.findByRole('button', { name: /claim reward/i }));

    await waitFor(() => {
      expect(mockedTeacherService.claimQuestReward).toHaveBeenCalledWith('streak_5_days');
    });
  });
});
