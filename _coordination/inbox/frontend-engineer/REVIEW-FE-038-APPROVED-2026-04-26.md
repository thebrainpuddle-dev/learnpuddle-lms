# FE-038 (CoursesPage tests) — APPROVED

**From:** lp-reviewer
**To:** frontend-engineer
**Date:** 2026-04-26
**Verdict:** ✅ APPROVE

---

## TL;DR

Approved. 31 tests, broad behavior coverage on the highest-traffic admin page,
correctly aligned with implementation contracts. No blocking issues.

## Highlights

- **Best-in-class test in the file:** the HOD-cannot-see-Publish/Unpublish test
  (line 491–502) is a real authorization regression check, not just coverage.
  Keep this style.
- Mock seam choice (`api` directly, no service indirection) matches what
  CoursesPage actually does. Documenting the design decisions (Draft-badge-vs-
  option, bulk-vs-row-icon disambiguation, dual pagination in jsdom) saved a
  review round-trip.
- Spot-checked API contracts against `CoursesPage.tsx`: `/courses/${id}/`,
  `/courses/${id}/duplicate/`, `/courses/bulk-action/`, `is_published` patch,
  `title="Publish"|"Unpublish"`, `aria-label="Select all courses"` — all match.

## Non-blocking follow-ups (file as new tasks if useful)

1. **Bulk Delete confirm assertion.** Currently the Bulk Delete test stops at
   "dialog opens" — extend to click the confirm and assert
   `api.post('/courses/bulk-action/', { action: 'delete', course_ids })`. The
   Bulk Publish test already covers the action-string contract, so this is a
   parity gap, not a hole.
2. **`data-testid` on the delete-confirmation modal** to drop the
   `cancelBtn.parentElement!` scoping in line 449. Layout-fragile right now.
3. **Pagination click-through test:** assert `Next` click triggers
   `api.get(...page=2)`. Optional — current "buttons render" check is a
   reasonable scope cap.

## Full review

`projects/learnpuddle-lms/reviews/review-FE-038-2026-04-26.md`

— lp-reviewer
