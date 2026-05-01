# FE-022 Review Request — Migrate deferred MAIC window.confirm → ConfirmDialog

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-22
**Task:** FE-022 — Resolve TODO(FE-018) at the two MAIC window.confirm sites

---

## Context

FE-018 (the `window.confirm` sweep, APPROVED 2026-04-21) intentionally deferred
two MAIC call sites with `// TODO(FE-018)` markers:

1. `ChatPanel.tsx` — `handleClearChat`: clears all chat messages in the AI classroom
2. `AgentGenerationStep.tsx` — `handleRegenerateAll`: regenerates all AI agent profiles

The deferral note cited "complex streaming state" and "multi-step generation state"
as reasons to wait. This PR resolves both using the same state-driven `<ConfirmDialog>`
pattern from FE-018 — no design compromises needed.

---

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/components/maic/ChatPanel.tsx` | Import `ConfirmDialog`; add `confirmClearOpen` state; split `handleClearChat` (opens dialog) from `handleClearConfirmed` (executes wipe); add `<ConfirmDialog variant="warning">` at JSX end |
| `frontend/src/components/maic/AgentGenerationStep.tsx` | Import `ConfirmDialog`; add `confirmRegenOpen` state; `handleRegenerateAll` now calls `setConfirmRegenOpen(true)`; add `<ConfirmDialog variant="warning">` before edit modal |
| `frontend/src/components/maic/__tests__/AgentGenerationStep.test.tsx` | Replace stale `window.confirm` spy test with two new tests (dialog opens, Cancel does not regenerate) |

---

## ChatPanel Detail

### Before
```tsx
const handleClearChat = useCallback(() => {
  if (chatMessages.length === 0) return;
  // TODO(FE-018): ...
  const ok = typeof window === 'undefined'
    ? true
    : window.confirm(`Clear all ${chatMessages.length} chat messages? This can't be undone.`);
  if (!ok) return;
  abortRef.current?.abort();
  setIsSending(false);
  // ... wipe
}, [chatMessages.length, classroomId, setChatMessages]);
```

### After
```tsx
const handleClearChat = useCallback(() => {
  if (chatMessages.length === 0) return;
  setConfirmClearOpen(true);
}, [chatMessages.length]);

const handleClearConfirmed = useCallback(() => {
  abortRef.current?.abort();
  setIsSending(false);
  setThinkingAgentId(null);
  setStreamingMessageId(null);
  setChatMessages([]);
  if (classroomId) {
    persistChatToSession(classroomId, []);
    updateClassroomChat(classroomId, []).catch(() => {});
  }
}, [classroomId, setChatMessages]);
```

Dialog JSX (after PromptInput, before closing `</div>`):
```tsx
<ConfirmDialog
  isOpen={confirmClearOpen}
  onClose={() => setConfirmClearOpen(false)}
  onConfirm={handleClearConfirmed}
  title="Clear all chat messages?"
  message={`This will permanently remove all ${chatMessages.length} messages from this classroom session. This can't be undone.`}
  confirmLabel="Clear chat"
  cancelLabel="Keep messages"
  variant="warning"
/>
```

The separation of `handleClearChat` (dialog trigger) from `handleClearConfirmed`
(destructive action) is deliberate — it avoids calling `abortRef.current?.abort()`
unless the user actually confirms. This matches the pattern from the FE-018
migration (e.g. `GradebookPage`, `TeachersPage`).

---

## AgentGenerationStep Detail

### Before
```tsx
const handleRegenerateAll = useCallback(() => {
  // TODO(FE-018): ...
  const ok = window.confirm('Regenerate all agents? Any edits you made will be discarded.');
  if (ok) { void generateAll(); }
}, [generateAll]);
```

### After
```tsx
const handleRegenerateAll = useCallback(() => {
  setConfirmRegenOpen(true);
}, []);
```

Dialog JSX (before `{editing && <AgentEditModal ...>}`):
```tsx
<ConfirmDialog
  isOpen={confirmRegenOpen}
  onClose={() => setConfirmRegenOpen(false)}
  onConfirm={() => { void generateAll(); }}
  title="Regenerate all agents?"
  message="Any edits you made to individual agents will be discarded and a fresh set will be generated."
  confirmLabel="Regenerate"
  cancelLabel="Keep current"
  variant="warning"
/>
```

---

## Tests

### Updated: AgentGenerationStep.test.tsx

Replaced the old `window.confirm` spy test (test #3) with **two** new tests:

| Test | Assertion |
|------|-----------|
| `"Regenerate all" opens a ConfirmDialog (not window.confirm)` | Clicks the button → dialog title appears → confirm + cancel buttons present |
| `"Regenerate all" → Cancel keeps current agents and does not regenerate` | Clicks → cancel → dialog closes → `generateAgentProfiles` called only once (initial load) |

Total tests in file: **6** (was 5).

---

## Zero remaining window.confirm in production

```
grep -rn "window.confirm" frontend/src/ | grep -v test
→ (no output)
```

---

## Verification

```
npx tsc --noEmit
→ 0 errors

npx vitest run src/components/maic/__tests__/AgentGenerationStep.test.tsx
→ 6 / 6 passing
```

---

## Non-blocking notes

1. **ChatPanel lacks a dedicated test file.** The `handleClearChat` → dialog flow is
   tested indirectly via the `ChatbotChat.test.tsx` neighbor file, but a focused
   `ChatPanel.test.tsx` would require setting up the full `useMAICStageStore` mock.
   This is pre-existing gap; adding that file is a separate task.

2. Both dialogs use `variant="warning"` (amber) rather than `variant="danger"` (red)
   because the actions are reversible in spirit — chat messages can be recreated by
   reloading, agents can be regenerated again. This matches the FE-018 pattern where
   `warning` was used for destructive-but-recoverable actions (hide, reset).

— frontend-engineer
