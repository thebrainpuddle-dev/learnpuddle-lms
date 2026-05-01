// src/pages/superadmin/SchoolsPage.test.tsx
//
// FE-074: Tests for the SuperAdmin Schools management page.
//
// Covers:
//   - Page heading, subtitle, Onboard School button
//   - Loading skeleton, empty state
//   - School list rendering (name, subdomain, teacher/course counts, status badge)
//   - Row click → navigate to school detail
//   - Activate / Deactivate toggle mutation
//   - Onboard modal: open/close, form fields, Zod validation errors, success flow
//   - Pagination controls (shown when count > 20)
//   - Checkbox selection + "Email Selected" button appearance
//   - Bulk email modal: open/close, form validation, success flow
//
// Note: the component renders both mobile-card (md:hidden) and desktop-table
// (hidden md:block) sections — JSDOM renders both since CSS media queries do not
// apply.  Where school names appear twice, tests use getAllByText / within scoping.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { SchoolsPage } from './SchoolsPage';
import { ToastProvider } from '../../components/common';
import { superAdminService } from '../../services/superAdminService';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

vi.mock('../../services/superAdminService', () => ({
  superAdminService: {
    listTenants:    vi.fn(),
    onboardSchool:  vi.fn(),
    updateTenant:   vi.fn(),
    bulkSendEmail:  vi.fn(),
    getStats:       vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed helpers ─────────────────────────────────────────────────────────────

const mockedService = superAdminService as {
  listTenants:   ReturnType<typeof vi.fn>;
  onboardSchool: ReturnType<typeof vi.fn>;
  updateTenant:  ReturnType<typeof vi.fn>;
  bulkSendEmail: ReturnType<typeof vi.fn>;
};

// ── Fixtures ──────────────────────────────────────────────────────────────────

const SCHOOL_RIVERSIDE = {
  id: 'school-1',
  name: 'Riverside Academy',
  slug: 'riverside-academy',
  subdomain: 'riverside',
  email: 'admin@riverside.edu',
  is_active: true,
  is_trial: false,
  trial_end_date: null,
  plan: 'STARTER',
  plan_started_at: null,
  plan_expires_at: null,
  max_teachers: 50,
  max_courses: 20,
  max_storage_mb: 500,
  primary_color: '#4f46e5',
  logo: null,
  teacher_count: 15,
  admin_count: 2,
  course_count: 8,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const SCHOOL_LAKEWOOD = {
  id: 'school-2',
  name: 'Lakewood High',
  slug: 'lakewood-high',
  subdomain: 'lakewood',
  email: 'admin@lakewood.edu',
  is_active: false,
  is_trial: true,
  trial_end_date: '2026-07-01T00:00:00Z',
  plan: 'FREE',
  plan_started_at: null,
  plan_expires_at: null,
  max_teachers: 10,
  max_courses: 5,
  max_storage_mb: 100,
  primary_color: '#0ea5e9',
  logo: null,
  teacher_count: 5,
  admin_count: 1,
  course_count: 3,
  created_at: '2026-02-01T00:00:00Z',
  updated_at: '2026-02-01T00:00:00Z',
};

const MOCK_LIST_RESPONSE = {
  count: 2,
  results: [SCHOOL_RIVERSIDE, SCHOOL_LAKEWOOD],
};

// ── QueryClient factory ───────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

// ── renderPage ────────────────────────────────────────────────────────────────

const renderPage = (initialPath = '/super-admin/schools') =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={[initialPath]}>
        <ToastProvider>
          <SchoolsPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SchoolsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedService.listTenants.mockResolvedValue(MOCK_LIST_RESPONSE);
    mockedService.onboardSchool.mockResolvedValue({
      tenant: SCHOOL_RIVERSIDE,
      admin_email: 'admin@new-school.com',
      subdomain: 'newschool',
    });
    mockedService.updateTenant.mockResolvedValue({ ...SCHOOL_RIVERSIDE, is_active: false });
    mockedService.bulkSendEmail.mockResolvedValue({ queued: 2, skipped: [] });
  });

  // ── Page-level rendering ─────────────────────────────────────────────────

  describe('page-level rendering', () => {
    it('renders Schools heading and subtitle', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { name: /Schools/i })).toBeInTheDocument();
      expect(screen.getByText(/Manage all schools on the platform/i)).toBeInTheDocument();
    });

    it('renders the Onboard School button', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /\+ Onboard School/i })).toBeInTheDocument();
    });

    it('renders search input', async () => {
      renderPage();
      expect(await screen.findByPlaceholderText(/Search schools/i)).toBeInTheDocument();
    });
  });

  // ── Loading state ────────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows loading skeleton while data is fetching', () => {
      mockedService.listTenants.mockReturnValue(new Promise(() => {}));
      renderPage();
      const pulseEls = document.querySelectorAll('.animate-pulse');
      expect(pulseEls.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── Empty state ──────────────────────────────────────────────────────────

  describe('empty state', () => {
    it('shows No schools found when results are empty', async () => {
      mockedService.listTenants.mockResolvedValue({ count: 0, results: [] });
      renderPage();
      expect(await screen.findAllByText(/No schools found/i)).not.toHaveLength(0);
    });
  });

  // ── School list ──────────────────────────────────────────────────────────

  describe('school list rendering', () => {
    it('renders school names', async () => {
      renderPage();
      // Both mobile and desktop sections render school name — use getAllByText
      expect(await screen.findAllByText('Riverside Academy')).not.toHaveLength(0);
      expect(await screen.findAllByText('Lakewood High')).not.toHaveLength(0);
    });

    it('shows Active badge for active school', async () => {
      renderPage();
      await screen.findAllByText('Riverside Academy');
      // "Active" badge for Riverside (is_active: true)
      const activeBadges = screen.getAllByText('Active');
      expect(activeBadges.length).toBeGreaterThanOrEqual(1);
    });

    it('shows Inactive badge for inactive school', async () => {
      renderPage();
      await screen.findAllByText('Lakewood High');
      const inactiveBadges = screen.getAllByText('Inactive');
      expect(inactiveBadges.length).toBeGreaterThanOrEqual(1);
    });

    it('shows Trial badge for trial school', async () => {
      renderPage();
      await screen.findAllByText('Lakewood High');
      // In desktop table Lakewood shows "Trial" in Plan column
      const trialBadges = screen.getAllByText('Trial');
      expect(trialBadges.length).toBeGreaterThanOrEqual(1);
    });

    it('shows teacher and course counts', async () => {
      renderPage();
      await screen.findAllByText('Riverside Academy');
      // Desktop table shows teacher_count (15) and course_count (8) as plain numbers
      const fifteens = screen.getAllByText('15');
      expect(fifteens.length).toBeGreaterThanOrEqual(1);
      const eights = screen.getAllByText('8');
      expect(eights.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── Navigation ───────────────────────────────────────────────────────────

  describe('navigation', () => {
    it('navigates to school detail when desktop row is clicked', async () => {
      renderPage();
      await screen.findAllByText('Riverside Academy');
      // Click the table row (desktop view) — the tr element in the hidden md:block section
      // Use getByRole for the first occurrence of the school name in the table
      const tableSection = document.querySelector('.hidden.md\\:block');
      expect(tableSection).not.toBeNull();
      const firstNameCell = within(tableSection as HTMLElement).getByText('Riverside Academy');
      const row = firstNameCell.closest('tr');
      expect(row).not.toBeNull();
      await userEvent.click(row as HTMLElement);
      expect(mockedUseNavigate).toHaveBeenCalledWith('/super-admin/schools/school-1');
    });
  });

  // ── Toggle active / deactivate ───────────────────────────────────────────

  describe('activate / deactivate', () => {
    it('calls updateTenant with is_active:false when Deactivate clicked for active school', async () => {
      renderPage();
      await screen.findAllByText('Riverside Academy');
      // In desktop table, find the Deactivate button for Riverside (active school)
      const tableSection = document.querySelector('.hidden.md\\:block') as HTMLElement;
      const deactivateBtns = within(tableSection).getAllByRole('button', { name: /Deactivate/i });
      await userEvent.click(deactivateBtns[0]);
      await waitFor(() => {
        expect(mockedService.updateTenant).toHaveBeenCalledWith('school-1', { is_active: false });
      });
    });

    it('calls updateTenant with is_active:true when Activate clicked for inactive school', async () => {
      renderPage();
      await screen.findAllByText('Lakewood High');
      const tableSection = document.querySelector('.hidden.md\\:block') as HTMLElement;
      // Use /^Activate$/i (anchored) so the regex does NOT match "Deactivate"
      // buttons — "Deactivate" contains "activate" and would be caught by /Activate/i.
      const activateBtns = within(tableSection).getAllByRole('button', { name: /^Activate$/i });
      await userEvent.click(activateBtns[0]);
      await waitFor(() => {
        expect(mockedService.updateTenant).toHaveBeenCalledWith('school-2', { is_active: true });
      });
    });
  });

  // ── Onboard modal ────────────────────────────────────────────────────────

  describe('Onboard modal', () => {
    it('opens modal when Onboard School button is clicked', async () => {
      renderPage();
      const btn = await screen.findByRole('button', { name: /\+ Onboard School/i });
      await userEvent.click(btn);
      expect(screen.getByRole('heading', { name: /Onboard New School/i })).toBeInTheDocument();
    });

    it('renders all form fields in modal', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /\+ Onboard School/i }));
      expect(screen.getByLabelText(/School Name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Admin First Name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Admin Last Name/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Admin Email/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Initial Password/i)).toBeInTheDocument();
    });

    it('closes modal when Cancel is clicked', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /\+ Onboard School/i }));
      expect(screen.getByRole('heading', { name: /Onboard New School/i })).toBeInTheDocument();
      await userEvent.click(screen.getByRole('button', { name: /Cancel/i }));
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Onboard New School/i })).not.toBeInTheDocument();
      });
    });

    it('shows Zod validation errors when form is submitted empty', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /\+ Onboard School/i }));
      // Click the submit button inside modal (not the cancel button)
      const submitBtn = screen.getByRole('button', { name: /^Onboard School$/i });
      await userEvent.click(submitBtn);
      await waitFor(() => {
        expect(screen.getByText(/School name is required/i)).toBeInTheDocument();
      });
    });

    it('calls onboardSchool with form data on successful submission', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /\+ Onboard School/i }));

      await userEvent.type(screen.getByLabelText(/School Name/i), 'New School');
      await userEvent.type(screen.getByLabelText(/Admin First Name/i), 'John');
      await userEvent.type(screen.getByLabelText(/Admin Last Name/i), 'Doe');
      await userEvent.type(screen.getByLabelText(/Admin Email/i), 'john@new-school.com');
      await userEvent.type(screen.getByLabelText(/Initial Password/i), 'password123');

      const submitBtn = screen.getByRole('button', { name: /^Onboard School$/i });
      await userEvent.click(submitBtn);

      await waitFor(() => {
        // TanStack Query v5 passes a second argument (mutation context) to a
        // directly-referenced mutationFn, so account for it with expect.anything().
        expect(mockedService.onboardSchool).toHaveBeenCalledWith(
          expect.objectContaining({
            school_name: 'New School',
            admin_first_name: 'John',
            admin_last_name: 'Doe',
            admin_email: 'john@new-school.com',
            admin_password: 'password123',
          }),
          expect.anything(),
        );
      });
    });

    it('closes modal after successful onboard', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /\+ Onboard School/i }));

      await userEvent.type(screen.getByLabelText(/School Name/i), 'New School');
      await userEvent.type(screen.getByLabelText(/Admin First Name/i), 'John');
      await userEvent.type(screen.getByLabelText(/Admin Last Name/i), 'Doe');
      await userEvent.type(screen.getByLabelText(/Admin Email/i), 'john@new-school.com');
      await userEvent.type(screen.getByLabelText(/Initial Password/i), 'password123');

      await userEvent.click(screen.getByRole('button', { name: /^Onboard School$/i }));

      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Onboard New School/i })).not.toBeInTheDocument();
      });
    });

    it('opens modal immediately when ?onboard=true in URL', async () => {
      renderPage('/super-admin/schools?onboard=true');
      expect(await screen.findByRole('heading', { name: /Onboard New School/i })).toBeInTheDocument();
    });
  });

  // ── Pagination ────────────────────────────────────────────────────────────

  describe('pagination', () => {
    it('does not show pagination when count <= 20', async () => {
      renderPage();
      await screen.findAllByText('Riverside Academy');
      // count = 2, so no pagination controls expected
      expect(screen.queryByRole('button', { name: /Previous/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /Next/i })).not.toBeInTheDocument();
    });

    it('shows pagination controls when count > 20', async () => {
      mockedService.listTenants.mockResolvedValue({ count: 40, results: [SCHOOL_RIVERSIDE] });
      renderPage();
      expect(await screen.findByRole('button', { name: /Previous/i })).toBeInTheDocument();
      expect(await screen.findByRole('button', { name: /Next/i })).toBeInTheDocument();
    });

    it('Previous button is disabled on page 1', async () => {
      mockedService.listTenants.mockResolvedValue({ count: 40, results: [SCHOOL_RIVERSIDE] });
      renderPage();
      const prevBtn = await screen.findByRole('button', { name: /Previous/i });
      expect(prevBtn).toBeDisabled();
    });

    it('clicking Next increments the page', async () => {
      mockedService.listTenants
        .mockResolvedValueOnce({ count: 40, results: [SCHOOL_RIVERSIDE] })
        .mockResolvedValue({ count: 40, results: [SCHOOL_LAKEWOOD] });
      renderPage();
      const nextBtn = await screen.findByRole('button', { name: /Next/i });
      await userEvent.click(nextBtn);
      await waitFor(() => {
        expect(mockedService.listTenants).toHaveBeenCalledWith(
          expect.objectContaining({ page: 2 }),
        );
      });
    });

    it('shows total count in pagination footer', async () => {
      mockedService.listTenants.mockResolvedValue({ count: 40, results: [SCHOOL_RIVERSIDE] });
      renderPage();
      expect(await screen.findByText(/40 schools total/i)).toBeInTheDocument();
    });
  });

  // ── Checkbox selection ────────────────────────────────────────────────────

  describe('checkbox selection and bulk actions', () => {
    it('shows Email Selected button after selecting a school', async () => {
      renderPage();
      await screen.findAllByText('Riverside Academy');
      // Select Riverside in the desktop table
      const tableSection = document.querySelector('.hidden.md\\:block') as HTMLElement;
      const checkbox = within(tableSection).getByRole('checkbox', { name: /Select Riverside Academy/i });
      await userEvent.click(checkbox);
      expect(await screen.findByRole('button', { name: /Email Selected/i })).toBeInTheDocument();
    });

    it('Email Selected button shows count of selected schools', async () => {
      renderPage();
      await screen.findAllByText('Riverside Academy');
      const tableSection = document.querySelector('.hidden.md\\:block') as HTMLElement;
      const checkbox = within(tableSection).getByRole('checkbox', { name: /Select Riverside Academy/i });
      await userEvent.click(checkbox);
      expect(await screen.findByRole('button', { name: /Email Selected \(1\)/i })).toBeInTheDocument();
    });

    it('Select All checkbox selects all schools', async () => {
      renderPage();
      await screen.findAllByText('Riverside Academy');
      const tableSection = document.querySelector('.hidden.md\\:block') as HTMLElement;
      const selectAllCb = within(tableSection).getByRole('checkbox', { name: /Select all schools/i });
      await userEvent.click(selectAllCb);
      // Both schools selected → button shows (2)
      expect(await screen.findByRole('button', { name: /Email Selected \(2\)/i })).toBeInTheDocument();
    });
  });

  // ── Bulk Email modal ──────────────────────────────────────────────────────

  describe('bulk email modal', () => {
    async function openBulkEmailModal() {
      renderPage();
      await screen.findAllByText('Riverside Academy');
      const tableSection = document.querySelector('.hidden.md\\:block') as HTMLElement;
      const checkbox = within(tableSection).getByRole('checkbox', { name: /Select Riverside Academy/i });
      await userEvent.click(checkbox);
      const emailBtn = await screen.findByRole('button', { name: /Email Selected/i });
      await userEvent.click(emailBtn);
    }

    it('opens bulk email modal on Email Selected click', async () => {
      await openBulkEmailModal();
      expect(screen.getByRole('heading', { name: /Email 1 School/i })).toBeInTheDocument();
    });

    it('shows subject and body fields in bulk email modal', async () => {
      await openBulkEmailModal();
      expect(screen.getByLabelText(/Subject/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/Dear School Administrator/i)).toBeInTheDocument();
    });

    it('closes bulk email modal on Cancel', async () => {
      await openBulkEmailModal();
      await userEvent.click(screen.getByRole('button', { name: /Cancel/i }));
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Email 1 School/i })).not.toBeInTheDocument();
      });
    });

    it('calls bulkSendEmail with correct payload on submission', async () => {
      await openBulkEmailModal();
      await userEvent.type(screen.getByLabelText(/Subject/i), 'Important Update');
      await userEvent.type(
        screen.getByPlaceholderText(/Dear School Administrator/i),
        'Please review the new guidelines.',
      );
      const sendBtn = screen.getByRole('button', { name: /Send to 1 School/i });
      await userEvent.click(sendBtn);
      await waitFor(() => {
        expect(mockedService.bulkSendEmail).toHaveBeenCalledWith(
          expect.objectContaining({
            tenant_ids: ['school-1'],
            subject: 'Important Update',
            body: 'Please review the new guidelines.',
          }),
        );
      });
    });

    it('closes bulk email modal after successful send', async () => {
      await openBulkEmailModal();
      await userEvent.type(screen.getByLabelText(/Subject/i), 'Test Subject');
      await userEvent.type(
        screen.getByPlaceholderText(/Dear School Administrator/i),
        'Test body content.',
      );
      await userEvent.click(screen.getByRole('button', { name: /Send to 1 School/i }));
      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Email 1 School/i })).not.toBeInTheDocument();
      });
    });
  });
});
