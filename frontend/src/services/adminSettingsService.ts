// src/services/adminSettingsService.ts
//
// Admin-only API clients for tenant password policy, SAML 2.0 SSO config,
// Education vs Corporate mode switching (FE-015 / TASK-020), and SCIM 2.0
// token management (FE-032 / TASK-023).
//
// Backend contracts:
//   GET  /users/admin/password-policy/         → TenantPasswordPolicy (GET, PATCH)
//   PATCH /users/admin/password-policy/        → TenantPasswordPolicy
//   GET   /users/admin/saml-config/            → TenantSAMLConfig (GET, PUT, PATCH)
//   PATCH /users/admin/saml-config/            → TenantSAMLConfig
//   GET   /tenants/settings/                   → TenantSettings (includes mode + mode_labels)
//   PATCH /tenants/settings/                   → accepts mode + mode_label_overrides
//   GET   /api/v1/admin/sso/scim-tokens/       → SCIMTokenListResponse
//   POST  /api/v1/admin/sso/scim-tokens/       → SCIMTokenCreated (token shown once)
//   DELETE /api/v1/admin/sso/scim-tokens/{id}/ → 204 No Content
//
// The SAML endpoints are gated behind `tenant.features['saml']` on the backend.
// The frontend should conditionally render the SAML section only when the feature
// is enabled (checked via `useTenantStore().features.saml`).
// SCIM token management is available to all tenant admins (no feature flag).

import api from '../config/api';
import type { TenantMode, ModeLabels } from '../stores/tenantStore';

// ── Password Policy ──────────────────────────────────────────────────────────

export interface PasswordPolicy {
  min_length: number;
  require_uppercase: boolean;
  require_lowercase: boolean;
  require_digit: boolean;
  require_special: boolean;
  prevent_common: boolean;
  prevent_reuse_last_n: number;
  max_age_days: number;
  lockout_threshold: number;
  lockout_duration_minutes: number;
  policy_rotated_at: string | null;
  updated_at: string;
}

export type PasswordPolicyPayload = Omit<PasswordPolicy, 'policy_rotated_at' | 'updated_at'>;

// ── SAML 2.0 SSO Configuration ───────────────────────────────────────────────

export type SAMLDefaultRole = 'TEACHER' | 'HOD' | 'IB_COORDINATOR' | 'SCHOOL_ADMIN' | 'STUDENT';

/**
 * Attribute mapping: SAML attribute URI → user model field.
 * Allowed keys (enforced server-side): email, first_name, last_name, groups, role.
 */
export type SAMLAttributeMapping = Partial<Record<
  'email' | 'first_name' | 'last_name' | 'groups' | 'role',
  string
>>;

export interface SAMLConfig {
  enabled: boolean;
  /** Full IdP metadata XML — pasting this auto-fills the fields below. */
  idp_metadata_xml: string;
  idp_entity_id: string;
  idp_sso_url: string;
  idp_slo_url: string;
  /** List of PEM-encoded IdP X.509 certificates extracted from metadata. */
  idp_x509_certs: string[];
  /** Read-only: this SP's entity ID (set by backend on first get_or_create). */
  sp_entity_id: string;
  /** Read-only: PEM-encoded SP signing certificate (blank when not configured). */
  sp_x509_cert: string;
  /** Whether a SP private key is configured (never exposed in responses). */
  sp_private_key_configured: boolean;
  attribute_mapping: SAMLAttributeMapping;
  auto_provision: boolean;
  default_role: SAMLDefaultRole;
  /** Comma-separated email domains; empty = allow any. */
  allowed_email_domains: string;
  updated_at: string;
}

export type SAMLConfigPayload = Partial<
  Pick<
    SAMLConfig,
    | 'enabled'
    | 'idp_metadata_xml'
    | 'idp_entity_id'
    | 'idp_sso_url'
    | 'idp_slo_url'
    | 'idp_x509_certs'
    | 'attribute_mapping'
    | 'auto_provision'
    | 'default_role'
    | 'allowed_email_domains'
  >
> & {
  /** Optional: upload SP private key PEM for signing AuthnRequests. */
  sp_private_key?: string;
};

// ── API surface ──────────────────────────────────────────────────────────────

export const adminSettingsService = {
  // ── Password Policy ───────────────────────────────────────────────────

  async getPasswordPolicy(): Promise<PasswordPolicy> {
    const res = await api.get('/users/admin/password-policy/');
    return res.data;
  },

  async updatePasswordPolicy(
    payload: Partial<PasswordPolicyPayload>,
  ): Promise<PasswordPolicy> {
    const res = await api.patch('/users/admin/password-policy/', payload);
    return res.data;
  },

  // ── SAML 2.0 Config ───────────────────────────────────────────────────

  /**
   * Fetch the current tenant's SAML config.
   * Requires `tenant.features['saml'] == True` — the backend returns 403
   * otherwise. The frontend should gate the UI on this feature flag.
   */
  async getSAMLConfig(): Promise<SAMLConfig> {
    const res = await api.get('/users/admin/saml-config/');
    return res.data;
  },

  /**
   * Update the SAML config (partial PATCH).
   *
   * If `idp_metadata_xml` is included, the backend auto-parses it and
   * overwrites `idp_entity_id`, `idp_sso_url`, `idp_slo_url`, and
   * `idp_x509_certs` — admins don't need to fill those fields manually.
   */
  async updateSAMLConfig(payload: SAMLConfigPayload): Promise<SAMLConfig> {
    const res = await api.patch('/users/admin/saml-config/', payload);
    return res.data;
  },

  // ── Education vs Corporate Mode (FE-015 / TASK-020) ──────────────────

  /**
   * Fetch the tenant's current mode and merged label map.
   *
   * Endpoint: `GET /tenants/settings/`
   * Requires: `@admin_only @tenant_required`
   *
   * Returns the full settings object; callers extract `mode`,
   * `mode_label_overrides`, and `mode_labels`.
   */
  async getModeSettings(): Promise<TenantModeSettings> {
    const res = await api.get('/tenants/settings/');
    return {
      mode: res.data.mode ?? 'education',
      mode_label_overrides: res.data.mode_label_overrides ?? {},
      mode_labels: res.data.mode_labels ?? {},
    };
  },

  /**
   * Update tenant mode and/or per-label overrides.
   *
   * Endpoint: `PATCH /tenants/settings/`
   * Requires: `@admin_only @tenant_required`
   *
   * `mode_label_overrides` is merged on top of the mode defaults by the
   * backend. Send `{}` to clear all overrides for the active mode.
   */
  async updateModeSettings(payload: TenantModePayload): Promise<TenantModeSettings> {
    const res = await api.patch('/tenants/settings/', payload);
    return {
      mode: res.data.mode ?? 'education',
      mode_label_overrides: res.data.mode_label_overrides ?? {},
      mode_labels: res.data.mode_labels ?? {},
    };
  },

  /**
   * Fetch mode labels for **any** authenticated user (not admin-only).
   *
   * Endpoint: `GET /tenants/me/`
   * Requires: `@tenant_required`
   *
   * Returns `mode` + `mode_labels` from the public tenant summary, which
   * is available to teachers and admins alike.
   */
  async getTenantModeForUser(): Promise<Pick<TenantModeSettings, 'mode' | 'mode_labels'>> {
    const res = await api.get('/tenants/me/');
    return {
      mode: res.data.mode ?? 'education',
      mode_labels: res.data.mode_labels ?? {},
    };
  },

  // ── SCIM 2.0 Token Management (FE-032 / TASK-023) ──────────────────────────

  /**
   * List all SCIM tokens for the current tenant (active + revoked).
   *
   * Endpoint: `GET /api/v1/admin/sso/scim-tokens/`
   * Requires: `@admin_only @tenant_required`
   */
  async listSCIMTokens(): Promise<SCIMTokenListResponse> {
    const res = await api.get('/admin/sso/scim-tokens/');
    return res.data;
  },

  /**
   * Generate a new SCIM bearer token for the current tenant.
   *
   * Endpoint: `POST /api/v1/admin/sso/scim-tokens/`
   * Requires: `@admin_only @tenant_required`
   *
   * The `token` field in the response is the raw bearer value and is returned
   * **once only** — store it immediately (present a copy-to-clipboard dialog).
   */
  async createSCIMToken(name: string): Promise<SCIMTokenCreated> {
    const res = await api.post('/admin/sso/scim-tokens/', { name });
    return res.data;
  },

  /**
   * Soft-revoke (deactivate) a SCIM token.
   *
   * Endpoint: `DELETE /api/v1/admin/sso/scim-tokens/{tokenId}/`
   * Requires: `@admin_only @tenant_required`
   *
   * The token row is retained for audit purposes with `is_active=False`.
   * Returns nothing on success (204 No Content).
   */
  async revokeSCIMToken(tokenId: string): Promise<void> {
    await api.delete(`/admin/sso/scim-tokens/${tokenId}/`);
  },
};

// ── Mode Settings Types ──────────────────────────────────────────────────────

/**
 * Subset of the `/tenants/settings/` response containing mode fields.
 * Full settings include branding, profile, etc. — only mode-related fields
 * are surfaced here to keep the service focused.
 */
export interface TenantModeSettings {
  /** Active mode: 'education' or 'corporate'. */
  mode: TenantMode;
  /**
   * Per-label overrides set by the admin (layered on top of mode defaults).
   * Partial — only overridden keys are present.
   */
  mode_label_overrides: Partial<ModeLabels>;
  /**
   * Merged label map (mode defaults + overrides) — the source of truth for
   * display strings. Matches `ModeLabels` shape but typed as
   * `Record<string, string>` since the backend may add future keys.
   */
  mode_labels: Record<string, string>;
}

export type TenantModePayload = Partial<Pick<TenantModeSettings, 'mode' | 'mode_label_overrides'>>;

// ── SCIM 2.0 Token Management (FE-032 / TASK-023) ───────────────────────────

/**
 * Summary of a SCIM bearer token (list items).
 *
 * The raw token value is never included in list responses — it is returned
 * once on creation (POST) and cannot be retrieved afterwards.
 */
export interface SCIMTokenSummary {
  id: string;
  name: string;
  created_at: string;
  /** ISO-8601 datetime of last use, or null if never used. */
  last_used_at: string | null;
  /** False once the token has been revoked. */
  is_active: boolean;
}

/**
 * Response body returned by POST /api/v1/admin/sso/scim-tokens/.
 *
 * `token` is the raw bearer token — show it to the admin once (copy-to-clipboard)
 * and discard. It is stored as a SHA-256 hash on the backend and cannot be
 * recovered afterwards.
 */
export interface SCIMTokenCreated {
  id: string;
  name: string;
  /** Raw bearer token — shown ONCE; cannot be recovered after this response. */
  token: string;
  created_at: string;
  is_active: boolean;
}

export interface SCIMTokenListResponse {
  count: number;
  results: SCIMTokenSummary[];
}
