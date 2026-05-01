---
tags: [review, task/FE-016, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: FE-016 — Full Mode Label Sweep

## Verdict: APPROVE

## Summary

Completes the work started in FE-015. Nine files correctly replace
hard-coded Education-mode strings with `label(key)` calls from
`useModeLabels()`, including two non-trivial refactors
(`GradebookPage.tsx`, `AssessmentGradebookPage.tsx`) where module-level
column definitions were converted to factory functions consumed via
`useMemo`. Type-safety preserved, no `any` introductions, test suites
adapt cleanly.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### m1 — `ModeLabelKey` value space not re-validated in sub-components

**Files**:
- `frontend/src/pages/admin/GradebookPage.tsx:134,207`
- `frontend/src/pages/admin/AssessmentGradebookPage.tsx:39`

Factory functions accept `lbl: (k: ModeLabelKey) => string` — good,
strongly typed. But I don't see a unit test that exercises
`makeCourseColumns(lbl)` / `makeAssignmentColumns(lbl)` / `makeColumns(lbl)`
with a mock `lbl` that returns distinguishing strings (e.g.
"COURSE_EDU" vs "COURSE_CORP"), which would prove the factory actually
wires the label through to the column header at runtime. The existing
tests use the real hook with default (Education) labels, so a
regression where the factory accidentally hardcodes `'Course'` after
accepting the `lbl` arg wouldn't be caught. Non-blocking — the runtime
behaviour is obviously correct from reading the code — but worth a
one-liner test per factory.

### m2 — Follow-up scope documented but not filed

The review request mentions three deferred items:

1. MAIC onboarding flow (`MAICCreatePage`, `MAICLibraryPage`)
2. `GamificationPage` `LeaderboardTab` chart/tab labels
3. Admin `DashboardPage.tsx` stat card "Courses"

These are real remaining hard-codes that *should* use `useModeLabels()`
when we enable Corporate mode for real tenants. Please file them as a
follow-up ticket (FE-017 or similar) rather than leaving them in a PR
comment — coordinator should track the sweep to completion.

## Positive Observations

- **All 9 files correctly wired**. Verified personally via grep:
  - `AchievementsPage.tsx` — `label('league')` (line 766), `label('streak')` (786)
  - `LeaguesPage.tsx` — `label('learner')` (131) inside `StandingsRow`
  - `DashboardPage.tsx` — `label('course')` (569)
  - `MyCoursesPage.tsx` — `label('course')` (247)
  - `GamificationPage.tsx` — `label('learner')`, `label('xp')`, `label('badge')` (lines 850, 979, 1240)
  - `GradebookPage.tsx` — factory pattern, `lbl('course')` (134), `lbl('assignment')` (207), `useMemo` deps correct (329-330)
  - `AssessmentGradebookPage.tsx` — factory pattern, `lbl('learner')` (39), `useMemo` dep correct (133)
  - `CoursesPage.tsx` — `label('course')` (531), `label('assignment')` (533)
  - `TeachersPage.tsx` — `label('learner_plural')` (217)
- **Factory-function pattern** for TanStack Table v8 columns is the TanStack-recommended idiom. Column defs stay declarative and easy to read; no JSX pollution of component bodies.
- **`useMemo([label], ...)` dependency arrays** are correct — the columns rebuild when the label function reference changes (i.e. when tenant mode flips), preserving referential stability otherwise.
- **`lbl` parameter naming** avoids shadowing object properties named `label` (e.g. `STATUS_COURSE[s].label`). Small detail, shows attention.
- **Valid `ModeLabelKey` values** — every call-site uses a key in the canonical union
  (`learner`, `learner_plural`, `course`, `course_plural`, `assignment`,
  `badge`, `league`, `streak`, `xp`, etc.). No typos, no string freedoms.
- **SuperAdmin exclusion is sound reasoning** — platform-wide pages don't have a tenant context, so they render EDUCATION_DEFAULTS regardless. Keeping them on hard-coded "Teachers"/"Schools" strings is consistent with the platform-level framing.
- **`useModeLabels.test.ts`** covers defaults, Education and Corporate modes, custom overrides, fallbacks, and reactivity — 9 tests, all passing.
- **Pre-existing App.test.tsx flake** confirmed pre-existing (mirrors FE-012/014 behaviour) — not introduced by this PR.
- **Test suite**: `vitest run` → 53 files / 433 tests passing (minus the one pre-existing flake). Targeted suites for modified pages pass cleanly.
- **`tsc --noEmit`** → 0 errors.

## Verification Notes

- Grep for `useModeLabels` in `CoursesPage.tsx` / `TeachersPage.tsx` returned matches at lines 7, 174, 531, 533 and 28, 63, 217 respectively — refuting an earlier false-negative from exploratory tooling. Both pages are correctly wired.
- Grep for remaining hard-coded "Teacher", "Course", "Assignment", "Badge", "League", "Streak", "XP" across the admin/teacher page tree turned up only (a) MAIC onboarding pages, (b) superadmin platform labels, and (c) the follow-up items the author already flagged.

## Ready to Merge

Yes.
