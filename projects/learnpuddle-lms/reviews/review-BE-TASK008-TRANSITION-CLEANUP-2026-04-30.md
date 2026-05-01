---
tags: [review, task/TASK-008, task/TASK-012, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: BE-TASK008 Transition Cleanup — Remove legacy `"detail"` key

## Verdict: REQUEST_CHANGES

## Summary

The diff itself is clean and minimal — 5 lines removed from `custom_exception_handler`,
6 tests inverted to assert `"detail"` is absent, docstrings updated. The TDD direction
is right and the code change is exactly what TASK-008's transition note prescribed.

**The premise of the cleanup is wrong, however.** The request claims "TASK-012
frontend cleanup is confirmed done" and points at
`docs/coordination/TASK-012-frontend-cleanup.md`. That document is **not** about
removing reads of `data.detail` from the frontend — its scope is `console.log`
removal, sonner/Toast wiring, and RHF+Zod migration. There has been no FE pass to
remove the legacy `data.detail` reads.

A static audit shows the regression surface this would create today:

```
$ rg --type ts --type tsx 'data\.detail|\.response\?\.data\?\.detail' frontend/src | wc -l
68 occurrences across 33 files
```

Of those, **most auth pages have `data.error` later in the fallback chain and will
keep working** (LoginPage, SuperAdminLoginPage, ResetPasswordPage, VerifyEmailPage,
ForgotPasswordPage all read `error || detail || …` or similar). But a meaningful
slice reads `data.detail` as the **only** server source before falling through to
a hard-coded generic string. Those will silently lose the real server message
the moment backend stops emitting `"detail"`. Examples (verified by reading the
files):

| File | Pattern | What the user sees after this PR |
|------|---------|----------------------------------|
| `frontend/src/stores/billingStore.ts` (×6) | `err?.response?.data?.detail ?? err.message ?? 'Failed to fetch plans'` | Always the hard-coded fallback (axios `err.message` is `"Request failed with status code 400"`) |
| `frontend/src/stores/gamificationStore.ts` (×16) | same shape | same — every gamification config / badge / leaderboard error degrades to a generic string |
| `frontend/src/pages/admin/BillingPage.tsx` | `err?.response?.data?.detail ?? err.message ?? 'Failed to initiate payment.'` | Stripe error reasons disappear from the payment flow |
| `frontend/src/stores/translationStore.ts` | `err?.response?.data?.detail ?? 'Please try again.'` | Translation errors lose context |
| `frontend/src/pages/teacher/AchievementsPage.tsx` | `if (data?.detail) return data.detail;` | Server message dropped, falls through to default |
| `frontend/src/pages/admin/SkillRadarPage.tsx`, `EngagementHeatmapPage.tsx`, `GamificationPage.tsx` | `if (data?.detail) return data.detail;` | Same |
| `frontend/src/pages/admin/ai-course-generator/AIGeneratorJobDetail.tsx`, `AIGeneratorJobsList.tsx`, `AIGeneratorHome.tsx`, `TranslatePage.tsx` | `err?.response?.data?.detail ?? 'Please try again.'` | Generation/translate error reasons gone |
| `frontend/src/components/student/StudySummaryPanel.tsx` | `body.detail || body.error` (line 183) | Reads `detail` first; falls through to `error` — **safe**, but the dependency on `detail` is still there |

(There are several others — `ManualSendSection`, `StaffPDTrackerTab`, `ReportDrillDown`,
`ParentVerifyPage`, `ReportBuilderEditorPage`, `ChatbotChat` — all in the same
"detail-only or detail-first" pattern.)

The safe fallbacks in the auth flow are not representative of the rest of the app.
For paid-product surfaces (billing, gamification, AI course generator), this PR
turns specific server-driven error messages into generic strings, which is a real
UX regression for both teachers and admins.

## Critical Issues

### C1 — Premise is incorrect: TASK-012 did not remove FE `data.detail` reads

`docs/coordination/TASK-012-frontend-cleanup.md` (Status: done) is scoped to
console.log / Toast / RHF — not the legacy `detail` key. The TASK-008 note
("after TASK-012 the frontend cleanup pass lands") was written before TASK-012
was scoped. There is no completed FE pass that migrated `data.detail` reads to
`data.error`.

**Required fix — pick one:**

(a) **Recommended — do the FE cleanup first.** Open a frontend follow-up that
    rewrites every `data.detail` read to read `data.error` (preferring `error`
    over `detail`, with `detail` as a transitional fallback for one release). Then
    land this BE cleanup. Concretely the FE work is mechanical for stores
    (`billingStore`, `gamificationStore`, `translationStore`) and pages listed
    above — replace `data?.detail` with `data?.error ?? data?.detail` (one-line
    change per call site, ~30 sites).

(b) **Or — keep `detail` emitting in the handler for one more release** with a
    deprecation warning header (`Deprecation: detail-key`) so we get a signal
    when the FE stops needing it. Then land the cleanup once telemetry is quiet.

(c) **Or — narrow this PR.** Remove `detail` only from the paths whose FE
    consumers all read `error` first (the auth `{"detail": ...}` system errors).
    Keep `detail` for the validation-error branches where stores still rely on
    it. This is the smallest "safe slice" but it bifurcates the canonical shape,
    so I'd avoid it unless the team really wants to ship a partial cleanup now.

### C2 — Acceptance criterion #6 in TASK-008 is not yet met

TASK-008's own checklist
(`docs/coordination/TASK-008-error-response-standardization.md`) says:

> - [ ] No regression in error display on any page (pending TASK-012 full FE audit)

That box is still unchecked, and a "full FE audit" didn't happen as part of
TASK-012. Removing the legacy key without that audit is what this review is
flagging.

## Major Issues

None — once the premise is fixed, the diff itself is correct.

## Minor Issues

### M1 — Test naming consistency

After the rename, tests read `test_..._no_legacy_detail_key`. Three of them
(`test_only_error_key_present_not_detail`, `test_field_validation_no_legacy_detail_key`,
`test_list_form_validation_no_legacy_detail_key`) are essentially the same shape
("`detail` not in data"). Worth collapsing to a single parametrised test once this
reland's, but not required.

### M2 — Module docstrings still say "TASK-012 cleanup is done"

If you take path (a) or (b) above, the docstrings updated in this PR will need a
small word-tweak ("TASK-012-FE legacy `detail` reads removed" rather than just
"TASK-012 cleanup complete") so future readers don't conflate this with the
unrelated TASK-012 console.log/RHF work.

## Positive Observations

- TDD is exemplary: every assertion is inverted to prove the legacy key is gone,
  not just absent-by-omission. `assert "detail" not in data` is the right
  assertion shape.
- The diff is exactly 5 production lines + the docstring — zero collateral
  changes, zero behavior drift in the code that remains.
- All four shape branches of `custom_exception_handler` (Case 1, 1b, 2, 3, 4)
  are touched symmetrically. No branch was missed.
- Renames are paired (one rename per old test) so git blame stays clean and the
  intent of each test is preserved.
- The note that TASK-012 must complete *before* this lands was respected — the
  author did look for the doc and check its status. The miss is that the doc
  matched on name only, not scope.

## Verification I performed

- Read full diff of `backend/utils/exception_handler.py` and
  `backend/tests/test_exception_handler.py`.
- Read `docs/coordination/TASK-012-frontend-cleanup.md` end-to-end. Scope is
  console.log / Toast / RHF; no `detail` key migration.
- Read `docs/coordination/TASK-008-error-response-standardization.md`. Confirmed
  AC6 ("No regression in error display on any page") is still unchecked and
  pending the FE audit.
- Static scan: 68 `data.detail` reads across 33 frontend files
  (`rg 'data\.detail|\.response\?\.data\?\.detail' frontend/src`).
- Spot-read of the highest-traffic call sites: auth pages are safe (have
  `error` fallback); `billingStore`/`gamificationStore`/admin AI pages are not.

— lp-reviewer
