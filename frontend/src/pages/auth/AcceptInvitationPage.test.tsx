// src/pages/auth/AcceptInvitationPage.test.tsx
//
// Vitest + React Testing Library tests for AcceptInvitationPage.
// Covers: loading state, error state, form rendering, submission, success state,
// and validation (password mismatch).

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ token: 'test-token' }),
  };
});

vi.mock('../../services/adminTeachersService', () => ({
  adminTeachersService: {
    validateInvitation: vi.fn(),
    acceptInvitation: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { adminTeachersService } from '../../services/adminTeachersService';

const mockValidateInvitation = adminTeachersService.validateInvitation as ReturnType<typeof vi.fn>;
const mockAcceptInvitation = adminTeachersService.acceptInvitation as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

const INVITATION_DATA = {
  school_name: 'Test School',
  email: 'teacher@test.com',
  first_name: 'John',
  last_name: 'Doe',
  expires_at: '2026-12-31T00:00:00Z',
};

import { AcceptInvitationPage } from './AcceptInvitationPage';

function renderPage() {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={['/invitation/test-token']}>
        <AcceptInvitationPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('AcceptInvitationPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // ── 1. Loading state ──────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows spinner while validating invitation', () => {
      mockValidateInvitation.mockReturnValue(new Promise(() => {})); // never resolves
      renderPage();
      // The spinner is a div with animate-spin; also check for text
      expect(screen.getByText(/validating invitation/i)).toBeInTheDocument();
    });

    it('shows "Validating invitation..." text while loading', () => {
      mockValidateInvitation.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByText('Validating invitation...')).toBeInTheDocument();
    });

    it('does not show the form while loading', () => {
      mockValidateInvitation.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.queryByRole('button', { name: /create account/i })).not.toBeInTheDocument();
    });
  });

  // ── 2. Error state ────────────────────────────────────────────────────────

  describe('error state', () => {
    it('shows "Invalid Invitation" heading on validation error', async () => {
      mockValidateInvitation.mockRejectedValue({
        response: { data: { error: 'This invitation has expired.' } },
      });
      renderPage();
      expect(await screen.findByText('Invalid Invitation')).toBeInTheDocument();
    });

    it('shows the error message from the API response', async () => {
      mockValidateInvitation.mockRejectedValue({
        response: { data: { error: 'This invitation has expired.' } },
      });
      renderPage();
      expect(await screen.findByText('This invitation has expired.')).toBeInTheDocument();
    });

    it('shows error message from err.message when no response data', async () => {
      mockValidateInvitation.mockRejectedValue(new Error('Network error'));
      renderPage();
      expect(await screen.findByText('Network error')).toBeInTheDocument();
    });

    it('shows fallback error text when no message available', async () => {
      mockValidateInvitation.mockRejectedValue({});
      renderPage();
      expect(await screen.findByText('Something went wrong.')).toBeInTheDocument();
    });

    it('shows "Go to Login" button in error state', async () => {
      mockValidateInvitation.mockRejectedValue({
        response: { data: { error: 'Expired.' } },
      });
      renderPage();
      await screen.findByText('Invalid Invitation');
      expect(screen.getByRole('button', { name: /go to login/i })).toBeInTheDocument();
    });

    it('"Go to Login" button in error state navigates to /login', async () => {
      const user = userEvent.setup();
      mockValidateInvitation.mockRejectedValue({
        response: { data: { error: 'Expired.' } },
      });
      renderPage();
      await screen.findByText('Invalid Invitation');
      await user.click(screen.getByRole('button', { name: /go to login/i }));
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });

    it('does not show the invitation form in error state', async () => {
      mockValidateInvitation.mockRejectedValue({
        response: { data: { error: 'Expired.' } },
      });
      renderPage();
      await screen.findByText('Invalid Invitation');
      expect(screen.queryByRole('button', { name: /create account/i })).not.toBeInTheDocument();
    });
  });

  // ── 3. Form state (valid invitation) ─────────────────────────────────────

  describe('form state (valid invitation)', () => {
    beforeEach(() => {
      mockValidateInvitation.mockResolvedValue(INVITATION_DATA);
    });

    it('shows school name in invitation banner', async () => {
      renderPage();
      expect(await screen.findByText(/Test School/)).toBeInTheDocument();
    });

    it('shows invitee email in invitation banner', async () => {
      renderPage();
      expect(await screen.findByText(/teacher@test.com/)).toBeInTheDocument();
    });

    it('shows first name in a disabled input', async () => {
      renderPage();
      await screen.findByText(/Test School/);
      const firstNameInput = screen.getByDisplayValue('John');
      expect(firstNameInput).toBeDisabled();
    });

    it('renders the password field', async () => {
      renderPage();
      await screen.findByText(/Test School/);
      expect(screen.getByPlaceholderText('Choose a strong password')).toBeInTheDocument();
    });

    it('renders the confirm password field', async () => {
      renderPage();
      await screen.findByText(/Test School/);
      expect(screen.getByPlaceholderText('Re-enter your password')).toBeInTheDocument();
    });

    it('shows "Create Account & Join" submit button', async () => {
      renderPage();
      await screen.findByText(/Test School/);
      expect(screen.getByRole('button', { name: /create account & join/i })).toBeInTheDocument();
    });

    it('shows invitation expiry date', async () => {
      renderPage();
      await screen.findByText(/Test School/);
      // The date is formatted via toLocaleDateString
      expect(screen.getByText(/invitation expires/i)).toBeInTheDocument();
    });
  });

  // ── 4. Form submission ────────────────────────────────────────────────────

  describe('form submission', () => {
    beforeEach(() => {
      mockValidateInvitation.mockResolvedValue(INVITATION_DATA);
    });

    it('calls acceptInvitation with the token and password on submit', async () => {
      const user = userEvent.setup();
      mockAcceptInvitation.mockResolvedValue({ message: 'ok', email: 'teacher@test.com' });
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'StrongPass123!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      await waitFor(() => {
        expect(mockAcceptInvitation).toHaveBeenCalledWith('test-token', 'StrongPass123!');
      });
    });

    it('shows "Account Created!" heading on successful acceptance', async () => {
      const user = userEvent.setup();
      mockAcceptInvitation.mockResolvedValue({ message: 'ok', email: 'teacher@test.com' });
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'StrongPass123!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      expect(await screen.findByText('Account Created!')).toBeInTheDocument();
    });

    it('shows success message after account creation', async () => {
      const user = userEvent.setup();
      mockAcceptInvitation.mockResolvedValue({ message: 'ok', email: 'teacher@test.com' });
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'StrongPass123!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      expect(
        await screen.findByText(/your account has been set up successfully/i),
      ).toBeInTheDocument();
    });

    it('shows "Go to Login" button in accepted state', async () => {
      const user = userEvent.setup();
      mockAcceptInvitation.mockResolvedValue({ message: 'ok', email: 'teacher@test.com' });
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'StrongPass123!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      await screen.findByText('Account Created!');
      expect(screen.getByRole('button', { name: /go to login/i })).toBeInTheDocument();
    });

    it('"Go to Login" in accepted state navigates to /login', async () => {
      const user = userEvent.setup();
      mockAcceptInvitation.mockResolvedValue({ message: 'ok', email: 'teacher@test.com' });
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'StrongPass123!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      await screen.findByText('Account Created!');
      await user.click(screen.getByRole('button', { name: /go to login/i }));
      expect(mockNavigate).toHaveBeenCalledWith('/login');
    });
  });

  // ── 5. Mutation error ─────────────────────────────────────────────────────

  describe('submission error', () => {
    beforeEach(() => {
      mockValidateInvitation.mockResolvedValue(INVITATION_DATA);
    });

    it('shows server error message when acceptInvitation fails', async () => {
      const user = userEvent.setup();
      mockAcceptInvitation.mockRejectedValue({
        response: { data: { error: 'Token already used.' } },
      });
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'StrongPass123!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      expect(await screen.findByText('Token already used.')).toBeInTheDocument();
    });

    it('shows joined details error when response has details array', async () => {
      const user = userEvent.setup();
      mockAcceptInvitation.mockRejectedValue({
        response: { data: { details: ['Password too short.', 'Use a number.'] } },
      });
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'StrongPass123!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      expect(await screen.findByText('Password too short. Use a number.')).toBeInTheDocument();
    });

    it('shows fallback error message when no API error detail', async () => {
      const user = userEvent.setup();
      mockAcceptInvitation.mockRejectedValue(new Error('Network'));
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'StrongPass123!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      expect(
        await screen.findByText('Failed to create account. Please try again.'),
      ).toBeInTheDocument();
    });

    it('does not navigate to /login on error', async () => {
      const user = userEvent.setup();
      mockAcceptInvitation.mockRejectedValue({
        response: { data: { error: 'Oops.' } },
      });
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'StrongPass123!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      await screen.findByText('Oops.');
      expect(mockNavigate).not.toHaveBeenCalled();
    });
  });

  // ── 6. Password validation ────────────────────────────────────────────────

  describe('password mismatch validation', () => {
    beforeEach(() => {
      mockValidateInvitation.mockResolvedValue(INVITATION_DATA);
    });

    it('shows password mismatch error when passwords differ', async () => {
      const user = userEvent.setup();
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'DifferentPass!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      expect(await screen.findByText('Passwords do not match')).toBeInTheDocument();
    });

    it('does not call acceptInvitation when passwords do not match', async () => {
      const user = userEvent.setup();
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'StrongPass123!');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'DifferentPass!');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      await screen.findByText('Passwords do not match');
      expect(mockAcceptInvitation).not.toHaveBeenCalled();
    });

    it('shows min-length error when password is too short', async () => {
      const user = userEvent.setup();
      renderPage();

      await screen.findByText(/Test School/);
      await user.type(screen.getByPlaceholderText('Choose a strong password'), 'short');
      await user.type(screen.getByPlaceholderText('Re-enter your password'), 'short');
      await user.click(screen.getByRole('button', { name: /create account & join/i }));

      expect(await screen.findByText('Password must be at least 8 characters')).toBeInTheDocument();
    });
  });
});
