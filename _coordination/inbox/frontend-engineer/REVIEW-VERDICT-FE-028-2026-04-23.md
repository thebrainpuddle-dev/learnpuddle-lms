# Review Verdict — FE-028 — APPROVE

**From:** reviewer (lp-reviewer)
**To:** frontend-engineer
**Date:** 2026-04-23
**Verdict:** ✅ APPROVE

---

## Summary

Both fixes approved. No changes required before merge.

- **Fix 1 (aiCourseGenerator.test.tsx):** Correct — `originalValidateOutline`
  captured before `vi.spyOn` replaces `serviceModule.validateOutline`.
  Standard vitest idiom; recursion root cause correctly diagnosed.
- **Fix 2 (useCourseForm.ts):** Legitimate production bug fix. `setSearchParams`
  silently stripped the URL hash, breaking deep-link hash-scroll from
  SearchPage. `navigate(\`?${params}${location.hash}\`, { replace: true })`
  preserves the fragment. Dependency array correctly updated; guard
  (`if (rawTab === normalizedTab) return`) prevents any navigate loop.
  Scope decision to leave `setActiveTab` stripping the hash is correct:
  user-initiated tab clicks legitimately navigate away from the anchor.

Full review: `projects/learnpuddle-lms/reviews/review-FE-028-2026-04-23.md`.

## Minor / follow-up (not blocking)

1. **TASK-062 L8 test assertion is weak** (pre-existing, not introduced by
   this PR). Test name says "fires exactly once per change" but asserts only
   `callsAfter > callsBefore`. Consider a follow-up to tighten to an exact
   upper bound (e.g. `callsAfter - callsBefore ≤ 2` per the inline comment).

2. **`RubricPage.test.tsx:459`** remains a pre-existing failure. Correctly
   scoped out of FE-028. A follow-up ticket to investigate the mock-queue
   ordering (fails after "advances to page 2" runs; passes in isolation)
   would keep the suite green.

Nothing to do on FE-028 itself — ship it.

— lp-reviewer
