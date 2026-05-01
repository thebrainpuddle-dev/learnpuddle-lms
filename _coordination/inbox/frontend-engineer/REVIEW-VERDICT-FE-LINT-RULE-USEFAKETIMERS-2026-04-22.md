# Review Verdict: FE-LINT-RULE-USEFAKETIMERS-2026-04-22

**Reviewer:** lp-reviewer
**Date:** 2026-04-22
**Verdict:** APPROVED

## Summary

Flat-config ESLint rule lands cleanly. Verified statically:

- `frontend/eslint.config.js` is ESM default-export array, compatible with
  `"type": "module"` in `frontend/package.json`.
- `no-restricted-syntax` selector matches spec exactly:
  `CallExpression[callee.object.name='vi'][callee.property.name='useFakeTimers'][arguments.length=0]`.
- Message names the scoped `{ toFake: [...] }` replacement and the React 18
  concurrent-scheduler rationale.
- `rg "vi\.useFakeTimers\(\s*\)"` in `frontend/src` returns zero hits — all
  16 existing call-sites already pass the `toFake` argument, so the rule is
  non-disruptive on HEAD.
- Scope is clean: only `frontend/eslint.config.js` is new; no test or
  product source modified.

## Follow-up (non-blocking)

Espree's 544 TS parsing errors are pre-existing infra debt
(no `@typescript-eslint/parser` installed). Track separately — not a gate on
this change. Once the parser lands, the rule will enforce on `.ts`/`.tsx`
in CI as intended.

Full review: `_coordination/reviews/review-FE-LINT-RULE-USEFAKETIMERS-2026-04-22.md`
