// src/pages/parent/ParentVerifyPage.test.tsx
//
// Vitest + React Testing Library tests for ParentVerifyPage.
// Covers: verifying state, no-token error, successful verification, API errors.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../../stores/parentStore', () => ({
  useParentStore: vi.fn(),
}));

vi.mock('../../services/parentService', () => ({
  parentService: {
    verifyToken: vi.fn(),
  },
}));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { useParentStore } from '../../stores/parentStore';
import { parentService } from '../../services/parentService';
import { ParentVerifyPage } from './ParentVerifyPage';

const mockedUseParentStore = useParentStore as unknown as ReturnType<typeof vi.fn>;
const mockedVerifyToken = parentService.verifyToken as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const mockSetSession = vi.fn();

function renderPageWithToken(token?: string) {
  const search = token ? `?token=${token}` : '';
  return render(
    <MemoryRouter initialEntries={[`/parent/verify${search}`]}>
      <ParentVerifyPage />
    </MemoryRouter>,
  );
}

const VERIFY_SUCCESS = {
  session_token: 'session-abc',
  refresh_token: 'refresh-xyz',
  expires_at: '2026-12-31T00:00:00Z',
  parent_email: 'parent@example.com',
  children: [
    { id: 'child-1', first_name: 'Sam', last_name: 'Jones' },
  ],
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ParentVerifyPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    sessionStorage.clear();
    mockedUseParentStore.mockReturnValue({ setSession: mockSetSession });
    // Stub sessionStorage to avoid side-effects
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null);
  });

  // ── 1. Verifying state ────────────────────────────────────────────────────

  describe('verifying state', () => {
    it('shows "Verifying your link..." heading when token is present and pending', () => {
      mockedVerifyToken.mockReturnValue(new Promise(() => {})); // never resolves
      renderPageWithToken('my-magic-token');
      expect(screen.getByText('Verifying your link...')).toBeInTheDocument();
    });

    it('shows "Please wait..." text while verifying', () => {
      mockedVerifyToken.mockReturnValue(new Promise(() => {}));
      renderPageWithToken('my-magic-token');
      expect(screen.getByText(/please wait while we verify/i)).toBeInTheDocument();
    });

    it('does not show error state while verifying', () => {
      mockedVerifyToken.mockReturnValue(new Promise(() => {}));
      renderPageWithToken('my-magic-token');
      expect(screen.queryByText('Verification Failed')).not.toBeInTheDocument();
    });

    it('does not show "Request New Link" while verifying', () => {
      mockedVerifyToken.mockReturnValue(new Promise(() => {}));
      renderPageWithToken('my-magic-token');
      expect(screen.queryByRole('link', { name: /request new link/i })).not.toBeInTheDocument();
    });
  });

  // ── 2. No-token error ─────────────────────────────────────────────────────

  describe('no token in URL', () => {
    it('immediately shows "Verification Failed" when no token', () => {
      renderPageWithToken(); // no token
      expect(screen.getByText('Verification Failed')).toBeInTheDocument();
    });

    it('shows "No verification token found in the URL." error message', () => {
      renderPageWithToken();
      expect(
        screen.getByText('No verification token found in the URL.'),
      ).toBeInTheDocument();
    });

    it('shows "Request New Link" link pointing to /parent', () => {
      renderPageWithToken();
      const link = screen.getByRole('link', { name: /request new link/i });
      expect(link).toBeInTheDocument();
      expect(link).toHaveAttribute('href', '/parent');
    });

    it('does not call verifyToken when there is no token', () => {
      renderPageWithToken();
      expect(mockedVerifyToken).not.toHaveBeenCalled();
    });
  });

  // ── 3. Successful verification ────────────────────────────────────────────

  describe('successful verification', () => {
    it('calls verifyToken with the token from URL', async () => {
      mockedVerifyToken.mockResolvedValue(VERIFY_SUCCESS);
      renderPageWithToken('magic-abc-123');
      await waitFor(() => {
        expect(mockedVerifyToken).toHaveBeenCalledWith('magic-abc-123');
      });
    });

    it('calls setSession with data from the API response', async () => {
      mockedVerifyToken.mockResolvedValue(VERIFY_SUCCESS);
      renderPageWithToken('magic-abc-123');
      await waitFor(() => {
        expect(mockSetSession).toHaveBeenCalledWith(
          expect.objectContaining({
            session_token: 'session-abc',
            refresh_token: 'refresh-xyz',
            expires_at: '2026-12-31T00:00:00Z',
            email: 'parent@example.com',
            children: VERIFY_SUCCESS.children,
          }),
        );
      });
    });

    it('navigates to /parent/dashboard after successful verification', async () => {
      mockedVerifyToken.mockResolvedValue(VERIFY_SUCCESS);
      renderPageWithToken('magic-abc-123');
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/parent/dashboard', { replace: true });
      });
    });

    it('falls back to sessionStorage email when response has no parent_email', async () => {
      sessionStorage.setItem('parent_email', 'stored@example.com');
      const dataWithoutEmail = { ...VERIFY_SUCCESS, parent_email: undefined };
      mockedVerifyToken.mockResolvedValue(dataWithoutEmail);
      renderPageWithToken('magic-abc-123');
      await waitFor(() => {
        expect(mockSetSession).toHaveBeenCalledWith(
          expect.objectContaining({ email: 'stored@example.com' }),
        );
      });
    });

    it('uses empty string for email when neither source provides it', async () => {
      const dataWithoutEmail = { ...VERIFY_SUCCESS, parent_email: undefined };
      mockedVerifyToken.mockResolvedValue(dataWithoutEmail);
      renderPageWithToken('magic-abc-123');
      await waitFor(() => {
        expect(mockSetSession).toHaveBeenCalledWith(
          expect.objectContaining({ email: '' }),
        );
      });
    });
  });

  // ── 4. API error ──────────────────────────────────────────────────────────

  describe('API error', () => {
    it('shows "Verification Failed" heading on API error', async () => {
      mockedVerifyToken.mockRejectedValue({
        response: { data: { detail: 'Token has expired.' } },
      });
      renderPageWithToken('bad-token');
      expect(await screen.findByText('Verification Failed')).toBeInTheDocument();
    });

    it('shows specific error message from API detail field', async () => {
      mockedVerifyToken.mockRejectedValue({
        response: { data: { detail: 'Token has expired.' } },
      });
      renderPageWithToken('bad-token');
      expect(await screen.findByText('Token has expired.')).toBeInTheDocument();
    });

    it('shows error message from API error field', async () => {
      mockedVerifyToken.mockRejectedValue({
        response: { data: { error: 'Invalid token signature.' } },
      });
      renderPageWithToken('bad-token');
      expect(await screen.findByText('Invalid token signature.')).toBeInTheDocument();
    });

    it('shows fallback message when API returns no detail', async () => {
      mockedVerifyToken.mockRejectedValue(new Error('Network Error'));
      renderPageWithToken('bad-token');
      expect(
        await screen.findByText('Verification failed. The link may have expired.'),
      ).toBeInTheDocument();
    });

    it('shows "Request New Link" link on error', async () => {
      mockedVerifyToken.mockRejectedValue({
        response: { data: { detail: 'Token expired.' } },
      });
      renderPageWithToken('bad-token');
      await screen.findByText('Verification Failed');
      expect(screen.getByRole('link', { name: /request new link/i })).toBeInTheDocument();
    });

    it('"Request New Link" points to /parent', async () => {
      mockedVerifyToken.mockRejectedValue({
        response: { data: { detail: 'Token expired.' } },
      });
      renderPageWithToken('bad-token');
      await screen.findByText('Verification Failed');
      const link = screen.getByRole('link', { name: /request new link/i });
      expect(link).toHaveAttribute('href', '/parent');
    });

    it('does not navigate to /parent/dashboard on error', async () => {
      mockedVerifyToken.mockRejectedValue({
        response: { data: { detail: 'Token expired.' } },
      });
      renderPageWithToken('bad-token');
      await screen.findByText('Verification Failed');
      expect(mockNavigate).not.toHaveBeenCalled();
    });

    it('does not call setSession on error', async () => {
      mockedVerifyToken.mockRejectedValue({
        response: { data: { detail: 'Token expired.' } },
      });
      renderPageWithToken('bad-token');
      await screen.findByText('Verification Failed');
      expect(mockSetSession).not.toHaveBeenCalled();
    });
  });
});
