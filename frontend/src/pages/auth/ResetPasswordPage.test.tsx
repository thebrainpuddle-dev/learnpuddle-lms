// src/pages/auth/ResetPasswordPage.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { ResetPasswordPage } from './ResetPasswordPage';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

vi.mock('../../stores/tenantStore');

vi.mock('../../services/authService', () => ({
  authService: {
    confirmPasswordReset: vi.fn(),
  },
}));

// useSearchParams is mocked per-test via the factory below.
// We keep a mutable reference so individual tests can override it.
let mockSearchParams = new URLSearchParams('uid=test-uid&token=test-token');

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useSearchParams: () => [mockSearchParams, vi.fn()],
  };
});

// ─── Typed mock references ────────────────────────────────────────────────────

import { useTenantStore } from '../../stores/tenantStore';
import { authService } from '../../services/authService';

const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedAuthService = authService as unknown as {
  confirmPasswordReset: ReturnType<typeof vi.fn>;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const renderPage = () =>
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={['/reset-password']}>
      <ResetPasswordPage />
    </MemoryRouter>
  );

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ResetPasswordPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();

    // Default: valid uid + token in URL
    mockSearchParams = new URLSearchParams('uid=test-uid&token=test-token');

    mockedUseTenantStore.mockReturnValue({
      theme: { name: 'Demo School', logo: null },
    });
  });

  // ── Invalid link state ─────────────────────────────────────────────────────

  describe('invalid link', () => {
    it('shows "Invalid Reset Link" heading when uid and token are missing', () => {
      mockSearchParams = new URLSearchParams('');
      renderPage();
      expect(screen.getByText('Invalid Reset Link')).toBeInTheDocument();
    });

    it('shows "Invalid Reset Link" heading when only uid is missing', () => {
      mockSearchParams = new URLSearchParams('token=some-token');
      renderPage();
      expect(screen.getByText('Invalid Reset Link')).toBeInTheDocument();
    });

    it('shows "Invalid Reset Link" heading when only token is missing', () => {
      mockSearchParams = new URLSearchParams('uid=some-uid');
      renderPage();
      expect(screen.getByText('Invalid Reset Link')).toBeInTheDocument();
    });

    it('shows a link to /forgot-password when the link is invalid', () => {
      mockSearchParams = new URLSearchParams('');
      renderPage();
      const link = screen.getByRole('link', { name: /request new reset link/i });
      expect(link).toHaveAttribute('href', '/forgot-password');
    });

    it('does not render the password form when the link is invalid', () => {
      mockSearchParams = new URLSearchParams('');
      renderPage();
      expect(screen.queryByLabelText(/new password/i)).not.toBeInTheDocument();
    });
  });

  // ── Form rendering ─────────────────────────────────────────────────────────

  describe('form rendering', () => {
    it('renders "Set new password" heading when uid and token are present', () => {
      renderPage();
      expect(screen.getByText('Set new password')).toBeInTheDocument();
    });

    it('renders the New Password field', () => {
      renderPage();
      expect(screen.getByLabelText('New Password')).toBeInTheDocument();
    });

    it('renders the Confirm New Password field', () => {
      renderPage();
      expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument();
    });

    it('renders the Reset Password submit button', () => {
      renderPage();
      expect(screen.getByRole('button', { name: /reset password/i })).toBeInTheDocument();
    });

    it('shows tenant name from store', () => {
      renderPage();
      expect(screen.getByText('Demo School')).toBeInTheDocument();
    });

    it('shows tenant initial when no logo is set', () => {
      renderPage();
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
  });

  // ── Submission ─────────────────────────────────────────────────────────────

  describe('form submission', () => {
    it('calls authService.confirmPasswordReset with uid, token and new password', async () => {
      mockedAuthService.confirmPasswordReset.mockResolvedValue({});
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'NewSecurePass1');
      await userEvent.type(screen.getByLabelText(/confirm new password/i), 'NewSecurePass1');
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        expect(mockedAuthService.confirmPasswordReset).toHaveBeenCalledWith(
          'test-uid',
          'test-token',
          'NewSecurePass1'
        );
      });
    });

    it('shows "Password Reset" success heading after successful submission', async () => {
      mockedAuthService.confirmPasswordReset.mockResolvedValue({});
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'NewSecurePass1');
      await userEvent.type(screen.getByLabelText(/confirm new password/i), 'NewSecurePass1');
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        expect(screen.getByText('Password Reset')).toBeInTheDocument();
      });
    });

    it('shows a "Sign In" link after successful password reset', async () => {
      mockedAuthService.confirmPasswordReset.mockResolvedValue({});
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'NewSecurePass1');
      await userEvent.type(screen.getByLabelText(/confirm new password/i), 'NewSecurePass1');
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        const link = screen.getByRole('link', { name: /sign in/i });
        expect(link).toHaveAttribute('href', '/login');
      });
    });
  });

  // ── Error handling ─────────────────────────────────────────────────────────

  describe('error handling', () => {
    it('shows error from err.response.data.error', async () => {
      mockedAuthService.confirmPasswordReset.mockRejectedValue({
        response: { data: { error: 'Token has expired.' } },
      });
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'NewSecurePass1');
      await userEvent.type(screen.getByLabelText(/confirm new password/i), 'NewSecurePass1');
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        expect(screen.getByText('Token has expired.')).toBeInTheDocument();
      });
    });

    it('shows error from err.response.data.detail', async () => {
      mockedAuthService.confirmPasswordReset.mockRejectedValue({
        response: { data: { detail: 'Invalid token.' } },
      });
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'NewSecurePass1');
      await userEvent.type(screen.getByLabelText(/confirm new password/i), 'NewSecurePass1');
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        expect(screen.getByText('Invalid token.')).toBeInTheDocument();
      });
    });

    it('shows error joined from err.response.data.details array', async () => {
      mockedAuthService.confirmPasswordReset.mockRejectedValue({
        response: { data: { details: ['Too short.', 'Too common.'] } },
      });
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'NewSecurePass1');
      await userEvent.type(screen.getByLabelText(/confirm new password/i), 'NewSecurePass1');
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        expect(screen.getByText('Too short. Too common.')).toBeInTheDocument();
      });
    });

    it('shows generic fallback error when no message is available', async () => {
      mockedAuthService.confirmPasswordReset.mockRejectedValue({
        response: { data: {} },
      });
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'NewSecurePass1');
      await userEvent.type(screen.getByLabelText(/confirm new password/i), 'NewSecurePass1');
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        expect(
          screen.getByText('An error occurred. Please try again.')
        ).toBeInTheDocument();
      });
    });
  });

  // ── Validation ─────────────────────────────────────────────────────────────

  describe('validation', () => {
    it('shows error when password is fewer than 8 characters', async () => {
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'short');
      await userEvent.type(screen.getByLabelText(/confirm new password/i), 'short');
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        expect(
          screen.getByText('Password must be at least 8 characters')
        ).toBeInTheDocument();
      });
      expect(mockedAuthService.confirmPasswordReset).not.toHaveBeenCalled();
    });

    it('shows error when passwords do not match', async () => {
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'ValidPass123');
      await userEvent.type(
        screen.getByLabelText(/confirm new password/i),
        'DifferentPass456'
      );
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
      });
      expect(mockedAuthService.confirmPasswordReset).not.toHaveBeenCalled();
    });
  });

  // ── Loading state ──────────────────────────────────────────────────────────

  describe('loading state', () => {
    it('does not call the service more than once while a request is in-flight', async () => {
      mockedAuthService.confirmPasswordReset.mockImplementation(() => new Promise(() => {}));
      renderPage();

      await userEvent.type(screen.getByLabelText('New Password'), 'NewSecurePass1');
      await userEvent.type(screen.getByLabelText(/confirm new password/i), 'NewSecurePass1');
      await userEvent.click(screen.getByRole('button', { name: /reset password/i }));

      await waitFor(() => {
        expect(mockedAuthService.confirmPasswordReset).toHaveBeenCalledTimes(1);
      });
    });
  });
});
