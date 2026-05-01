# FE-015 Review Request — Education vs Corporate Mode Switching UI

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-20
**Task:** FE-015 — Education vs Corporate mode switching

---

## Summary

Implements the frontend surface for TASK-020 (Education vs Corporate mode
switching). The backend exposes `mode` and `mode_labels` on `GET /tenants/me/`
and admin-editable on `GET/PATCH /tenants/settings/`. This PR wires the
labels into the store, provides a reactive hook, adds an admin settings tab,
and applies the hook to the TeacherSidebar "learner" role label.

---

## Files Changed

| Type | File | Change |
|------|------|--------|
| EDIT | `src/stores/tenantStore.ts` | +`TenantMode`, `ModeLabelKey`, `ModeLabels` types; `EDUCATION_DEFAULTS`, `CORPORATE_DEFAULTS` constants; `mode` + `modeLabels` state; `setModeLabels` action |
| NEW  | `src/hooks/useModeLabels.ts` | `label(key)` hook with fallback to `EDUCATION_DEFAULTS` |
| EDIT | `src/hooks/index.ts` | Barrel export of new hook |
| EDIT | `src/services/adminSettingsService.ts` | +`TenantModeSettings`, `TenantModePayload`; `getModeSettings()`, `updateModeSettings()`, `getTenantModeForUser()` — zero `any` |
| EDIT | `src/App.tsx` | `useEffect` → `GET /tenants/me/` after auth → `setModeLabels()`; silent fallback; SUPER_ADMIN excluded |
| EDIT | `src/pages/admin/SettingsPage.tsx` | +6th "Mode & Labels" tab + `ModeSwitchSection` component (mode radio + 12-row overrides table + save) |
| EDIT | `src/components/layout/TeacherSidebar.tsx` | `"Teacher"` → `label('learner')` |
| NEW  | `src/hooks/useModeLabels.test.ts` | 9 tests for the hook |

---

## Verification

```
npx tsc --noEmit  → 0 errors
npx vitest run    → 49 files / 402 tests passing (9 new in useModeLabels.test.ts)
```

---

## Key Design Decisions

### 1. Where mode labels are loaded

After auth, `App.tsx` calls `GET /tenants/me/` (not `/tenants/settings/`,
which is admin-only) so both teachers and admins receive the active labels.
Labels are merged with `EDUCATION_DEFAULTS` client-side to guard against
pre-migration tenants where `mode_labels` may be absent or partial.

### 2. Fallback strategy

`label(key)` in `useModeLabels` always falls back to `EDUCATION_DEFAULTS[key]`
— no empty-string renders ever. This is the same defensive pattern used in
`coinsService.parseInsufficientCoinsError`.

### 3. CORPORATE_DEFAULTS mirrored client-side

Like `DEFAULT_STREAK_FREEZE_PRICE = 100` in FE-014, the corporate defaults are
mirrored on the frontend from the backend's `MODE_LABEL_DEFAULTS`. Drift risk
is low (these are UX display strings, not pricing), but noted for awareness.

### 4. Component integration scope

Only `TeacherSidebar` ("Teacher" → `label('learner')`) is wired in this PR as
a proof-of-concept. A full sweep of hard-coded role/course/badge/league strings
across `DashboardPage`, `AchievementsPage`, `LeaguesPage`, and the MAIC
onboarding flow is scoped as a follow-up task to keep this PR reviewable.

---

## What to Check

1. **Zero `any`** in new service types (`TenantModeSettings`, `TenantModePayload`).
2. **`setModeLabels` called on success** of `updateModeSettings` mutation in
   `ModeSwitchSection` — this is the "live update" path so a page reload is not
   required after saving.
3. **`tenantModeSettings` query invalidated** after save — prevents stale reads
   if the settings page is re-opened.
4. **SUPER_ADMIN excluded** from mode-labels fetch in App.tsx (cross-tenant user,
   no single tenant context).
5. **Silent fallback** in App.tsx `catch` — backend pre-TASK-020 doesn't expose
   `mode_labels` on `/tenants/me/`; the UI falls back to `EDUCATION_DEFAULTS`.

---

## Follow-up Items (non-blocking, not in this PR)

- **FE-016 (proposed):** Full sweep of hard-coded label strings in 10+ pages
  to wire `useModeLabels`. Mechanical work, one hook call per component.
- **Admin leaderboard labels** (GamificationPage "League" tab header, etc.) —
  same hook integration.
- **MAIC onboarding flow** — "Course" references in the teacher onboarding wizard.

— frontend-engineer
