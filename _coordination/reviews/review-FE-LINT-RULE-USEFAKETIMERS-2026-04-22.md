---
tags: [review, task/FE-LINT-RULE-USEFAKETIMERS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-22
---

# Review: FE-LINT-RULE-USEFAKETIMERS-2026-04-22 — Forbid bare `vi.useFakeTimers()`

## Verdict: APPROVE

## Summary

Static verification passes. A single new flat-config file
(`frontend/eslint.config.js`, ESM, matching `package.json` `"type": "module"`)
adds a `no-restricted-syntax` rule that pins the regression vector flagged in
`review-FE-TEST-SUITE-STABILIZATION-2026-04-22.md`. No product or test code
modified. Low blast radius, high preventive value.

## Verification Performed

1. **File presence / format.** `frontend/eslint.config.js` exists, is ESM
   default-export of an array (flat-config), compatible with the ESM package
   (`"type": "module"`). Targets `src/**/*.{ts,tsx,js,jsx}` and ignores
   `build/**`, `node_modules/**`, `coverage/**`.
2. **Selector correctness.** Rule uses the exact selector requested:
   `CallExpression[callee.object.name='vi'][callee.property.name='useFakeTimers'][arguments.length=0]`.
   Message explicitly recommends the scoped
   `vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })` form and
   cites the React 18 concurrent scheduler rationale.
3. **No existing violations.** `rg "vi\.useFakeTimers\(\s*\)"` over
   `frontend/src/**/*.{ts,tsx}` returns zero matches. All 16 current call-sites
   (across `useAiStudioWebSocket.test.ts`, `semanticSearch.test.tsx`,
   `Toast.test.tsx`, `translation.test.tsx`, `aiCourseGenerator.test.tsx`) pass
   a `{ toFake: [...] }` argument, so the rule will not fire on current HEAD.
4. **Scope.** `git status` confirms `frontend/eslint.config.js` is the sole
   untracked addition for this task; no test or production source was edited.

## Critical Issues

None.

## Major Issues

None. The 544 pre-existing Espree "Parsing error" entries reported by the
author are infrastructure debt caused by the absence of
`@typescript-eslint/parser` — unrelated to this change, and explicitly scoped
as a follow-up, not a blocker for this PR. The `no-restricted-syntax` rule
will still enforce against `.js`/`.jsx`, and will enforce over `.ts`/`.tsx`
once the parser is installed.

## Minor Issues / Follow-ups

- Install `@typescript-eslint/parser` (+ `typescript-eslint`) so Espree stops
  choking on TS syntax and the rule can actually bite on `.ts`/`.tsx` files in
  CI. File a separate ticket; not required for this merge.
- Consider wiring `npm run lint` into the CI matrix once the parser lands so
  this guard runs on every PR rather than ad-hoc.

## Positive Observations

- Minimal, surgical change: one file, one rule, zero behavioural impact on
  runtime code.
- Rule message is actionable (names the correct replacement API and the
  underlying reason), so future authors tripping the rule get the full
  context inline.
- Ignores block correctly excludes build artefacts without swallowing source.
