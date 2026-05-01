// src/pages/auth/SuperAdminLoginPage.test.tsx
//
// Vitest + React Testing Library tests for SuperAdminLoginPage.
// Covers: rendering, successful login, role guard, error states, and logout-reason banners.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    // useSearchParams is provided by MemoryRouter; we override per-test via initialEntries
  };
});

vi.mock('../../stores/authStore', () => ({
  useAuthStore: vi.fn(),
}));

vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { useAuthStore } from '../../stores/authStore';
import api from '../../config/api';
import { SuperAdminLoginPage } from './SuperAdminLoginPage';

const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;
const mockedApi = api as unknown as { post: ReturnType<typeof vi.fn> };

// ── Helpers ───────────────────────────────────────────────────────────────────

const mockSetAuth = vi.fn();
const mockSetLoading = vi.fn();

function renderPage(search = '') {
  return render(
    <MemoryRouter initialEntries={[`/super-admin/login${search}`]}>
      <SuperAdminLoginPage />
    </MemoryRouter>,
  );
}

async function fillAndSubmit(email = 'admin@lms.com', password = 'Secret123!') {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/email address/i), email);
  await user.type(screen.getByLabelText(/password/i), password);
  await user.click(screen.getByRole('button', { name: /sign in to command center/i }));
  return user;
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SuperAdminLoginPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedUseAuthStore.mockReturnValue({
      setAuth: mockSetAuth,
      setLoading: mockSetLoading,
    });
  });

  // ── 1. Rendering ──────────────────────────────────────────────────────────

  describe('rendering', () => {
    it('renders the "Command Center" heading', () => {
      renderPage();
      expect(screen.getByText('Command Center')).toBeInTheDocument();
    });

    it('renders the "LearnPuddle Platform Administration" subtitle', () => {
      renderPage();
      expect(screen.getByText('LearnPuddle Platform Administration')).toBeInTheDocument();
    });

    it('renders the email input with id "superadmin-email"', () => {
      renderPage();
      expect(document.getElementById('superadmin-email')).toBeInTheDocument();
    });

    it('renders the password input with id "superadmin-password"', () => {
      renderPage();
      expect(document.getElementById('superadmin-password')).toBeInTheDocument();
    });

    it('renders the "Sign In to Command Center" button', () => {
      renderPage();
      expect(
        screen.getByRole('button', { name: /sign in to command center/i }),
      ).toBeInTheDocument();
    });

    it('renders the "Go to school login" link', () => {
      renderPage();
      expect(screen.getByRole('link', { name: /go to school login/i })).toBeInTheDocument();
    });

    it('does not show any banner by default', () => {
      renderPage();
      expect(screen.queryByText(/signed out after/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/session expired/i)).not.toBeInTheDocument();
    });
  });

  // ── 2. Successful login ───────────────────────────────────────────────────

  describe('successful SUPER_ADMIN login', () => {
    it('calls api.post with correct payload including portal:super_admin', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          user: { id: '1', email: 'admin@lms.com', role: 'SUPER_ADMIN' },
          tokens: { access: 'acc', refresh: 'ref' },
        },
      });
      renderPage();
      await fillAndSubmit();
      await waitFor(() => {
        expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/login/', {
          email: 'admin@lms.com',
          password: 'Secret123!',
          portal: 'super_admin',
        });
      });
    });

    it('calls setAuth with user and tokens on success', async () => {
      const user = { id: '1', email: 'admin@lms.com', role: 'SUPER_ADMIN' };
      const tokens = { access: 'acc', refresh: 'ref' };
      mockedApi.post.mockResolvedValueOnce({ data: { user, tokens } });
      renderPage();
      await fillAndSubmit();
      await waitFor(() => {
        expect(mockSetAuth).toHaveBeenCalledWith(user, tokens);
      });
    });

    it('navigates to /super-admin/dashboard on successful SUPER_ADMIN login', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          user: { id: '1', email: 'admin@lms.com', role: 'SUPER_ADMIN' },
          tokens: { access: 'acc', refresh: 'ref' },
        },
      });
      renderPage();
      await fillAndSubmit();
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/super-admin/dashboard');
      });
    });

    it('calls setLoading(true) then setLoading(false) during login', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          user: { id: '1', email: 'admin@lms.com', role: 'SUPER_ADMIN' },
          tokens: { access: 'acc', refresh: 'ref' },
        },
      });
      renderPage();
      await fillAndSubmit();
      await waitFor(() => {
        expect(mockSetLoading).toHaveBeenCalledWith(true);
        expect(mockSetLoading).toHaveBeenCalledWith(false);
      });
    });
  });

  // ── 3. Role guard ─────────────────────────────────────────────────────────

  describe('non-SUPER_ADMIN role guard', () => {
    it('shows "This portal is for platform administrators only." when role is not SUPER_ADMIN', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          user: { id: '2', email: 'teacher@school.com', role: 'TEACHER' },
          tokens: { access: 'acc', refresh: 'ref' },
        },
      });
      renderPage();
      await fillAndSubmit('teacher@school.com', 'pass1234');
      expect(
        await screen.findByText('This portal is for platform administrators only.'),
      ).toBeInTheDocument();
    });

    it('does not navigate when role is SCHOOL_ADMIN', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          user: { id: '3', email: 'admin@school.com', role: 'SCHOOL_ADMIN' },
          tokens: { access: 'acc', refresh: 'ref' },
        },
      });
      renderPage();
      await fillAndSubmit('admin@school.com', 'pass1234');
      await screen.findByText('This portal is for platform administrators only.');
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('does not call setAuth when role is not SUPER_ADMIN', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          user: { id: '2', email: 'teacher@school.com', role: 'TEACHER' },
          tokens: { access: 'acc', refresh: 'ref' },
        },
      });
      renderPage();
      await fillAndSubmit('teacher@school.com', 'pass1234');
      await screen.findByText('This portal is for platform administrators only.');
      expect(mockSetAuth).not.toHaveBeenCalled();
    });
  });

  // ── 4. Error states ───────────────────────────────────────────────────────

  describe('error handling', () => {
    it('shows error detail from response on 400', async () => {
      mockedApi.post.mockRejectedValueOnce({
        response: { status: 400, data: { detail: 'Incorrect email or password.' } },
      });
      renderPage();
      await fillAndSubmit();
      expect(await screen.findByText('Incorrect email or password.')).toBeInTheDocument();
    });

    it('shows "Invalid credentials" when 400 response has no detail', async () => {
      mockedApi.post.mockRejectedValueOnce({
        response: { status: 400, data: {} },
      });
      renderPage();
      await fillAndSubmit();
      expect(await screen.findByText('Invalid credentials')).toBeInTheDocument();
    });

    it('prefers non_field_errors over detail on 400', async () => {
      mockedApi.post.mockRejectedValueOnce({
        response: {
          status: 400,
          data: { non_field_errors: ['Custom non-field error.'], detail: 'Fallback' },
        },
      });
      renderPage();
      await fillAndSubmit();
      expect(await screen.findByText('Custom non-field error.')).toBeInTheDocument();
    });

    it('shows "Access denied" on 403', async () => {
      mockedApi.post.mockRejectedValueOnce({
        response: { status: 403, data: {} },
      });
      renderPage();
      await fillAndSubmit();
      expect(await screen.findByText('Access denied')).toBeInTheDocument();
    });

    it('shows "An error occurred. Please try again." on generic error', async () => {
      mockedApi.post.mockRejectedValueOnce({
        response: { status: 500, data: {} },
      });
      renderPage();
      await fillAndSubmit();
      expect(
        await screen.findByText('An error occurred. Please try again.'),
      ).toBeInTheDocument();
    });

    it('shows generic error on network failure (no response)', async () => {
      mockedApi.post.mockRejectedValueOnce(new Error('Network Error'));
      renderPage();
      await fillAndSubmit();
      expect(
        await screen.findByText('An error occurred. Please try again.'),
      ).toBeInTheDocument();
    });
  });

  // ── 5. Logout-reason banners ──────────────────────────────────────────────

  describe('logout-reason banners', () => {
    it('shows idle_timeout banner with amber styling', () => {
      renderPage('?reason=idle_timeout');
      expect(
        screen.getByText(/you were signed out after 30 minutes of inactivity/i),
      ).toBeInTheDocument();
    });

    it('shows session_expired banner', () => {
      renderPage('?reason=session_expired');
      expect(
        screen.getByText(/session expired\. please sign in again\./i),
      ).toBeInTheDocument();
    });

    it('shows tenant_access_denied banner', () => {
      renderPage('?reason=tenant_access_denied');
      expect(
        screen.getByText(/session context changed\. please sign in again\./i),
      ).toBeInTheDocument();
    });

    it('hides logout-reason banner when there is a form error', async () => {
      // Show the session_expired banner first
      renderPage('?reason=session_expired');
      expect(screen.getByText(/session expired/i)).toBeInTheDocument();

      // Trigger a form error
      mockedApi.post.mockRejectedValueOnce({
        response: { status: 400, data: {} },
      });
      await fillAndSubmit();

      await waitFor(() => {
        expect(screen.getByText('Invalid credentials')).toBeInTheDocument();
      });
      // Banner is hidden once a root error is set
      expect(screen.queryByText(/session expired\. please sign in again\./i)).not.toBeInTheDocument();
    });
  });

  // ── 6. Form validation ────────────────────────────────────────────────────

  describe('form validation', () => {
    it('shows email required error when submitting empty form', async () => {
      const user = userEvent.setup();
      renderPage();
      await user.click(screen.getByRole('button', { name: /sign in to command center/i }));
      expect(await screen.findByText('Email is required')).toBeInTheDocument();
    });

    it('shows invalid email error for bad email format', async () => {
      const user = userEvent.setup();
      renderPage();
      await user.type(document.getElementById('superadmin-email')!, 'notanemail');
      await user.click(screen.getByRole('button', { name: /sign in to command center/i }));
      expect(await screen.findByText('Enter a valid email address')).toBeInTheDocument();
    });

    it('shows password required error when password is empty', async () => {
      const user = userEvent.setup();
      renderPage();
      await user.type(document.getElementById('superadmin-email')!, 'admin@lms.com');
      await user.click(screen.getByRole('button', { name: /sign in to command center/i }));
      expect(await screen.findByText('Password is required')).toBeInTheDocument();
    });
  });
});
