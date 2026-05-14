// src/pages/auth/VerifyEmailPage.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { VerifyEmailPage } from './VerifyEmailPage';

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

// useSearchParams is mutable so individual tests can set params.
let mockSearchParams = new URLSearchParams('uid=test-uid&token=test-token');

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
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
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={['/verify-email']}>
      <VerifyEmailPage />
    </MemoryRouter>
  );

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('VerifyEmailPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Default: valid uid + token
    mockSearchParams = new URLSearchParams('uid=test-uid&token=test-token');
  });

  // ── Always-present elements ────────────────────────────────────────────────

  describe('constant elements', () => {
    it('always renders the "Email Verification" heading', async () => {
      mockedApi.post.mockResolvedValue({ data: { message: 'Verified.' } });
      renderPage();
      expect(screen.getByText('Email Verification')).toBeInTheDocument();
    });

    it('always renders the "Go to Login" link pointing to /login', async () => {
      mockedApi.post.mockResolvedValue({ data: { message: 'Verified.' } });
      renderPage();
      const link = screen.getByRole('link', { name: /go to login/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', '/login');
    });
  });

  // ── Invalid link (no params) ───────────────────────────────────────────────

  describe('invalid verification link', () => {
    it('shows "Invalid verification link." when uid and token are missing', async () => {
      mockSearchParams = new URLSearchParams('');
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Invalid verification link.')).toBeInTheDocument();
      });
    });

    it('shows error message when only uid is missing', async () => {
      mockSearchParams = new URLSearchParams('token=some-token');
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Invalid verification link.')).toBeInTheDocument();
      });
    });

    it('shows error message when only token is missing', async () => {
      mockSearchParams = new URLSearchParams('uid=some-uid');
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Invalid verification link.')).toBeInTheDocument();
      });
    });

    it('does not call the API when params are missing', () => {
      mockSearchParams = new URLSearchParams('');
      renderPage();
      expect(mockedApi.post).not.toHaveBeenCalled();
    });
  });

  // ── Loading state ──────────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows a spinner while the API call is in-flight', () => {
      // Never resolves — keeps the page in loading state
      mockedApi.post.mockImplementation(() => new Promise(() => {}));
      renderPage();

      // The spinner is rendered as an animated div while state === 'loading'
      // We verify by checking the initial message displayed alongside it
      expect(screen.getByText('Verifying your email...')).toBeInTheDocument();
    });

    it('does not show the error message while loading', () => {
      mockedApi.post.mockImplementation(() => new Promise(() => {}));
      renderPage();

      expect(screen.queryByText('Invalid verification link.')).not.toBeInTheDocument();
    });
  });

  // ── Success state ──────────────────────────────────────────────────────────

  describe('success state', () => {
    it('shows the success message returned from the API', async () => {
      mockedApi.post.mockResolvedValue({
        data: { message: 'Your email has been verified successfully.' },
      });
      renderPage();

      await waitFor(() => {
        expect(
          screen.getByText('Your email has been verified successfully.')
        ).toBeInTheDocument();
      });
    });

    it('falls back to "Email verified successfully." when API returns no message', async () => {
      mockedApi.post.mockResolvedValue({ data: {} });
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Email verified successfully.')).toBeInTheDocument();
      });
    });

    it('calls the API with the correct uid and token', async () => {
      mockedApi.post.mockResolvedValue({ data: { message: 'OK' } });
      renderPage();

      await waitFor(() => {
        expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/verify-email/', {
          uid: 'test-uid',
          token: 'test-token',
        });
      });
    });
  });

  // ── Error state ────────────────────────────────────────────────────────────

  describe('error state from API', () => {
    it('shows err.response.data.error when available', async () => {
      mockedApi.post.mockRejectedValue({
        response: { data: { error: 'Token has already been used.' } },
      });
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Token has already been used.')).toBeInTheDocument();
      });
    });

    it('shows err.response.data.detail when error field is absent', async () => {
      mockedApi.post.mockRejectedValue({
        response: { data: { detail: 'Link has expired.' } },
      });
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Link has expired.')).toBeInTheDocument();
      });
    });

    it('shows fallback message when neither error nor detail are present', async () => {
      mockedApi.post.mockRejectedValue({ response: { data: {} } });
      renderPage();

      await waitFor(() => {
        expect(
          screen.getByText('Verification link is invalid or expired.')
        ).toBeInTheDocument();
      });
    });

    it('shows fallback message when there is no response object at all', async () => {
      mockedApi.post.mockRejectedValue(new Error('Network error'));
      renderPage();

      await waitFor(() => {
        expect(
          screen.getByText('Verification link is invalid or expired.')
        ).toBeInTheDocument();
      });
    });
  });
});
