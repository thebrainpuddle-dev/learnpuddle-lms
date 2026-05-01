# Review Request — FE-006 SAML SSO Configuration UI + SecuritySection Overhaul

**From**: frontend-engineer
**To**: reviewer
**Date**: 2026-04-19
**Phase**: Phase 3 — Enterprise Auth SSO Polish

## What changed

### `frontend/src/stores/tenantStore.ts`
- Added `saml`, `sso`, `2fa`, `students` to `TenantFeatures` interface + `DEFAULT_FEATURES`
- Maps to backend `tenant.features` dict (backed by `feature_saml`, `feature_sso`, `feature_2fa`, `feature_students` BooleanFields on `Tenant` model)

### `frontend/src/services/adminSettingsService.ts` (new file)
- `getPasswordPolicy()` / `updatePasswordPolicy()` → `GET/PATCH /users/admin/password-policy/`
- `getSAMLConfig()` / `updateSAMLConfig()` → `GET/PATCH /users/admin/saml-config/`
- Types `PasswordPolicy`, `SAMLConfig`, `SAMLConfigPayload` aligned with backend serializers in `password_policy_views.py`

### `frontend/src/pages/admin/SettingsPage.tsx`
Overhauled the Security tab with three independent sub-cards:

| Card | API | Notes |
|------|-----|-------|
| `PasswordPolicyCard` | `GET/PATCH /users/admin/password-policy/` | RHF + Zod; 10 policy fields |
| `TwoFactorSessionCard` | `GET/PATCH /tenants/settings/security/` (legacy) | Auto-saves on change |
| `SAMLSSOCard` | `GET/PATCH /users/admin/saml-config/` | Feature-gated on `features.saml` |

**SAMLSSOCard** highlights:
- SP metadata panel with copy buttons (SP Entity ID, ACS URL, SLS URL, Metadata URL)
- Paste-and-parse IdP metadata XML → auto-fills entity_id, sso_url, slo_url, certs
- Manual fallback fields for all IdP settings
- Provisioning settings: auto_provision toggle, default_role, allowed_email_domains
- Collapsible attribute mapping section with Azure AD/Okta defaults pre-filled
- SAML attribute URI → user field mapping for email, first_name, last_name, groups, role

## Test results

```
npx tsc --noEmit  → 0 errors
npx vitest run    → Test Files 33 passed (33) / Tests 246 passed (246)
```

## Checklist

- [x] TypeScript strict — 0 errors
- [x] Tests green — 246/246
- [x] Uses RHF + Zod (not raw `useState`) for all form state
- [x] Feature-gated: SAML card only renders when `useTenantStore().features.saml === true`
- [x] No `alert()` calls — uses `useToast()` throughout
- [x] No `console.log` debug statements
- [x] Heroicons (no emoji icons)
- [x] `cursor-pointer` on all interactive elements
- [x] Backend contracts verified against `password_policy_views.py` and `saml_models.py`
- [x] SP URLs built from `theme.subdomain` — correct subdomain-scoped ACS/SLS paths

— frontend-engineer

## Processed 2026-04-19

Round 1 reviewed at
`projects/learnpuddle-lms/reviews/review-FE-006-2026-04-19.md` (08:06) —
REQUEST_CHANGES. Round 2 fixes APPROVED at
`projects/learnpuddle-lms/reviews/review-FE-006-r2-2026-04-19.md`.
Closing out of queue.
