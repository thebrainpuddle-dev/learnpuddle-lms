// src/pages/teacher/MyCertificationsPage.test.tsx
//
// FE-054: Tests for the Teacher My Certifications page.
// Covers: page header, subtitle, loading skeleton, error state, summary cards,
//         required certifications checklist, missing/action-required section,
//         all certifications list, cert expansion (collapse/expand details),
//         and no-certifications empty state.
//
// Mocking strategy:
//   - api.get is mocked as a vi.fn() (MyCertificationsPage calls api.get directly,
//     not via a service module)
//   - usePageTitle is stubbed to avoid side-effects

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MyCertificationsPage } from './MyCertificationsPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../config/api', () => ({
  default: { get: vi.fn() },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helper ─────────────────────────────────────────────────────────

import api from '../../config/api';
const mockApiGet = api.get as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>
        <MyCertificationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const mockSummary = {
  total: 8,
  completed: 5,
  expiring: 1,
  expired: 1,
  required_total: 4,
  required_met: 3,    // 75% compliance
  missing_count: 1,
};

const mockRequired = [
  {
    certification_type: 'FIRST_AID',
    display_name: 'First Aid',
    status: 'VALID',
    held: true,
  },
  {
    certification_type: 'CPR',
    display_name: 'CPR Certification',
    status: 'NOT_STARTED',
    held: false,
  },
];

const mockMissing = [
  {
    certification_type: 'CPR',
    display_name: 'CPR Certification',
    reason: 'not_started',
  },
];

const mockCertifications = [
  {
    id: 'cert-1',
    certification_type: 'FIRST_AID',
    certification_type_display: 'First Aid Certification',
    custom_name: '',
    status: 'VALID',
    completed_date: '2024-01-15',
    expiry_date: '2026-01-15',
    certificate_url: 'https://example.com/cert.pdf',
    provider: 'Red Cross',
    notes: 'Annual renewal required',
  },
  {
    id: 'cert-2',
    certification_type: 'SAFEGUARDING',
    certification_type_display: 'Safeguarding Training',
    custom_name: '',
    status: 'EXPIRED',
    completed_date: '2023-05-01',
    expiry_date: '2024-05-01',
    certificate_url: '',
    provider: 'SafeGuard Institute',
    notes: '',
  },
];

const mockCertsResponse = {
  summary: mockSummary,
  certifications: mockCertifications,
  required: mockRequired,
  missing: mockMissing,
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('MyCertificationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── Page header ─────────────────────────────────────────────────────────────

  it('renders "My Certifications & PD" heading', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /my certifications.*pd/i }),
    ).toBeInTheDocument();
  });

  it('renders subtitle text', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(
      await screen.findByText(/track your professional development/i),
    ).toBeInTheDocument();
  });

  // ── Loading ─────────────────────────────────────────────────────────────────

  it('shows animate-pulse skeletons while loading', () => {
    mockApiGet.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  // ── Error ───────────────────────────────────────────────────────────────────

  it('shows "Failed to load certifications" when query fails', async () => {
    mockApiGet.mockRejectedValue(new Error('Server error'));
    renderPage();
    expect(
      await screen.findByText('Failed to load certifications'),
    ).toBeInTheDocument();
  });

  it('shows "Please try refreshing the page." on error', async () => {
    mockApiGet.mockRejectedValue(new Error('Server error'));
    renderPage();
    expect(
      await screen.findByText(/please try refreshing the page/i),
    ).toBeInTheDocument();
  });

  // ── Summary cards ───────────────────────────────────────────────────────────

  it('shows Compliance summary card with computed percent', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    // 3 of 4 required met = 75%. Card title uses CSS "uppercase" class — DOM text is "Compliance"
    expect(await screen.findByText('75%')).toBeInTheDocument();
    expect(screen.getByText('Compliance')).toBeInTheDocument();
  });

  it('shows "3 of 4 required" compliance subtitle', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(await screen.findByText('3 of 4 required')).toBeInTheDocument();
  });

  it('shows Valid Certifications summary card', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    // CSS "uppercase" class — DOM text is "Valid Certifications"
    expect(await screen.findByText('Valid Certifications')).toBeInTheDocument();
    // summary.completed = 5
    expect(screen.getByText('5')).toBeInTheDocument();
  });

  it('shows "8 total tracked" subtitle on Valid Certifications card', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(await screen.findByText('8 total tracked')).toBeInTheDocument();
  });

  it('shows Expiring Soon summary card', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    // CSS "uppercase" class — DOM text is "Expiring Soon"
    expect(await screen.findByText('Expiring Soon')).toBeInTheDocument();
    expect(screen.getByText('Within 90 days')).toBeInTheDocument();
  });

  it('shows Action Needed summary card with missing+expired count', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    // CSS "uppercase" class — DOM text is "Action Needed"
    expect(await screen.findByText('Action Needed')).toBeInTheDocument();
    // missing_count (1) + expired (1) = 2
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('Missing or expired')).toBeInTheDocument();
  });

  // ── Required certifications ─────────────────────────────────────────────────

  it('renders Required Certifications section heading', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 2, name: /required certifications/i }),
    ).toBeInTheDocument();
  });

  it('renders required cert display names', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(await screen.findByText('First Aid')).toBeInTheDocument();
    // "CPR Certification" appears in both required certs and action-required sections
    expect(screen.getAllByText('CPR Certification').length).toBeGreaterThan(0);
  });

  it('shows "Valid" badge for VALID required cert', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    // The required certs section shows status labels. VALID → "Valid"
    const validBadges = await screen.findAllByText('Valid');
    expect(validBadges.length).toBeGreaterThan(0);
  });

  it('shows "Not Started" badge for NOT_STARTED required cert', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(await screen.findByText('Not Started')).toBeInTheDocument();
  });

  // ── Missing / Action Required ───────────────────────────────────────────────

  it('shows "Action Required" section when missing certs exist', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(await screen.findByText('Action Required')).toBeInTheDocument();
  });

  it('shows missing cert name in action section', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    await screen.findByText('Action Required');
    expect(screen.getAllByText('CPR Certification').length).toBeGreaterThan(0);
  });

  it('shows "Not yet completed" reason for not_started missing cert', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(
      await screen.findByText(/— Not yet completed/),
    ).toBeInTheDocument();
  });

  it('shows expired renewal reason in action section', async () => {
    const expiredMissing = [
      { certification_type: 'FIRST_AID', display_name: 'First Aid', reason: 'expired' },
    ];
    mockApiGet.mockResolvedValue({
      data: { ...mockCertsResponse, missing: expiredMissing },
    });
    renderPage();
    expect(
      await screen.findByText(/— Certificate has expired, renewal required/),
    ).toBeInTheDocument();
  });

  it('does not show "Action Required" section when missing list is empty', async () => {
    mockApiGet.mockResolvedValue({
      data: { ...mockCertsResponse, missing: [] },
    });
    renderPage();
    await screen.findByRole('heading', { level: 1, name: /my certifications/i });
    expect(screen.queryByText('Action Required')).not.toBeInTheDocument();
  });

  // ── All Certifications list ─────────────────────────────────────────────────

  it('renders All Certifications section heading', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 2, name: /all certifications/i }),
    ).toBeInTheDocument();
  });

  it('renders certification type display names in list', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(await screen.findByText('First Aid Certification')).toBeInTheDocument();
    expect(screen.getByText('Safeguarding Training')).toBeInTheDocument();
  });

  it('renders provider name in certification row', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(await screen.findByText('Red Cross')).toBeInTheDocument();
  });

  it('shows "Expired" status badge in All Certifications list', async () => {
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    expect(await screen.findByText('Expired')).toBeInTheDocument();
  });

  // ── Cert expansion ──────────────────────────────────────────────────────────

  it('expands cert row to show details when clicked', async () => {
    const user = userEvent.setup();
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    // "Completed" label is only shown when a cert row is expanded
    expect(screen.queryByText('Completed')).not.toBeInTheDocument();
    const certButton = await screen.findByRole('button', {
      name: /first aid certification/i,
    });
    await user.click(certButton);
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Expires')).toBeInTheDocument();
  });

  it('shows certificate URL link when cert is expanded', async () => {
    const user = userEvent.setup();
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    const certButton = await screen.findByRole('button', {
      name: /first aid certification/i,
    });
    await user.click(certButton);
    const certLink = screen.getByRole('link', { name: /view certificate/i });
    expect(certLink).toHaveAttribute('href', 'https://example.com/cert.pdf');
  });

  it('shows notes when cert is expanded', async () => {
    const user = userEvent.setup();
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    const certButton = await screen.findByRole('button', {
      name: /first aid certification/i,
    });
    await user.click(certButton);
    expect(screen.getByText('Annual renewal required')).toBeInTheDocument();
  });

  it('collapses cert row when clicked again', async () => {
    const user = userEvent.setup();
    mockApiGet.mockResolvedValue({ data: mockCertsResponse });
    renderPage();
    const certButton = await screen.findByRole('button', {
      name: /first aid certification/i,
    });
    // Expand
    await user.click(certButton);
    expect(screen.getByText('Completed')).toBeInTheDocument();
    // Collapse
    await user.click(certButton);
    await waitFor(() => {
      expect(screen.queryByText('Completed')).not.toBeInTheDocument();
    });
  });

  // ── No certifications empty state ───────────────────────────────────────────

  it('shows "No certifications recorded yet" when list is empty', async () => {
    mockApiGet.mockResolvedValue({
      data: { ...mockCertsResponse, certifications: [] },
    });
    renderPage();
    expect(
      await screen.findByText('No certifications recorded yet.'),
    ).toBeInTheDocument();
  });

  it('shows "Contact your admin" hint in empty cert state', async () => {
    mockApiGet.mockResolvedValue({
      data: { ...mockCertsResponse, certifications: [] },
    });
    renderPage();
    expect(
      await screen.findByText(/contact your admin to add your pd records/i),
    ).toBeInTheDocument();
  });
});
