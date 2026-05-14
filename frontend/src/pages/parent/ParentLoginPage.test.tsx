// src/pages/parent/ParentLoginPage.test.tsx
//
// Vitest + React Testing Library tests for ParentLoginPage.
// Covers: rendering, magic link flow, success/error states, demo login, disabled state.

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
  };
});

vi.mock('../../stores/tenantStore', () => ({
  useTenantStore: vi.fn(),
}));

vi.mock('../../stores/parentStore', () => ({
  useParentStore: vi.fn(),
}));

vi.mock('../../services/parentService', () => ({
  parentService: {
    requestMagicLink: vi.fn(),
    demoLogin: vi.fn(),
  },
}));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { useTenantStore } from '../../stores/tenantStore';
import { useParentStore } from '../../stores/parentStore';
import { parentService } from '../../services/parentService';
import { ParentLoginPage } from './ParentLoginPage';

const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseParentStore = useParentStore as unknown as ReturnType<typeof vi.fn>;
const mockedRequestMagicLink = parentService.requestMagicLink as ReturnType<typeof vi.fn>;
const mockedDemoLogin = parentService.demoLogin as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const mockSetSession = vi.fn();

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={['/parent']}>
      <ParentLoginPage />
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ParentLoginPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();

    mockedUseTenantStore.mockReturnValue({
      theme: { name: 'Test School', logo: null },
    });

    mockedUseParentStore.mockReturnValue({
      setSession: mockSetSession,
    });
  });

  // ── 1. Rendering ──────────────────────────────────────────────────────────

  describe('rendering', () => {
    it('renders the tenant name as heading', () => {
      renderPage();
      expect(screen.getByRole('heading', { name: 'Test School' })).toBeInTheDocument();
    });

    it('renders "Parent Portal" subtitle', () => {
      renderPage();
      expect(screen.getByText('Parent Portal')).toBeInTheDocument();
    });

    it('renders the email input with id "parent-email"', () => {
      renderPage();
      expect(document.getElementById('parent-email')).toBeInTheDocument();
    });

    it('renders the email address label', () => {
      renderPage();
      expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    });

    it('renders the "Send Login Link" button', () => {
      renderPage();
      expect(screen.getByRole('button', { name: /send login link/i })).toBeInTheDocument();
    });

    it('renders the "Not a parent?" footer link', () => {
      renderPage();
      expect(screen.getByText(/not a parent\?/i)).toBeInTheDocument();
      expect(screen.getByRole('link', { name: /sign in as teacher or admin/i })).toBeInTheDocument();
    });

    it('renders tenant initial when no logo', () => {
      renderPage();
      expect(screen.getByText('T')).toBeInTheDocument(); // 'T' for 'Test School'
    });

    it('renders tenant logo when available', () => {
      mockedUseTenantStore.mockReturnValue({
        theme: { name: 'Test School', logo: 'https://cdn.example.com/logo.png' },
      });
      renderPage();
      expect(screen.getByAltText('Test School')).toHaveAttribute(
        'src',
        'https://cdn.example.com/logo.png',
      );
    });

    it('renders "LearnPuddle" when theme name is not available', () => {
      mockedUseTenantStore.mockReturnValue({ theme: null });
      renderPage();
      expect(screen.getByRole('heading', { name: 'LearnPuddle' })).toBeInTheDocument();
    });
  });

  // ── 2. Send Login Link flow ───────────────────────────────────────────────

  describe('send login link flow', () => {
    it('calls requestMagicLink with the trimmed email on submit', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockResolvedValue(undefined);
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), '  parent@example.com  ');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      await waitFor(() => {
        expect(mockedRequestMagicLink).toHaveBeenCalledWith('parent@example.com');
      });
    });

    it('shows success state after successful magic link request', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockResolvedValue(undefined);
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), 'parent@example.com');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      expect(await screen.findByText('Check your email')).toBeInTheDocument();
    });

    it('shows the email in the success message', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockResolvedValue(undefined);
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), 'parent@example.com');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      expect(await screen.findByText(/parent@example\.com/)).toBeInTheDocument();
    });

    it('shows "Use a different email" button after success', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockResolvedValue(undefined);
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), 'parent@example.com');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      expect(await screen.findByRole('button', { name: /use a different email/i })).toBeInTheDocument();
    });

    it('"Use a different email" resets to the form', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockResolvedValue(undefined);
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), 'parent@example.com');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      await screen.findByText('Check your email');
      await user.click(screen.getByRole('button', { name: /use a different email/i }));

      expect(screen.queryByText('Check your email')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /send login link/i })).toBeInTheDocument();
    });

    it('"Use a different email" clears the email input', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockResolvedValue(undefined);
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), 'parent@example.com');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      await screen.findByText('Check your email');
      await user.click(screen.getByRole('button', { name: /use a different email/i }));

      expect((document.getElementById('parent-email') as HTMLInputElement).value).toBe('');
    });
  });

  // ── 3. Error state ────────────────────────────────────────────────────────

  describe('error state', () => {
    it('shows error message when requestMagicLink fails with detail', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockRejectedValue({
        response: { data: { detail: 'No account found with this email.' } },
      });
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), 'bad@example.com');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      expect(await screen.findByText('No account found with this email.')).toBeInTheDocument();
    });

    it('shows error message from response.data.error field', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockRejectedValue({
        response: { data: { error: 'Rate limit exceeded.' } },
      });
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), 'parent@example.com');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      expect(await screen.findByText('Rate limit exceeded.')).toBeInTheDocument();
    });

    it('shows fallback error message when no response data', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockRejectedValue(new Error('Network'));
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), 'parent@example.com');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      expect(
        await screen.findByText('Failed to send login link. Please try again.'),
      ).toBeInTheDocument();
    });

    it('does not show success state on error', async () => {
      const user = userEvent.setup();
      mockedRequestMagicLink.mockRejectedValue(new Error('Network'));
      renderPage();

      await user.type(screen.getByLabelText(/email address/i), 'parent@example.com');
      await user.click(screen.getByRole('button', { name: /send login link/i }));

      await screen.findByText('Failed to send login link. Please try again.');
      expect(screen.queryByText('Check your email')).not.toBeInTheDocument();
    });
  });

  // ── 4. Button disabled state ──────────────────────────────────────────────

  describe('button disabled state', () => {
    it('send login link button is disabled when email is empty', () => {
      renderPage();
      expect(screen.getByRole('button', { name: /send login link/i })).toBeDisabled();
    });

    it('send login link button is enabled when email is typed', async () => {
      const user = userEvent.setup();
      renderPage();
      await user.type(screen.getByLabelText(/email address/i), 'a@b.com');
      expect(screen.getByRole('button', { name: /send login link/i })).not.toBeDisabled();
    });

    it('button is disabled when email is only spaces', async () => {
      const user = userEvent.setup();
      renderPage();
      await user.type(screen.getByLabelText(/email address/i), '   ');
      expect(screen.getByRole('button', { name: /send login link/i })).toBeDisabled();
    });
  });

  // ── 5. Demo login (IS_DEV = true in Vitest) ───────────────────────────────

  describe('demo login', () => {
    it('renders the demo login button (DEV mode)', () => {
      renderPage();
      expect(
        screen.getByRole('button', { name: /demo login as/i }),
      ).toBeInTheDocument();
    });

    it('calls demoLogin with the demo email', async () => {
      const user = userEvent.setup();
      mockedDemoLogin.mockResolvedValue({
        session_token: 'tok',
        refresh_token: 'ref',
        expires_at: '2026-12-31T00:00:00Z',
        children: [],
        parent_email: 'parent@keystoneeducation.in',
      });
      renderPage();

      await user.click(screen.getByRole('button', { name: /demo login as/i }));

      await waitFor(() => {
        expect(mockedDemoLogin).toHaveBeenCalledWith('parent@keystoneeducation.in');
      });
    });

    it('calls setSession after successful demo login', async () => {
      const user = userEvent.setup();
      const demoData = {
        session_token: 'demo-tok',
        refresh_token: 'demo-ref',
        expires_at: '2026-12-31T00:00:00Z',
        children: [{ id: 'c1', first_name: 'Alice', last_name: 'Demo' }],
        parent_email: 'parent@keystoneeducation.in',
      };
      mockedDemoLogin.mockResolvedValue(demoData);
      renderPage();

      await user.click(screen.getByRole('button', { name: /demo login as/i }));

      await waitFor(() => {
        expect(mockSetSession).toHaveBeenCalledWith(
          expect.objectContaining({
            session_token: 'demo-tok',
            email: 'parent@keystoneeducation.in',
          }),
        );
      });
    });

    it('navigates to /parent/dashboard after successful demo login', async () => {
      const user = userEvent.setup();
      mockedDemoLogin.mockResolvedValue({
        session_token: 'tok',
        refresh_token: 'ref',
        expires_at: '2026-12-31T00:00:00Z',
        children: [],
        parent_email: 'parent@keystoneeducation.in',
      });
      renderPage();

      await user.click(screen.getByRole('button', { name: /demo login as/i }));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/parent/dashboard', { replace: true });
      });
    });

    it('shows error message when demo login fails', async () => {
      const user = userEvent.setup();
      mockedDemoLogin.mockRejectedValue({
        response: { data: { detail: 'Demo data not seeded.' } },
      });
      renderPage();

      await user.click(screen.getByRole('button', { name: /demo login as/i }));

      expect(await screen.findByText('Demo data not seeded.')).toBeInTheDocument();
    });

    it('shows fallback error message on demo login failure', async () => {
      const user = userEvent.setup();
      mockedDemoLogin.mockRejectedValue(new Error('Network'));
      renderPage();

      await user.click(screen.getByRole('button', { name: /demo login as/i }));

      expect(
        await screen.findByText('Demo login failed. Make sure seed data is loaded.'),
      ).toBeInTheDocument();
    });
  });
});
