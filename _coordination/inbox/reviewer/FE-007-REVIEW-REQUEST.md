# Review Request — FE-007 Rubric Management + Grading UI

**From**: frontend-engineer
**To**: reviewer
**Date**: 2026-04-19
**Phase**: Phase 3 — Enterprise Grading / Rubric Builder

## What changed

### `frontend/src/services/adminRubricService.ts` (new file)
Full typed API client for the TASK-044 rubric backend:

| Method | Endpoint | Purpose |
|--------|----------|---------|
| `listRubrics(params?)` | `GET /admin/rubrics/` | Paginated list w/ search + is_active filter |
| `getRubric(id)` | `GET /admin/rubrics/:id/` | Detail |
| `createRubric(payload)` | `POST /admin/rubrics/` | Create with nested criteria+levels |
| `updateRubric(id, payload)` | `PATCH /admin/rubrics/:id/` | Partial update |
| `deleteRubric(id)` | `DELETE /admin/rubrics/:id/` | Hard delete |
| `cloneRubric(id, title?)` | `POST /admin/rubrics/:id/clone/` | Deep-copy |
| `getAssignmentRubric(assignmentId)` | `GET /admin/assignments/:id/attach-rubric/` | Read current attachment |
| `attachRubric(assignmentId, rubricId)` | `POST /admin/assignments/:id/attach-rubric/` | Attach/detach |
| `evaluateSubmission(submissionId, payload)` | `POST /admin/submissions/:id/evaluate/` | Grade submission |
| `getMyEvaluation(submissionId)` | `GET /teacher/submissions/:id/evaluation/` | Teacher views grade |

### `frontend/src/pages/admin/RubricPage.tsx` (new file)

**Zod validation** (`zodResolver` on all forms):
```
RubricLevelSchema     — title (required), description, points (≥0), order
RubricCriterionSchema — title (required), description, max_points (≥0), order, levels[]
RubricSchema          — title (required), description, is_active, criteria[]
```

**Component hierarchy**:
```
RubricPage
├── DataTable (TanStack Table — sort/filter/paginate)
│   └── columns: Title | Criteria | Total Pts | Status | Actions
├── RubricModal (create / edit dialog)
│   ├── useFieldArray → criteria[]
│   └── CriterionCard (per criterion)
│       ├── useFieldArray → levels[] (nested)
│       └── collapsible performance-levels panel
└── ConfirmDialog (delete confirmation)
```

**Key behaviours**:
- Search box filters by rubric title (DataTable `filterColumn="title"`)
- Clone action calls `cloneRubric()` and immediately invalidates the list query (no page reload)
- Delete requires confirmation in `ConfirmDialog` before firing mutation
- `is_active` toggled by a Switch (shadcn/ui pattern, rendered as Badge in table)
- Total points auto-computed and displayed live in the modal footer as criteria/levels change
- All success/error feedback via `useToast()` — zero `alert()` calls

### `frontend/src/App.tsx` (modified)
```tsx
const RubricPage = React.lazy(() =>
  import('./pages/admin/RubricPage').then((m) => ({ default: m.RubricPage }))
);
// ...
<Route path="rubrics" element={<RoutePage><RubricPage /></RoutePage>} />
```

### `frontend/src/components/layout/AdminSidebar.tsx` (modified)
```tsx
import { ClipboardDocumentCheckIcon } from '@heroicons/react/24/outline';
// INSIGHTS section, after Question Banks:
{ name: 'Rubrics', href: '/admin/rubrics', icon: ClipboardDocumentCheckIcon, feature: null, tourId: 'admin-nav-rubrics' },
```

## Test results

```
npx tsc --noEmit  → 0 errors
npx vitest run    → Test Files 33 passed (33) / Tests 246 passed (246)
```

## Checklist

- [x] TypeScript strict — 0 errors
- [x] Tests green — 246/246
- [x] Uses RHF + Zod (`zodResolver`) for all form state — no raw `useState` for form fields
- [x] TanStack Table via `DataTable` — sortable columns, filter, pagination
- [x] `React.lazy` + `Suspense` for code-split route
- [x] No `alert()` calls — uses `useToast()` throughout
- [x] No `console.log` debug statements
- [x] Heroicons only (no emoji icons) — `ClipboardDocumentCheckIcon` for nav
- [x] `cursor-pointer` on all interactive elements
- [x] `useMutation` with `onSuccess` query invalidation for create/update/delete/clone
- [x] Backend contracts verified against `adminRubricService.ts` endpoint map
- [x] Nested `useFieldArray` pattern (criteria → levels) works correctly with RHF

— frontend-engineer

## Processed 2026-04-19

Round 1 reviewed at
`projects/learnpuddle-lms/reviews/review-FE-007-2026-04-19.md` (08:08) —
REQUEST_CHANGES. Round 2 fixes APPROVED at
`projects/learnpuddle-lms/reviews/review-FE-007-r2-2026-04-19.md`.
Closing out of queue.
