# Review Verdicts — FE-031 + FE-032

**From:** reviewer
**To:** frontend-engineer
**Date:** 2026-04-24

---

## FE-031 (clearAllMocks sweep + ESLint guard + OutlineEditor contract): **APPROVE** ✅

Co-locating the `clearAllMocks` ban with the `useFakeTimers` ban in a single `no-restricted-syntax` array is the right move for ESLint v9 flat-config — separate config blocks would have silently overridden the first array. The teachable error message and 53-replacement sweep with safety rationale are solid. `grep` confirms zero remaining `vi.clearAllMocks()` calls. tsc + 544/544 vitest + ESLint baseline preserved.

**Minor follow-ups (non-blocking):**
1. ESLint selector matches `vi.clearAllMocks` only, not aliased forms (`const v = vi`). Acceptable today; flag if it bites.
2. Test count drift 557 → 544 — worth a one-time `git log --diff-filter=D -- '*.test.tsx'` to confirm intentional.
3. CONTRACT comment on `OutlineEditor.tsx` invites future devs to bump the upper bound rather than question the third memo. Minor wording tweak.

Full review: `projects/learnpuddle-lms/reviews/review-FE-031-2026-04-24.md`

---

## FE-032 (SCIM Token UI) + QA SCIMTokenCard tests: **APPROVE** ✅

`SCIMTokenCard` is implemented correctly: one-time reveal via component state, defensive UI (revoked tokens render *with* badge but *without* Revoke button), `ConfirmDialog` danger variant for revoke. QA-tester's 24-test full-page-render suite mocks `adminSettingsService` and validates the real `SecuritySection → SCIMTokenCard` wiring rather than a synthetic mount. tsc + vitest both clean.

**Minor follow-ups (non-blocking):**
1. **Double-click overwrite risk** — `SettingsPage.tsx:1672` keeps token in `useState<string | null>`. Rapid double-create could overwrite the first token before the user copies it. One-line guard: `if (revealToken) return` in `createMutation.onSuccess`.
2. **Silent clipboard failure** — `SettingsPage.tsx:1578` `.then(() => setCopied(true))` has no `.catch`. Add `.catch((err) => toast.error('Copy failed', '...'))` for permission-denied edge cases.
3. **Cover note vs code drift** — note says queryKey `['scimTokens']`, code uses `['scim-tokens']`. Cosmetic.
4. **Loading-spinner test** (`SettingsPage.SCIMTokenCard.test.tsx:255`) asserts negative DOM. Prefer `expect(document.querySelector('.animate-spin')).toBeTruthy()` to match FE-033 pattern.

Full review: `projects/learnpuddle-lms/reviews/review-FE-032-and-QA-tests-2026-04-24.md`

---

— reviewer
