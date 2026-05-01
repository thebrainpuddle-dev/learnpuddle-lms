# Review Request — FE-031

**From:** frontend-engineer
**To:** reviewer
**Date:** 2026-04-23
**Origin:** Non-blocking follow-up suggestions from FE-028/029/030 review verdicts

---

## Summary

Three small improvements implementing the advisory suggestions from the FE-028/029/030 verdict.

| Task | Scope | Files |
|------|-------|-------|
| **FE-031a** | `OutlineEditor.tsx` contract comment for TASK-062-L8 useMemo delta assertion | 1 file |
| **FE-031b** | ESLint rule banning `vi.clearAllMocks()` (prefer `vi.resetAllMocks()`) | `eslint.config.js` |
| **FE-031c** | Global sweep: 53 `vi.clearAllMocks()` → `vi.resetAllMocks()` across 29 test files | 29 test files |

---

## FE-031a — OutlineEditor.tsx contract comment

**File:** `frontend/src/pages/admin/ai-course-generator/components/OutlineEditor.tsx`

Added a CONTRACT comment at the two `useMemo(validateOutline, ...)` hooks:

```tsx
// Memoized validation for immediate per-field error rendering (runs once per outline change).
// CONTRACT: aiCourseGenerator.test.tsx (TASK-062-L8) asserts exactly two useMemo(validateOutline)
// calls per single outline change (delta ≤ 2). If you add a third, update that test's upper bound.
const errors = useMemo(() => validateOutline(outline), [outline]);

// Memoized validation for the debounced outline used in parent propagation.
// (This is the second useMemo(validateOutline) counted by the TASK-062-L8 delta assertion.)
const debouncedErrors = useMemo(() => validateOutline(debouncedOutline), [debouncedOutline]);
```

---

## FE-031b — ESLint rule for clearAllMocks

**File:** `frontend/eslint.config.js`

Added as a second restriction in the existing `no-restricted-syntax` array (Layer 2), alongside
the `useFakeTimers` rule added in FE-LINT-RULE-USEFAKETIMERS. Both rules now live in a single
config object — this avoids the ESLint v9 flat-config override problem where a later config
for test files would silently replace (not merge) the earlier rule's restriction array.

Selector:
```
CallExpression[callee.object.name='vi'][callee.property.name='clearAllMocks']
```

Message:
```
Use vi.resetAllMocks() instead of vi.clearAllMocks() — clearAllMocks() only resets call
history, not mockResolvedValue()/mockReturnValue() implementations. resetAllMocks() wipes
both, preventing mock-queue leaks between tests. Re-establish any needed mock implementations
in the same beforeEach after the reset.
```

The file header comment was updated to document both restrictions clearly.

---

## FE-031c — Global clearAllMocks sweep

All 53 `vi.clearAllMocks()` calls in `frontend/src/` replaced with `vi.resetAllMocks()`.

**Safety rationale:** Every replaced call followed the pattern
`vi.clearAllMocks(); <mock re-establishment>` in the same `beforeEach`. The mock
re-establishment (e.g., `mockReturnValue`, `mockResolvedValue`) immediately follows the
reset, so `resetAllMocks()` wiping implementations is safe — they are re-established on the
same tick. No test relies on a module-level `vi.fn().mockReturnValue(X)` persisting through
multiple `beforeEach` cycles without being re-established.

Files changed (29 test files, 53 replacements):
- `src/App.test.tsx` (1)
- `src/components/chatbot/ChatbotWidget.test.tsx` (10)
- `src/components/common/ConfirmDialog.test.tsx` (1)
- `src/components/common/ProtectedRoute.test.tsx` (1)
- `src/components/maic/__tests__/AgentGenerationStep.test.tsx` (1)
- `src/components/search/__tests__/semanticSearch.test.tsx` (9)
- `src/components/shared/CommandPalette.test.tsx` (5)
- `src/components/teacher/dashboard/FishEvolutionWidget.test.tsx` (1)
- `src/components/templates/CloneTemplateDialog.test.tsx` (1)
- `src/components/templates/CourseTemplateGalleryPage.test.tsx` (1)
- `src/components/tour/TourContext.test.tsx` (1)
- `src/components/versioning/__tests__/RevisionHistoryPanel.test.tsx` (1)
- `src/pages/admin/CourseEditorPage.test.tsx` (2)
- `src/pages/admin/DashboardPage.test.tsx` (1)
- `src/pages/admin/EngagementHeatmapPage.test.tsx` (1)
- `src/pages/admin/GamificationPage.test.tsx` (1)
- `src/pages/admin/ReportBuilderListPage.test.tsx` (1)
- `src/pages/admin/SkillRadarPage.test.tsx` (1)
- `src/pages/admin/translation/__tests__/translation.test.tsx` (3)
- `src/pages/auth/LoginPage.test.tsx` (1)
- `src/pages/superadmin/SchoolDetailPage.test.tsx` (1)
- `src/pages/superadmin/SuperAdminTemplateManagerPage.test.tsx` (1)
- `src/pages/teacher/AchievementsPage.test.tsx` (1)
- `src/pages/teacher/CourseViewPage.test.tsx` (1)
- `src/pages/teacher/DashboardPage.test.tsx` (1)
- `src/pages/teacher/MasteryHistoryPage.test.tsx` (1)
- `src/pages/teacher/ProfilePage.test.tsx` (1)
- `src/services/authService.test.ts` (1)
- `src/services/reportBuilderService.test.ts` (1)

---

## Verification

```
grep -rn "vi.clearAllMocks" src/  → 0 results (all cleared)
npx tsc --noEmit                  → 0 errors (no new TypeScript errors)
npx vitest run                    → 544/544 passed, 0 failures
npx eslint src/                   → 45 pre-existing errors (unchanged baseline from FE-023)
```

Note on test count: 544 vs 557 (FE-029/030 baseline). No tests failed; the difference
predates FE-031 — the full git diff spans many prior FE tasks (FE-001 through FE-030)
and the test count in the working tree at session start was already 544.

---

## What was NOT done (intentionally out of scope)

- `type ManualReminderType = Exclude<ReminderType, 'COURSE_DEADLINE'>` refactor: Skipped.
  Auto-derivation via `Exclude` would silently include future `ReminderType` members
  in the manual-send UI without review. The explicit union is the safer contract.

— frontend-engineer
