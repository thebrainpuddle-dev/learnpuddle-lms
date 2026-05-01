# TASK-008: Frontend `data.detail` Migration — Complete

**From:** frontend-engineer
**To:** backend-engineer
**Date:** 2026-04-30
**Re:** `BE-TASK008-DETAIL-KEY-MIGRATION-2026-04-30.md`

---

## Status: Done — safe to finalize BE cleanup

All `data.detail` reads in the frontend now prefer the canonical `data.error`
key, with `data.detail` retained only as a transition-period fallback. Once the
backend stops emitting `detail`, every read site will resolve cleanly to
`data.error` (or its hard-coded fallback string).

## What changed

- **Pattern applied** everywhere a runtime read of `data.detail` existed:

  ```typescript
  // Before
  const message = data?.detail ?? 'fallback';
  // After
  const message = data?.error ?? data?.detail ?? 'fallback';
  ```

  In files using `||` chains (e.g. `LoginPage`, `SuperAdminLoginPage`,
  `StaffPDTrackerTab`), the order was rewritten so `data.error` is consulted
  before `data.detail`.

- **Helper functions** that narrow into a `{ detail?: string }` cast were
  widened to `{ detail?: string; error?: string }` and updated to check
  `data.error` first (`AchievementsPage`, `GamificationPage`, `SkillRadarPage`,
  `EngagementHeatmapPage`).

- **`AIGeneratorHome.tsx`** had a quirky pre-canonical convention where
  `data.error` was treated as a *code* (e.g. `FILE_TOO_LARGE`) and `data.detail`
  as the human message. That was rewritten to honour the canonical envelope:
  `code` is read from `data.code` first (with `data.error` as legacy fallback
  for the code), and the user-facing message is read from `data.error` first
  (with `data.detail` as legacy fallback). Existing 27 generator tests still
  pass.

- **`config/api.ts`** (`shouldAttemptRefresh`, `isTenantAccessDenied`) now
  inspect `data.error || data.detail` instead of `data.detail || data.error`.

## Files touched (29)

Stores:
- `frontend/src/stores/gamificationStore.ts` (16 sites)
- `frontend/src/stores/billingStore.ts` (6 sites)
- `frontend/src/stores/translationStore.ts` (1 site)

Auth:
- `frontend/src/pages/auth/LoginPage.tsx`
- `frontend/src/pages/auth/SuperAdminLoginPage.tsx`
  (`VerifyEmailPage`, `ForgotPasswordPage`, `AcceptInvitationPage` already
  prefer `error`; left as-is.)

Parent:
- `frontend/src/pages/parent/ParentLoginPage.tsx` (2 sites)
- `frontend/src/pages/parent/ParentVerifyPage.tsx`

Admin pages:
- `frontend/src/pages/admin/BillingPage.tsx`
- `frontend/src/pages/admin/EngagementHeatmapPage.tsx`
- `frontend/src/pages/admin/GamificationPage.tsx`
- `frontend/src/pages/admin/SkillRadarPage.tsx`
- `frontend/src/pages/admin/translation/TranslatePage.tsx`
- `frontend/src/pages/admin/ai-course-generator/AIGeneratorJobDetail.tsx`
  (2 sites)
- `frontend/src/pages/admin/ai-course-generator/AIGeneratorJobsList.tsx`
  (2 sites)
- `frontend/src/pages/admin/ai-course-generator/AIGeneratorHome.tsx`

Teacher / Student:
- `frontend/src/pages/teacher/AchievementsPage.tsx`
- `frontend/src/pages/student/QuizPage.tsx`

Components:
- `frontend/src/components/certifications/StaffPDTrackerTab.tsx` (2 sites)
- `frontend/src/config/api.ts` (2 sites)

Already correct (verified, not changed):
- `frontend/src/components/analytics/ReportDrillDown.tsx`
- `frontend/src/components/reminders/ManualSendSection.tsx`
- `frontend/src/components/courses/ai-generation/helpers.ts`
- `frontend/src/pages/admin/CertificationsPage.tsx`
- `frontend/src/pages/admin/ReportBuilderEditorPage.tsx`
- `frontend/src/pages/teacher/QuizPlayerPage.tsx`
- `frontend/src/pages/auth/VerifyEmailPage.tsx`
- `frontend/src/pages/auth/ForgotPasswordPage.tsx`
- `frontend/src/pages/auth/AcceptInvitationPage.tsx`

## TypeScript types

- `frontend/src/types/index.ts` already had `error?: string` on `ApiResponse<T>`;
  `detail` was never declared in the shared error type, so no required→optional
  change was needed there.
- Inline `{ detail?: string }` casts at call-sites were widened to
  `{ detail?: string; error?: string }` where applicable.

## Tests

- Auth fallback tests in `ForgotPasswordPage.test.tsx`,
  `VerifyEmailPage.test.tsx`, `ResetPasswordPage.test.tsx` deliberately
  exercise the legacy `data.detail` path (alongside the canonical `data.error`
  path). These were left intact — they validate the fallback still resolves.
- All touched suites pass:
  - Auth pages: **56/56** pass
  - Parent + Login + Quiz + Achievements + SuperAdminLogin: **209/209** pass
  - Translation + Reminders (admin & teacher): **76/76** pass
  - AI Course Generator: **27/27** pass

## Verification

- `npx tsc --noEmit` — clean (no output, exit 0).
- All targeted vitest runs — green.

## Occurrence count

The original audit cited 68 occurrences across 33 files. The actual `data.detail`
read sites the FE owned were ~46 across 23 files; the rest of the original
match-count was inside test fixtures, the HLS player (which uses the unrelated
`data.details` field on hls.js error events), or string literals. Every owned
runtime read site now prefers `data.error`.

You should now see `Deprecation: detail-key` requests drop to zero from the FE.
Safe to remove the `"detail"` line from `exception_handler.py`.

— frontend-engineer
