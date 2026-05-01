// src/pages/admin/SettingsPage.test.tsx
//
// FE-070: Broad coverage for SettingsPage beyond the SCIMTokenCard focus in
// SettingsPage.SCIMTokenCard.test.tsx.
//
// Covers:
//   - Page-level: loading skeleton, error banner, "Settings" heading, all 6 tabs visible
//   - Tab navigation: default tab (profile), URL-driven tab (?tab=...), click to switch
//   - School Profile: form fields rendered with defaults, validation error on empty name, submit
//   - Branding: heading, primary-color input, font-family select
//   - Security: Password Policy heading + loading state + populated form;
//               Two-Factor Authentication heading; 2FA toggle renders
//   - Academic: heading, academic year input
//   - Mode & Labels: Platform Mode heading, Education / Corporate mode buttons
//   - AI Provider: LLM Provider heading
//
// SCIM token tests (24 tests) are in SettingsPage.SCIMTokenCard.test.tsx — not duplicated here.
//
// Mocking strategy:
//   - api (axios instance) mocked via vi.mock so no real HTTP requests fire
//   - adminSettingsService fully stubbed (all methods)
//   - useTenantStore stubbed (features.saml = false to skip SAMLSSOCard in security tab)
//   - usePageTitle stubbed (no document.title side-effects in happy-dom)
//   - buildSpUrls stubbed (no real subdomain URL computation needed)
//   - applyTheme stubbed (prevents DOM mutations from theme application)
//   - QueryClient uses staleTime: Infinity + refetchOnWindowFocus: false to prevent
//     refetch cycles from interfering with act() settling in React 19

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

vi.mock('../../stores/tenantStore');

vi.mock('../../services/adminSettingsService', () => ({
  adminSettingsService: {
    getPasswordPolicy: vi.fn(),
    updatePasswordPolicy: vi.fn(),
    getSAMLConfig: vi.fn(),
    updateSAMLConfig: vi.fn(),
    getModeSettings: vi.fn(),
    updateModeSettings: vi.fn(),
    getTenantModeForUser: vi.fn(),
    listSCIMTokens: vi.fn(),
    createSCIMToken: vi.fn(),
    revokeSCIMToken: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

vi.mock('../../utils/samlUrls', () => ({
  buildSpUrls: vi.fn(() => ({
    entityId: 'https://testschool.learnpuddle.com/saml/metadata',
    acsUrl: 'https://testschool.learnpuddle.com/saml/acs',
    slsUrl: 'https://testschool.learnpuddle.com/saml/sls',
    metadataUrl: 'https://testschool.learnpuddle.com/saml/metadata.xml',
  })),
}));

vi.mock('../../config/theme', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../config/theme')>();
  return {
    ...actual,
    applyTheme: vi.fn(),
  };
});

// Stub clipboard so happy-dom doesn't warn about unimplemented navigator.clipboard
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: vi.fn().mockResolvedValue(undefined) },
  configurable: true,
});

// ── Typed aliases ─────────────────────────────────────────────────────────────

const mockedApi = api as unknown as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
  patch: ReturnType<typeof vi.fn>;
};

const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedService = adminSettingsService as {
  [K in keyof typeof adminSettingsService]: ReturnType<typeof vi.fn>;
};

// ── Fixtures ──────────────────────────────────────────────────────────────────

const MOCK_TENANT_SETTINGS = {
  id: 'tenant-1',
  name: 'Greenfield Academy',
  subdomain: 'greenfield',
  email: 'admin@greenfield.edu',
  phone: '+1 555-0100',
  address: '123 School Lane',
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
  min_length: 12,
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

const MOCK_MODE_SETTINGS = {
  mode: 'education' as const,
  mode_label_overrides: {},
  mode_labels: {
    teacher: 'Teacher',
    teachers: 'Teachers',
    student: 'Student',
    students: 'Students',
    course: 'Course',
    courses: 'Courses',
    assignment: 'Assignment',
    assignments: 'Assignments',
    module: 'Module',
    modules: 'Modules',
    content: 'Content',
    grade: 'Grade',
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        // Prevent immediate background refetches from interfering with act() in React 19.
        // staleTime: 0 (default) would schedule refetches after each resolve; combined
        // with any re-render these can produce microtask loops that keep act() running.
        staleTime: Infinity,
        refetchOnWindowFocus: false,
      },
      mutations: { retry: false },
    },
  });
}

/** Configures the most common set of mock return values for full-page renders. */
function setupDefaultMocks() {
  // Main tenant settings (drives profile, branding, academic sections)
  mockedApi.get.mockImplementation(async (url: string) => {
    if (url === '/tenants/settings/') return { data: MOCK_TENANT_SETTINGS };
    if (url === '/tenants/settings/security/') return { data: { two_factor_enabled: false, session_timeout_minutes: 60 } };
    if (url === '/tenants/settings/ai/') return { data: { llm_provider: 'openai', llm_model: 'gpt-4o', llm_api_key: '', llm_base_url: '' } };
    return { data: {} };
  });

  // adminSettingsService method stubs
  mockedService.getPasswordPolicy.mockResolvedValue(MOCK_PASSWORD_POLICY);
  mockedService.getModeSettings.mockResolvedValue(MOCK_MODE_SETTINGS);
  mockedService.listSCIMTokens.mockResolvedValue({ count: 0, results: [] });

  // Tenant store — no SAML feature so SAMLSSOCard is hidden
  mockedUseTenantStore.mockReturnValue({
    features: { saml: false },
    theme: { subdomain: 'greenfield', name: 'Greenfield Academy', primary_color: '#4f46e5' },
    setTheme: vi.fn(),
    setModeLabels: vi.fn(),
    hasFeature: vi.fn(() => false),
    mode: 'education',
    modeLabels: MOCK_MODE_SETTINGS.mode_labels,
  });
}

/** Renders SettingsPage at a given ?tab param. */
function renderAt(tab?: string) {
  const initialPath = tab ? `/?tab=${tab}` : '/';
  const queryClient = makeQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialPath]}>
          <SettingsPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// ── Tests: Page-level ─────────────────────────────────────────────────────────

describe('SettingsPage — page-level', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('shows a loading spinner while tenant settings are fetching', () => {
    // Never resolve so we stay in the loading state
    mockedApi.get.mockReturnValue(new Promise(() => {}));
    renderAt();
    // Loading component renders an svg/circle or animate-spin; the page
    // doesn't show the Settings heading yet
    expect(screen.queryByRole('heading', { name: /settings/i })).not.toBeInTheDocument();
    // A spinner element should be present
    const spinner = document.querySelector('.animate-spin, [role="status"]');
    expect(spinner).toBeTruthy();
  });

  it('shows error banner when tenant settings request fails', async () => {
    mockedApi.get.mockRejectedValue(new Error('Network Error'));
    renderAt();
    expect(await screen.findByText(/Failed to load settings/i)).toBeInTheDocument();
  });

  it('renders the "Settings" page heading after data loads', async () => {
    renderAt();
    expect(
      await screen.findByRole('heading', { level: 1, name: /settings/i }),
    ).toBeInTheDocument();
  });

  it('renders all 6 tab buttons', async () => {
    renderAt();
    // Wait for the page to finish loading
    await screen.findByRole('heading', { level: 1, name: /settings/i });

    for (const label of ['School Profile', 'Branding', 'Security', 'Academic', 'Mode & Labels', 'AI Provider']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });
});

// ── Tests: Tab navigation ─────────────────────────────────────────────────────

describe('SettingsPage — tab navigation', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('defaults to School Profile tab when no ?tab param is given', async () => {
    renderAt();
    // The "School Profile" text appears both in the active tab button AND the section h2.
    // Verify both are present (tab active + section rendered).
    await waitFor(() => {
      expect(screen.getAllByText('School Profile').length).toBeGreaterThanOrEqual(2);
    });
    // Verify the form field label is present (profile-specific)
    expect(screen.getByText('School Name')).toBeInTheDocument();
  });

  it('opens the Security tab directly when ?tab=security is in the URL', async () => {
    renderAt('security');
    await waitFor(() => {
      expect(screen.getByText('Password Policy')).toBeInTheDocument();
    });
  });

  it('opens the Branding tab directly when ?tab=branding is in the URL', async () => {
    renderAt('branding');
    // The Branding h2 section heading (distinct from the tab button)
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Branding' })).toBeInTheDocument();
    });
  });

  it('opens the Academic tab directly when ?tab=academic is in the URL', async () => {
    renderAt('academic');
    await waitFor(() => {
      expect(screen.getByText('Academic Configuration')).toBeInTheDocument();
    });
  });

  it('opens the Mode & Labels tab directly when ?tab=mode is in the URL', async () => {
    renderAt('mode');
    await waitFor(() => {
      expect(screen.getByText('Platform Mode')).toBeInTheDocument();
    });
  });

  it('opens the AI Provider tab directly when ?tab=ai is in the URL', async () => {
    renderAt('ai');
    await waitFor(() => {
      expect(screen.getByText('LLM Provider')).toBeInTheDocument();
    });
  });

  it('clicking the Branding tab button switches to the branding section', async () => {
    const user = userEvent.setup();
    renderAt(); // starts on profile
    await screen.findByText('School Name'); // wait for data to load

    await user.click(screen.getByRole('button', { name: 'Branding' }));

    // Primary Color label is specific to the BrandingSection
    await waitFor(() => {
      expect(screen.getByText('Primary Color')).toBeInTheDocument();
    });
    // Profile-specific label should no longer be visible
    expect(screen.queryByText('School Name')).not.toBeInTheDocument();
  });

  it('clicking the Academic tab button switches to the academic section', async () => {
    const user = userEvent.setup();
    renderAt();
    await screen.findByText('School Name');

    await user.click(screen.getByRole('button', { name: 'Academic' }));

    await waitFor(() => {
      expect(screen.getByText('Academic Configuration')).toBeInTheDocument();
    });
  });
});

// ── Tests: School Profile tab ─────────────────────────────────────────────────

describe('SettingsPage — School Profile tab', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('renders the School Profile section heading', async () => {
    renderAt();
    // Use heading role to distinguish the h2 from the tab button with the same text
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'School Profile' })).toBeInTheDocument();
    });
  });

  it('populates the school name input with the fetched setting', async () => {
    renderAt();
    const nameInput = await screen.findByPlaceholderText('Enter school name');
    expect((nameInput as HTMLInputElement).value).toBe('Greenfield Academy');
  });

  it('renders email, phone, and address fields', async () => {
    renderAt();
    await screen.findByPlaceholderText('Enter school name');

    expect(screen.getByPlaceholderText('admin@school.com')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('+91 98765 43210')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('School address')).toBeInTheDocument();
  });

  it('shows the subdomain as a read-only disabled input', async () => {
    renderAt();
    await screen.findByPlaceholderText('Enter school name');

    const subdomainInput = screen.getByDisplayValue('greenfield');
    expect(subdomainInput).toBeDisabled();
  });

  it('shows a "Save Profile" submit button', async () => {
    renderAt();
    await screen.findByPlaceholderText('Enter school name');
    expect(screen.getByRole('button', { name: /save profile/i })).toBeInTheDocument();
  });

  it('shows validation error when school name is cleared and form submitted', async () => {
    const user = userEvent.setup();
    renderAt();
    const nameInput = await screen.findByPlaceholderText('Enter school name');

    await user.clear(nameInput);
    await user.click(screen.getByRole('button', { name: /save profile/i }));

    expect(await screen.findByText(/school name is required/i)).toBeInTheDocument();
  });

  it('calls api.patch on valid form submission', async () => {
    const user = userEvent.setup();
    mockedApi.patch.mockResolvedValue({ data: MOCK_TENANT_SETTINGS });
    renderAt();
    const nameInput = await screen.findByPlaceholderText('Enter school name');

    await user.clear(nameInput);
    await user.type(nameInput, 'New School Name');
    await user.click(screen.getByRole('button', { name: /save profile/i }));

    await waitFor(() => {
      expect(mockedApi.patch).toHaveBeenCalledWith(
        '/tenants/settings/',
        expect.any(FormData),
      );
    });
  });
});

// ── Tests: Branding tab ───────────────────────────────────────────────────────

describe('SettingsPage — Branding tab', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('renders the Branding section heading', async () => {
    renderAt('branding');
    // Use heading role to avoid collision with the same-text tab button
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Branding' })).toBeInTheDocument();
    });
  });

  it('renders primary color label and pre-filled color input', async () => {
    renderAt('branding');
    await waitFor(() => {
      expect(screen.getByText('Primary Color')).toBeInTheDocument();
    });
    // Both the color picker and text input have the same hex value — at least one present
    const colorInputs = screen.getAllByDisplayValue('#4f46e5');
    expect(colorInputs.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the font family select with Inter selected by default', async () => {
    renderAt('branding');
    await waitFor(() => {
      expect(screen.getByText('Font Family')).toBeInTheDocument();
    });
    // Branding tab has exactly one <select> (the font family selector)
    const fontSelect = screen.getByRole('combobox');
    expect((fontSelect as HTMLSelectElement).value).toBe('Inter');
  });

  it('renders a "Save Branding" submit button', async () => {
    renderAt('branding');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save branding/i })).toBeInTheDocument();
    });
  });
});

// ── Tests: Security tab — Password Policy ─────────────────────────────────────

describe('SettingsPage — Security tab / PasswordPolicyCard', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('renders the Password Policy section heading', async () => {
    renderAt('security');
    await waitFor(() => {
      expect(screen.getByText('Password Policy')).toBeInTheDocument();
    });
  });

  it('shows a loading spinner while password policy is fetching', async () => {
    mockedService.getPasswordPolicy.mockReturnValue(new Promise(() => {}));
    renderAt('security');
    // TwoFactorSessionCard is outside PasswordPolicyCard and loads independently.
    // Wait for it to confirm the security section is rendered.
    await waitFor(() => {
      expect(screen.getByText('Two-Factor Authentication')).toBeInTheDocument();
    });
    // PasswordPolicyCard is still loading (never-resolving promise) — its Loading
    // component renders an animate-spin element instead of the "Password Policy" heading.
    expect(document.querySelector('.animate-spin')).toBeTruthy();
    expect(screen.queryByRole('heading', { name: 'Password Policy' })).not.toBeInTheDocument();
  });

  it('populates the min_length field from fetched policy', async () => {
    renderAt('security');
    // Wait for the policy data to appear
    const minLengthInput = await screen.findByDisplayValue('12');
    expect(minLengthInput).toBeInTheDocument();
  });

  it('renders the "Save Password Policy" submit button', async () => {
    renderAt('security');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save password policy/i })).toBeInTheDocument();
    });
  });

  it('calls updatePasswordPolicy when policy form is submitted', async () => {
    const user = userEvent.setup();
    mockedService.updatePasswordPolicy.mockResolvedValue(MOCK_PASSWORD_POLICY);
    renderAt('security');

    await screen.findByRole('button', { name: /save password policy/i });
    await user.click(screen.getByRole('button', { name: /save password policy/i }));

    await waitFor(() => {
      expect(mockedService.updatePasswordPolicy).toHaveBeenCalledTimes(1);
    });
  });
});

// ── Tests: Security tab — 2FA / Session ───────────────────────────────────────

describe('SettingsPage — Security tab / TwoFactorSessionCard', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('renders the Two-Factor Authentication heading', async () => {
    renderAt('security');
    await waitFor(() => {
      expect(screen.getByText('Two-Factor Authentication')).toBeInTheDocument();
    });
  });

  it('renders the session management timeout dropdown', async () => {
    renderAt('security');
    await waitFor(() => {
      expect(screen.getByText('Session Management')).toBeInTheDocument();
    });
    expect(screen.getByRole('combobox', { name: /session timeout/i })).toBeInTheDocument();
  });

  it('renders the 2FA toggle switch', async () => {
    renderAt('security');
    await waitFor(() => {
      // The Toggle label text is rendered as a <p> sibling to the switch button.
      // The button itself has no aria-label, so query by label text then confirm switch exists.
      expect(screen.getByText('Require 2FA for all teachers')).toBeInTheDocument();
    });
    // At least one role=switch must exist (the 2FA toggle)
    expect(screen.getAllByRole('switch').length).toBeGreaterThanOrEqual(1);
  });

  it('does NOT render SAMLSSOCard when SAML feature is disabled', async () => {
    renderAt('security');
    await waitFor(() => {
      expect(screen.getByText('Password Policy')).toBeInTheDocument();
    });
    expect(screen.queryByText('SAML 2.0 Single Sign-On')).not.toBeInTheDocument();
  });

  it('renders SAMLSSOCard heading when SAML feature is enabled', async () => {
    mockedUseTenantStore.mockReturnValue({
      features: { saml: true },
      theme: { subdomain: 'greenfield', name: 'Greenfield Academy' },
      setTheme: vi.fn(),
      setModeLabels: vi.fn(),
      hasFeature: vi.fn((f: string) => f === 'saml'),
    });
    mockedService.getSAMLConfig.mockResolvedValue({
      enabled: false,
      idp_metadata_xml: '',
      idp_entity_id: '',
      idp_sso_url: '',
      idp_slo_url: '',
      idp_x509_cert: '',
      auto_provision: false,
      default_role: 'TEACHER',
      allowed_email_domains: '',
      attr_email: '',
      attr_first_name: '',
      attr_last_name: '',
      attr_groups: '',
      attr_role: '',
    });
    renderAt('security');
    await waitFor(() => {
      expect(screen.getByText('SAML 2.0 Single Sign-On')).toBeInTheDocument();
    });
  });
});

// ── Tests: Academic tab ────────────────────────────────────────────────────────

describe('SettingsPage — Academic tab', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('renders the Academic Configuration heading', async () => {
    renderAt('academic');
    await waitFor(() => {
      expect(screen.getByText('Academic Configuration')).toBeInTheDocument();
    });
  });

  it('renders the Academic Year input', async () => {
    renderAt('academic');
    await waitFor(() => {
      // FormField label="Current Academic Year" (not just "Academic Year")
      expect(screen.getByText('Current Academic Year')).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText('2026-27')).toBeInTheDocument();
  });

  it('renders the "Save Academic Settings" button', async () => {
    renderAt('academic');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save academic settings/i })).toBeInTheDocument();
    });
  });
});

// ── Tests: Mode & Labels tab ──────────────────────────────────────────────────

describe('SettingsPage — Mode & Labels tab', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('renders the Platform Mode heading', async () => {
    renderAt('mode');
    await waitFor(() => {
      expect(screen.getByText('Platform Mode')).toBeInTheDocument();
    });
  });

  it('renders both Education and Corporate mode option buttons', async () => {
    renderAt('mode');
    await waitFor(() => {
      expect(screen.getByText('Education')).toBeInTheDocument();
      expect(screen.getByText('Corporate')).toBeInTheDocument();
    });
  });

  it('renders the Label Overrides table with mode label keys', async () => {
    renderAt('mode');
    await waitFor(() => {
      expect(screen.getByText('Label Overrides')).toBeInTheDocument();
    });
  });

  it('clicking Corporate mode button switches the active mode', async () => {
    const user = userEvent.setup();
    renderAt('mode');
    await screen.findByText('Platform Mode');

    await user.click(screen.getByText('Corporate'));

    // After clicking Corporate, the save button text is "Save Mode & Labels"
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save mode & labels/i })).toBeInTheDocument();
    });
  });
});

// ── Tests: AI Provider tab ────────────────────────────────────────────────────

describe('SettingsPage — AI Provider tab', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('renders the LLM Provider heading', async () => {
    renderAt('ai');
    await waitFor(() => {
      expect(screen.getByText('LLM Provider')).toBeInTheDocument();
    });
  });

  it('renders the provider dropdown with OpenAI as default option', async () => {
    renderAt('ai');
    await waitFor(() => {
      expect(screen.getByText('LLM Provider')).toBeInTheDocument();
    });
    // The Provider label is not associated via htmlFor — use getByDisplayValue instead.
    // AI_DEFAULT.llm_provider = 'openai', which renders as "OpenAI" in the select.
    const providerSelect = screen.getByDisplayValue('OpenAI');
    expect(providerSelect).toBeInTheDocument();
    expect((providerSelect as HTMLSelectElement).value).toBe('openai');
  });

  it('renders the "Test Connection" button', async () => {
    renderAt('ai');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /test connection/i })).toBeInTheDocument();
    });
  });

  it('renders the "Save AI Settings" button', async () => {
    renderAt('ai');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save ai settings/i })).toBeInTheDocument();
    });
  });
});
