// src/pages/student/SettingsPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for the Student
// SettingsPage component.
//
// Covers:
//   - Page heading ("Settings") and subtitle
//   - Security section rendering and navigation to /student/settings/security
//   - Notifications section heading and description
//   - Loading state while preferences are fetching
//   - Error/fallback state (API failure — toggles default to off)
//   - All three notification toggle labels and descriptions render
//   - Toggle initial checked state reflects fetched prefs
//   - Toggling a switch calls api.patch with correct key/value
//   - Optimistic toggle update (switch flips immediately)
//   - Revert on PATCH failure
//   - Per-toggle saving state disables the button during in-flight request
//   - About section: App Version, Platform, Support email link
//   - Reconciling server response after successful PATCH
//
// Mocking strategy:
//   - api (axios instance) is mocked with vi.fn() stubs.
//   - useNavigate is replaced with a stable mockedUseNavigate spy.
//   - usePageTitle is stubbed to avoid document.title side-effects.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { SettingsPage } from './SettingsPage';
import api from '../../config/api';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ── Typed mock helpers ────────────────────────────────────────────────────────

const mockedApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
};

// ── Default fixtures ──────────────────────────────────────────────────────────

/** Preferences with all three tracked toggles explicitly set. */
const PREFS_ALL_OFF = {
  email_courses: false,
  email_assignments: false,
  email_reminders: false,
  in_app_courses: false,
  in_app_assignments: false,
  in_app_reminders: false,
  in_app_announcements: false,
  email_announcements: false,
};

const PREFS_ALL_ON = {
  email_courses: true,
  email_assignments: true,
  email_reminders: true,
  in_app_courses: true,
  in_app_assignments: true,
  in_app_reminders: true,
  in_app_announcements: true,
  email_announcements: true,
};

// ── Render helper ─────────────────────────────────────────────────────────────

const renderPage = () =>
  render(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedUseNavigate.mockReset();
    // Default: GET resolves immediately with all prefs off.
    mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
    // Default: PATCH echoes back all prefs off.
    mockedApi.patch.mockResolvedValue({ data: PREFS_ALL_OFF });
  });

  // ── 1. Page heading ──────────────────────────────────────────────────────────

  describe('page heading', () => {
    it('renders "Settings" h1 heading', async () => {
      renderPage();
      expect(
        screen.getByRole('heading', { level: 1, name: /^settings$/i }),
      ).toBeInTheDocument();
    });

    it('renders subtitle describing the settings page purpose', async () => {
      renderPage();
      expect(
        screen.getByText(/manage your account security, notification preferences/i),
      ).toBeInTheDocument();
    });
  });

  // ── 2. Security section ──────────────────────────────────────────────────────

  describe('security section', () => {
    it('renders "Security" section heading', async () => {
      renderPage();
      expect(
        screen.getByRole('heading', { level: 2, name: /^security$/i }),
      ).toBeInTheDocument();
    });

    it('renders security section description', async () => {
      renderPage();
      expect(
        screen.getByText(/manage your password and account security settings/i),
      ).toBeInTheDocument();
    });

    it('renders "Password & Authentication" row label', async () => {
      renderPage();
      expect(screen.getByText(/password & authentication/i)).toBeInTheDocument();
    });

    it('renders "Change your password, enable two-factor authentication" row subtitle', async () => {
      renderPage();
      expect(
        screen.getByText(/change your password, enable two-factor authentication/i),
      ).toBeInTheDocument();
    });

    it('clicking the security row navigates to /student/settings/security', async () => {
      renderPage();
      await userEvent.click(screen.getByRole('button', { name: /password & authentication/i }));
      expect(mockedUseNavigate).toHaveBeenCalledWith('/student/settings/security');
    });
  });

  // ── 3. Notifications section — structure ─────────────────────────────────────

  describe('notifications section structure', () => {
    it('renders "Notifications" section heading', async () => {
      renderPage();
      expect(
        screen.getByRole('heading', { level: 2, name: /^notifications$/i }),
      ).toBeInTheDocument();
    });

    it('renders notifications section description', async () => {
      renderPage();
      expect(
        screen.getByText(/choose what notifications you would like to receive/i),
      ).toBeInTheDocument();
    });
  });

  // ── 4. Loading state ─────────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows loading spinner while preferences are being fetched', () => {
      // GET never resolves — component stays in loading state.
      mockedApi.get.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByText(/loading preferences/i)).toBeInTheDocument();
    });

    it('hides toggle rows while loading', () => {
      mockedApi.get.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    });

    it('hides loading spinner once preferences load', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.queryByText(/loading preferences/i)).not.toBeInTheDocument();
      });
    });
  });

  // ── 5. Fallback on API error ─────────────────────────────────────────────────

  describe('fallback on API error', () => {
    it('shows toggle rows even when GET fails (defaults all to off)', async () => {
      mockedApi.get.mockRejectedValue(new Error('Network error'));
      renderPage();

      // All three switches should appear in the off state.
      await waitFor(() => {
        const switches = screen.getAllByRole('switch');
        expect(switches).toHaveLength(3);
        switches.forEach((sw) => {
          expect(sw).toHaveAttribute('aria-checked', 'false');
        });
      });
    });
  });

  // ── 6. Toggle labels and descriptions ───────────────────────────────────────

  describe('notification toggle rows', () => {
    beforeEach(async () => {
      renderPage();
      // Wait for loading to finish.
      await waitFor(() => {
        expect(screen.queryByText(/loading preferences/i)).not.toBeInTheDocument();
      });
    });

    it('renders "Course Updates" toggle label', () => {
      expect(screen.getByText('Course Updates')).toBeInTheDocument();
    });

    it('renders Course Updates description', () => {
      expect(
        screen.getByText(/get notified when new courses or content are available/i),
      ).toBeInTheDocument();
    });

    it('renders "Assignment Reminders" toggle label', () => {
      expect(screen.getByText('Assignment Reminders')).toBeInTheDocument();
    });

    it('renders Assignment Reminders description', () => {
      expect(
        screen.getByText(/receive reminders for upcoming assignments and deadlines/i),
      ).toBeInTheDocument();
    });

    it('renders "General Reminders" toggle label', () => {
      expect(screen.getByText('General Reminders')).toBeInTheDocument();
    });

    it('renders General Reminders description', () => {
      expect(
        screen.getByText(/get notified about general reminders and updates/i),
      ).toBeInTheDocument();
    });

    it('renders exactly three toggle switches', () => {
      expect(screen.getAllByRole('switch')).toHaveLength(3);
    });
  });

  // ── 7. Initial toggle state reflects fetched prefs ───────────────────────────

  describe('initial toggle checked state', () => {
    it('all switches are aria-checked=false when prefs are all off', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      renderPage();

      await waitFor(() => {
        const switches = screen.getAllByRole('switch');
        switches.forEach((sw) => {
          expect(sw).toHaveAttribute('aria-checked', 'false');
        });
      });
    });

    it('all switches are aria-checked=true when prefs are all on', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_ON });
      renderPage();

      await waitFor(() => {
        const switches = screen.getAllByRole('switch');
        switches.forEach((sw) => {
          expect(sw).toHaveAttribute('aria-checked', 'true');
        });
      });
    });

    it('individual switch reflects its specific pref value', async () => {
      mockedApi.get.mockResolvedValue({
        data: { ...PREFS_ALL_OFF, email_courses: true },
      });
      renderPage();

      await waitFor(() => {
        const switches = screen.getAllByRole('switch');
        // The first switch rendered is email_courses (Course Updates).
        expect(switches[0]).toHaveAttribute('aria-checked', 'true');
        expect(switches[1]).toHaveAttribute('aria-checked', 'false');
        expect(switches[2]).toHaveAttribute('aria-checked', 'false');
      });
    });
  });

  // ── 8. Toggling calls api.patch ──────────────────────────────────────────────

  describe('toggle interaction — PATCH call', () => {
    it('clicking Course Updates switch calls api.patch with email_courses: true when off', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      mockedApi.patch.mockResolvedValue({ data: { ...PREFS_ALL_OFF, email_courses: true } });

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const [courseUpdatesSwitch] = screen.getAllByRole('switch');
      await userEvent.click(courseUpdatesSwitch);

      await waitFor(() => {
        expect(mockedApi.patch).toHaveBeenCalledWith('/users/auth/preferences/', {
          email_courses: true,
        });
      });
    });

    it('clicking Course Updates switch calls api.patch with email_courses: false when on', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_ON });
      mockedApi.patch.mockResolvedValue({ data: { ...PREFS_ALL_ON, email_courses: false } });

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const [courseUpdatesSwitch] = screen.getAllByRole('switch');
      await userEvent.click(courseUpdatesSwitch);

      await waitFor(() => {
        expect(mockedApi.patch).toHaveBeenCalledWith('/users/auth/preferences/', {
          email_courses: false,
        });
      });
    });

    it('clicking Assignment Reminders switch calls api.patch with email_assignments', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      mockedApi.patch.mockResolvedValue({ data: { ...PREFS_ALL_OFF, email_assignments: true } });

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const switches = screen.getAllByRole('switch');
      await userEvent.click(switches[1]); // email_assignments is second

      await waitFor(() => {
        expect(mockedApi.patch).toHaveBeenCalledWith('/users/auth/preferences/', {
          email_assignments: true,
        });
      });
    });

    it('clicking General Reminders switch calls api.patch with email_reminders', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      mockedApi.patch.mockResolvedValue({ data: { ...PREFS_ALL_OFF, email_reminders: true } });

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const switches = screen.getAllByRole('switch');
      await userEvent.click(switches[2]); // email_reminders is third

      await waitFor(() => {
        expect(mockedApi.patch).toHaveBeenCalledWith('/users/auth/preferences/', {
          email_reminders: true,
        });
      });
    });
  });

  // ── 9. Optimistic update ─────────────────────────────────────────────────────

  describe('optimistic toggle update', () => {
    it('switch flips to aria-checked=true immediately before PATCH resolves', async () => {
      // PATCH will never resolve — we only check the optimistic flip.
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      mockedApi.patch.mockReturnValue(new Promise(() => {}));

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const [courseUpdatesSwitch] = screen.getAllByRole('switch');
      expect(courseUpdatesSwitch).toHaveAttribute('aria-checked', 'false');

      await userEvent.click(courseUpdatesSwitch);

      // Optimistic: should be true immediately.
      expect(courseUpdatesSwitch).toHaveAttribute('aria-checked', 'true');
    });
  });

  // ── 10. Revert on PATCH failure ──────────────────────────────────────────────

  describe('revert on PATCH failure', () => {
    it('reverts the switch back to its original state when PATCH rejects', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      mockedApi.patch.mockRejectedValue(new Error('Server error'));

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const [courseUpdatesSwitch] = screen.getAllByRole('switch');

      await userEvent.click(courseUpdatesSwitch);

      // After the rejection settles the switch should revert to false.
      await waitFor(() => {
        expect(courseUpdatesSwitch).toHaveAttribute('aria-checked', 'false');
      });
    });
  });

  // ── 11. Saving state disables the switch ─────────────────────────────────────

  describe('per-toggle saving/disabled state', () => {
    it('disables the switch while its PATCH request is in-flight', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      // Return a never-resolving promise so the saving state persists.
      mockedApi.patch.mockReturnValue(new Promise(() => {}));

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const [courseUpdatesSwitch] = screen.getAllByRole('switch');
      await userEvent.click(courseUpdatesSwitch);

      expect(courseUpdatesSwitch).toBeDisabled();
    });

    it('re-enables the switch after PATCH resolves', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      mockedApi.patch.mockResolvedValue({ data: { ...PREFS_ALL_OFF, email_courses: true } });

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const [courseUpdatesSwitch] = screen.getAllByRole('switch');
      await userEvent.click(courseUpdatesSwitch);

      await waitFor(() => {
        expect(courseUpdatesSwitch).not.toBeDisabled();
      });
    });

    it('does not disable sibling switches while one is saving', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      mockedApi.patch.mockReturnValue(new Promise(() => {}));

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const switches = screen.getAllByRole('switch');
      await userEvent.click(switches[0]); // click email_courses

      // The other switches (index 1 and 2) should not be disabled.
      expect(switches[1]).not.toBeDisabled();
      expect(switches[2]).not.toBeDisabled();
    });
  });

  // ── 12. Server reconciliation after PATCH ────────────────────────────────────

  describe('server reconciliation', () => {
    it('applies the server response data after a successful PATCH', async () => {
      mockedApi.get.mockResolvedValue({ data: PREFS_ALL_OFF });
      // Server sends back a slightly different state (e.g., also enables in_app_courses).
      mockedApi.patch.mockResolvedValue({
        data: { ...PREFS_ALL_OFF, email_courses: true, in_app_courses: true },
      });

      renderPage();
      await waitFor(() => screen.getAllByRole('switch'));

      const [courseUpdatesSwitch] = screen.getAllByRole('switch');
      await userEvent.click(courseUpdatesSwitch);

      await waitFor(() => {
        expect(courseUpdatesSwitch).toHaveAttribute('aria-checked', 'true');
        expect(courseUpdatesSwitch).not.toBeDisabled();
      });
    });
  });

  // ── 13. About section ────────────────────────────────────────────────────────

  describe('about section', () => {
    it('renders "About" section heading', async () => {
      renderPage();
      expect(
        screen.getByRole('heading', { level: 2, name: /^about$/i }),
      ).toBeInTheDocument();
    });

    it('renders App Version row with value "1.0.0"', async () => {
      renderPage();
      expect(screen.getByText('App Version')).toBeInTheDocument();
      expect(screen.getByText('1.0.0')).toBeInTheDocument();
    });

    it('renders Platform row with value "LearnPuddle LMS"', async () => {
      renderPage();
      expect(screen.getByText('Platform')).toBeInTheDocument();
      expect(screen.getByText('LearnPuddle LMS')).toBeInTheDocument();
    });

    it('renders Support row with a mailto link to support@learnpuddle.com', async () => {
      renderPage();
      const link = screen.getByRole('link', { name: /support@learnpuddle\.com/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', 'mailto:support@learnpuddle.com');
    });
  });

  // ── 14. GET call ─────────────────────────────────────────────────────────────

  describe('initial data fetch', () => {
    it('calls api.get on /users/auth/preferences/ on mount', async () => {
      renderPage();
      await waitFor(() => {
        expect(mockedApi.get).toHaveBeenCalledWith('/users/auth/preferences/');
      });
    });

    it('calls api.get exactly once on initial mount', async () => {
      renderPage();
      await waitFor(() => {
        expect(mockedApi.get).toHaveBeenCalledTimes(1);
      });
    });
  });
});
