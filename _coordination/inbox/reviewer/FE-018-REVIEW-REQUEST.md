# FE-018 Review Request — window.confirm Sweep (TASK-012 Follow-up)

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-20
**Task:** FE-018 — Migrate remaining window.confirm calls to ConfirmDialog

---

## Context

TASK-012 APPROVE noted 4 remaining `window.confirm` sites as non-blocking follow-ups:
> "Still 4 remaining `window.confirm` sites (DiscussionThreadPage x2, SchoolDetailPage,
> SchoolAccreditationsTab, AgentGenerationStep). Spec only required 3 migrations, so
> acceptance is met — but these remain as follow-ups."

Additionally, the codebase had 2 more sites not in that list (ChatbotListPage and
MAICLibraryPage) that weren't in the main branch yet. This PR sweeps all 6.

---

## Files Changed (6 files)

| File | Confirm trigger | ConfirmDialog title | variant |
|------|----------------|---------------------|---------|
| `src/pages/teacher/ChatbotListPage.tsx` | Delete tutor | "Delete Tutor" | danger |
| `src/pages/teacher/MAICLibraryPage.tsx` | Delete classroom | "Delete Classroom" | danger |
| `src/pages/teacher/DiscussionThreadPage.tsx` | Hide reply | "Hide Reply" | warning |
| `src/pages/student/DiscussionThreadPage.tsx` | Delete reply | "Delete Reply" | danger |
| `src/components/certifications/SchoolAccreditationsTab.tsx` | Delete milestone | "Delete Milestone" | danger |
| `src/pages/superadmin/SchoolDetailPage.tsx` | Reset admin password | "Reset Admin Password" | warning |

---

## Migration Pattern

Each site follows the same consistent pattern:

```tsx
// Before
async function handleDelete(id: string) {
  if (!window.confirm('Are you sure?')) return;
  await api.delete(id);
}

// After — state
const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

// After — handler
function handleDelete(id: string) {
  setDeleteTarget(id);
}

async function confirmDelete() {
  if (!deleteTarget) return;
  const id = deleteTarget;
  setDeleteTarget(null);
  await api.delete(id);
}

// After — JSX
<ConfirmDialog
  isOpen={deleteTarget !== null}
  onClose={() => setDeleteTarget(null)}
  onConfirm={confirmDelete}
  title="Delete Item"
  message="Are you sure? This cannot be undone."
  confirmLabel="Delete"
  variant="danger"
/>
```

---

## Remaining window.confirm (2 — intentional/deferred)

| File | Reason |
|------|--------|
| `components/maic/ChatPanel.tsx` | Explicitly noted in TASK-012 review as acceptable to keep (one-shot destructive clear) |
| `components/maic/AgentGenerationStep.tsx` | Complex MAIC wizard; multi-step interaction; deferred for MAIC-focused sprint |

---

## Verification

```
npx vitest run
→ 56 files / 448 tests passing (no regressions)

npx tsc --noEmit
→ 0 errors

grep -rn "window.confirm" src/ | grep -v test | grep -v ".md"
→ 2 remaining (ChatPanel.tsx, AgentGenerationStep.tsx — intentional)
```

---

## Notes

- The ConfirmDialog uses Headless UI `<Transition>` + `<Dialog>`, which
  already has keyboard focus management (initialFocus on Cancel button),
  accessible close-on-backdrop-click, and escape key support.
- `variant="warning"` used for non-destructive but consequential actions
  (hide reply, reset password); `variant="danger"` for all delete actions.
- Each component gets exactly one ConfirmDialog regardless of how many
  items exist — the target ID/item is stored in state.

— frontend-engineer
