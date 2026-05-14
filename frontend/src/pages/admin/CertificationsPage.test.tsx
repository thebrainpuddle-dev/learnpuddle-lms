// src/pages/admin/CertificationsPage.test.tsx
//
// FE-069: Tests for the Admin Certifications & Compliance page.
// Covers: page heading, 7 top-level tab labels, default Certifications tab
//         (CertificationTypes sub-tab: loading skeleton, empty state, cert name,
//          validity months, auto-renew badge, New Type modal, createType call,
//          delete ConfirmDialog), URL-param-driven tab routing (?tab=approvals,
//          ?tab=ib-dashboard).
//
// Mocking strategy:
//   - certificationsService.types (list, create, update, delete) mocked
//   - certificationsService (list, expiryCheck) mocked for other sub-tabs
//   - adminTeachersService.getTeachers mocked (used by IssuedCertificationsTab)
//   - ApprovalsTab / IBDashboard / SchoolAccreditationsTab / RankingsLinksTab /
//     ComplianceTrackerTab / StaffPDTrackerTab → stubs
//   - useToast + ConfirmDialog via partial mock of ../../components/common
//   - usePageTitle stubbed
//
// Tab routing: CertificationsPage reads `?tab=` from URL via useSearchParams.
// Tests supply tab params via MemoryRouter initialEntries.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { CertificationsPage } from './CertificationsPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  showToast: vi.fn(),
};

vi.mock('../../services/certificationsService', () => ({
  certificationsService: {
    types: {
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
    },
    list: vi.fn(),
    issue: vi.fn(),
    revoke: vi.fn(),
    renew: vi.fn(),
    expiryCheck: vi.fn(),
  },
}));

vi.mock('../../services/adminTeachersService', () => ({
  adminTeachersService: {
    getTeachers: vi.fn(),
    getTeacher: vi.fn(),
  },
}));

// Stub all heavy sub-tab components to avoid their internal API calls
vi.mock('../../components/certifications/ApprovalsTab', () => ({
  ApprovalsTab: () => <div data-testid="approvals-tab-stub">ApprovalsTab</div>,
}));

vi.mock('../../components/certifications/IBDashboard', () => ({
  IBDashboard: () => <div data-testid="ib-dashboard-stub">IBDashboard</div>,
}));

vi.mock('../../components/certifications/SchoolAccreditationsTab', () => ({
  SchoolAccreditationsTab: () => <div data-testid="school-accreditations-stub" />,
}));

vi.mock('../../components/certifications/RankingsLinksTab', () => ({
  RankingsLinksTab: () => <div data-testid="rankings-links-stub" />,
}));

vi.mock('../../components/certifications/ComplianceTrackerTab', () => ({
  ComplianceTrackerTab: () => <div data-testid="compliance-tracker-stub" />,
}));

vi.mock('../../components/certifications/StaffPDTrackerTab', () => ({
  StaffPDTrackerTab: () => <div data-testid="staff-pd-stub" />,
}));

vi.mock('../../components/common', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../components/common')>();
  return {
    ...actual,
    useToast: () => mockToast,
    ConfirmDialog: ({
      isOpen,
      onConfirm,
      onClose,
      title,
    }: {
      isOpen: boolean;
      onConfirm: () => void;
      onClose: () => void;
      title: string;
    }) =>
      isOpen ? (
        <div data-testid="confirm-dialog">
          <p>{title}</p>
          <button onClick={onConfirm}>Confirm</button>
          <button onClick={onClose}>Cancel</button>
        </div>
      ) : null,
  };
});

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { certificationsService } from '../../services/certificationsService';

const mockTypesList = certificationsService.types.list as ReturnType<typeof vi.fn>;
const mockTypesCreate = certificationsService.types.create as ReturnType<typeof vi.fn>;
const mockTypesDelete = certificationsService.types.delete as ReturnType<typeof vi.fn>;
const mockCertsList = certificationsService.list as ReturnType<typeof vi.fn>;
const mockExpiryCheck = certificationsService.expiryCheck as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage(search = '') {
  const path = `/admin/certifications${search}`;
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[path]}>
        <Routes>
          <Route path="/admin/certifications" element={<CertificationsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeCertType(overrides: Record<string, unknown> = {}) {
  return {
    id: 'ct-1',
    name: 'First Aid Certificate',
    description: 'Annual first aid training certification.',
    validity_months: 12,
    auto_renew: true,
    required_course_ids: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('CertificationsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Default: empty data for all sub-tabs
    mockTypesList.mockResolvedValue([]);
    mockCertsList.mockResolvedValue([]);
    mockExpiryCheck.mockResolvedValue({
      expiring_soon: [],
      already_expired: [],
      threshold_days: 90,
    });
  });

  // ── Page header ───────────────────────────────────────────────────────────

  it('renders "Certifications & Compliance" heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /certifications & compliance/i }),
    ).toBeInTheDocument();
  });

  // ── Top-level tabs ────────────────────────────────────────────────────────

  it('renders all 7 top-level tab labels', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('tab', { name: /^certifications$/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /^approvals$/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /^accreditations$/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /rankings & links/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /compliance tracker/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /staff pd/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /ib compliance/i })).toBeInTheDocument();
  });

  // ── Default Certifications tab: sub-tab bar ───────────────────────────────

  it('shows Certification Types sub-tab by default', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(
      screen.getByRole('tab', { name: /certification types/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('tab', { name: /issued certifications/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('tab', { name: /expiry dashboard/i }),
    ).toBeInTheDocument();
  });

  // ── CertificationTypesTab: loading ────────────────────────────────────────

  it('shows loading skeleton while cert types load', async () => {
    mockTypesList.mockReturnValue(new Promise(() => {}));
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    const skeleton = document.querySelector('.animate-pulse');
    expect(skeleton).not.toBeNull();
  });

  // ── CertificationTypesTab: empty state ────────────────────────────────────

  it('shows "No certification types defined yet." when empty', async () => {
    renderPage();
    expect(
      await screen.findByText(/no certification types defined yet/i),
    ).toBeInTheDocument();
  });

  it('shows "Create one to start issuing certifications." subtitle', async () => {
    renderPage();
    expect(
      await screen.findByText(/create one to start issuing certifications/i),
    ).toBeInTheDocument();
  });

  // ── CertificationTypesTab: cert type list ─────────────────────────────────

  it('renders certification type name in table', async () => {
    mockTypesList.mockResolvedValue([makeCertType()]);
    renderPage();
    expect(await screen.findByText('First Aid Certificate')).toBeInTheDocument();
  });

  it('renders validity months in table ("12 months")', async () => {
    mockTypesList.mockResolvedValue([makeCertType({ validity_months: 12 })]);
    renderPage();
    await screen.findByText('First Aid Certificate');
    expect(screen.getByText('12 months')).toBeInTheDocument();
  });

  it('renders auto-renew badge "Yes" for auto_renew=true', async () => {
    mockTypesList.mockResolvedValue([makeCertType({ auto_renew: true })]);
    renderPage();
    await screen.findByText('First Aid Certificate');
    expect(screen.getByText('Yes')).toBeInTheDocument();
  });

  it('renders auto-renew badge "No" for auto_renew=false', async () => {
    mockTypesList.mockResolvedValue([makeCertType({ auto_renew: false })]);
    renderPage();
    await screen.findByText('First Aid Certificate');
    expect(screen.getByText('No')).toBeInTheDocument();
  });

  // ── CertificationTypesTab: New Type modal ─────────────────────────────────

  it('clicking "New Type" opens Create Certification Type modal', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/no certification types defined yet/i);
    await user.click(screen.getByRole('button', { name: /new type/i }));
    expect(
      screen.getByRole('heading', { level: 3, name: /create certification type/i }),
    ).toBeInTheDocument();
  });

  it('form submit calls types.create with entered name', async () => {
    const user = userEvent.setup();
    mockTypesCreate.mockResolvedValue(makeCertType({ name: 'CPR Training' }));
    renderPage();
    await screen.findByText(/no certification types defined yet/i);
    await user.click(screen.getByRole('button', { name: /new type/i }));
    // Type a name in the form (Controller-rendered Input)
    const nameInput = screen.getByLabelText(/name/i);
    await user.clear(nameInput);
    await user.type(nameInput, 'CPR Training');
    // Submit
    await user.click(screen.getByRole('button', { name: /create/i }));
    await waitFor(() => expect(mockTypesCreate).toHaveBeenCalledTimes(1));
    expect(mockTypesCreate.mock.calls[0][0]).toMatchObject({ name: 'CPR Training' });
  });

  // ── CertificationTypesTab: delete ─────────────────────────────────────────

  it('clicking delete icon opens ConfirmDialog', async () => {
    const user = userEvent.setup();
    mockTypesList.mockResolvedValue([makeCertType()]);
    renderPage();
    await screen.findByText('First Aid Certificate');
    await user.click(screen.getByTitle('Delete'));
    expect(await screen.findByTestId('confirm-dialog')).toBeInTheDocument();
  });

  it('confirming delete calls types.delete with cert type id', async () => {
    const user = userEvent.setup();
    mockTypesDelete.mockResolvedValue(undefined);
    mockTypesList.mockResolvedValue([makeCertType({ id: 'ct-1' })]);
    renderPage();
    await screen.findByText('First Aid Certificate');
    await user.click(screen.getByTitle('Delete'));
    await screen.findByTestId('confirm-dialog');
    await user.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() =>
      expect(mockTypesDelete).toHaveBeenCalledWith('ct-1'),
    );
  });

  // ── URL-param tab routing ─────────────────────────────────────────────────

  it('?tab=approvals renders ApprovalsTab stub', async () => {
    renderPage('?tab=approvals');
    expect(await screen.findByTestId('approvals-tab-stub')).toBeInTheDocument();
  });

  it('?tab=ib-dashboard renders IBDashboard stub', async () => {
    renderPage('?tab=ib-dashboard');
    expect(await screen.findByTestId('ib-dashboard-stub')).toBeInTheDocument();
  });

  it('?tab=accreditations renders SchoolAccreditationsTab stub', async () => {
    renderPage('?tab=accreditations');
    expect(
      await screen.findByTestId('school-accreditations-stub'),
    ).toBeInTheDocument();
  });
});
