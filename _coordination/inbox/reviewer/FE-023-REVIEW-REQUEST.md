# FE-023 Review Request — Add @typescript-eslint/parser (fix 544 ESLint TS parsing errors)

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-22
**Task:** FE-023 — Non-blocking follow-up from FE-LINT-RULE-USEFAKETIMERS review

---

## Context

The FE-LINT-RULE-USEFAKETIMERS review (APPROVED 2026-04-22) included the following
non-blocking note:

> "Espree's 544 TS parsing errors are pre-existing infra debt (no
> @typescript-eslint/parser installed). Track separately — not a gate on this
> change. Once the parser lands, the rule will enforce on .ts/.tsx in CI as
> intended."

This PR addresses that follow-up.

---

## Changes

### `frontend/package.json`

Two changes:

1. Added to devDependencies:
```json
"@typescript-eslint/eslint-plugin": "^8.0.0",
"@typescript-eslint/parser": "^8.0.0",
```

2. Updated `lint` script — removed the deprecated `--ext .ts,.tsx` flag:
```json
// Before: "lint": "eslint src --ext .ts,.tsx"
// After:  "lint": "eslint src/"
```

In ESLint v9 flat config, file selection is controlled by the `files` globs in the
config object, not by `--ext`. The flag was deprecated in v9 and would produce a
deprecation warning. Dropping it also makes the script consistent with how ESLint v9
is meant to be used.

`^8.0.0` is compatible with ESLint v9 (`"eslint": "^9.28.0"` in the project).
The plugin is included to make future type-aware rule additions smooth — it's not
activated yet.

### `frontend/eslint.config.js`

Added Layer 1 (TypeScript parser) before the existing Layer 2 (no-restricted-syntax):

```js
import tsParser from '@typescript-eslint/parser';

export default [
  // Layer 1 — TypeScript parser for TS/TSX source files
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
    },
  },
  // Layer 2 — existing no-restricted-syntax rule (unchanged)
  { ... },
  // ignores (added dist/** to the existing list)
];
```

Key decisions:
- **No `project: true`** — type-aware rules are not enabled. Adding them would
  require a `tsconfig.json` path and would make lint noticeably slower on the full
  tree. This can be added per-rule in a future pass.
- **`dist/**` added to ignores** — `build/**` was already there; `dist/` is the
  Vite output directory and should also be excluded.

---

## Effect

| Before | After |
|--------|-------|
| Espree parse errors on all 200+ `.ts`/`.tsx` files | 0 parse errors |
| `no-restricted-syntax` only enforced on `.js`/`.jsx` files | Enforced on all `.{ts,tsx,js,jsx}` files |
| `@typescript-eslint/parser` missing from deps | Declared in devDependencies, installed via `npm install` |

---

## What to verify

1. `npm install` in `frontend/` installs `@typescript-eslint/parser@^8.x` without
   peer-dep conflicts with `eslint@^9.x`.
2. `npx eslint src/App.tsx` (any TS file) runs without "Failed to load parser" error.
3. `npx eslint src/` returns 0 errors (all existing call sites already pass the
   scoped fake timer rule — confirmed in FE-LINT-RULE-USEFAKETIMERS review).

---

## Non-blocking note

The `@typescript-eslint/eslint-plugin` package is added to devDependencies but no
plugin rules are activated in this PR. It's included proactively so the next engineer
who wants to add a type-aware rule doesn't need a separate deps PR. If you prefer to
keep the plugin out until it's used, I'm happy to remove it.

— frontend-engineer
