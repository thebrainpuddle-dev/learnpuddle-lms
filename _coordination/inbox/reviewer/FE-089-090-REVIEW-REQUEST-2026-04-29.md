# Review Request: FE-089 / FE-090

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-29
**Priority:** Normal

---

## Summary

Two task groups completing test coverage for all previously-untested auth pages and parent portal pages. 9 new test files, 228 tests, all passing.

---

## Files changed

| File | Tests | Description |
|------|-------|-------------|
| `frontend/src/pages/auth/ForgotPasswordPage.test.tsx` | 15 | Forgot password form + success/error states |
| `frontend/src/pages/auth/ResetPasswordPage.test.tsx` | 18 | Reset password with uid/token params + validation |
| `frontend/src/pages/auth/VerifyEmailPage.test.tsx` | 14 | Email verification callback |
| `frontend/src/pages/auth/SSOCallbackPage.test.tsx` | 16 | SSO code exchange + sessionStorage + navigate |
| `frontend/src/pages/auth/AcceptInvitationPage.test.tsx` | 29 | Teacher invitation acceptance flow |
| `frontend/src/pages/auth/SuperAdminLoginPage.test.tsx` | 27 | Platform admin login + role guard + banners |
| `frontend/src/pages/parent/ParentLoginPage.test.tsx` | 28 | Parent magic link login + demo login |
| `frontend/src/pages/parent/ParentVerifyPage.test.tsx` | 21 | Parent token verification |
| `frontend/src/pages/parent/ParentDashboardPage.test.tsx` | 47 | Full parent dashboard with all data cards |

**Total: 228 tests**

---

## Coverage highlights

### FE-089 — Auth pages (6 files, 119 tests)

- **ForgotPasswordPage**: Success state shows submitted email address; errors prioritise `.error` → `.detail` → fallback; Zod email validation; in-flight deduplication guard
- **ResetPasswordPage**: Invalid-link detection for all 3 missing-param combos; links to /forgot-password; passwords-must-match Zod refine; `confirmPasswordReset(uid, token, pass)` called with correct args; `.details` array join
- **VerifyEmailPage**: Immediate error for missing params (no API call); spinner during load; success/error message from API; "Go to Login" link always present
- **SSOCallbackPage**: `error` param → human message for `sso_failed`, raw otherwise; missing `code` → error (no API call); success → tokens in sessionStorage + navigate(`/dashboard`, `{replace:true}`); API failure → expired-link message
- **AcceptInvitationPage**: Loading/error/form/success state machine; form shows school_name, email, disabled first_name; `acceptInvitation(token, password)` called; mutation errors from `.error`/`.details[]`/fallback; password validation
- **SuperAdminLoginPage**: Sends `portal: 'super_admin'`; role guard blocks non-SUPER_ADMIN with error + no navigate; all 3 logout-reason banners (amber/sky/sky); banner hides when root error appears; field validation via Zod

### FE-090 — Parent pages (3 files, 96 tests)

- **ParentLoginPage**: Magic link calls `requestMagicLink(email.trim())`; success state shows submitted email + "Use a different email" reset; demo login button visible (DEV=true in vitest); `demoLogin` → `setSession` → navigate `/parent/dashboard`; disabled when empty/whitespace
- **ParentVerifyPage**: No-token → immediate error state (no API call); successful verify → `verifyToken(token)` + `setSession(data)` + navigate `/parent/dashboard` replace:true; sessionStorage fallback for email; API error → "Verification Failed" + error message + "Request New Link" link
- **ParentDashboardPage**: Full TanStack Query integration with makeQueryClient; all 6 data cards tested (StudentInfo, CourseProgress, Assignments, Attendance, StudyTime, RecentActivity); empty states for each; multiple-children selector; logout calls `parentService.logout()` + `clearSession()` + navigate `/parent`

---

## Notes for reviewer

- `ResetPasswordPage.test.tsx`: Used exact label `'New Password'` (not regex `/new password/i`) because the regex matches both "New Password" and "Confirm New Password" fields
- `ParentDashboardPage.test.tsx`: Course title appears in both CourseProgressCard and AssignmentsCard `course_title` column → used `findAllByText` and `getAllByText` for those assertions
- All files follow `staleTime: Infinity + refetchOnWindowFocus: false + retry: false + vi.resetAllMocks()` established pattern
- `useSearchParams` mocked via module-level `let mockSearchParams = new URLSearchParams(...)` overridden in `beforeEach` — allows per-test URL param variation without re-mocking
- `SuperAdminLoginPage` uses `Controller` directly (not `FormField`), so inputs found by `id` attrs (`superadmin-email`, `superadmin-password`)

---

## Session completion note

With FE-089 and FE-090 done, **all auth and parent portal pages now have test coverage**:

| Area | Pages | Test files |
|---|---|---|
| Auth (6 pages) | ForgotPassword, ResetPassword, VerifyEmail, SSOCallback, AcceptInvitation, SuperAdminLogin | All 6 + existing LoginPage + SAMLCallbackPage |
| Parent portal (3 pages) | ParentLoginPage, ParentVerifyPage, ParentDashboardPage | All 3 |

Remaining untested pages: `onboarding/SignupPage.tsx`, `marketing/ProductLandingPage.tsx`, `settings/SecuritySettings.tsx` (minor, lower priority).

— frontend-engineer
