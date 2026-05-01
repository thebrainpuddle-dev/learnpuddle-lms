// src/pages/auth/SSOCallbackPage.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { SSOCallbackPage } from './SSOCallbackPage';

// ─── Mocks ────────────────────────────────────────────────────────────────────

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

vi.mock('../../components/common', () => ({
  Loading: () => <div data-testid="loading-spinner">Loading...</div>,
}));

// Mutable search-params reference so tests can set different URL states.
let mockSearchParams = new URLSearchParams('code=auth-code-123');
const mockNavigate = vi.fn();

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useSearchParams: () => [mockSearchParams, vi.fn()],
  };
});

// ─── Typed mock references ────────────────────────────────────────────────────

import api from '../../config/api';

const mockedApi = api as unknown as {
  post: ReturnType<typeof vi.fn>;
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

const renderPage = () =>
  render(
    <MemoryRouter initialEntries={['/auth/sso/callback']}>
      <SSOCallbackPage />
    </MemoryRouter>
  );

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('SSOCallbackPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockSearchParams = new URLSearchParams('code=auth-code-123');
    sessionStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  // ── Loading state ──────────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows the Loading component while processing a valid code', () => {
      mockedApi.post.mockImplementation(() => new Promise(() => {}));
      renderPage();
      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
    });

    it('shows "Completing sign in..." text while processing', () => {
      mockedApi.post.mockImplementation(() => new Promise(() => {}));
      renderPage();
      expect(screen.getByText('Completing sign in...')).toBeInTheDocument();
    });

    it('does not show an error while processing', () => {
      mockedApi.post.mockImplementation(() => new Promise(() => {}));
      renderPage();
      expect(screen.queryByText('Sign In Failed')).not.toBeInTheDocument();
    });
  });

  // ── Error: sso_failed param ────────────────────────────────────────────────

  describe('sso_failed error param', () => {
    it('shows "Sign In Failed" heading when error=sso_failed is in the URL', () => {
      mockSearchParams = new URLSearchParams('error=sso_failed');
      renderPage();
      expect(screen.getByText('Sign In Failed')).toBeInTheDocument();
    });

    it('shows the human-readable SSO failure message for error=sso_failed', () => {
      mockSearchParams = new URLSearchParams('error=sso_failed');
      renderPage();
      expect(
        screen.getByText('SSO login failed. Please try again.')
      ).toBeInTheDocument();
    });

    it('shows the raw error value when the error param is not "sso_failed"', () => {
      mockSearchParams = new URLSearchParams('error=account_disabled');
      renderPage();
      expect(screen.getByText('account_disabled')).toBeInTheDocument();
    });

    it('does not call the API when an error param is present', () => {
      mockSearchParams = new URLSearchParams('error=sso_failed');
      renderPage();
      expect(mockedApi.post).not.toHaveBeenCalled();
    });
  });

  // ── Error: missing code param ──────────────────────────────────────────────

  describe('missing code param', () => {
    it('shows "Sign In Failed" heading when no code is in the URL', () => {
      mockSearchParams = new URLSearchParams('');
      renderPage();
      expect(screen.getByText('Sign In Failed')).toBeInTheDocument();
    });

    it('shows the missing-code error message', () => {
      mockSearchParams = new URLSearchParams('');
      renderPage();
      expect(
        screen.getByText('Invalid SSO response. Missing authorization code.')
      ).toBeInTheDocument();
    });

    it('does not call the API when no code is present', () => {
      mockSearchParams = new URLSearchParams('');
      renderPage();
      expect(mockedApi.post).not.toHaveBeenCalled();
    });
  });

  // ── Successful token exchange ───────────────────────────────────────────────

  describe('successful token exchange', () => {
    it('calls the token-exchange endpoint with the code', async () => {
      mockedApi.post.mockResolvedValue({
        data: { access_token: 'acc-123', refresh_token: 'ref-456' },
      });
      renderPage();

      await waitFor(() => {
        expect(mockedApi.post).toHaveBeenCalledWith(
          '/users/auth/sso/token-exchange/',
          { code: 'auth-code-123' }
        );
      });
    });

    it('stores the access token in sessionStorage', async () => {
      mockedApi.post.mockResolvedValue({
        data: { access_token: 'acc-123', refresh_token: 'ref-456' },
      });
      renderPage();

      await waitFor(() => {
        expect(sessionStorage.getItem('access_token')).toBe('acc-123');
      });
    });

    it('stores the refresh token in sessionStorage', async () => {
      mockedApi.post.mockResolvedValue({
        data: { access_token: 'acc-123', refresh_token: 'ref-456' },
      });
      renderPage();

      await waitFor(() => {
        expect(sessionStorage.getItem('refresh_token')).toBe('ref-456');
      });
    });

    it('navigates to /dashboard after a successful exchange', async () => {
      mockedApi.post.mockResolvedValue({
        data: { access_token: 'acc-123', refresh_token: 'ref-456' },
      });
      renderPage();

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true });
      });
    });
  });

  // ── API error during token exchange ────────────────────────────────────────

  describe('API error during token exchange', () => {
    it('shows "Sign In Failed" heading on API error', async () => {
      mockedApi.post.mockRejectedValue(new Error('Network error'));
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Sign In Failed')).toBeInTheDocument();
      });
    });

    it('shows the expired-link error message on API failure', async () => {
      mockedApi.post.mockRejectedValue(new Error('Unauthorized'));
      renderPage();

      await waitFor(() => {
        expect(
          screen.getByText('Failed to complete sign in. The link may have expired.')
        ).toBeInTheDocument();
      });
    });

    it('does not navigate to /dashboard on API failure', async () => {
      mockedApi.post.mockRejectedValue(new Error('Unauthorized'));
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Sign In Failed')).toBeInTheDocument();
      });
      expect(mockNavigate).not.toHaveBeenCalledWith('/dashboard', expect.anything());
    });

    it('does not store tokens in sessionStorage on API failure', async () => {
      mockedApi.post.mockRejectedValue(new Error('Unauthorized'));
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Sign In Failed')).toBeInTheDocument();
      });
      expect(sessionStorage.getItem('access_token')).toBeNull();
      expect(sessionStorage.getItem('refresh_token')).toBeNull();
    });
  });

  // ── "Return to Login" button ───────────────────────────────────────────────

  describe('"Return to Login" button in error state', () => {
    it('renders the "Return to Login" button when there is an error', () => {
      mockSearchParams = new URLSearchParams('error=sso_failed');
      renderPage();
      expect(
        screen.getByRole('button', { name: /return to login/i })
      ).toBeInTheDocument();
    });

    it('navigates to /login when "Return to Login" is clicked', async () => {
      mockSearchParams = new URLSearchParams('error=sso_failed');
      renderPage();

      await userEvent.click(screen.getByRole('button', { name: /return to login/i }));

      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });
  });
});
