// src/pages/admin/SettingsPage.SCIMTokenCard.test.tsx
//
// Tests for the SCIMTokenCard component (FE-032 / TASK-023).
// Covers: token list (loading, error, empty, populated), SCIM endpoint URL,
// create-token form + validation + reveal modal, revoke flow + confirm dialog,
// toast feedback on errors.
//
// Strategy: render the full SettingsPage at ?tab=security so we exercise the
// real component tree without any unstable component extraction. The security
// tab renders SecuritySection → SCIMTokenCard unconditionally.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { SettingsPage } from './SettingsPage';
import { ToastProvider } from '../../components/common';
import api from '../../config/api';
import { useTenantStore } from '../../stores/tenantStore';
import { adminSettingsService } from '../../services/adminSettingsService';
import type { SCIMTokenSummary, SCIMTokenCreated } from '../../services/adminSettingsService';

// ─── Module mocks ─────────────────────────────────────────────────────────────

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

vi.mock('../../stores/tenantStore');

vi.mock('../../services/adminSettingsService', () => ({
  adminSettingsService: {
    getPasswordPolicy: vi.fn(),
    updatePasswordPolicy: vi.fn(),
    getSAMLConfig: vi.fn(),
    updateSAMLConfig: vi.fn(),
    listSCIMTokens: vi.fn(),
    createSCIMToken: vi.fn(),
    revokeSCIMToken: vi.fn(),
    getTenantModeSettings: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

vi.mock('../../utils/samlUrls', () => ({
  buildSpUrls: vi.fn(() => ({
    entityId: 'https://example.com/saml/metadata',
    acsUrl: 'https://example.com/saml/acs',
    slsUrl: 'https://example.com/saml/sls',
    metadataUrl: 'https://example.com/saml/metadata.xml',
  })),
}));

// Stub clipboard to avoid jsdom "Not implemented" warnings
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: vi.fn().mockResolvedValue(undefined) },
  configurable: true,
});

// ─── Typed aliases ────────────────────────────────────────────────────────────

const mockedApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
  put: ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedService = adminSettingsService as {
  [K in keyof typeof adminSettingsService]: ReturnType<typeof vi.fn>;
};

// ─── Fixtures ────────────────────────────────────────────────────────────────

const MOCK_TENANT_SETTINGS = {
  id: 'tenant-1',
  name: 'Test School',
  subdomain: 'testschool',
  email: 'admin@testschool.com',
  phone: '',
  address: '',
  logo: null,
  logo_url: null,
  primary_color: '#4f46e5',
  secondary_color: '#818cf8',
  font_family: 'Inter',
  is_active: true,
  is_trial: false,
  trial_end_date: null,
};

const MOCK_PASSWORD_POLICY = {
  min_length: 8,
  require_uppercase: true,
  require_lowercase: true,
  require_digit: true,
  require_special: false,
  prevent_common: true,
  prevent_reuse_last_n: 5,
  max_age_days: 90,
  lockout_threshold: 5,
  lockout_duration_minutes: 15,
  policy_rotated_at: null,
  updated_at: '2026-01-01T00:00:00Z',
};

const TOKEN_ACTIVE: SCIMTokenSummary = {
  id: 'tok-active-1',
  name: 'Okta SCIM Provisioner',
  created_at: '2026-03-15T10:00:00Z',
  last_used_at: '2026-04-10T09:30:00Z',
  is_active: true,
};

const TOKEN_REVOKED: SCIMTokenSummary = {
  id: 'tok-revoked-2',
  name: 'Legacy Azure AD Token',
  created_at: '2025-11-01T10:00:00Z',
  last_used_at: null,
  is_active: false,
};

const CREATED_TOKEN: SCIMTokenCreated = {
  id: 'tok-new-99',
  name: 'New Provisioner',
  token: 'raw-bearer-token-value-9876543210',
  created_at: '2026-04-23T12:00:00Z',
  is_active: true,
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function setupDefaultMocks() {
  // Full-page dependencies
  mockedApi.get.mockImplementation(async (url: string) => {
    if (url === '/tenants/settings/') return { data: MOCK_TENANT_SETTINGS };
    if (url === '/tenants/settings/security/') return { data: { two_factor_enabled: false, session_timeout_minutes: 60 } };
    return { data: {} };
  });

  // Password policy (loaded by PasswordPolicyCard inside SecuritySection)
  mockedService.getPasswordPolicy.mockResolvedValue(MOCK_PASSWORD_POLICY);

  // SCIM token list — default: one active token
  mockedService.listSCIMTokens.mockResolvedValue({
    count: 1,
    results: [TOKEN_ACTIVE],
  });

  // Tenant store — no SAML feature so we skip SAMLSSOCard
  mockedUseTenantStore.mockReturnValue({
    features: { saml: false },
    theme: { subdomain: 'testschool', name: 'Test School' },
    setTheme: vi.fn(),
    hasFeature: vi.fn(() => false),
    setModeLabels: vi.fn(),
  });
}

function renderOnSecurityTab() {
  const queryClient = makeQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/?tab=security']}>
          <SettingsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('SCIMTokenCard — SCIM endpoint URL', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('displays the correct SCIM endpoint URL for the subdomain', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('SCIM 2.0 Provisioning')).toBeInTheDocument();
    });

    // CopyableField renders the URL as a `<code>` element
    expect(
      screen.getByText('https://testschool.learnpuddle.com/scim/v2/'),
    ).toBeInTheDocument();
  });

  it('shows placeholder URL when subdomain is empty', async () => {
    mockedUseTenantStore.mockReturnValue({
      features: { saml: false },
      theme: { subdomain: '', name: 'Test School' },
      setTheme: vi.fn(),
      hasFeature: vi.fn(() => false),
    });

    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('SCIM 2.0 Provisioning')).toBeInTheDocument();
    });

    expect(
      screen.getByText('https://<your-school>.learnpuddle.com/scim/v2/'),
    ).toBeInTheDocument();
  });
});

describe('SCIMTokenCard — token list rendering', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('shows a loading spinner while fetching tokens', async () => {
    // Never resolve so we stay in loading state
    mockedService.listSCIMTokens.mockReturnValue(new Promise(() => {}));

    renderOnSecurityTab();

    // Wait for the security section header to appear first
    await waitFor(() => {
      expect(screen.getByText('SCIM 2.0 Provisioning')).toBeInTheDocument();
    });

    // The animate-spin spinner must be present in the DOM (FE-032 M1 follow-up:
    // stronger assertion matching the FE-033 pattern — see review-FE-032-and-QA-tests-2026-04-24.md)
    expect(document.querySelector('.animate-spin')).toBeTruthy();
    // The token table is not yet rendered
    expect(screen.queryByText('Okta SCIM Provisioner')).not.toBeInTheDocument();
  });

  it('shows error banner when token list fetch fails', async () => {
    mockedService.listSCIMTokens.mockRejectedValue(new Error('Network error'));

    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('SCIM 2.0 Provisioning')).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(
        screen.getByText(/failed to load scim tokens/i),
      ).toBeInTheDocument();
    });
  });

  it('shows empty-state message when no tokens exist', async () => {
    mockedService.listSCIMTokens.mockResolvedValue({ count: 0, results: [] });

    renderOnSecurityTab();

    await waitFor(() => {
      expect(
        screen.getByText(/no tokens yet/i),
      ).toBeInTheDocument();
    });
  });

  it('renders active token name, status badge, and last-used date', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('Okta SCIM Provisioner')).toBeInTheDocument();
    });

    // Status badge
    expect(screen.getByText('Active')).toBeInTheDocument();

    // Last-used date (localeDateString of '2026-04-10T09:30:00Z')
    const lastUsedDate = new Date('2026-04-10T09:30:00Z').toLocaleDateString();
    expect(screen.getByText(lastUsedDate)).toBeInTheDocument();
  });

  it('renders revoked token with "Revoked" badge and no revoke button', async () => {
    mockedService.listSCIMTokens.mockResolvedValue({
      count: 2,
      results: [TOKEN_ACTIVE, TOKEN_REVOKED],
    });

    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('Legacy Azure AD Token')).toBeInTheDocument();
    });

    expect(screen.getByText('Revoked')).toBeInTheDocument();

    // Only the active token has a revoke button; the revoked one must not
    const revokeButtons = screen.getAllByText('Revoke');
    // There should be exactly one revoke button (for the active token only)
    expect(revokeButtons).toHaveLength(1);
  });

  it('renders "Never" for tokens that have never been used', async () => {
    mockedService.listSCIMTokens.mockResolvedValue({
      count: 1,
      results: [TOKEN_REVOKED],  // TOKEN_REVOKED has last_used_at: null
    });

    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('Legacy Azure AD Token')).toBeInTheDocument();
    });

    expect(screen.getByText('Never')).toBeInTheDocument();
  });
});

describe('SCIMTokenCard — create token form', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('shows "Add token" button and hides create form initially', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('SCIM 2.0 Provisioning')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    expect(screen.queryByText('Create a new SCIM token')).not.toBeInTheDocument();
  });

  it('shows create form when "Add token" button is clicked', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    expect(screen.getByText('Create a new SCIM token')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^create$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });

  it('hides create form when Cancel is clicked', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));
    expect(screen.getByText('Create a new SCIM token')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByText('Create a new SCIM token')).not.toBeInTheDocument();
  });

  it('requires a non-empty token name (Zod validation)', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(screen.getByText(/token name is required/i)).toBeInTheDocument();
    });

    expect(mockedService.createSCIMToken).not.toHaveBeenCalled();
  });

  it('rejects token names exceeding 64 characters', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    const input = screen.getByRole('textbox', { name: /token name/i });
    await userEvent.type(input, 'A'.repeat(65));
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(screen.getByText(/64 characters or fewer/i)).toBeInTheDocument();
    });

    expect(mockedService.createSCIMToken).not.toHaveBeenCalled();
  });

  it('rejects token names with special characters outside the allowed set', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    const input = screen.getByRole('textbox', { name: /token name/i });
    await userEvent.type(input, 'Token <script>');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/only letters, numbers, spaces, hyphens/i),
      ).toBeInTheDocument();
    });

    expect(mockedService.createSCIMToken).not.toHaveBeenCalled();
  });

  it('submits create form with valid name and calls createSCIMToken', async () => {
    mockedService.createSCIMToken.mockResolvedValue(CREATED_TOKEN);

    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    const input = screen.getByRole('textbox', { name: /token name/i });
    await userEvent.type(input, 'New Provisioner');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(mockedService.createSCIMToken).toHaveBeenCalledWith('New Provisioner');
    });
  });
});

describe('SCIMTokenCard — token reveal modal', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
    mockedService.createSCIMToken.mockResolvedValue(CREATED_TOKEN);
    // After creation, refresh returns the new token in the list
    mockedService.listSCIMTokens
      .mockResolvedValueOnce({ count: 1, results: [TOKEN_ACTIVE] })
      .mockResolvedValue({
        count: 2,
        results: [TOKEN_ACTIVE, { ...TOKEN_ACTIVE, id: CREATED_TOKEN.id, name: CREATED_TOKEN.name }],
      });
  });

  it('opens reveal modal after successful token creation', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    const input = screen.getByRole('textbox', { name: /token name/i });
    await userEvent.type(input, 'New Provisioner');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(screen.getByText('Token created — copy it now')).toBeInTheDocument();
    });
  });

  it('displays the raw token value in the reveal modal', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    const input = screen.getByRole('textbox', { name: /token name/i });
    await userEvent.type(input, 'New Provisioner');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(screen.getByText(CREATED_TOKEN.token)).toBeInTheDocument();
    });
  });

  it('shows "shown only once" warning in the reveal modal', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    const input = screen.getByRole('textbox', { name: /token name/i });
    await userEvent.type(input, 'New Provisioner');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/this token will not be shown again/i),
      ).toBeInTheDocument();
    });
  });

  it('copies token to clipboard when copy button is clicked', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    const input = screen.getByRole('textbox', { name: /token name/i });
    await userEvent.type(input, 'New Provisioner');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /copy token to clipboard/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /copy token to clipboard/i }));

    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(CREATED_TOKEN.token);
    });
  });

  it('closes reveal modal when "I\'ve copied the token" button is clicked', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    const input = screen.getByRole('textbox', { name: /token name/i });
    await userEvent.type(input, 'New Provisioner');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => {
      expect(screen.getByText('Token created — copy it now')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /i've copied the token/i }));

    await waitFor(() => {
      expect(screen.queryByText('Token created — copy it now')).not.toBeInTheDocument();
    });
  });
});

describe('SCIMTokenCard — revoke token flow', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('shows revoke confirmation dialog when Revoke is clicked', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('Okta SCIM Provisioner')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /revoke/i }));

    await waitFor(() => {
      expect(screen.getByText('Revoke SCIM token')).toBeInTheDocument();
    });

    expect(
      screen.getByText(/revoking "okta scim provisioner"/i),
    ).toBeInTheDocument();
  });

  it('calls revokeSCIMToken after confirming the revoke dialog', async () => {
    mockedService.revokeSCIMToken.mockResolvedValue(undefined);

    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('Okta SCIM Provisioner')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /revoke/i }));

    await waitFor(() => {
      expect(screen.getByText('Revoke SCIM token')).toBeInTheDocument();
    });

    // Click the confirm button in the ConfirmDialog
    await userEvent.click(screen.getByRole('button', { name: /revoke token/i }));

    await waitFor(() => {
      expect(mockedService.revokeSCIMToken).toHaveBeenCalledWith(TOKEN_ACTIVE.id);
    });
  });

  it('does NOT call revokeSCIMToken when revoke dialog is cancelled', async () => {
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByText('Okta SCIM Provisioner')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /revoke/i }));

    await waitFor(() => {
      expect(screen.getByText('Revoke SCIM token')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /keep active/i }));

    expect(mockedService.revokeSCIMToken).not.toHaveBeenCalled();
  });
});

describe('SCIMTokenCard — error handling', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('shows error toast when token creation fails', async () => {
    mockedService.createSCIMToken.mockRejectedValue(new Error('Server error'));

    // Capture toast calls via the ToastProvider aria output
    renderOnSecurityTab();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add token/i })).toBeInTheDocument();
    });

    await userEvent.click(screen.getByRole('button', { name: /add token/i }));

    const input = screen.getByRole('textbox', { name: /token name/i });
    await userEvent.type(input, 'Failing Token');
    await userEvent.click(screen.getByRole('button', { name: /^create$/i }));

    // The component calls toast.error('Failed to create SCIM token', ...)
    // ToastProvider renders the toast into the DOM as an alert
    await waitFor(() => {
      expect(
        screen.getByText(/failed to create scim token/i),
      ).toBeInTheDocument();
    });
  });
});
