---
tags: [review, task/FE-042, verdict/approve, reviewer/lp-reviewer, area/frontend, area/testing]
created: 2026-04-26
---

# Review: FE-042 — DirectoryPage test suite

## Verdict: APPROVE

## Summary

First test coverage for the Admin School Directory page — 25 tests across 8 describe blocks covering grade-band/grade/section visualisation, lazy expand, and client-side search. Test-only addition; no production code touched.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None blocking.

## Notes / verified

- File `frontend/src/pages/admin/DirectoryPage.test.tsx` present in tree (372 LOC).
- Reported: `tsc --noEmit` clean; `vitest run` 1020/1020 (25 new + 0 regressions).
- Lazy-query gating assertion (`getSectionStudents` / `getSectionTeachers` NOT called pre-expand, ARE called post-expand) is exactly the right "behaviour, not implementation" check — the test would still pass if the gating mechanism changes from `enabled: expanded` to a different React Query primitive, as long as the user-visible call timing is preserved.
- "Grade 5 in multiple cards" handled with `getAllByText('Grade 5').length >= 2` — fine; alternatively `getByRole('heading', { level: 3, name: 'Grade 5' })` could disambiguate by section heading, but the count assertion is simpler and conveys intent.
- `curriculum_framework` underscore replacement (`IB_PYP` → `IB PYP`) tested against rendered string, not raw API value — correct.

## Positive Observations

- "No class teacher assigned" fallback for null `class_teacher_name` explicitly tested — a fallback that easily silently regresses to blank.
- Search filter tested both by section name AND by teacher name — confirms the dual-search-field implementation isn't reduced to a single field.
- `<div onClick>` (not semantic `<button>`) noted in the request and tested via the visible label, not by trying to coerce role assertions. Honest about the markup. (Future polish: convert SectionCard root to a `<button>`/`role="button"` for keyboard a11y — separate ticket.)

## Follow-up suggestions (non-blocking)

- The `<div onClick>` pattern on SectionCard is an a11y gap (not keyboard-operable, not announced as interactive by screen readers). Worth filing a small ticket: convert to `<button>` or add `role="button" tabIndex={0}` + keyboard handler. Out of scope for FE-042 (test-only).

— lp-reviewer
