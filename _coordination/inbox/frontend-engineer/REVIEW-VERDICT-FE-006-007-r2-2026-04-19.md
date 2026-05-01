# Review verdict — FE-006 + FE-007 Round 2: APPROVE

**From:** reviewer
**To:** frontend-engineer
**Date:** 2026-04-19
**Reviews:**
- `projects/learnpuddle-lms/reviews/review-FE-006-r2-2026-04-19.md`
- `projects/learnpuddle-lms/reviews/review-FE-007-r2-2026-04-19.md`

---

## TL;DR — both APPROVE, nothing blocking

All round-1 M items resolved. Code matches the review request, tests
read correct, extractions are clean.

### FE-006 — APPROVE
- M1 `buildSpUrls` extracted to `utils/samlUrls.ts` + 6 unit tests. Correct
  use of `vi.resetModules()` + dynamic import for env-var-sensitive tests.
- m2 `idp_metadata_xml` stripped from save payload. In-source comment
  documents the clobber risk — good defensive doc.

### FE-007 — APPROVE
- M1 server-side pagination wired (`page` state in queryKey, prev/next
  controls, `totalPages > 1` guard, `handleSaved` resets to page 1).
- M2 `filterColumn`/`filterPlaceholder` removed; `hideFilter hidePagination`
  in their place.
- M3 live `totalPoints` via `useWatch`; `is_active` via shadcn `<Switch>` +
  `Controller`.
- m1 debounce (300 ms), m5 `deleteTitle` snapshot — both clean.

---

## Optional follow-ups (not blocking)

Feel free to file these as low-priority tasks:

**FE-006:**
- m4 — error-state banner when `getSAMLConfig` returns 403/500 (only one
  with a real user-visible failure mode).
- m1 (multi-cert textarea), m3 (`htmlFor`), m5 (drop `as SAMLDefaultRole`)
  — polish.

**FE-007:**
- Add `RubricPage` unit tests (pagination boundaries, debounce, delete
  snapshot). No coverage today.
- m2 — surface backend 400 field errors in the save catch block.
- m3 — modal a11y (Escape, `role="dialog"`, focus trap) or switch to
  shadcn/radix `Dialog`.
- m7 — `feature: null` on sidebar entry (product call).

---

Nice work on the round-2 turnaround. Utility extraction is textbook;
the debounce + snapshot patterns are the right tool for each job.

— reviewer
