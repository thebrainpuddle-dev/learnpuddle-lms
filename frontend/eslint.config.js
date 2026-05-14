// eslint.config.js — LearnPuddle frontend ESLint flat config (ESLint v9)
//
// Three layers:
//   1. TypeScript parser for .ts/.tsx files — resolves the 544 Espree parsing
//      errors that occurred when ESLint tried to parse TypeScript syntax with
//      the default JavaScript parser.
//   2. no-restricted-syntax rules applied to all source files:
//        a. Bans bare vi.useFakeTimers() which breaks React 18's concurrent scheduler.
//        b. Bans vi.clearAllMocks() — use vi.resetAllMocks() instead.
//           clearAllMocks() only wipes call history; it does NOT clear mockResolvedValue()
//           implementations or mockReturnValue queues. This causes mock-queue leaks between
//           tests when one test sets a persistent mock and the next expects a different value.
//           resetAllMocks() wipes both call history AND implementations, preventing flaky
//           test failures. (Root-cause: RubricPage flaky test fixed in FE-029.)
//   3. Ignore patterns for build artefacts.
//
// Prerequisites: `npm install` must have been run so that
// @typescript-eslint/parser (declared in devDependencies) is present.

import tsPlugin from '@typescript-eslint/eslint-plugin';
import tsParser from '@typescript-eslint/parser';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import reactHooks from 'eslint-plugin-react-hooks';

export default [
  {
    linterOptions: {
      reportUnusedDisableDirectives: 'off',
    },
  },

  // Layer 1 — TypeScript parser for TS/TSX source files
  {
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        // Type-aware rules are NOT enabled here (no `project: true`) to keep
        // lint fast on the full source tree. Enable per-rule as needed when
        // type-aware checks (e.g. @typescript-eslint/no-floating-promises)
        // are introduced in a future pass.
        ecmaVersion: 'latest',
        sourceType: 'module',
        ecmaFeatures: { jsx: true },
      },
    },
  },

  // Layer 2 — Project-wide rules (TS, TSX, JS, JSX)
  {
    files: ['src/**/*.{ts,tsx,js,jsx}'],
    plugins: {
      '@typescript-eslint': tsPlugin,
      'jsx-a11y': jsxA11y,
      'react-hooks': reactHooks,
    },
    rules: {
      'no-restricted-syntax': [
        'error',
        // (a) Scoped fake timers — bare vi.useFakeTimers() fakes MessageChannel/Date
        //     globally and breaks React 18's concurrent scheduler in sibling tests.
        //     Use: vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
        {
          selector:
            "CallExpression[callee.object.name='vi'][callee.property.name='useFakeTimers'][arguments.length=0]",
          message:
            "Use scoped fake timers: vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }) — bare vi.useFakeTimers() breaks React 18 concurrent scheduler.",
        },
        // (b) Prefer vi.resetAllMocks() over vi.clearAllMocks() — clearAllMocks() only
        //     resets call history (.mock.calls / .mock.results); it does NOT clear
        //     mockResolvedValue() or mockReturnValue() implementations set by earlier
        //     tests. This causes latent mock-queue leaks that produce flaky failures
        //     when test execution order changes. resetAllMocks() wipes both call
        //     history AND implementations, giving each test a clean slate.
        {
          selector:
            "CallExpression[callee.object.name='vi'][callee.property.name='clearAllMocks']",
          message:
            "Use vi.resetAllMocks() instead of vi.clearAllMocks() — clearAllMocks() only resets call history, not mockResolvedValue()/mockReturnValue() implementations. resetAllMocks() wipes both, preventing mock-queue leaks between tests. Re-establish any needed mock implementations in the same beforeEach after the reset.",
        },
      ],
    },
  },

  // Ignore build artefacts and vendored code
  {
    ignores: ['build/**', 'dist/**', 'node_modules/**', 'coverage/**'],
  },
];
