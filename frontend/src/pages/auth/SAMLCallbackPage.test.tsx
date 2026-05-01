// src/pages/auth/SAMLCallbackPage.test.tsx
//
// AUDIT-2026-04-26-PHASE3-10 frontend follow-up.
//
// Backend SAML ACS no longer redirects with `#access=...&refresh=...` in the
// URL fragment.  It now redirects with `?code=<token>` which the frontend
// must POST to /users/auth/sso/token-exchange/ for the JWT pair (mirrors the
// OAuth callback flow).  This test pins that contract.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { SAMLCallbackPage } from './SAMLCallbackPage';
import api from '../../config/api';

vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = (await vi.importActual('react-router-dom')) as Record<string, unknown>;
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockedApi = api as unknown as {
  post: ReturnType<typeof vi.fn>;
};

const renderAt = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/auth/saml-callback" element={<SAMLCallbackPage />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>
  );

describe('SAMLCallbackPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  it('reads ?code= from the query string and POSTs it to the SSO token-exchange endpoint', async () => {
    mockedApi.post.mockResolvedValueOnce({
      data: {
        access_token: 'header.access.sig',
        refresh_token: 'header.refresh.sig',
      },
    });

    renderAt('/auth/saml-callback?code=opaque-saml-code-xyz');

    await waitFor(() => {
      expect(mockedApi.post).toHaveBeenCalledWith(
        '/users/auth/sso/token-exchange/',
        { code: 'opaque-saml-code-xyz' }
      );
    });
  });

  it('on successful exchange stores JWT pair and navigates to dashboard', async () => {
    mockedApi.post.mockResolvedValueOnce({
      data: {
        access_token: 'jwt.access.token',
        refresh_token: 'jwt.refresh.token',
      },
    });

    renderAt('/auth/saml-callback?code=happy-path-code');

    await waitFor(() => {
      expect(sessionStorage.getItem('access_token')).toBe('jwt.access.token');
      expect(sessionStorage.getItem('refresh_token')).toBe('jwt.refresh.token');
    });
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/dashboard', { replace: true });
    });
  });

  it('on failed exchange (network/4xx) renders the error UI without storing tokens', async () => {
    mockedApi.post.mockRejectedValueOnce(new Error('boom'));

    renderAt('/auth/saml-callback?code=bad-code');

    await waitFor(() => {
      expect(screen.getByText(/sign in failed/i)).toBeInTheDocument();
    });
    expect(sessionStorage.getItem('access_token')).toBeNull();
    expect(sessionStorage.getItem('refresh_token')).toBeNull();
    // User can recover via the error CTA — should not auto-navigate to dashboard.
    expect(mockNavigate).not.toHaveBeenCalledWith('/dashboard', expect.anything());
  });

  it('renders an error and does not POST when ?code= is missing entirely', async () => {
    renderAt('/auth/saml-callback');

    await waitFor(() => {
      expect(screen.getByText(/sign in failed/i)).toBeInTheDocument();
    });
    expect(mockedApi.post).not.toHaveBeenCalled();
  });

  it('surfaces ?error= passed through by the backend without making a network call', async () => {
    renderAt('/auth/saml-callback?error=saml_exchange_failed');

    await waitFor(() => {
      expect(screen.getByText(/sign in failed/i)).toBeInTheDocument();
    });
    expect(mockedApi.post).not.toHaveBeenCalled();
  });

  it('regression guard: never reads tokens from window.location.hash (the old fragment contract)', async () => {
    // Old contract was: backend redirected with `#access=<jwt>&refresh=<jwt>`.
    // We must NOT regress to reading those.  Stub the hash to obviously-invalid
    // material; if the page reads it we'd fail the no-POST assertion below.
    const originalHash = window.location.hash;
    Object.defineProperty(window.location, 'hash', {
      configurable: true,
      writable: true,
      value: '#access=LEAKED_JWT&refresh=LEAKED_REFRESH',
    });

    try {
      mockedApi.post.mockResolvedValueOnce({
        data: { access_token: 'a.b.c', refresh_token: 'd.e.f' },
      });

      renderAt('/auth/saml-callback?code=real-code');

      await waitFor(() => {
        expect(mockedApi.post).toHaveBeenCalledWith(
          '/users/auth/sso/token-exchange/',
          { code: 'real-code' }
        );
      });

      // Tokens stored must come from the POST response, NOT from the hash.
      await waitFor(() => {
        expect(sessionStorage.getItem('access_token')).toBe('a.b.c');
      });
      expect(sessionStorage.getItem('access_token')).not.toContain('LEAKED');
    } finally {
      Object.defineProperty(window.location, 'hash', {
        configurable: true,
        writable: true,
        value: originalHash,
      });
    }
  });
});
