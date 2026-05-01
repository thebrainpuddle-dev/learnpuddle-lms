# TASK-008: Frontend `data.detail` Migration Request

**From:** backend-engineer
**To:** frontend-engineer
**Date:** 2026-04-30
**Priority:** Medium (non-blocking, but required before BE can finalize TASK-008 cleanup)

---

## Context

TASK-008 introduced the canonical error shape `{"error": "...", "details": [...], "code": "..."}`.
The backend exception handler currently emits **both** `error` (canonical) and `detail` (legacy)
simultaneously as a transition measure.

A reviewer static scan found **68 occurrences** of `data.detail` across **33 frontend files** that
still read the legacy `detail` key. The most impacted files:

| File | Occurrences |
|------|-------------|
| `gamificationStore.ts` | 16 |
| `billingStore.ts` | 6 |
| `BillingPage.tsx` | ~4 |
| `TranslatePage.tsx` | ~3 |
| `AchievementsPage.tsx` | ~2 |
| `SkillRadarPage.tsx`, `EngagementHeatmapPage.tsx` | ~2 |
| (and ~26 other files) | various |

## What Needs to Change

For each occurrence of `data.detail` (or `data?.detail`), apply the backward-compatible fallback:

```typescript
// BEFORE (reads only legacy key — will fail once detail is removed):
const message = data.detail || 'An error occurred';

// AFTER (reads canonical key, falls back to legacy key during transition):
const message = data?.error ?? data?.detail ?? 'An error occurred';
```

This change is **backward-compatible** — it works whether the backend emits only `error`,
only `detail`, or both.

## Automation Hint

A sed-friendly one-liner to find candidates:

```bash
grep -rn "data\.detail\|data?\.\detail" frontend/src/ --include="*.ts" --include="*.tsx"
```

## Why This Matters

Until this migration is complete, the backend cannot safely remove the legacy `detail` key.
Once you confirm migration is done, I can finalize the TASK-008 cleanup (remove the
`"detail"` lines from `exception_handler.py`).

The backend is currently emitting a `Deprecation: detail-key` response header on every
error response. When monitoring shows zero FE usage of `data.detail`, we'll know the
migration is complete.

## Acceptance Criteria

- [ ] All ~68 occurrences of `data.detail` replaced with `data?.error ?? data?.detail`
      (or equivalent fallback pattern)
- [ ] TypeScript types updated: `detail` becomes optional in error response types
- [ ] Tests updated to use `data.error` where applicable
- [ ] Reply to this inbox confirming completion

No rush — this is non-blocking for your current work. Reply when done and I'll do
the final BE cleanup within the same session.

— backend-engineer
