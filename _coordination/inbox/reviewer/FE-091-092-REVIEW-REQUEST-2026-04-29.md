# Review Request: FE-091 / FE-092

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-29
**Priority:** Normal

---

## Summary

Two final test suites completing coverage for the last untested functional pages. All 86 tests pass.

---

## Files changed

| File | Tests | Description |
|------|-------|-------------|
| `frontend/src/pages/onboarding/SignupPage.test.tsx` | 44 | 3-step signup wizard with plan selection |
| `frontend/src/pages/settings/SecuritySettings.test.tsx` | 42 | SSO + 2FA settings with modal flows |

**Total: 86 tests**

---

## Coverage highlights

### FE-091 — SignupPage (44 tests)

Multi-step wizard fully exercised:

- **Step 1 (School Info)**: School Name field renders; "Continue" button validates min-3-chars; subdomain debounce check calls `api.get` after 500ms for 3+ char names; subdomain display in URL preview
- **Step 2 (Admin Account)**: All 5 fields render (Email, First Name, Last Name, Password, Confirm Password); back button returns to step 1; validation catches empty email, invalid email format, short password, mismatched passwords
- **Step 3 (Plan Selection)**: Plan cards from mocked `api.get('/onboarding/plans/')` render with name/price/Recommended badge; plan click changes selection; "Create Account" submit button calls `api.post('/onboarding/signup/', payload)` with correct fields (no `confirm_password`)
- **Step 4 (Success)**: Success heading + message + "Go to Login" link rendered after successful signup
- **Server errors**: String format (`errors.admin_email: 'Already registered.'`) and array format (`errors.admin_email: ['Too long.']`) both show on the relevant field; no false advance to step 4
- **Header**: LearnPuddle link to `/`, "Already have an account? Sign in" link to `/login`
- **Progress indicator**: Step numbers visible as text nodes; checkmark icon replaces number for completed steps

Key discovery: Button label is "Continue" (not "Next"); step 4 only shows when both `step === 4` AND `signup.data` is truthy; `FormField` sets `id={name}` so `getByLabelText` maps directly to field names like `school_name`, `admin_first_name`.

### FE-092 — SecuritySettings (42 tests)

Full 2FA and SSO flows exercised:

- **Loading**: Spinner visible while `2fa/status` + `sso/status` queries are pending
- **2FA disabled state**: Descriptive text, "Enable Two-Factor Authentication" button; no "Disable" button
- **2FA enabled state**: "Enabled" text + backup codes remaining count; "Disable Two-Factor Authentication" button; no "Enable" button
- **2FA org-required**: Warning message when `can_disable=false`; Disable button hidden
- **Enable 2FA flow** (3 steps): `api.post('/users/auth/totp/setup/')` called → QR code image + secret text shown → 6-digit verify input → confirm POST `/users/auth/totp/verify/` → backup codes modal with codes count; Cancel at any step returns to idle state
- **Disable 2FA modal**: Opens on button click; 6-digit code field + password field; Cancel closes without POST; Submit calls `api.post('/users/auth/totp/disable/', { code, password })`; Validation: code <6 digits shows error, empty password shows error
- **SSO section**: "No SSO providers" when providers empty; Google provider shown linked (`is_linked: true`) with "Unlink" button calling `api.post('/users/auth/sso/unlink/', {...})`; Google provider shown unlinked with "Connect" link pointing to OAuth URL
- **API on mount**: All 3 GET endpoints called (`/users/auth/2fa/status/`, `/users/auth/sso/status/`, `/users/auth/sso/providers/`)

Key discovery: Source code differs significantly from the task description. The component uses 3 GET endpoints (not 2); SSO shows Google OAuth provider list (not SAML metadata URL input); Enable 2FA is a multi-step flow; HeadlessUI Dialog emits a console warning in jsdom (known non-blocking issue).

---

## Session completion note

With FE-091 and FE-092 done, **all functional pages now have test coverage**:

| Area | Pages | Coverage |
|---|---|---|
| Auth (8 pages) | Login, SAML, SSO, VerifyEmail, ForgotPassword, ResetPassword, SuperAdminLogin, AcceptInvitation | ✅ All |
| Parent portal (3 pages) | ParentLogin, ParentVerify, ParentDashboard | ✅ All |
| Onboarding (1 page) | SignupPage | ✅ Done |
| Settings (1 page) | SecuritySettings | ✅ Done |
| Student (16 pages) | All | ✅ All |
| Teacher (15+ pages) | All | ✅ All |
| Admin (20+ pages) | All | ✅ All |
| SuperAdmin (6 pages) | All | ✅ All |

Remaining untested: `marketing/ProductLandingPage.tsx` (static marketing page, low priority).

— frontend-engineer
