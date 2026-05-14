// src/pages/auth/ForgotPasswordPage.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { ForgotPasswordPage } from './ForgotPasswordPage';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

vi.mock('../../stores/tenantStore');

vi.mock('../../services/authService', () => ({
  authService: {
    requestPasswordReset: vi.fn(),
  },
}));

// ─── Typed mock references ────────────────────────────────────────────────────

import { useTenantStore } from '../../stores/tenantStore';
import { authService } from '../../services/authService';

const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedAuthService = authService as unknown as {
  requestPasswordReset: ReturnType<typeof vi.fn>;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const renderPage = () =>
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={['/forgot-password']}>
      <ForgotPasswordPage />
    </MemoryRouter>
  );

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ForgotPasswordPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();

    mockedUseTenantStore.mockReturnValue({
      theme: { name: 'Demo School', logo: null },
    });
  });

  // ── Rendering ──────────────────────────────────────────────────────────────

  describe('rendering', () => {
    it('renders the "Forgot your password?" heading', () => {
      renderPage();
      expect(screen.getByText('Forgot your password?')).toBeInTheDocument();
    });

    it('renders the email address input', () => {
      renderPage();
      expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    });

    it('renders the Send Reset Link button', () => {
      renderPage();
      expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument();
    });

    it('renders the "Back to Sign In" link pointing to /login', () => {
      renderPage();
      const link = screen.getByRole('link', { name: /back to sign in/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', '/login');
    });

    it('shows tenant name from store', () => {
      renderPage();
      expect(screen.getByText('Demo School')).toBeInTheDocument();
    });

    it('shows tenant initial when no logo is set', () => {
      renderPage();
      // "Demo School" → initial "D"
      expect(screen.getByText('D')).toBeInTheDocument();
    });

    it('shows tenant logo image when a logo URL is provided', () => {
      mockedUseTenantStore.mockReturnValue({
        theme: { name: 'Demo School', logo: 'https://example.com/logo.png' },
      });
      renderPage();
      const logo = screen.getByAltText('Demo School');
      expect(logo).toBeInTheDocument();
      expect(logo).toHaveAttribute('src', 'https://example.com/logo.png');
    });

    it('falls back to "School" when theme has no name', () => {
      mockedUseTenantStore.mockReturnValue({ theme: null });
      renderPage();
      expect(screen.getByText('School')).toBeInTheDocument();
    });
  });

  // ── Submission ─────────────────────────────────────────────────────────────

  describe('form submission', () => {
    it('calls authService.requestPasswordReset with the entered email', async () => {
      mockedAuthService.requestPasswordReset.mockResolvedValue({});
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'teacher@example.com');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(mockedAuthService.requestPasswordReset).toHaveBeenCalledWith(
          'teacher@example.com'
        );
      });
    });

    it('shows "Check your email" success heading after successful submission', async () => {
      mockedAuthService.requestPasswordReset.mockResolvedValue({});
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'teacher@example.com');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(screen.getByText('Check your email')).toBeInTheDocument();
      });
    });

    it('shows the submitted email address in the success message', async () => {
      mockedAuthService.requestPasswordReset.mockResolvedValue({});
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'teacher@example.com');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(screen.getByText('teacher@example.com')).toBeInTheDocument();
      });
    });

    it('shows the "Back to Sign In" link in the success state', async () => {
      mockedAuthService.requestPasswordReset.mockResolvedValue({});
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'teacher@example.com');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        const link = screen.getByRole('link', { name: /back to sign in/i });
        expect(link).toHaveAttribute('href', '/login');
      });
    });
  });

  // ── Error handling ─────────────────────────────────────────────────────────

  describe('error handling', () => {
    it('shows the server error message from err.response.data.error', async () => {
      mockedAuthService.requestPasswordReset.mockRejectedValue({
        response: { data: { error: 'No account with that email.' } },
      });
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'bad@example.com');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(screen.getByText('No account with that email.')).toBeInTheDocument();
      });
    });

    it('shows the server error message from err.response.data.detail', async () => {
      mockedAuthService.requestPasswordReset.mockRejectedValue({
        response: { data: { detail: 'Rate limit exceeded.' } },
      });
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'bad@example.com');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(screen.getByText('Rate limit exceeded.')).toBeInTheDocument();
      });
    });

    it('shows a generic error when no specific message is available', async () => {
      mockedAuthService.requestPasswordReset.mockRejectedValue({
        response: { data: {} },
      });
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'bad@example.com');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(
          screen.getByText('An error occurred. Please try again.')
        ).toBeInTheDocument();
      });
    });

    it('shows a generic error when there is no response at all', async () => {
      mockedAuthService.requestPasswordReset.mockRejectedValue(new Error('Network error'));
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'bad@example.com');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(
          screen.getByText('An error occurred. Please try again.')
        ).toBeInTheDocument();
      });
    });
  });

  // ── Validation ─────────────────────────────────────────────────────────────

  describe('email validation', () => {
    it('shows a validation error for an invalid email address', async () => {
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'not-an-email');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(screen.getByText('Enter a valid email address')).toBeInTheDocument();
      });
      expect(mockedAuthService.requestPasswordReset).not.toHaveBeenCalled();
    });

    it('shows a required error when email is left empty', async () => {
      renderPage();

      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(screen.getByText('Email is required')).toBeInTheDocument();
      });
      expect(mockedAuthService.requestPasswordReset).not.toHaveBeenCalled();
    });
  });

  // ── Loading state ──────────────────────────────────────────────────────────

  describe('loading state', () => {
    it('does not call the service more than once while a request is in-flight', async () => {
      // Never resolves — simulates a slow request
      mockedAuthService.requestPasswordReset.mockImplementation(() => new Promise(() => {}));
      renderPage();

      await userEvent.type(screen.getByLabelText(/email address/i), 'teacher@example.com');
      await userEvent.click(screen.getByRole('button', { name: /send reset link/i }));

      await waitFor(() => {
        expect(mockedAuthService.requestPasswordReset).toHaveBeenCalledTimes(1);
      });
    });
  });
});
