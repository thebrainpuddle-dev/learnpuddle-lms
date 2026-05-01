// src/pages/onboarding/SignupPage.test.tsx
//
// Vitest + React Testing Library tests for SignupPage.
// Covers: rendering, progress indicator, step validation, step navigation,
// subdomain preview, plan selection, form submission, success state, and
// server-side error handling.

import React from 'react';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SignupPage } from './SignupPage';
import api from '../../config/api';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

const mockApiGet = api.get as ReturnType<typeof vi.fn>;
const mockApiPost = api.post as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

const MOCK_PLANS = [
  {
    id: 'FREE',
    name: 'Free',
    price: 0,
    price_yearly: 0,
    max_teachers: 5,
    max_courses: 3,
    max_storage_mb: 500,
    features: ['Up to 5 teachers', '3 courses'],
    recommended: false,
  },
  {
    id: 'PRO',
    name: 'Pro',
    price: 49,
    price_yearly: 490,
    max_teachers: 50,
    max_courses: 50,
    max_storage_mb: 10000,
    features: ['Up to 50 teachers', 'Unlimited courses'],
    recommended: true,
  },
];

function renderPage(queryClient?: QueryClient) {
  const client = queryClient ?? makeQueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/signup']}>
        <SignupPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Fill step 1 with a valid school name and advance to step 2. */
async function advanceToStep2(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText(/school name/i), 'Demo School');
  await user.click(screen.getByRole('button', { name: /continue/i }));
  await screen.findByText(/create admin account/i);
}

/** Fill step 2 with valid admin details and advance to step 3. */
async function advanceToStep3(user: ReturnType<typeof userEvent.setup>) {
  await advanceToStep2(user);
  await user.type(screen.getByLabelText(/first name/i), 'Jane');
  await user.type(screen.getByLabelText(/last name/i), 'Doe');
  await user.type(screen.getByLabelText(/^email$/i), 'jane@school.com');
  await user.type(screen.getByLabelText(/^password$/i), 'Strongpass1!');
  await user.type(screen.getByLabelText(/confirm password/i), 'Strongpass1!');
  await user.click(screen.getByRole('button', { name: /continue/i }));
  await screen.findByText(/choose your plan/i);
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SignupPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Plans query fires on mount; return empty list by default to avoid errors.
    mockApiGet.mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
    cleanup();
  });

  // ── 1. Rendering ────────────────────────────────────────────────────────────

  describe('initial rendering (step 1)', () => {
    it('renders the LearnPuddle header link pointing to /', () => {
      renderPage();
      const logoLink = screen.getByRole('link', { name: /learnpuddle/i });
      expect(logoLink).toBeInTheDocument();
      expect(logoLink).toHaveAttribute('href', '/');
    });

    it('renders "Already have an account? Sign in" link pointing to /login', () => {
      renderPage();
      const signInLink = screen.getByRole('link', { name: /already have an account\? sign in/i });
      expect(signInLink).toBeInTheDocument();
      expect(signInLink).toHaveAttribute('href', '/login');
    });

    it('renders the step 1 heading "Create your school\'s LMS"', () => {
      renderPage();
      expect(
        screen.getByRole('heading', { name: /create your school's lms/i }),
      ).toBeInTheDocument();
    });

    it('renders the School Name input field', () => {
      renderPage();
      expect(screen.getByLabelText(/school name/i)).toBeInTheDocument();
    });

    it('renders a "Continue" button on step 1', () => {
      renderPage();
      expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();
    });
  });

  // ── 2. Progress indicator ───────────────────────────────────────────────────

  describe('progress indicator', () => {
    it('shows "1" as the active step on initial render', () => {
      renderPage();
      // Step numbers are rendered as text nodes inside div circles
      expect(screen.getByText('1')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
    });

    it('shows step labels: School Info, Admin Account, Select Plan', () => {
      renderPage();
      expect(screen.getByText('School Info')).toBeInTheDocument();
      expect(screen.getByText('Admin Account')).toBeInTheDocument();
      expect(screen.getByText('Select Plan')).toBeInTheDocument();
    });

    it('no longer shows "1" as a text node after advancing to step 2 (replaced by checkmark)', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      // Step 1 circle now renders <CheckCircleIcon> instead of the number "1"
      expect(screen.queryByText('1')).not.toBeInTheDocument();
    });
  });

  // ── 3. Step 1 validation ────────────────────────────────────────────────────

  describe('step 1 validation', () => {
    it('shows "School name must be at least 3 characters" when Next is clicked with empty name', async () => {
      const user = userEvent.setup();
      renderPage();
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(
        await screen.findByText(/school name must be at least 3 characters/i),
      ).toBeInTheDocument();
    });

    it('shows the same error when school name is only 2 characters', async () => {
      const user = userEvent.setup();
      renderPage();
      await user.type(screen.getByLabelText(/school name/i), 'AB');
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(
        await screen.findByText(/school name must be at least 3 characters/i),
      ).toBeInTheDocument();
    });

    it('does not advance to step 2 when school name is too short', async () => {
      const user = userEvent.setup();
      renderPage();
      await user.type(screen.getByLabelText(/school name/i), 'AB');
      await user.click(screen.getByRole('button', { name: /continue/i }));
      await screen.findByText(/school name must be at least 3 characters/i);
      expect(screen.queryByText(/create admin account/i)).not.toBeInTheDocument();
    });
  });

  // ── 4. Step 1 → Step 2 navigation ──────────────────────────────────────────

  describe('step 1 → step 2 navigation', () => {
    it('shows "Create admin account" heading after typing a valid school name and clicking Continue', async () => {
      const user = userEvent.setup();
      renderPage();
      await user.type(screen.getByLabelText(/school name/i), 'Demo School');
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(await screen.findByText(/create admin account/i)).toBeInTheDocument();
    });

    it('hides the step 1 heading after advancing to step 2', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      expect(screen.queryByText(/create your school's lms/i)).not.toBeInTheDocument();
    });
  });

  // ── 5. Subdomain preview ────────────────────────────────────────────────────

  describe('subdomain preview', () => {
    it('calls api.get with the check-subdomain endpoint after typing 3+ chars (real timers)', async () => {
      // Use real timers: just type and await the debounced call naturally
      mockApiGet
        .mockResolvedValueOnce({ data: [] }) // plans query
        .mockResolvedValueOnce({ data: { suggested_subdomain: 'demo-school' } });

      const user = userEvent.setup();
      renderPage();
      await user.type(screen.getByLabelText(/school name/i), 'Dem');

      await waitFor(
        () => {
          const subdomainCalls = mockApiGet.mock.calls.filter((args) =>
            String(args[0]).includes('check-subdomain'),
          );
          expect(subdomainCalls).toHaveLength(1);
        },
        { timeout: 2000 },
      );

      expect(mockApiGet).toHaveBeenCalledWith(
        expect.stringContaining('/onboarding/check-subdomain/'),
      );
    });

    it('displays the suggested subdomain URL after the debounced check resolves', async () => {
      mockApiGet
        .mockResolvedValueOnce({ data: [] }) // plans query
        .mockResolvedValueOnce({ data: { suggested_subdomain: 'demo-school' } });

      const user = userEvent.setup();
      renderPage();
      await user.type(screen.getByLabelText(/school name/i), 'Dem');

      // Wait for the subdomain text to appear (after debounce + mutation resolves)
      await waitFor(
        () => expect(screen.getByText(/demo-school/i)).toBeInTheDocument(),
        { timeout: 2000 },
      );
    });

    it('does not call the subdomain check when school name is fewer than 3 characters', async () => {
      mockApiGet.mockResolvedValue({ data: [] }); // only plans

      const user = userEvent.setup();
      renderPage();
      // Mount fires the plans query; wait for it to settle
      await waitFor(() => expect(mockApiGet).toHaveBeenCalledTimes(1));

      await user.type(screen.getByLabelText(/school name/i), 'AB');

      // Advance past the debounce window using real timers — just wait a bit
      await new Promise((r) => setTimeout(r, 700));

      const subdomainCalls = mockApiGet.mock.calls.filter((args) =>
        String(args[0]).includes('check-subdomain'),
      );
      expect(subdomainCalls).toHaveLength(0);
    });
  });

  // ── 6. Step 2 rendering ─────────────────────────────────────────────────────

  describe('step 2 rendering', () => {
    it('renders First Name field', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
    });

    it('renders Last Name field', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
    });

    it('renders Email field', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();
    });

    it('renders Password field', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    });

    it('renders Confirm Password field', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    });

    it('renders Back and Continue buttons on step 2', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /continue/i })).toBeInTheDocument();
    });
  });

  // ── 7. Step 2 validation ────────────────────────────────────────────────────

  describe('step 2 validation', () => {
    it('shows email error when email field is empty', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(await screen.findByText(/email is required/i)).toBeInTheDocument();
    });

    it('shows invalid email error when email format is wrong', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      await user.type(screen.getByLabelText(/^email$/i), 'not-an-email');
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(await screen.findByText(/invalid email format/i)).toBeInTheDocument();
    });

    it('shows "Passwords do not match" error when passwords differ', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      await user.type(screen.getByLabelText(/first name/i), 'Jane');
      await user.type(screen.getByLabelText(/last name/i), 'Doe');
      await user.type(screen.getByLabelText(/^email$/i), 'jane@school.com');
      await user.type(screen.getByLabelText(/^password$/i), 'Strongpass1!');
      await user.type(screen.getByLabelText(/confirm password/i), 'DifferentPass!');
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(await screen.findByText(/passwords do not match/i)).toBeInTheDocument();
    });

    it('shows password min-length error when password is too short', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      await user.type(screen.getByLabelText(/^password$/i), 'short');
      await user.click(screen.getByRole('button', { name: /continue/i }));
      expect(
        await screen.findByText(/password must be at least 8 characters/i),
      ).toBeInTheDocument();
    });

    it('does not advance to step 3 when step 2 validation fails', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      // Click Continue without filling anything
      await user.click(screen.getByRole('button', { name: /continue/i }));
      await screen.findByText(/email is required/i);
      expect(screen.queryByText(/choose your plan/i)).not.toBeInTheDocument();
    });
  });

  // ── 8. Step 2 → Step 3 navigation ──────────────────────────────────────────

  describe('step 2 → step 3 navigation', () => {
    it('advances to step 3 when all step 2 fields are filled correctly', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      expect(screen.getByRole('heading', { name: /choose your plan/i })).toBeInTheDocument();
    });
  });

  // ── 9. Back button ──────────────────────────────────────────────────────────

  describe('back button', () => {
    it('returns to step 1 when Back is clicked on step 2', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep2(user);
      await user.click(screen.getByRole('button', { name: /back/i }));
      expect(screen.getByRole('heading', { name: /create your school's lms/i })).toBeInTheDocument();
    });

    it('returns to step 2 when Back is clicked on step 3', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      await user.click(screen.getByRole('button', { name: /back/i }));
      expect(screen.getByRole('heading', { name: /create admin account/i })).toBeInTheDocument();
    });
  });

  // ── 10. Step 3 rendering ────────────────────────────────────────────────────

  describe('step 3 rendering', () => {
    it('shows plan cards from API when plans are loaded', async () => {
      mockApiGet.mockResolvedValue({ data: MOCK_PLANS });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      expect(await screen.findByText('Free')).toBeInTheDocument();
      expect(screen.getByText('Pro')).toBeInTheDocument();
    });

    it('shows "Create Account" submit button on step 3', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
    });

    it('shows Back button on step 3', async () => {
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
    });

    it('shows the "Recommended" badge on the recommended plan', async () => {
      mockApiGet.mockResolvedValue({ data: MOCK_PLANS });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      expect(await screen.findByText('Recommended')).toBeInTheDocument();
    });

    it('shows plan pricing', async () => {
      mockApiGet.mockResolvedValue({ data: MOCK_PLANS });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      expect(await screen.findByText('$49')).toBeInTheDocument();
    });
  });

  // ── 11. Plan selection ──────────────────────────────────────────────────────

  describe('plan selection', () => {
    it('changes the selected plan when a plan card is clicked', async () => {
      mockApiGet.mockResolvedValue({ data: MOCK_PLANS });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);

      const proPlanCard = (await screen.findByText('Pro')).closest('[class*="rounded-xl"]')!;
      await user.click(proPlanCard);

      // After clicking, the PRO plan card should have the selected border style
      await waitFor(() => {
        expect(proPlanCard.className).toMatch(/border-primary-600/);
      });
    });
  });

  // ── 12. Form submission ─────────────────────────────────────────────────────

  describe('form submission', () => {
    const SIGNUP_RESPONSE = {
      message: 'Your school is being set up!',
      login_url: 'https://demo-school.learnpuddle.com/login',
    };

    it('calls api.post with the correct payload (no confirm_password) on submit', async () => {
      mockApiPost.mockResolvedValue({ data: SIGNUP_RESPONSE });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);

      await user.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalledWith(
          '/onboarding/signup/',
          expect.objectContaining({
            school_name: 'Demo School',
            admin_email: 'jane@school.com',
            admin_first_name: 'Jane',
            admin_last_name: 'Doe',
            admin_password: 'Strongpass1!',
            plan: 'FREE',
          }),
        );
      });

      // confirm_password must NOT be in the payload
      const [, postedPayload] = mockApiPost.mock.calls[0];
      expect(postedPayload).not.toHaveProperty('confirm_password');
    });
  });

  // ── 13. Success state (step 4) ──────────────────────────────────────────────

  describe('success state', () => {
    const SIGNUP_RESPONSE = {
      message: 'Your school is being set up!',
      login_url: 'https://demo-school.learnpuddle.com/login',
    };

    it('shows "Account Created!" heading after successful signup', async () => {
      mockApiPost.mockResolvedValue({ data: SIGNUP_RESPONSE });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      await user.click(screen.getByRole('button', { name: /create account/i }));
      expect(await screen.findByRole('heading', { name: /account created!/i })).toBeInTheDocument();
    });

    it('displays the success message from the server response', async () => {
      mockApiPost.mockResolvedValue({ data: SIGNUP_RESPONSE });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      await user.click(screen.getByRole('button', { name: /create account/i }));
      expect(await screen.findByText('Your school is being set up!')).toBeInTheDocument();
    });

    it('shows the school login URL from the server response', async () => {
      mockApiPost.mockResolvedValue({ data: SIGNUP_RESPONSE });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      await user.click(screen.getByRole('button', { name: /create account/i }));
      expect(
        await screen.findByText('https://demo-school.learnpuddle.com/login'),
      ).toBeInTheDocument();
    });

    it('shows "Go to Login" link after successful signup', async () => {
      mockApiPost.mockResolvedValue({ data: SIGNUP_RESPONSE });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      await user.click(screen.getByRole('button', { name: /create account/i }));
      await screen.findByRole('heading', { name: /account created!/i });
      expect(
        screen.getByRole('link', { name: /go to login/i }),
      ).toBeInTheDocument();
    });
  });

  // ── 14. Server-side errors ──────────────────────────────────────────────────

  describe('server-side errors', () => {
    it('displays a field-level server error on the email field', async () => {
      mockApiPost.mockRejectedValue({
        response: {
          data: {
            errors: { admin_email: 'Already registered.' },
          },
        },
      });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      await user.click(screen.getByRole('button', { name: /create account/i }));

      // After server error, user clicks Back to step 2 where the error is shown
      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalled();
      });

      // The error is set on the form field; navigate back to step 2 to see it
      await user.click(screen.getByRole('button', { name: /back/i }));
      expect(await screen.findByText('Already registered.')).toBeInTheDocument();
    });

    it('displays field-level server error when error value is an array', async () => {
      mockApiPost.mockRejectedValue({
        response: {
          data: {
            errors: { admin_email: ['This email is already in use.'] },
          },
        },
      });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      await user.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalled();
      });

      await user.click(screen.getByRole('button', { name: /back/i }));
      expect(await screen.findByText('This email is already in use.')).toBeInTheDocument();
    });

    it('does not advance to success state on server error', async () => {
      mockApiPost.mockRejectedValue({
        response: {
          data: {
            errors: { admin_email: 'Already registered.' },
          },
        },
      });
      const user = userEvent.setup();
      renderPage();
      await advanceToStep3(user);
      await user.click(screen.getByRole('button', { name: /create account/i }));

      await waitFor(() => {
        expect(mockApiPost).toHaveBeenCalled();
      });

      expect(screen.queryByRole('heading', { name: /account created!/i })).not.toBeInTheDocument();
    });
  });
});
