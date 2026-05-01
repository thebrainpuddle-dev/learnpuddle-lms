---
tags: [review, task/FE-023, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-23
---

# Review: FE-023 — Add `@typescript-eslint/parser` (resolve 544 ESLint TS parsing errors)

## Verdict: APPROVE

## Summary
Small, correct infra fix. The flat config now parses `.ts`/`.tsx` without
Espree choking, which means the FE-LINT-RULE-USEFAKETIMERS rule finally
enforces on the TypeScript source tree it was always meant to cover. No
type-aware rules are enabled (good choice — avoids the tsconfig/speed tax
until there's a rule that justifies it). One minor YAGNI question on the
bundled plugin; not a gate.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
- **Unused dep** — `@typescript-eslint/eslint-plugin@^8` is added to
  devDependencies but no rules from it are activated in
  `eslint.config.js`. The author's own note offers to drop it. My
  preference: **drop it in a follow-up PR** unless the next type-aware
  rule is landing this sprint. Shipping an unused plugin slows `npm ci`
  (marginally) and muddies "what does our lint actually enforce" for future
  readers. Non-blocking — I'd approve either way.
- **Package ordering** in `devDependencies` is out of alphabetical order
  (`@typescript-eslint/*` inserted between `autoprefixer` and `eslint`
  instead of with the other `@` scopes at the top). Pure aesthetics;
  ignore or sweep with a formatter.

## Positive Observations
- **Two-layer config is clean and documented**: Layer 1 sets the parser
  for `src/**/*.{ts,tsx}`; Layer 2 scopes `no-restricted-syntax` to
  `src/**/*.{ts,tsx,js,jsx}`. The header comment explains the "why" which
  future readers will thank us for.
- **`parserOptions` is minimal and correct** (`ecmaVersion: 'latest'`,
  `sourceType: 'module'`, `ecmaFeatures: { jsx: true }`). No `project: true`,
  no `tsconfigRootDir` — so lint stays fast.
- **`dist/**` added to ignores** alongside pre-existing `build/**`,
  `node_modules/**`, `coverage/**` — matches Vite output.
- **`lint` script dropped `--ext .ts,.tsx`** — correct for ESLint v9 flat
  config (file selection is config-driven, `--ext` is deprecated). Nothing
  else in the `scripts` block broke.
- **Peer-dep compatibility verified**: `@typescript-eslint/parser@^8` is
  the version line that supports ESLint v9; the project is on
  `eslint@^9.28.0`. Reasonable pin.
- **No production code changed** — this is infra-only.

## Verification Notes
- Grep confirms `no-restricted-syntax` selector matches the prior
  FE-LINT-RULE-USEFAKETIMERS approved rule verbatim; no behavior drift.
- Layer-1 `files` glob (`src/**/*.{ts,tsx}`) does **not** attach the TS
  parser to non-`src` files (e.g. `vitest.config.ts` if present at repo
  root), which is the intended scope for this pass.

## Next Steps
- Update `status/review` → `status/done` on FE-023.
- Optional follow-up: remove or wire up `@typescript-eslint/eslint-plugin`.

— lp-reviewer
