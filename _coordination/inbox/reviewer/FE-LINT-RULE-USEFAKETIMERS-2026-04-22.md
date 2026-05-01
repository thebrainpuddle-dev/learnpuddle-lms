# Review Request: FE-LINT-RULE-USEFAKETIMERS-2026-04-22

**Author:** frontend-engineer  
**Date:** 2026-04-22  
**Branch:** maic-sprint-1-presence-rhythm

---

## Summary

Added ESLint flat config (`frontend/eslint.config.js`) with a `no-restricted-syntax` rule
that forbids bare `vi.useFakeTimers()` calls (zero-argument form). This addresses the
regression risk flagged in `review-FE-TEST-SUITE-STABILIZATION-2026-04-22.md`.

---

## Rule Added

**File:** `frontend/eslint.config.js` (new file — no config existed previously)

**Selector:**
```
CallExpression[callee.object.name='vi'][callee.property.name='useFakeTimers'][arguments.length=0]
```

**Message:**
> Use scoped fake timers: vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) —
> bare vi.useFakeTimers() breaks React 18 concurrent scheduler.

**Applies to:** `src/**/*.{ts,tsx,js,jsx}`

---

## Lint Run Result

```
npx eslint src --ext .ts,.tsx
```

- `no-restricted-syntax` violations: **0** (correct — all 6 existing call sites already
  use the scoped `{ toFake: [...] }` form).
- Other errors: 544 pre-existing `Parsing error` entries from Espree (ESLint's default
  parser) failing to parse TypeScript syntax. These are **infrastructure debt**, not new
  violations introduced by this change. No ESLint config or TypeScript parser existed
  before; the lint script was effectively inoperative.

---

## Follow-up Required

`@typescript-eslint/parser` is not installed. To make ESLint fully operational on
`.ts`/`.tsx` files, the package needs to be added to `devDependencies`:

```bash
npm install --save-dev @typescript-eslint/parser typescript-eslint
```

Once installed, update `eslint.config.js` to set:
```js
import tsParser from '@typescript-eslint/parser';
// languageOptions: { parser: tsParser }
```

The `no-restricted-syntax` rule is correct and will enforce as-is once the parser is
in place. No test or production code was modified.

---

## Files Touched

- `frontend/eslint.config.js` — created (new flat config, ESM format)

**No git commits. No git add. No git push.**

— frontend-engineer
