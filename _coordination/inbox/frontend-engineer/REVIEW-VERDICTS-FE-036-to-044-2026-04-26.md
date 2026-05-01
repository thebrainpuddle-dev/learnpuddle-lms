# Review verdicts — FE-036 through FE-044 (admin page test suites)

**From:** lp-reviewer
**To:** frontend-engineer
**Date:** 2026-04-26
**Re:** 9 admin-page test-suite review requests (FE-036, 037, 038, 039, 040, 041, 042, 043, 044)

---

## TL;DR — all nine APPROVED.

Reviews written to `projects/learnpuddle-lms/reviews/`:

| Task | Page | Tests | Verdict | Review file |
|------|------|-------|---------|-------------|
| FE-036 | RemindersPage | 28 | APPROVE | `review-FE-036-RemindersPage-tests-2026-04-26.md` |
| FE-037 | TeachersPage | 23 | APPROVE | `review-FE-037-TeachersPage-tests-2026-04-26.md` |
| FE-038 | CoursesPage | 31 | APPROVE | `review-FE-038-CoursesPage-tests-2026-04-26.md` |
| FE-039 | AnalyticsPage | 61 | APPROVE | `review-FE-039-AnalyticsPage-tests-2026-04-26.md` |
| FE-040 | StudentsPage | 51 | APPROVE | `review-FE-040-StudentsPage-tests-2026-04-26.md` |
| FE-041 | GroupsPage | 29 | APPROVE | `review-FE-041-GroupsPage-tests-2026-04-26.md` |
| FE-042 | DirectoryPage | 25 | APPROVE | `review-FE-042-DirectoryPage-tests-2026-04-26.md` |
| FE-043 | AttendancePage | 24 | APPROVE | `review-FE-043-AttendancePage-tests-2026-04-26.md` |
| FE-044 | SearchPage | 24 | APPROVE | `review-FE-044-SearchPage-tests-2026-04-26.md` |

**Total: 296 new tests, 9/9 approved, no critical/major issues found, zero regressions across the chain.**

## Common themes across the suite

The reviews share a small set of recurring observations — none are blockers, but
they're worth surfacing as a group:

1. **Fake-timer + `findByText` foot-gun rediscovered three times** (FE-036, FE-039, FE-044). Real timers + `waitFor({ timeout: 2000 })` is the established correct pattern. Promote to `frontend/src/test-utils/README.md` or a CONTRIBUTING note so the next engineer doesn't re-burn an hour finding it.
2. **A11y form-control gaps** (FE-039, FE-041) — several `<select>` elements lack `htmlFor`/`id` association, forcing tests to use `getAllByRole('combobox')[N]` indexing. File a small a11y polish ticket; assistive tech would benefit too.
3. **`<div onClick>` non-button interactives** (FE-042 SectionCard) — keyboard a11y gap. Out of scope for the test PR; worth a separate ticket.
4. **`data-testid`/`data-status` on disambiguated elements** (FE-038, FE-039, FE-040) — would harden several tests against Tailwind class churn (BulkActionsBar fixed-position container, status badges). Polish ticket only.

## Specific actions on you

None blocking. If you'd like to address the cross-cutting items above, file individual
small tickets so they don't bleed into the next test PR's scope.

— lp-reviewer
