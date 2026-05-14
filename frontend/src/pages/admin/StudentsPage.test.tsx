// src/pages/admin/StudentsPage.test.tsx
//
// Test suite for StudentsPage — admin student management.
//
// Coverage strategy:
//   1. Page render states (loading, empty, populated)
//   2. Tab navigation (Students ↔ Invitations)
//   3. Search input triggers re-fetch
//   4. Filters panel (toggle, grade/section filters)
//   5. Create Student modal (open, form validation, submit, server errors, cancel)
//   6. Edit Student modal (open with pre-populated data, save, cancel)
//   7. Delete student (confirmation dialog, confirm, cancel)
//   8. Bulk selection (checkbox, select all, BulkActionsBar)
//   9. Bulk actions (activate, deactivate, delete)
//  10. Invitations tab (table renders, Invite Student modal, submit, cancel)
//  11. Usage quota display
//
// Mock decisions:
//   • adminStudentsService: all methods vi.fn()
//   • useTenantStore: provides usage quota
//   • useToast: captured for assertion
//   • usePageTitle: no-op
//
// jsdom note: Tailwind `hidden md:block` / `md:hidden` CSS is NOT processed,
// so BOTH desktop table and mobile cards render simultaneously. Tests use
// getAllByText()[0] to target desktop-table elements (first in DOM order)
// and scope action buttons via within(row).

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { StudentsPage } from './StudentsPage';
import { adminStudentsService } from '../../services/adminStudentsService';
import { useTenantStore } from '../../stores/tenantStore';

// ── service mock ─────────────────────────────────────────────────────────────
vi.mock('../../services/adminStudentsService', () => ({
  adminStudentsService: {
    listStudents: vi.fn(),
    createStudent: vi.fn(),
    updateStudent: vi.fn(),
    deleteStudent: vi.fn(),
    bulkImportCSV: vi.fn(),
    bulkAction: vi.fn(),
    listInvitations: vi.fn(),
    createInvitation: vi.fn(),
    bulkInviteCSV: vi.fn(),
  },
}));

// ── tenant store mock ────────────────────────────────────────────────────────
vi.mock('../../stores/tenantStore');
const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;

// ── page utility mocks ───────────────────────────────────────────────────────
vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── toast mock ───────────────────────────────────────────────────────────────
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('../../components/common', async () => {
  const actual = await vi.importActual('../../components/common');
  return {
    ...actual,
    useToast: () => ({ success: mockToastSuccess, error: mockToastError }),
  };
});

// ── typed refs ───────────────────────────────────────────────────────────────
const mockedService = adminStudentsService as {
  listStudents: ReturnType<typeof vi.fn>;
  createStudent: ReturnType<typeof vi.fn>;
  updateStudent: ReturnType<typeof vi.fn>;
  deleteStudent: ReturnType<typeof vi.fn>;
  bulkImportCSV: ReturnType<typeof vi.fn>;
  bulkAction: ReturnType<typeof vi.fn>;
  listInvitations: ReturnType<typeof vi.fn>;
  createInvitation: ReturnType<typeof vi.fn>;
  bulkInviteCSV: ReturnType<typeof vi.fn>;
};

// ── fixture data ─────────────────────────────────────────────────────────────
const STUDENT_A = {
  id: 's-1',
  email: 'alice@school.edu',
  first_name: 'Alice',
  last_name: 'Wong',
  student_id: 'KIS-001',
  grade_level: 'Grade 5',
  section: 'A',
  parent_email: 'parent@home.com',
  enrollment_date: '2025-09-01',
  is_active: true,
  last_login: null,
  created_at: '2025-09-01T00:00:00Z',
};

const STUDENT_B = {
  id: 's-2',
  email: 'bob@school.edu',
  first_name: 'Bob',
  last_name: 'Chen',
  student_id: '',
  grade_level: 'Grade 6',
  section: 'B',
  parent_email: '',
  enrollment_date: '',
  is_active: false,
  last_login: null,
  created_at: '2025-09-01T00:00:00Z',
};

const MOCK_STUDENTS_RESPONSE = {
  results: [STUDENT_A, STUDENT_B],
  count: 2,
  next: null,
  previous: null,
};

const MOCK_INVITATIONS = [
  {
    id: 'inv-1',
    email: 'charlie@home.com',
    first_name: 'Charlie',
    last_name: 'Day',
    status: 'pending' as const,
    created_at: '2026-04-01T00:00:00Z',
    expires_at: '2026-04-08T00:00:00Z',
    accepted_at: null,
    invited_by: 'Admin User',
  },
  {
    id: 'inv-2',
    email: 'dana@home.com',
    first_name: 'Dana',
    last_name: 'Smith',
    status: 'accepted' as const,
    created_at: '2026-03-15T00:00:00Z',
    expires_at: '2026-03-22T00:00:00Z',
    accepted_at: '2026-03-16T00:00:00Z',
    invited_by: null,
  },
];

// ── helpers ──────────────────────────────────────────────────────────────────
function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
}

function renderPage(search = '') {
  const url = search ? `/?${search}` : '/';
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[url]}>
        <StudentsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/**
 * Find the first desktop-table <tr> that contains the given student name.
 * Both desktop table and mobile cards render in jsdom (Tailwind CSS not applied).
 * Desktop table comes first in DOM order, so getAllByText()[0] is the <td>.
 */
function getStudentTableRow(name: string): HTMLElement {
  const cell = screen.getAllByText(name)[0];
  const row = cell.closest('tr');
  if (!row) throw new Error(`No <tr> ancestor for text "${name}"`);
  return row;
}

// ────────────────────────────────────────────────────────────────────────────
describe('StudentsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedUseTenantStore.mockReturnValue({ usage: null });
    mockedService.listStudents.mockResolvedValue(MOCK_STUDENTS_RESPONSE);
    mockedService.listInvitations.mockResolvedValue(MOCK_INVITATIONS);
    mockedService.createStudent.mockResolvedValue(STUDENT_A);
    mockedService.updateStudent.mockResolvedValue(STUDENT_A);
    mockedService.deleteStudent.mockResolvedValue(undefined);
    mockedService.bulkAction.mockResolvedValue({ message: 'Done', affected_count: 1, requested_count: 1 });
    mockedService.bulkImportCSV.mockResolvedValue({ created: 3, total_rows: 3, results: [] });
    mockedService.createInvitation.mockResolvedValue({});
    mockedService.bulkInviteCSV.mockResolvedValue({ created: 2, total_rows: 2, results: [] });
  });

  // ── 1. Loading state ─────────────────────────────────────────────────────
  describe('loading state', () => {
    it('shows Loading text while query is pending', () => {
      mockedService.listStudents.mockReturnValue(new Promise(() => {}));
      renderPage();
      // Both desktop table <td> and mobile <div> render "Loading..." — use >= 1
      expect(screen.getAllByText('Loading...').length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 2. Page header ───────────────────────────────────────────────────────
  describe('page header', () => {
    it('renders the Students heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { name: /Students/i })).toBeInTheDocument();
    });

    it('shows Add Student button on students tab', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /Add Student/i })).toBeInTheDocument();
    });

    it('shows CSV Import button on students tab', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /CSV Import/i })).toBeInTheDocument();
    });
  });

  // ── 3. Student table renders ─────────────────────────────────────────────
  describe('student table', () => {
    it('renders student names in the table', async () => {
      renderPage();
      await waitFor(() => {
        // getAllByText handles the dual desktop+mobile rendering
        expect(screen.getAllByText('Alice Wong').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('Bob Chen').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders student emails', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getAllByText('alice@school.edu').length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText('bob@school.edu').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('renders student ID when present', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getAllByText('KIS-001').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows dash when student_id is empty', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows grade level badge for Alice', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getAllByText('Grade 5').length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows active status (Yes) for Alice in desktop table', async () => {
      renderPage();
      expect(await screen.findByText('Yes')).toBeInTheDocument();
    });

    it('shows inactive status (No) for Bob in desktop table', async () => {
      renderPage();
      expect(await screen.findByText('No')).toBeInTheDocument();
    });

    it('shows empty state when no students found', async () => {
      mockedService.listStudents.mockResolvedValue({ results: [], count: 0, next: null, previous: null });
      renderPage();
      // Both desktop table <td> and mobile <div> render "No students found." — use >= 1
      await waitFor(() => {
        expect(screen.getAllByText(/No students found/i).length).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows result count', async () => {
      renderPage();
      expect(await screen.findByText(/2 students found/i)).toBeInTheDocument();
    });
  });

  // ── 4. Tab navigation ────────────────────────────────────────────────────
  describe('tab navigation', () => {
    it('shows Students and Invitations tabs', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /^Students$/i })).toBeInTheDocument();
      expect(await screen.findByRole('button', { name: /^Invitations$/i })).toBeInTheDocument();
    });

    it('defaults to Students tab with Add Student button', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /Add Student/i })).toBeInTheDocument();
    });

    it('switching to Invitations tab shows Invite Student button', async () => {
      renderPage();
      const invTab = await screen.findByRole('button', { name: /^Invitations$/i });
      await userEvent.click(invTab);
      expect(await screen.findByRole('button', { name: /Invite Student/i })).toBeInTheDocument();
    });

    it('switching to Invitations tab hides Add Student button', async () => {
      renderPage();
      const invTab = await screen.findByRole('button', { name: /^Invitations$/i });
      await userEvent.click(invTab);
      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /Add Student/i })).not.toBeInTheDocument();
      });
    });
  });

  // ── 5. Search ────────────────────────────────────────────────────────────
  describe('search', () => {
    it('renders search input', async () => {
      renderPage();
      expect(await screen.findByPlaceholderText(/Search by name, email/i)).toBeInTheDocument();
    });

    it('typing in search re-fetches students with search param', async () => {
      renderPage();
      const input = await screen.findByPlaceholderText(/Search by name, email/i);
      await userEvent.type(input, 'alice');
      await waitFor(() => {
        expect(mockedService.listStudents).toHaveBeenCalledWith(
          expect.objectContaining({ search: 'alice' })
        );
      });
    });
  });

  // ── 6. Filters ───────────────────────────────────────────────────────────
  describe('filters', () => {
    it('Filters button is visible', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /Filters/i })).toBeInTheDocument();
    });

    it('clicking Filters button shows grade and section dropdowns', async () => {
      renderPage();
      const filtersBtn = await screen.findByRole('button', { name: /Filters/i });
      await userEvent.click(filtersBtn);
      expect(await screen.findByLabelText(/Grade Level/i)).toBeInTheDocument();
      expect(await screen.findByLabelText(/Section/i)).toBeInTheDocument();
    });

    it('grade filter re-fetches students with grade_level', async () => {
      renderPage();
      const filtersBtn = await screen.findByRole('button', { name: /Filters/i });
      await userEvent.click(filtersBtn);
      const gradeSelect = await screen.findByLabelText(/Grade Level/i);
      await userEvent.selectOptions(gradeSelect, 'Grade 5');
      await waitFor(() => {
        expect(mockedService.listStudents).toHaveBeenCalledWith(
          expect.objectContaining({ grade_level: 'Grade 5' })
        );
      });
    });
  });

  // ── 7. Create Student modal ──────────────────────────────────────────────
  describe('create student modal', () => {
    it('clicking Add Student opens the create modal', async () => {
      renderPage();
      const btn = await screen.findByRole('button', { name: /Add Student/i });
      await userEvent.click(btn);
      expect(await screen.findByRole('heading', { name: /Add Student/i })).toBeInTheDocument();
    });

    it('create modal has required form fields', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Student/i }));
      expect(await screen.findByLabelText(/First Name \*/i)).toBeInTheDocument();
      expect(await screen.findByLabelText(/Last Name \*/i)).toBeInTheDocument();
      expect(await screen.findByLabelText(/Email \*/i)).toBeInTheDocument();
    });

    it('Cancel button closes the create modal', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Student/i }));
      const cancelBtn = await screen.findByRole('button', { name: /Cancel/i });
      await userEvent.click(cancelBtn);
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Add Student/i })).not.toBeInTheDocument();
      });
    });

    it('submitting with empty fields shows validation errors', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Student/i }));
      const submitBtn = await screen.findByRole('button', { name: /Create Student/i });
      await userEvent.click(submitBtn);
      await waitFor(() => {
        expect(screen.queryAllByText(/required/i).length).toBeGreaterThan(0);
      });
    });

    it('successful create shows success toast and closes modal', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Student/i }));

      await userEvent.type(await screen.findByLabelText(/First Name \*/i), 'Alice');
      await userEvent.type(screen.getByLabelText(/Last Name \*/i), 'Wong');
      await userEvent.type(screen.getByLabelText(/Email \*/i), 'alice@school.edu');
      const passwordFields = screen.getAllByLabelText(/Password/i);
      await userEvent.type(passwordFields[0], 'Pass1234!');
      await userEvent.type(passwordFields[1], 'Pass1234!');

      await userEvent.click(screen.getByRole('button', { name: /Create Student/i }));

      await waitFor(() => {
        expect(mockedService.createStudent).toHaveBeenCalledWith(
          expect.objectContaining({ first_name: 'Alice', last_name: 'Wong', email: 'alice@school.edu' })
        );
      });
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Student created', expect.any(String));
      });
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Add Student/i })).not.toBeInTheDocument();
      });
    });

    it('create failure shows error toast', async () => {
      mockedService.createStudent.mockRejectedValue(new Error('Server Error'));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Student/i }));

      await userEvent.type(await screen.findByLabelText(/First Name \*/i), 'Alice');
      await userEvent.type(screen.getByLabelText(/Last Name \*/i), 'Wong');
      await userEvent.type(screen.getByLabelText(/Email \*/i), 'alice@school.edu');
      const passwordFields = screen.getAllByLabelText(/Password/i);
      await userEvent.type(passwordFields[0], 'Pass1234!');
      await userEvent.type(passwordFields[1], 'Pass1234!');

      await userEvent.click(screen.getByRole('button', { name: /Create Student/i }));

      await waitFor(() => {
        expect(mockToastError).toHaveBeenCalled();
      });
    });
  });

  // ── 8. Edit Student modal ────────────────────────────────────────────────
  describe('edit student modal', () => {
    // NOTE: Both desktop table <td> and mobile card <p> render "Alice Wong".
    // getStudentTableRow() uses getAllByText()[0] which targets the desktop
    // table <td> (first in DOM order) and traverses up to the <tr>.

    it('clicking pencil icon opens edit modal', async () => {
      renderPage();
      await waitFor(() => expect(screen.getAllByText('Alice Wong').length).toBeGreaterThan(0));
      const aliceRow = getStudentTableRow('Alice Wong');
      const editBtn = within(aliceRow).getAllByRole('button')[0]; // first = pencil
      await userEvent.click(editBtn);
      expect(await screen.findByRole('heading', { name: /Edit Student/i })).toBeInTheDocument();
    });

    it('edit modal pre-populates first name', async () => {
      renderPage();
      await waitFor(() => expect(screen.getAllByText('Alice Wong').length).toBeGreaterThan(0));
      const aliceRow = getStudentTableRow('Alice Wong');
      await userEvent.click(within(aliceRow).getAllByRole('button')[0]);
      const firstNameInput = await screen.findByLabelText(/First Name$/i);
      expect((firstNameInput as HTMLInputElement).value).toBe('Alice');
    });

    it('Cancel closes the edit modal', async () => {
      renderPage();
      await waitFor(() => expect(screen.getAllByText('Alice Wong').length).toBeGreaterThan(0));
      const aliceRow = getStudentTableRow('Alice Wong');
      await userEvent.click(within(aliceRow).getAllByRole('button')[0]);
      const cancelBtn = await screen.findByRole('button', { name: /Cancel/i });
      await userEvent.click(cancelBtn);
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Edit Student/i })).not.toBeInTheDocument();
      });
    });

    it('saving edit calls updateStudent and shows success toast', async () => {
      renderPage();
      await waitFor(() => expect(screen.getAllByText('Alice Wong').length).toBeGreaterThan(0));
      const aliceRow = getStudentTableRow('Alice Wong');
      await userEvent.click(within(aliceRow).getAllByRole('button')[0]);
      const saveBtn = await screen.findByRole('button', { name: /^Save$/i });
      await userEvent.click(saveBtn);
      await waitFor(() => {
        expect(mockedService.updateStudent).toHaveBeenCalledWith('s-1', expect.any(Object));
      });
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Student updated', '');
      });
    });
  });

  // ── 9. Delete student ────────────────────────────────────────────────────
  describe('delete student', () => {
    it('clicking remove icon opens confirmation dialog', async () => {
      renderPage();
      await waitFor(() => expect(screen.getAllByText('Alice Wong').length).toBeGreaterThan(0));
      const aliceRow = getStudentTableRow('Alice Wong');
      // Alice has is_active=true so she has 2 buttons: pencil + XCircle
      const buttons = within(aliceRow).getAllByRole('button');
      const removeBtn = buttons[buttons.length - 1];
      await userEvent.click(removeBtn);
      expect(await screen.findByText(/Remove Student/i)).toBeInTheDocument();
    });

    it('confirming delete calls deleteStudent', async () => {
      renderPage();
      await waitFor(() => expect(screen.getAllByText('Alice Wong').length).toBeGreaterThan(0));
      const aliceRow = getStudentTableRow('Alice Wong');
      const buttons = within(aliceRow).getAllByRole('button');
      await userEvent.click(buttons[buttons.length - 1]);
      // Wait for the confirmation dialog to appear, then scope the button search
      // to within the dialog to avoid matching the row's remove icon button.
      const dialog = await screen.findByRole('dialog');
      const confirmBtn = within(dialog).getByRole('button', { name: /^Remove$/i });
      await userEvent.click(confirmBtn);
      await waitFor(() => {
        expect(mockedService.deleteStudent).toHaveBeenCalledWith('s-1');
      });
    });

    it('cancel on delete dialog closes without deleting', async () => {
      renderPage();
      await waitFor(() => expect(screen.getAllByText('Alice Wong').length).toBeGreaterThan(0));
      const aliceRow = getStudentTableRow('Alice Wong');
      const buttons = within(aliceRow).getAllByRole('button');
      await userEvent.click(buttons[buttons.length - 1]);
      await screen.findByText(/Remove Student/i);
      const cancelBtn = screen.getByRole('button', { name: /^Cancel$/i });
      await userEvent.click(cancelBtn);
      await waitFor(() => {
        expect(mockedService.deleteStudent).not.toHaveBeenCalled();
      });
    });
  });

  // ── 10. Bulk selection ──────────────────────────────────────────────────
  describe('bulk selection', () => {
    it('renders Select All checkbox', async () => {
      renderPage();
      expect(
        await screen.findByRole('checkbox', { name: /Select all students/i })
      ).toBeInTheDocument();
    });

    it('renders per-row selection checkbox for Alice', async () => {
      renderPage();
      expect(
        await screen.findByRole('checkbox', { name: /Select Alice Wong/i })
      ).toBeInTheDocument();
    });

    it('selecting a student checkbox shows BulkActionsBar "selected" text', async () => {
      renderPage();
      const aliceCheckbox = await screen.findByRole('checkbox', { name: /Select Alice Wong/i });
      await userEvent.click(aliceCheckbox);
      await waitFor(() => {
        expect(screen.getByText(/^selected$/i)).toBeInTheDocument();
      });
    });

    it('Select All selects all students and shows count in bar', async () => {
      renderPage();
      const selectAll = await screen.findByRole('checkbox', { name: /Select all students/i });
      await userEvent.click(selectAll);
      // BulkActionsBar renders count in <span>{selectedCount}</span> + "selected" text
      await waitFor(() => {
        // count badge shows "2" and "selected" label appears
        expect(screen.getByText('selected')).toBeInTheDocument();
        // Count appears in the emerald badge
        const countBadges = screen.getAllByText('2');
        expect(countBadges.length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  // ── 11. Bulk actions ─────────────────────────────────────────────────────
  describe('bulk actions', () => {
    // NOTE: BulkActionsBar has Activate (success), Deactivate, Delete.
    // /Activate/i matches "Deactivate" too — use exact name /^Activate$/i.

    it('Activate bulk action calls bulkAction with activate', async () => {
      renderPage();
      const aliceCheckbox = await screen.findByRole('checkbox', { name: /Select Alice Wong/i });
      await userEvent.click(aliceCheckbox);
      // Exact match prevents matching "Deactivate"
      const activateBtn = await screen.findByRole('button', { name: /^Activate$/i });
      await userEvent.click(activateBtn);
      await waitFor(() => {
        expect(mockedService.bulkAction).toHaveBeenCalledWith('activate', ['s-1']);
      });
    });

    it('bulk action success shows toast', async () => {
      renderPage();
      const aliceCheckbox = await screen.findByRole('checkbox', { name: /Select Alice Wong/i });
      await userEvent.click(aliceCheckbox);
      const activateBtn = await screen.findByRole('button', { name: /^Activate$/i });
      await userEvent.click(activateBtn);
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Bulk action complete', 'Done');
      });
    });

    it('Deactivate bulk action calls bulkAction with deactivate', async () => {
      renderPage();
      const aliceCheckbox = await screen.findByRole('checkbox', { name: /Select Alice Wong/i });
      await userEvent.click(aliceCheckbox);
      const deactivateBtn = await screen.findByRole('button', { name: /^Deactivate$/i });
      await userEvent.click(deactivateBtn);
      await waitFor(() => {
        expect(mockedService.bulkAction).toHaveBeenCalledWith('deactivate', ['s-1']);
      });
    });
  });

  // ── 12. Invitations tab ──────────────────────────────────────────────────
  describe('invitations tab', () => {
    async function switchToInvitations() {
      const invTab = await screen.findByRole('button', { name: /^Invitations$/i });
      await userEvent.click(invTab);
    }

    it('shows invitation table with emails', async () => {
      renderPage();
      await switchToInvitations();
      expect(await screen.findByText('charlie@home.com')).toBeInTheDocument();
      expect(await screen.findByText('dana@home.com')).toBeInTheDocument();
    });

    it('shows invitation status badges', async () => {
      renderPage();
      await switchToInvitations();
      expect(await screen.findByText('Pending')).toBeInTheDocument();
      expect(await screen.findByText('Accepted')).toBeInTheDocument();
    });

    it('shows invited_by name for Charlie', async () => {
      renderPage();
      await switchToInvitations();
      expect(await screen.findByText('Admin User')).toBeInTheDocument();
    });

    it('shows empty message when no invitations', async () => {
      mockedService.listInvitations.mockResolvedValue([]);
      renderPage();
      await switchToInvitations();
      expect(await screen.findByText(/No invitations sent yet/i)).toBeInTheDocument();
    });

    it('clicking Invite Student opens invite modal', async () => {
      renderPage();
      await switchToInvitations();
      const inviteBtn = await screen.findByRole('button', { name: /Invite Student/i });
      await userEvent.click(inviteBtn);
      expect(await screen.findByRole('heading', { name: /Invite Student/i })).toBeInTheDocument();
    });

    it('Cancel closes the invite modal', async () => {
      renderPage();
      await switchToInvitations();
      await userEvent.click(await screen.findByRole('button', { name: /Invite Student/i }));
      const cancelBtn = await screen.findByRole('button', { name: /Cancel/i });
      await userEvent.click(cancelBtn);
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Invite Student/i })).not.toBeInTheDocument();
      });
    });

    it('successful invite shows success toast and closes modal', async () => {
      renderPage();
      await switchToInvitations();
      await userEvent.click(await screen.findByRole('button', { name: /Invite Student/i }));

      await userEvent.type(await screen.findByLabelText(/Email \*/i), 'newstudent@home.com');
      await userEvent.type(screen.getByLabelText(/First Name \*/i), 'New');

      await userEvent.click(screen.getByRole('button', { name: /Send Invitation/i }));

      await waitFor(() => {
        expect(mockedService.createInvitation).toHaveBeenCalledWith(
          expect.objectContaining({ email: 'newstudent@home.com', first_name: 'New' })
        );
      });
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Invitation Sent', expect.any(String));
      });
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Invite Student/i })).not.toBeInTheDocument();
      });
    });

    it('invite with missing email shows validation error', async () => {
      renderPage();
      await switchToInvitations();
      await userEvent.click(await screen.findByRole('button', { name: /Invite Student/i }));
      await userEvent.click(screen.getByRole('button', { name: /Send Invitation/i }));
      await waitFor(() => {
        expect(screen.queryAllByText(/required/i).length).toBeGreaterThan(0);
      });
    });
  });

  // ── 13. Usage quota ──────────────────────────────────────────────────────
  describe('usage quota', () => {
    it('shows usage count when tenant provides student quota', async () => {
      mockedUseTenantStore.mockReturnValue({
        usage: { students: { used: 12, limit: 100 } },
      });
      renderPage();
      expect(await screen.findByText(/12\/100 used/i)).toBeInTheDocument();
    });
  });
});
