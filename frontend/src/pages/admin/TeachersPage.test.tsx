// src/pages/admin/TeachersPage.test.tsx
//
// FE-037: Tests for the Admin Teachers management page.
// Covers: teacher list (loading, empty, populated), search, edit modal, deactivate
// confirmation, bulk selection + bulk actions, invite form (success + Zod validation
// + server error), invitations tab rendering, and Create Teacher navigation.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { TeachersPage } from './TeachersPage';
import { ToastProvider } from '../../components/common';
import { adminTeachersService } from '../../services/adminTeachersService';
import type { TeacherInvitation } from '../../services/adminTeachersService';
import type { User } from '../../types';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/adminTeachersService', () => ({
  adminTeachersService: {
    listTeachers:      vi.fn(),
    updateTeacher:     vi.fn(),
    deactivateTeacher: vi.fn(),
    bulkImportCSV:     vi.fn(),
    bulkAction:        vi.fn(),
    listInvitations:   vi.fn(),
    createInvitation:  vi.fn(),
    bulkInviteCSV:     vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('../../hooks/useModeLabels', () => ({
  useModeLabels: () => ({
    label: (key: string) => (key === 'learner_plural' ? 'Teachers' : key),
    mode: 'education',
    modeLabels: {},
  }),
}));

vi.mock('../../stores/tenantStore', () => ({
  useTenantStore: () => ({ usage: null }),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const TEACHER_ALICE: User = {
  id: 't-1',
  email: 'alice@example.com',
  first_name: 'Alice',
  last_name: 'Smith',
  role: 'TEACHER',
  is_active: true,
  email_verified: true,
  department: 'Mathematics',
  employee_id: 'EMP001',
  created_at: '2026-01-01T00:00:00Z',
};

const TEACHER_BOB: User = {
  id: 't-2',
  email: 'bob@example.com',
  first_name: 'Bob',
  last_name: 'Jones',
  role: 'HOD',
  is_active: true,
  email_verified: true,
  department: 'Science',
  employee_id: 'EMP002',
  created_at: '2026-01-02T00:00:00Z',
};

const TEACHER_INACTIVE: User = {
  id: 't-3',
  email: 'carol@example.com',
  first_name: 'Carol',
  last_name: 'Lee',
  role: 'TEACHER',
  is_active: false,
  email_verified: true,
  department: '',
  employee_id: '',
  created_at: '2026-01-03T00:00:00Z',
};

const INVITATION_PENDING: TeacherInvitation = {
  id: 'inv-1',
  email: 'newteacher@example.com',
  first_name: 'New',
  last_name: 'Teacher',
  status: 'pending',
  created_at: '2026-04-01T10:00:00Z',
  expires_at: '2026-04-08T10:00:00Z',
  accepted_at: null,
  invited_by: 'admin@example.com',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const svc = adminTeachersService as {
  listTeachers:      ReturnType<typeof vi.fn>;
  updateTeacher:     ReturnType<typeof vi.fn>;
  deactivateTeacher: ReturnType<typeof vi.fn>;
  bulkImportCSV:     ReturnType<typeof vi.fn>;
  bulkAction:        ReturnType<typeof vi.fn>;
  listInvitations:   ReturnType<typeof vi.fn>;
  createInvitation:  ReturnType<typeof vi.fn>;
  bulkInviteCSV:     ReturnType<typeof vi.fn>;
};

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries:   { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderPage() {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <TeachersPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  mockNavigate.mockReset();
  // Default: one active teacher, invitations load empty
  svc.listTeachers.mockResolvedValue([TEACHER_ALICE]);
  svc.listInvitations.mockResolvedValue([]);
  svc.updateTeacher.mockResolvedValue({ ...TEACHER_ALICE, first_name: 'Alicia' });
  svc.deactivateTeacher.mockResolvedValue(undefined);
  svc.bulkAction.mockResolvedValue({ message: '1 teacher activated', affected_count: 1, requested_count: 1 });
  svc.createInvitation.mockResolvedValue(INVITATION_PENDING);
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('TeachersPage', () => {
  // ── 1. Teachers tab — default render ─────────────────────────────────────

  describe('teachers tab — default render', () => {
    it('shows loading state while query is pending', async () => {
      svc.listTeachers.mockReturnValue(new Promise(() => {})); // never resolves
      renderPage();
      // Both desktop table and mobile cards render "Loading..." in jsdom (no CSS)
      expect(screen.getAllByText('Loading...').length).toBeGreaterThanOrEqual(1);
    });

    it('renders teacher name and email after query resolves', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getAllByText('Alice Smith').length).toBeGreaterThanOrEqual(1);
      });
      expect(screen.getAllByText('alice@example.com').length).toBeGreaterThanOrEqual(1);
    });

    it('shows empty state when no teachers exist', async () => {
      svc.listTeachers.mockResolvedValue([]);
      renderPage();
      // Desktop EmptyState title + mobile card message both contain "No teachers yet"
      await waitFor(() => {
        expect(screen.getAllByText(/no teachers yet/i).length).toBeGreaterThanOrEqual(1);
      });
    });

    it('active teacher shows Deactivate button; inactive teacher does not', async () => {
      svc.listTeachers.mockResolvedValue([TEACHER_ALICE, TEACHER_INACTIVE]);
      renderPage();
      await waitFor(() => {
        expect(screen.getAllByText('Alice Smith').length).toBeGreaterThanOrEqual(1);
      });
      // Mobile card "Deactivate" button exists for active Alice
      expect(screen.getAllByRole('button', { name: /deactivate/i }).length).toBeGreaterThanOrEqual(1);
      // Carol (inactive) should not add a second Deactivate button in mobile cards
      // Only one mobile-card Deactivate button total (Alice's)
      const deactivateBtns = screen.getAllByRole('button', { name: /deactivate/i });
      expect(deactivateBtns.length).toBe(1);
    });
  });

  // ── 2. Search ─────────────────────────────────────────────────────────────

  describe('search', () => {
    it('typing in the search input calls listTeachers with the search term', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => expect(svc.listTeachers).toHaveBeenCalledWith({ search: '' }));

      const searchInput = screen.getByPlaceholderText('Search by name or email');
      await user.clear(searchInput);
      await user.type(searchInput, 'alice');

      await waitFor(() =>
        expect(svc.listTeachers).toHaveBeenCalledWith({ search: 'alice' }),
      );
    });
  });

  // ── 3. Navigation ─────────────────────────────────────────────────────────

  describe('navigation', () => {
    it('clicking Create Teacher navigates to /admin/teachers/new', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      await user.click(screen.getByRole('button', { name: /create teacher/i }));
      expect(mockNavigate).toHaveBeenCalledWith('/admin/teachers/new');
    });
  });

  // ── 4. Edit modal ─────────────────────────────────────────────────────────

  describe('edit modal', () => {
    it('clicking Edit opens modal pre-populated with teacher fields', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      // Mobile card Edit button (desktop table has icon-only edit button)
      await user.click(screen.getAllByRole('button', { name: /edit/i })[0]);

      // The edit panel is a plain <div> (not Headless UI Dialog) — check heading
      await waitFor(() => expect(screen.getByText('Edit Teacher')).toBeInTheDocument());

      // Fields should be pre-populated with Alice's data
      expect(screen.getByDisplayValue('Alice')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Smith')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Mathematics')).toBeInTheDocument();
      expect(screen.getByDisplayValue('EMP001')).toBeInTheDocument();
    });

    it('submitting the edit form calls updateTeacher with updated data', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      // Open edit modal
      await user.click(screen.getAllByRole('button', { name: /edit/i })[0]);

      // Change first name
      const firstNameInput = screen.getByDisplayValue('Alice');
      await user.clear(firstNameInput);
      await user.type(firstNameInput, 'Alicia');

      // Submit
      await user.click(screen.getByRole('button', { name: /save/i }));

      await waitFor(() =>
        expect(svc.updateTeacher).toHaveBeenCalledWith(
          't-1',
          expect.objectContaining({ first_name: 'Alicia' }),
        ),
      );
    });

    it('successful edit shows success toast and closes modal', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      await user.click(screen.getAllByRole('button', { name: /edit/i })[0]);
      await user.click(screen.getByRole('button', { name: /save/i }));

      await waitFor(() =>
        expect(screen.getByText('Teacher updated')).toBeInTheDocument(),
      );
      // Modal heading should no longer be visible
      expect(screen.queryByText('Edit Teacher')).not.toBeInTheDocument();
    });

    it('Cancel button closes modal without calling updateTeacher', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      await user.click(screen.getAllByRole('button', { name: /edit/i })[0]);
      expect(screen.getByText('Edit Teacher')).toBeInTheDocument();

      await user.click(screen.getByRole('button', { name: /cancel/i }));
      expect(screen.queryByText('Edit Teacher')).not.toBeInTheDocument();
      expect(svc.updateTeacher).not.toHaveBeenCalled();
    });
  });

  // ── 5. Deactivate teacher ─────────────────────────────────────────────────

  describe('deactivate teacher', () => {
    it('clicking Deactivate opens ConfirmDialog with teacher name', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      // Mobile card Deactivate button
      await user.click(screen.getByRole('button', { name: /deactivate/i }));

      await waitFor(() => {
        expect(screen.getByText(/deactivate alice smith/i)).toBeInTheDocument();
      });
    });

    it('confirming deactivation calls deactivateTeacher and shows success toast', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      // Click mobile-card Deactivate button to open ConfirmDialog
      await user.click(screen.getByRole('button', { name: /deactivate/i }));

      // Headless UI Dialog renders with role="dialog" when isOpen=true
      const dialog = await screen.findByRole('dialog');
      // Confirm button inside the dialog shares the label "Deactivate" (confirmLabel prop)
      await user.click(within(dialog).getByRole('button', { name: /^deactivate$/i }));

      await waitFor(() =>
        expect(svc.deactivateTeacher).toHaveBeenCalledWith('t-1'),
      );
      await waitFor(() =>
        expect(screen.getByText('Teacher deactivated')).toBeInTheDocument(),
      );
    });
  });

  // ── 6. Bulk selection and actions ─────────────────────────────────────────

  describe('bulk selection and actions', () => {
    it('checking a row checkbox shows BulkActionsBar with selected count', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      // Desktop row checkbox has aria-label
      const rowCheckbox = screen.getByRole('checkbox', {
        name: /select alice smith/i,
      });
      await user.click(rowCheckbox);

      await waitFor(() =>
        expect(screen.getByText(/1/)).toBeInTheDocument(),
      );
      expect(screen.getByText('selected')).toBeInTheDocument();
    });

    it('Select All selects all loaded teachers', async () => {
      svc.listTeachers.mockResolvedValue([TEACHER_ALICE, TEACHER_BOB]);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      const selectAll = screen.getByRole('checkbox', { name: /select all teachers/i });
      await user.click(selectAll);

      await waitFor(() => {
        const countEl = screen.getByText('2');
        expect(countEl).toBeInTheDocument();
      });
      expect(screen.getByText('selected')).toBeInTheDocument();
    });

    it('clicking Activate calls bulkAction with activate + selected teacher ids', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      // Select Alice via the desktop-table aria-labelled checkbox
      await user.click(
        screen.getByRole('checkbox', { name: /select alice smith/i }),
      );

      // Wait for BulkActionsBar to appear (it renders only when selectedCount > 0)
      const activateBtn = await screen.findByRole('button', { name: /^activate$/i });
      await user.click(activateBtn);

      await waitFor(() =>
        expect(svc.bulkAction).toHaveBeenCalledWith('activate', ['t-1']),
      );
      await waitFor(() =>
        expect(screen.getByText('Bulk action complete')).toBeInTheDocument(),
      );
    });
  });

  // ── 7. Invitations tab — render ───────────────────────────────────────────

  describe('invitations tab', () => {
    it('clicking Invitations tab shows the invitations table', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      await user.click(screen.getByRole('button', { name: /invitations/i }));

      await waitFor(() => {
        // Table header "Email" is unique to the invitations view
        expect(screen.getByRole('columnheader', { name: /email/i })).toBeInTheDocument();
      });
    });

    it('renders invitation rows with email, name, and status badge', async () => {
      svc.listInvitations.mockResolvedValue([INVITATION_PENDING]);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      await user.click(screen.getByRole('button', { name: /invitations/i }));

      await waitFor(() =>
        expect(screen.getByText('newteacher@example.com')).toBeInTheDocument(),
      );
      expect(screen.getByText('New Teacher')).toBeInTheDocument();
      expect(screen.getByText('Pending')).toBeInTheDocument();
    });

    it('shows empty state message when no invitations exist', async () => {
      svc.listInvitations.mockResolvedValue([]);
      const user = userEvent.setup();
      renderPage();
      await waitFor(() => screen.getAllByText('Alice Smith'));

      await user.click(screen.getByRole('button', { name: /invitations/i }));

      await waitFor(() =>
        expect(screen.getByText('No invitations sent yet.')).toBeInTheDocument(),
      );
    });
  });

  // ── 8. Invite form ────────────────────────────────────────────────────────

  describe('invite form', () => {
    async function openInviteModal(user: ReturnType<typeof userEvent.setup>) {
      await waitFor(() => screen.getAllByText('Alice Smith'));
      // Navigate to invitations tab first
      await user.click(screen.getByRole('button', { name: /invitations/i }));
      await waitFor(() => screen.getByText('No invitations sent yet.'));
      await user.click(screen.getByRole('button', { name: /invite teacher/i }));
      await waitFor(() => screen.getByText(/invitation expires in 7 days/i));
    }

    it('clicking Invite Teacher shows the invite modal form', async () => {
      const user = userEvent.setup();
      renderPage();
      await openInviteModal(user);

      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /send invitation/i })).toBeInTheDocument();
    });

    it('filling and submitting the form calls createInvitation with correct data', async () => {
      const user = userEvent.setup();
      renderPage();
      await openInviteModal(user);

      await user.type(screen.getByLabelText(/email/i), 'jane@school.com');
      await user.type(screen.getByLabelText(/first name/i), 'Jane');
      await user.type(screen.getByLabelText(/last name/i), 'Doe');
      await user.click(screen.getByRole('button', { name: /send invitation/i }));

      await waitFor(() =>
        expect(svc.createInvitation).toHaveBeenCalledWith(
          expect.objectContaining({
            email: 'jane@school.com',
            first_name: 'Jane',
            last_name: 'Doe',
          }),
        ),
      );
    });

    it('successful invite shows toast and closes modal', async () => {
      const user = userEvent.setup();
      renderPage();
      await openInviteModal(user);

      await user.type(screen.getByLabelText(/email/i), 'jane@school.com');
      await user.type(screen.getByLabelText(/first name/i), 'Jane');
      await user.click(screen.getByRole('button', { name: /send invitation/i }));

      await waitFor(() =>
        expect(screen.getByText('Invitation Sent')).toBeInTheDocument(),
      );
      expect(screen.queryByRole('button', { name: /send invitation/i })).not.toBeInTheDocument();
    });

    it('empty email shows Zod validation error and does not call createInvitation', async () => {
      const user = userEvent.setup();
      renderPage();
      await openInviteModal(user);

      // Submit without filling email
      await user.click(screen.getByRole('button', { name: /send invitation/i }));

      await waitFor(() =>
        expect(screen.getByText(/email is required/i)).toBeInTheDocument(),
      );
      expect(svc.createInvitation).not.toHaveBeenCalled();
    });

    it('server error on invite sets field-level error on email', async () => {
      svc.createInvitation.mockRejectedValue({
        response: {
          data: {
            email: ['A user with this email already exists.'],
            error: 'Failed to send invitation',
          },
        },
      });

      const user = userEvent.setup();
      renderPage();
      await openInviteModal(user);

      await user.type(screen.getByLabelText(/email/i), 'existing@school.com');
      await user.type(screen.getByLabelText(/first name/i), 'Jane');
      await user.click(screen.getByRole('button', { name: /send invitation/i }));

      await waitFor(() =>
        expect(
          screen.getByText('A user with this email already exists.'),
        ).toBeInTheDocument(),
      );
    });
  });
});
