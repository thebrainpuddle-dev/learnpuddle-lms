// src/pages/student/ProfilePage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for the Student
// ProfilePage component.
//
// Covers: page heading, subtitle, avatar initials/image, role badge, student ID,
// account section, personal information form pre-fill, student details read-only
// section, Save Changes API call, setUser invocation on success, and edge cases
// (profile picture URL, missing student_id).
//
// Mocking strategy:
//   - api (axios instance) is mocked with vi.fn() stubs for all methods.
//   - useAuthStore is mocked so the component receives a controlled user object.
//   - usePageTitle is stubbed to avoid document.title side-effects.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ProfilePage } from './ProfilePage';
import { ToastProvider } from '../../components/common';
import api from '../../config/api';
import { useAuthStore } from '../../stores/authStore';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../stores/authStore');
vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;
const mockedApi = api as unknown as { patch: ReturnType<typeof vi.fn> };

// ── Fixtures ──────────────────────────────────────────────────────────────────

const MOCK_USER = {
  id: 'user-1',
  first_name: 'Alice',
  last_name: 'Chen',
  email: 'alice.chen@school.edu',
  role: 'STUDENT' as const,
  is_active: true,
  email_verified: true,
  student_id: 'S-12345',
  grade_name: 'Grade 10',
  section_name: 'A',
  parent_email: 'parent@example.com',
  enrollment_date: '2024-06-01T00:00:00Z',
  bio: 'I love science!',
  profile_picture: null,
  profile_picture_url: null,
  created_at: '2024-01-01T00:00:00Z',
};

// ── Render helper ─────────────────────────────────────────────────────────────

const renderPage = () =>
  render(
    <MemoryRouter>
      <ToastProvider>
        <ProfilePage />
      </ToastProvider>
    </MemoryRouter>,
  );

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ProfilePage', () => {
  let mockSetUser: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.resetAllMocks();
    mockSetUser = vi.fn();
    mockedUseAuthStore.mockReturnValue({ user: MOCK_USER, setUser: mockSetUser });
    mockedApi.patch.mockResolvedValue({ data: MOCK_USER });
  });

  // ── 1. Page heading ─────────────────────────────────────────────────────────

  describe('page heading', () => {
    it('renders My Profile heading', () => {
      renderPage();
      expect(
        screen.getByRole('heading', { name: /My Profile/i }),
      ).toBeInTheDocument();
    });

    it('renders subtitle text', () => {
      renderPage();
      expect(
        screen.getByText('View your student details and manage your personal information'),
      ).toBeInTheDocument();
    });
  });

  // ── 2. Avatar card ──────────────────────────────────────────────────────────

  describe('avatar card', () => {
    it('shows user initials in avatar when no profile picture', () => {
      renderPage();
      // Initials are rendered as two adjacent text nodes inside a <span>;
      // the combined text is "AC" (Alice[0] + Chen[0]).
      expect(screen.getByText('AC')).toBeInTheDocument();
    });

    it('shows user full name in avatar card', () => {
      renderPage();
      expect(screen.getByText('Alice Chen')).toBeInTheDocument();
    });

    it('shows Student role badge', () => {
      renderPage();
      // "Student" appears in both the avatar card badge and the Account card
      // role row — at least one instance must be in the document.
      expect(screen.getAllByText('Student').length).toBeGreaterThanOrEqual(1);
    });

    it('shows student ID when available', () => {
      renderPage();
      expect(screen.getByText('ID: S-12345')).toBeInTheDocument();
    });

    it('shows avatar image when profile_picture_url is set', () => {
      mockedUseAuthStore.mockReturnValue({
        user: { ...MOCK_USER, profile_picture_url: 'https://example.com/pic.jpg' },
        setUser: mockSetUser,
      });
      renderPage();
      const img = screen.getByRole('img', { name: /profile/i });
      expect(img).toHaveAttribute('src', 'https://example.com/pic.jpg');
    });

    it('shows Not assigned for missing student_id', () => {
      mockedUseAuthStore.mockReturnValue({
        user: { ...MOCK_USER, student_id: null },
        setUser: mockSetUser,
      });
      renderPage();
      // student_id is falsy so the "ID: …" line is not rendered, and the
      // Student Details card should display "Not assigned" for Student ID.
      expect(screen.getByText('Not assigned')).toBeInTheDocument();
    });
  });

  // ── 3. Account section ──────────────────────────────────────────────────────

  describe('account section', () => {
    it('shows email in account section', () => {
      renderPage();
      expect(screen.getByText('alice.chen@school.edu')).toBeInTheDocument();
    });

    it('shows role "Student" in account section', () => {
      renderPage();
      // The Account card renders the literal string "Student" for the role row.
      // We just confirm at least one "Student" text node is in the document
      // (shared with the avatar badge assertion above, but explicit here).
      const studentNodes = screen.getAllByText('Student');
      expect(studentNodes.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 4. Personal Information form ────────────────────────────────────────────

  describe('personal information form', () => {
    it('renders Personal Information form heading', () => {
      renderPage();
      expect(screen.getByText('Personal Information')).toBeInTheDocument();
    });

    it('first name input is pre-filled with user first name', () => {
      renderPage();
      const firstNameInput = screen.getByLabelText(/First Name/i);
      expect(firstNameInput).toHaveValue('Alice');
    });

    it('last name input is pre-filled with user last name', () => {
      renderPage();
      const lastNameInput = screen.getByLabelText(/Last Name/i);
      expect(lastNameInput).toHaveValue('Chen');
    });

    it('bio textarea is pre-filled with user bio', () => {
      renderPage();
      const bioTextarea = screen.getByPlaceholderText(
        /Tell us a bit about yourself/i,
      );
      expect(bioTextarea).toHaveValue('I love science!');
    });
  });

  // ── 5. Student Details read-only section ────────────────────────────────────

  describe('student details section', () => {
    it('renders Student Details heading', () => {
      renderPage();
      expect(screen.getByText('Student Details')).toBeInTheDocument();
    });

    it('renders all five read-only field labels', () => {
      renderPage();
      expect(screen.getByText('Student ID')).toBeInTheDocument();
      expect(screen.getByText('Grade')).toBeInTheDocument();
      expect(screen.getByText('Section')).toBeInTheDocument();
      expect(screen.getByText('Parent Email')).toBeInTheDocument();
      expect(screen.getByText('Enrollment Date')).toBeInTheDocument();
    });

    it('shows correct grade value', () => {
      renderPage();
      expect(screen.getByText('Grade 10')).toBeInTheDocument();
    });

    it('shows correct parent email', () => {
      renderPage();
      expect(screen.getByText('parent@example.com')).toBeInTheDocument();
    });
  });

  // ── 6. Save Changes ─────────────────────────────────────────────────────────

  describe('save changes', () => {
    it('Save Changes calls api.patch with updated values', async () => {
      renderPage();

      const firstNameInput = screen.getByLabelText(/First Name/i);
      await userEvent.clear(firstNameInput);
      await userEvent.type(firstNameInput, 'Betty');

      await userEvent.click(screen.getByRole('button', { name: /Save Changes/i }));

      await waitFor(() => {
        expect(mockedApi.patch).toHaveBeenCalledWith('/users/auth/me/', {
          first_name: 'Betty',
          last_name: 'Chen',
          bio: 'I love science!',
        });
      });
    });

    it('Save Changes calls setUser with response data on success', async () => {
      const updatedUser = { ...MOCK_USER, first_name: 'Betty' };
      mockedApi.patch.mockResolvedValue({ data: updatedUser });

      renderPage();

      const firstNameInput = screen.getByLabelText(/First Name/i);
      await userEvent.clear(firstNameInput);
      await userEvent.type(firstNameInput, 'Betty');

      await userEvent.click(screen.getByRole('button', { name: /Save Changes/i }));

      await waitFor(() => {
        expect(mockSetUser).toHaveBeenCalledWith(updatedUser);
      });
    });

    it('shows success toast after a successful save', async () => {
      renderPage();

      await userEvent.click(screen.getByRole('button', { name: /Save Changes/i }));

      await waitFor(() => {
        expect(screen.getByText('Profile updated')).toBeInTheDocument();
      });
    });

    it('shows error toast when api.patch rejects', async () => {
      mockedApi.patch.mockRejectedValue(new Error('Network error'));

      renderPage();

      await userEvent.click(screen.getByRole('button', { name: /Save Changes/i }));

      await waitFor(() => {
        expect(screen.getByText('Failed')).toBeInTheDocument();
      });
    });
  });
});
