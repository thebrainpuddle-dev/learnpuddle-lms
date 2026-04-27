// src/pages/admin/GroupsPage.test.tsx
//
// Test suite for GroupsPage — admin teacher-group management.
//
// Coverage strategy:
//   1. Loading state
//   2. Page header (h1 + Create Group button)
//   3. Groups list (render, empty state, search filter, group type label)
//   4. Members panel placeholder (no group selected)
//   5. Group selection (click → heading shown; members listed; empty members)
//   6. Create group modal (open, fields, cancel, validation, success, error)
//   7. Delete group (ConfirmDialog flow)
//   8. Add members (teacher list, checkbox, submit, toast)
//   9. Remove member (button → service call + toast)
//
// Mock notes:
//   • adminGroupsService: all methods vi.fn()
//   • adminTeachersService.listTeachers: vi.fn()
//   • useToast: captured for assertions
//   • usePageTitle: no-op

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { GroupsPage } from './GroupsPage';
import { adminGroupsService } from '../../services/adminGroupsService';
import { adminTeachersService } from '../../services/adminTeachersService';

// ── service mocks ─────────────────────────────────────────────────────────────
vi.mock('../../services/adminGroupsService', () => ({
  adminGroupsService: {
    listGroups: vi.fn(),
    createGroup: vi.fn(),
    deleteGroup: vi.fn(),
    listMembers: vi.fn(),
    addMembers: vi.fn(),
    removeMember: vi.fn(),
  },
}));

vi.mock('../../services/adminTeachersService', () => ({
  adminTeachersService: {
    listTeachers: vi.fn(),
  },
}));

// ── utility mocks ─────────────────────────────────────────────────────────────
vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('../../components/common', async () => {
  const actual = await vi.importActual('../../components/common');
  return {
    ...actual,
    useToast: () => ({ success: mockToastSuccess, error: mockToastError }),
  };
});

// ── typed service refs ────────────────────────────────────────────────────────
const mockedGroups = adminGroupsService as {
  listGroups: ReturnType<typeof vi.fn>;
  createGroup: ReturnType<typeof vi.fn>;
  deleteGroup: ReturnType<typeof vi.fn>;
  listMembers: ReturnType<typeof vi.fn>;
  addMembers: ReturnType<typeof vi.fn>;
  removeMember: ReturnType<typeof vi.fn>;
};

const mockedTeachers = adminTeachersService as {
  listTeachers: ReturnType<typeof vi.fn>;
};

// ── fixture data ──────────────────────────────────────────────────────────────
const GROUP_A = {
  id: 'g-1',
  name: 'Math Teachers',
  description: 'Mathematics department',
  group_type: 'SUBJECT',
  created_at: '2025-09-01T00:00:00Z',
  updated_at: '2025-09-01T00:00:00Z',
};

const GROUP_B = {
  id: 'g-2',
  name: 'Grade 9',
  description: '',
  group_type: 'GRADE',
  created_at: '2025-09-01T00:00:00Z',
  updated_at: '2025-09-01T00:00:00Z',
};

// Member already in GROUP_A
const MEMBER_ALICE = {
  id: 't-1',
  email: 'alice@school.edu',
  first_name: 'Alice',
  last_name: 'Wong',
  role: 'TEACHER',
  is_active: true,
};

// Teachers available to be added (not yet members)
const TEACHER_BOB = {
  id: 't-2',
  email: 'bob@school.edu',
  first_name: 'Bob',
  last_name: 'Chen',
  role: 'TEACHER',
  is_active: true,
};

const TEACHER_CAROL = {
  id: 't-3',
  email: 'carol@school.edu',
  first_name: 'Carol',
  last_name: 'Lee',
  role: 'TEACHER',
  is_active: true,
};

// ── helpers ───────────────────────────────────────────────────────────────────
function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>
        <GroupsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/** Click a group item in the groups list panel and wait for the heading to appear. */
async function selectGroup(name: string) {
  const btn = await screen.findByRole('button', { name: new RegExp(name, 'i') });
  await userEvent.click(btn);
  await screen.findByRole('heading', { name: new RegExp(name, 'i') });
}

// ─────────────────────────────────────────────────────────────────────────────
describe('GroupsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedGroups.listGroups.mockResolvedValue([GROUP_A, GROUP_B]);
    mockedGroups.listMembers.mockResolvedValue([MEMBER_ALICE]);
    mockedGroups.createGroup.mockResolvedValue({ ...GROUP_A, id: 'g-new' });
    mockedGroups.deleteGroup.mockResolvedValue(undefined);
    mockedGroups.addMembers.mockResolvedValue([TEACHER_BOB]);
    mockedGroups.removeMember.mockResolvedValue(undefined);
    mockedTeachers.listTeachers.mockResolvedValue([TEACHER_BOB, TEACHER_CAROL]);
  });

  // ── 1. Loading state ───────────────────────────────────────────────────────
  describe('loading state', () => {
    it('shows Loading text while groups query is pending', () => {
      mockedGroups.listGroups.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });
  });

  // ── 2. Page header ─────────────────────────────────────────────────────────
  describe('page header', () => {
    it('renders the Groups heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { name: /^Groups$/i })).toBeInTheDocument();
    });

    it('shows Create Group button', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /Create Group/i })).toBeInTheDocument();
    });
  });

  // ── 3. Groups list ─────────────────────────────────────────────────────────
  describe('groups list', () => {
    it('renders group names from the API', async () => {
      renderPage();
      expect(await screen.findByText('Math Teachers')).toBeInTheDocument();
      expect(await screen.findByText('Grade 9')).toBeInTheDocument();
    });

    it('shows group_type label under the group name', async () => {
      renderPage();
      expect(await screen.findByText('SUBJECT')).toBeInTheDocument();
      expect(await screen.findByText('GRADE')).toBeInTheDocument();
    });

    it('shows "No groups yet." when groups list is empty', async () => {
      mockedGroups.listGroups.mockResolvedValue([]);
      renderPage();
      expect(await screen.findByText(/No groups yet\./i)).toBeInTheDocument();
    });

    it('search input filters groups by name', async () => {
      renderPage();
      await screen.findByText('Math Teachers');
      const searchInput = screen.getByPlaceholderText(/Search groups/i);
      await userEvent.type(searchInput, 'grade');
      await waitFor(() => {
        expect(screen.queryByText('Math Teachers')).not.toBeInTheDocument();
        expect(screen.getByText('Grade 9')).toBeInTheDocument();
      });
    });
  });

  // ── 4. Members panel — no selection ───────────────────────────────────────
  describe('members panel placeholder', () => {
    it('shows "Select a group" prompt when no group is selected', async () => {
      renderPage();
      await screen.findByText('Math Teachers');
      expect(screen.getByText(/Select a group to manage members/i)).toBeInTheDocument();
    });
  });

  // ── 5. Group selection ─────────────────────────────────────────────────────
  describe('group selection', () => {
    it('selecting a group shows its name as the section heading', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      expect(screen.getByRole('heading', { name: /Math Teachers/i })).toBeInTheDocument();
    });

    it('shows the group description when selected', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      expect(await screen.findByText('Mathematics department')).toBeInTheDocument();
    });

    it('shows "No description" when group description is empty', async () => {
      renderPage();
      await selectGroup('Grade 9');
      expect(await screen.findByText(/No description/i)).toBeInTheDocument();
    });

    it('shows existing member names after selecting a group', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      expect(await screen.findByText('Alice Wong')).toBeInTheDocument();
    });

    it('shows "No members in this group yet." when group has no members', async () => {
      mockedGroups.listMembers.mockResolvedValue([]);
      renderPage();
      await selectGroup('Math Teachers');
      expect(await screen.findByText(/No members in this group yet/i)).toBeInTheDocument();
    });

    it('shows Members count in the members panel header', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      expect(await screen.findByText(/Members \(1\)/i)).toBeInTheDocument();
    });
  });

  // ── 6. Create group modal ──────────────────────────────────────────────────
  describe('create group modal', () => {
    it('clicking Create Group opens the modal', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Create Group/i }));
      expect(await screen.findByRole('heading', { name: /Create Group/i })).toBeInTheDocument();
    });

    it('modal contains Group name and Description fields', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Create Group/i }));
      expect(await screen.findByLabelText(/Group name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Description/i)).toBeInTheDocument();
    });

    it('modal contains a Type select with CUSTOM as default', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Create Group/i }));
      await screen.findByLabelText(/Group name/i);
      const typeSelect = screen.getByRole('combobox') as HTMLSelectElement;
      expect(typeSelect.value).toBe('CUSTOM');
    });

    it('Cancel button closes the modal', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Create Group/i }));
      await userEvent.click(await screen.findByRole('button', { name: /Cancel/i }));
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Create Group/i })).not.toBeInTheDocument();
      });
    });

    it('submitting without a name shows Zod validation error', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Create Group/i }));
      await userEvent.click(await screen.findByRole('button', { name: /^Create$/i }));
      await waitFor(() => {
        expect(screen.queryAllByText(/required/i).length).toBeGreaterThan(0);
      });
    });

    it('successful create calls createGroup, shows toast, and closes modal', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Create Group/i }));
      await userEvent.type(await screen.findByLabelText(/Group name/i), 'Science Team');
      await userEvent.click(screen.getByRole('button', { name: /^Create$/i }));
      await waitFor(() => {
        expect(mockedGroups.createGroup).toHaveBeenCalledWith(
          expect.objectContaining({ name: 'Science Team' })
        );
      });
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Group created', expect.any(String));
      });
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Create Group/i })).not.toBeInTheDocument();
      });
    });

    it('create failure shows error toast', async () => {
      mockedGroups.createGroup.mockRejectedValue(new Error('Server error'));
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Create Group/i }));
      await userEvent.type(await screen.findByLabelText(/Group name/i), 'Science Team');
      await userEvent.click(screen.getByRole('button', { name: /^Create$/i }));
      await waitFor(() => {
        expect(mockToastError).toHaveBeenCalledWith('Failed to create group', expect.any(String));
      });
    });
  });

  // ── 7. Delete group ────────────────────────────────────────────────────────
  describe('delete group', () => {
    it('Delete button opens ConfirmDialog with "Delete Group" title', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      await userEvent.click(await screen.findByRole('button', { name: /Delete/i }));
      expect(await screen.findByText(/Delete Group/i)).toBeInTheDocument();
    });

    it('confirming delete calls deleteGroup and shows success toast', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      await userEvent.click(await screen.findByRole('button', { name: /Delete/i }));
      // Scope to the dialog to avoid matching the group panel "Delete" button
      const dialog = await screen.findByRole('dialog');
      await userEvent.click(within(dialog).getByRole('button', { name: /^Delete$/i }));
      await waitFor(() => {
        expect(mockedGroups.deleteGroup).toHaveBeenCalledWith('g-1');
      });
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Group deleted', expect.any(String));
      });
    });
  });

  // ── 8. Add members ─────────────────────────────────────────────────────────
  describe('add members', () => {
    it('shows available teachers in the add panel', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      // Bob and Carol are not members — they should appear in available teachers
      expect(await screen.findByText('Bob Chen')).toBeInTheDocument();
      expect(await screen.findByText('Carol Lee')).toBeInTheDocument();
    });

    it('checking a teacher enables and increments the Add selected button', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      const bobCheckbox = await screen.findByRole('checkbox', { name: /Bob Chen/i });
      await userEvent.click(bobCheckbox);
      expect(await screen.findByRole('button', { name: /Add selected \(1\)/i })).not.toBeDisabled();
    });

    it('clicking Add selected calls addMembers and shows success toast', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      const bobCheckbox = await screen.findByRole('checkbox', { name: /Bob Chen/i });
      await userEvent.click(bobCheckbox);
      await userEvent.click(await screen.findByRole('button', { name: /Add selected \(1\)/i }));
      await waitFor(() => {
        expect(mockedGroups.addMembers).toHaveBeenCalledWith('g-1', ['t-2']);
      });
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Members added', expect.any(String));
      });
    });

    it('Add selected (0) button is disabled when no teachers selected', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      const addBtn = await screen.findByRole('button', { name: /Add selected \(0\)/i });
      expect(addBtn).toBeDisabled();
    });
  });

  // ── 9. Remove member ───────────────────────────────────────────────────────
  describe('remove member', () => {
    it('clicking Remove on a member calls removeMember', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      await screen.findByText('Alice Wong');
      // Scope to the members section to avoid matching the "Remove" from a modal
      const removeBtn = await screen.findByRole('button', { name: /^Remove$/i });
      await userEvent.click(removeBtn);
      await waitFor(() => {
        expect(mockedGroups.removeMember).toHaveBeenCalledWith('g-1', 't-1');
      });
    });

    it('removing a member shows success toast', async () => {
      renderPage();
      await selectGroup('Math Teachers');
      await screen.findByText('Alice Wong');
      await userEvent.click(await screen.findByRole('button', { name: /^Remove$/i }));
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Member removed', expect.any(String));
      });
    });
  });
});
