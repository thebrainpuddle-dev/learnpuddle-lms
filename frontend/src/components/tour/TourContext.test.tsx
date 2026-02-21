import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation, useNavigationType } from 'react-router-dom';
import { TourProvider } from './TourContext';
import type { TourStep } from './types';
import { TOUR_STEPS } from './tourConfig';
import { useAuthStore } from '../../stores/authStore';

jest.mock('../../stores/authStore');

jest.mock('./tourConfig', () => ({
  TOUR_STEPS: {
    SUPER_ADMIN: [],
    SCHOOL_ADMIN: [],
    TEACHER: [],
  },
}));

const mockedUseAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;
const mockedTourSteps = TOUR_STEPS as Record<'SUPER_ADMIN' | 'SCHOOL_ADMIN' | 'TEACHER', TourStep[]>;

const LocationProbe: React.FC = () => {
  const location = useLocation();
  const navType = useNavigationType();
  return (
    <div>
      <span data-testid="pathname">{location.pathname}</span>
      <span data-testid="search">{location.search}</span>
      <span data-testid="nav-type">{navType}</span>
    </div>
  );
};

const DashboardPage: React.FC<{ showSecondTarget?: boolean }> = ({ showSecondTarget = false }) => (
  <div>
    <LocationProbe />
    <div id="primary-target">Primary target</div>
    {showSecondTarget && <div id="second-target">Second target</div>}
  </div>
);

describe('TourContext', () => {
  beforeAll(() => {
    Object.defineProperty(window, 'ResizeObserver', {
      writable: true,
      value: class {
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    });

    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      writable: true,
      value: jest.fn(),
    });
  });

  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    jest.clearAllMocks();

    mockedTourSteps.SUPER_ADMIN = [];
    mockedTourSteps.SCHOOL_ADMIN = [];
    mockedTourSteps.TEACHER = [];

    mockedUseAuthStore.mockReturnValue({
      user: {
        id: 'user-1',
        role: 'SCHOOL_ADMIN',
      } as any,
      accessToken: 'token-a',
      refreshToken: 'refresh-a',
      isAuthenticated: true,
      isLoading: false,
      setAuth: jest.fn(),
      clearAuth: jest.fn(),
      setUser: jest.fn(),
      setLoading: jest.fn(),
      initializeFromStorage: jest.fn(),
    });
  });

  const renderTour = (initialPath = '/admin/dashboard', showSecondTarget = false) =>
    render(
      <MemoryRouter initialEntries={[initialPath]}>
        <TourProvider>
          <Routes>
            <Route path="*" element={<DashboardPage showSecondTarget={showSecondTarget} />} />
          </Routes>
        </TourProvider>
      </MemoryRouter>
    );

  it('does not auto-start when a legacy completion key exists', async () => {
    mockedTourSteps.SCHOOL_ADMIN = [
      {
        id: 'legacy-check',
        title: 'Legacy check',
        description: 'Should not open when legacy completion exists.',
        path: '/admin/dashboard',
        selector: '#primary-target',
      },
    ];

    localStorage.setItem('lms:tour:completed:user-1:SCHOOL_ADMIN:legacy-token-suffix', '1');

    renderTour();

    await waitFor(() => {
      expect(screen.queryByText('Legacy check')).not.toBeInTheDocument();
    });
  });

  it('pauses on missing selector instead of auto-skipping optional steps', async () => {
    mockedTourSteps.SCHOOL_ADMIN = [
      {
        id: 'missing-step',
        title: 'Missing element step',
        description: 'Wait for a selector that does not exist.',
        path: '/admin/dashboard',
        selector: '#does-not-exist',
        optional: true,
        waitMs: 30,
      },
      {
        id: 'second-step',
        title: 'Second step',
        description: 'This step should only render after manual next.',
        path: '/admin/dashboard',
        selector: '#second-target',
      },
    ];

    renderTour('/admin/dashboard', true);

    expect(await screen.findByText('Missing element step')).toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.getByText("Couldn't locate this element yet. Complete page load or click Next to continue.")
      ).toBeInTheDocument();
    });

    expect(screen.queryByText('Second step')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    expect(await screen.findByText('Second step')).toBeInTheDocument();
  });

  it('uses replace navigation for tour-driven route transitions', async () => {
    mockedTourSteps.SCHOOL_ADMIN = [
      {
        id: 'route-step',
        title: 'Route step',
        description: 'Navigate to another route.',
        path: '/admin/reports',
      },
    ];

    renderTour('/admin/dashboard');

    await waitFor(() => {
      expect(screen.getByTestId('pathname')).toHaveTextContent('/admin/reports');
    });

    expect(screen.getByTestId('nav-type')).toHaveTextContent('REPLACE');
  });

  it('pauses automatic routing when navigation burst threshold is exceeded', async () => {
    let routeCounter = 0;

    mockedTourSteps.SCHOOL_ADMIN = [
      {
        id: 'burst-step',
        title: 'Burst step',
        description: 'Force repeated route changes to validate guardrails.',
        path: () => `/admin/loop-${routeCounter++}`,
      },
    ];

    renderTour('/admin/dashboard');

    await waitFor(
      () => {
        expect(
          screen.getByText(
            'Automatic tour navigation paused to avoid rapid route changes. Use Next or Back to continue manually.'
          )
        ).toBeInTheDocument();
      },
      { timeout: 6000 }
    );
  });
});
