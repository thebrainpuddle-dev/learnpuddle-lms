// src/pages/settings/SecuritySettings.test.tsx
//
// Vitest + React Testing Library tests for SecuritySettings.
//
// The page has two sections:
//   1. Two-Factor Authentication (2FA) — setup QR flow + disable modal
//   2. Single Sign-On (SSO) — shows linked providers or "not enabled" message
//
// API calls:
//   GET /users/auth/2fa/status/   → TwoFAStatus  (drives 2FA section)
//   GET /users/auth/sso/status/   → SSOStatus    (drives linked-provider state)
//   GET /users/auth/sso/providers/ → SSOProviders (drives SSO provider list)
//
// Mocking strategy:
//   - api (axios instance) mocked via vi.mock — no real HTTP requests
//   - usePageTitle stubbed (avoids document.title side-effects in happy-dom)
//   - Loading stubbed with a simple data-testid div
//   - QueryClient uses retry:false + staleTime:Infinity to prevent refetch loops

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SecuritySettings } from './SecuritySettings';
import api from '../../config/api';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('../../components/common', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/common')>();
  return { ...actual, Loading: () => <div data-testid="loading-spinner">Loading...</div> };
});

// ── Typed aliases ─────────────────────────────────────────────────────────────

const mockedApiGet = api.get as ReturnType<typeof vi.fn>;
const mockedApiPost = api.post as ReturnType<typeof vi.fn>;

// ── Fixtures ──────────────────────────────────────────────────────────────────

const TWOFA_ENABLED = {
  enabled: true,
  required: false,
  totp_configured: true,
  backup_codes_remaining: 8,
  can_disable: true,
};

const TWOFA_ENABLED_REQUIRED = {
  enabled: true,
  required: true,
  totp_configured: true,
  backup_codes_remaining: 5,
  can_disable: false,
};

const TWOFA_DISABLED = {
  enabled: false,
  required: false,
  totp_configured: false,
  backup_codes_remaining: 0,
  can_disable: false,
};

const SSO_STATUS_LINKED = {
  has_password: true,
  linked_providers: [{ provider: 'google', uid: '12345' }],
  can_unlink: true,
};

const SSO_STATUS_UNLINKED = {
  has_password: true,
  linked_providers: [],
  can_unlink: false,
};

const SSO_PROVIDERS_WITH_GOOGLE = {
  providers: [
    {
      id: 'google',
      name: 'Google',
      icon: 'google',
      auth_url: 'https://accounts.google.com/o/oauth2/auth',
    },
  ],
  sso_enabled: true,
  sso_required: false,
};

const SSO_PROVIDERS_EMPTY = {
  providers: [],
  sso_enabled: false,
  sso_required: false,
};

const QR_SETUP_DATA = {
  qr_code: 'data:image/png;base64,abc123',
  secret: 'TOTP_SECRET_KEY_ABCD',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

function setupDefaultMocks() {
  mockedApiGet.mockImplementation((url: string) => {
    if (url.includes('2fa/status')) return Promise.resolve({ data: TWOFA_DISABLED });
    if (url.includes('sso/status')) return Promise.resolve({ data: SSO_STATUS_UNLINKED });
    if (url.includes('sso/providers')) return Promise.resolve({ data: SSO_PROVIDERS_EMPTY });
    return Promise.resolve({ data: {} });
  });
}

function renderPage() {
  const queryClient = makeQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <SecuritySettings />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SecuritySettings — loading state', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('shows loading spinner while queries are pending', () => {
    // Never resolve so the component stays in loading state
    mockedApiGet.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /security settings/i })).not.toBeInTheDocument();
  });

  it('hides loading spinner once data has loaded', async () => {
    setupDefaultMocks();
    renderPage();
    await waitFor(() => {
      expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument();
    });
    expect(screen.getByRole('heading', { level: 1, name: /security settings/i })).toBeInTheDocument();
  });
});

describe('SecuritySettings — 2FA section headings and layout', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('renders the main "Security Settings" page heading', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: /security settings/i })).toBeInTheDocument();
    });
  });

  it('renders the "Two-Factor Authentication (2FA)" section heading', async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByRole('heading', { name: /two-factor authentication/i }),
      ).toBeInTheDocument();
    });
  });

  it('renders the "Single Sign-On (SSO)" section heading', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /single sign-on/i })).toBeInTheDocument();
    });
  });
});

describe('SecuritySettings — 2FA disabled state', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks(); // TWOFA_DISABLED by default
  });

  it('shows the descriptive text inviting the user to enable 2FA', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/add an extra layer of security/i)).toBeInTheDocument();
    });
  });

  it('shows the "Enable 2FA" button when 2FA is not enabled', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /enable 2fa/i })).toBeInTheDocument();
    });
  });

  it('does not show "Disable 2FA" button when 2FA is off', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /disable 2fa/i })).not.toBeInTheDocument();
    });
  });

  it('does not show "2FA is enabled" status text when disabled', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByText(/2fa is enabled/i)).not.toBeInTheDocument();
    });
  });
});

describe('SecuritySettings — 2FA enabled state', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApiGet.mockImplementation((url: string) => {
      if (url.includes('2fa/status')) return Promise.resolve({ data: TWOFA_ENABLED });
      if (url.includes('sso/status')) return Promise.resolve({ data: SSO_STATUS_UNLINKED });
      if (url.includes('sso/providers')) return Promise.resolve({ data: SSO_PROVIDERS_EMPTY });
      return Promise.resolve({ data: {} });
    });
  });

  it('shows "2FA is enabled" status text when 2FA is active', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/2fa is enabled/i)).toBeInTheDocument();
    });
  });

  it('shows backup codes remaining count', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/backup codes remaining: 8/i)).toBeInTheDocument();
    });
  });

  it('shows "Disable 2FA" button when 2FA is enabled and can_disable is true', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /disable 2fa/i })).toBeInTheDocument();
    });
  });

  it('does not show "Enable 2FA" button when 2FA is already on', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /enable 2fa/i })).not.toBeInTheDocument();
    });
  });
});

describe('SecuritySettings — 2FA required by org', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApiGet.mockImplementation((url: string) => {
      if (url.includes('2fa/status')) return Promise.resolve({ data: TWOFA_ENABLED_REQUIRED });
      if (url.includes('sso/status')) return Promise.resolve({ data: SSO_STATUS_UNLINKED });
      if (url.includes('sso/providers')) return Promise.resolve({ data: SSO_PROVIDERS_EMPTY });
      return Promise.resolve({ data: {} });
    });
  });

  it('shows the org-required warning message', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/your organization requires 2fa/i)).toBeInTheDocument();
    });
  });

  it('hides "Disable 2FA" button when can_disable is false', async () => {
    renderPage();
    await waitFor(() => {
      // 2FA is enabled, page content is present
      expect(screen.getByText(/2fa is enabled/i)).toBeInTheDocument();
    });
    // The "Disable 2FA" button must NOT be in the document because can_disable=false
    expect(screen.queryByRole('button', { name: /disable 2fa/i })).not.toBeInTheDocument();
  });
});

describe('SecuritySettings — Enable 2FA flow', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('clicking "Enable 2FA" calls api.post /users/auth/2fa/setup/', async () => {
    const user = userEvent.setup();
    mockedApiPost.mockResolvedValue({ data: QR_SETUP_DATA });

    renderPage();
    const enableBtn = await screen.findByRole('button', { name: /enable 2fa/i });
    await user.click(enableBtn);

    await waitFor(() => {
      expect(mockedApiPost).toHaveBeenCalledWith('/users/auth/2fa/setup/');
    });
  });

  it('shows QR code image after api.post /users/auth/2fa/setup/ succeeds', async () => {
    const user = userEvent.setup();
    mockedApiPost.mockResolvedValue({ data: QR_SETUP_DATA });

    renderPage();
    const enableBtn = await screen.findByRole('button', { name: /enable 2fa/i });
    await user.click(enableBtn);

    await waitFor(() => {
      expect(screen.getByAltText(/2fa qr code/i)).toBeInTheDocument();
    });
  });

  it('shows the secret key text after setup response', async () => {
    const user = userEvent.setup();
    mockedApiPost.mockResolvedValue({ data: QR_SETUP_DATA });

    renderPage();
    const enableBtn = await screen.findByRole('button', { name: /enable 2fa/i });
    await user.click(enableBtn);

    await waitFor(() => {
      expect(screen.getByText('TOTP_SECRET_KEY_ABCD')).toBeInTheDocument();
    });
  });

  it('shows a "Verify" button and 6-digit code input during scanning step', async () => {
    const user = userEvent.setup();
    mockedApiPost.mockResolvedValue({ data: QR_SETUP_DATA });

    renderPage();
    await user.click(await screen.findByRole('button', { name: /enable 2fa/i }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/enter 6-digit code/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /verify/i })).toBeInTheDocument();
    });
  });

  it('"Verify" button is disabled when code input is fewer than 6 digits', async () => {
    const user = userEvent.setup();
    mockedApiPost.mockResolvedValue({ data: QR_SETUP_DATA });

    renderPage();
    await user.click(await screen.findByRole('button', { name: /enable 2fa/i }));

    const codeInput = await screen.findByPlaceholderText(/enter 6-digit code/i);
    await user.type(codeInput, '123');

    expect(screen.getByRole('button', { name: /verify/i })).toBeDisabled();
  });

  it('clicking "Verify" with a 6-digit code calls api.post /users/auth/2fa/confirm/', async () => {
    const user = userEvent.setup();
    // First call: setup; second call: confirm
    mockedApiPost
      .mockResolvedValueOnce({ data: QR_SETUP_DATA })
      .mockResolvedValueOnce({ data: { backup_codes: ['aaa-bbb', 'ccc-ddd'] } });

    renderPage();
    await user.click(await screen.findByRole('button', { name: /enable 2fa/i }));

    const codeInput = await screen.findByPlaceholderText(/enter 6-digit code/i);
    await user.type(codeInput, '123456');
    await user.click(screen.getByRole('button', { name: /verify/i }));

    await waitFor(() => {
      expect(mockedApiPost).toHaveBeenCalledWith('/users/auth/2fa/confirm/', { code: '123456' });
    });
  });

  it('shows backup codes modal after confirm succeeds', async () => {
    const user = userEvent.setup();
    mockedApiPost
      .mockResolvedValueOnce({ data: QR_SETUP_DATA })
      .mockResolvedValueOnce({ data: { backup_codes: ['aaa-bbb', 'ccc-ddd'] } });

    renderPage();
    await user.click(await screen.findByRole('button', { name: /enable 2fa/i }));

    const codeInput = await screen.findByPlaceholderText(/enter 6-digit code/i);
    await user.type(codeInput, '123456');
    await user.click(screen.getByRole('button', { name: /verify/i }));

    await waitFor(() => {
      expect(screen.getByText(/save your backup codes/i)).toBeInTheDocument();
    });
    expect(screen.getByText('aaa-bbb')).toBeInTheDocument();
    expect(screen.getByText('ccc-ddd')).toBeInTheDocument();
  });

  it('clicking Cancel during scanning step returns to idle state', async () => {
    const user = userEvent.setup();
    mockedApiPost.mockResolvedValue({ data: QR_SETUP_DATA });

    renderPage();
    await user.click(await screen.findByRole('button', { name: /enable 2fa/i }));

    // Wait for scanning UI
    await screen.findByPlaceholderText(/enter 6-digit code/i);
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /enable 2fa/i })).toBeInTheDocument();
    });
  });
});

describe('SecuritySettings — Disable 2FA modal', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApiGet.mockImplementation((url: string) => {
      if (url.includes('2fa/status')) return Promise.resolve({ data: TWOFA_ENABLED });
      if (url.includes('sso/status')) return Promise.resolve({ data: SSO_STATUS_UNLINKED });
      if (url.includes('sso/providers')) return Promise.resolve({ data: SSO_PROVIDERS_EMPTY });
      return Promise.resolve({ data: {} });
    });
  });

  it('clicking "Disable 2FA" opens the confirmation modal', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /disable 2fa/i }));

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText(/disable two-factor authentication/i)).toBeInTheDocument();
  });

  it('modal contains an "Authenticator code" field', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /disable 2fa/i }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText(/authenticator code/i)).toBeInTheDocument();
  });

  it('modal contains a "Current password" field', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /disable 2fa/i }));

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByLabelText(/current password/i)).toBeInTheDocument();
  });

  it('clicking "Cancel" in the modal closes it', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /disable 2fa/i }));
    await screen.findByRole('dialog');

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('submitting the modal calls api.post /users/auth/2fa/disable/ with code and password', async () => {
    const user = userEvent.setup();
    mockedApiPost.mockResolvedValue({ data: {} });

    renderPage();
    await user.click(await screen.findByRole('button', { name: /disable 2fa/i }));

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/authenticator code/i), '654321');
    await user.type(within(dialog).getByLabelText(/current password/i), 'myS3cur3Pass!');
    await user.click(within(dialog).getByRole('button', { name: /disable 2fa/i }));

    await waitFor(() => {
      expect(mockedApiPost).toHaveBeenCalledWith('/users/auth/2fa/disable/', {
        code: '654321',
        password: 'myS3cur3Pass!',
      });
    });
  });

  it('modal closes after successful disable', async () => {
    const user = userEvent.setup();
    mockedApiPost.mockResolvedValue({ data: {} });

    renderPage();
    await user.click(await screen.findByRole('button', { name: /disable 2fa/i }));

    const dialog = await screen.findByRole('dialog');
    await user.type(within(dialog).getByLabelText(/authenticator code/i), '654321');
    await user.type(within(dialog).getByLabelText(/current password/i), 'myS3cur3Pass!');
    await user.click(within(dialog).getByRole('button', { name: /disable 2fa/i }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });

  it('shows a Zod validation error when code is not exactly 6 digits', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /disable 2fa/i }));
    const dialog = await screen.findByRole('dialog');

    await user.type(within(dialog).getByLabelText(/authenticator code/i), '123');
    await user.type(within(dialog).getByLabelText(/current password/i), 'anyPass');
    await user.click(within(dialog).getByRole('button', { name: /disable 2fa/i }));

    await waitFor(() => {
      expect(
        within(dialog).getByText(/enter the 6-digit code|code must be 6 digits/i),
      ).toBeInTheDocument();
    });
    // API must NOT have been called for an invalid submission
    expect(mockedApiPost).not.toHaveBeenCalled();
  });

  it('shows a validation error when password is empty', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /disable 2fa/i }));
    const dialog = await screen.findByRole('dialog');

    await user.type(within(dialog).getByLabelText(/authenticator code/i), '123456');
    // Leave password blank
    await user.click(within(dialog).getByRole('button', { name: /disable 2fa/i }));

    await waitFor(() => {
      expect(within(dialog).getByText(/password is required/i)).toBeInTheDocument();
    });
    expect(mockedApiPost).not.toHaveBeenCalled();
  });
});

describe('SecuritySettings — SSO section (no providers)', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks(); // SSO_PROVIDERS_EMPTY by default
  });

  it('shows "not enabled for your organization" message when no providers are configured', async () => {
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/single sign-on is not enabled for your organization/i),
      ).toBeInTheDocument();
    });
  });

  it('does not show a "Connect" button when no providers are available', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /connect/i })).not.toBeInTheDocument();
    });
  });
});

describe('SecuritySettings — SSO section (Google provider, unlinked)', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApiGet.mockImplementation((url: string) => {
      if (url.includes('2fa/status')) return Promise.resolve({ data: TWOFA_DISABLED });
      if (url.includes('sso/status')) return Promise.resolve({ data: SSO_STATUS_UNLINKED });
      if (url.includes('sso/providers')) return Promise.resolve({ data: SSO_PROVIDERS_WITH_GOOGLE });
      return Promise.resolve({ data: {} });
    });
  });

  it('shows the Google provider name', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Google')).toBeInTheDocument();
    });
  });

  it('shows a "Connect" button for the unlinked Google provider', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /connect/i })).toBeInTheDocument();
    });
  });

  it('does not show "Connected" status for an unlinked provider', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByText('Connected')).not.toBeInTheDocument();
    });
  });
});

describe('SecuritySettings — SSO section (Google provider, linked)', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApiGet.mockImplementation((url: string) => {
      if (url.includes('2fa/status')) return Promise.resolve({ data: TWOFA_DISABLED });
      if (url.includes('sso/status')) return Promise.resolve({ data: SSO_STATUS_LINKED });
      if (url.includes('sso/providers')) return Promise.resolve({ data: SSO_PROVIDERS_WITH_GOOGLE });
      return Promise.resolve({ data: {} });
    });
  });

  it('shows "Connected" status text for a linked provider', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeInTheDocument();
    });
  });

  it('shows an "Unlink" button when the provider is linked and can_unlink is true', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /unlink/i })).toBeInTheDocument();
    });
  });

  it('does not show "Connect" button when provider is already linked', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /connect/i })).not.toBeInTheDocument();
    });
  });

  it('calls /users/auth/sso/unlink/ with the provider id when the Unlink button is clicked', async () => {
    const user = userEvent.setup();
    mockedApiPost.mockResolvedValue({ data: {} });

    renderPage();

    const unlinkBtn = await screen.findByRole('button', { name: /unlink/i });
    await user.click(unlinkBtn);

    await waitFor(() => {
      expect(mockedApiPost).toHaveBeenCalledWith(
        '/users/auth/sso/unlink/',
        expect.objectContaining({ provider: 'google' }),
      );
    });
  });
});

describe('SecuritySettings — API calls', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  it('fetches 2FA status from /users/auth/2fa/status/ on mount', async () => {
    renderPage();
    await waitFor(() => {
      expect(mockedApiGet).toHaveBeenCalledWith('/users/auth/2fa/status/');
    });
  });

  it('fetches SSO status from /users/auth/sso/status/ on mount', async () => {
    renderPage();
    await waitFor(() => {
      expect(mockedApiGet).toHaveBeenCalledWith('/users/auth/sso/status/');
    });
  });

  it('fetches SSO providers from /users/auth/sso/providers/ on mount', async () => {
    renderPage();
    await waitFor(() => {
      expect(mockedApiGet).toHaveBeenCalledWith('/users/auth/sso/providers/');
    });
  });
});
