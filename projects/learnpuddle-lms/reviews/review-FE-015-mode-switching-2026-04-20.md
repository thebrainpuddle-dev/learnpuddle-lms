---
tags: [review, task/FE-015, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: FE-015 — Education vs Corporate Mode Switching UI

## Verdict: APPROVE

## Summary
Clean, well-typed wiring of TASK-020's backend contract. Store state, hook, service layer, admin settings tab, and proof-of-concept component integration are all present, cohesive, and zero-`any`. Tests are meaningful and cover the hook's contract end-to-end. One minor duplicate-fetch issue worth cleaning up in a follow-up. Ship it.

## Verification

### Store — `tenantStore.ts` ✅
- `TenantMode`, `ModeLabelKey`, `ModeLabels` types added (lines 31–48). `ModeLabels = Record<ModeLabelKey, string>` — strict.
- `EDUCATION_DEFAULTS` / `CORPORATE_DEFAULTS` mirror backend `MODE_LABEL_DEFAULTS`. Author's own note on drift risk is accurate — acceptable since these are UX strings, not auth data.
- `mode` and `modeLabels` in state (lines 120–125) with sensible defaults.
- `setModeLabels(mode, labels)` action (line 154) — explicit pair update.
- `reset()` resets mode fields too (line 162–163) — important for logout correctness. ✅

### Hook — `useModeLabels.ts` ✅
- `label(key)` uses nullish-coalescing fallback `modeLabels[key] ?? EDUCATION_DEFAULTS[key]` — no empty strings.
- Also exposes raw `mode` + `modeLabels` for structural and enumeration needs.
- Zero dependencies beyond the store — no side effects, pure read.

### Hook tests — `useModeLabels.test.ts` ✅
9 tests covering:
- Default state (test 1)
- Education mode labels (test 2)
- Corporate mode flip (tests 3, 4)
- Per-tenant override layering (test 5) — includes the important "non-overridden keys still return mode default" assertion
- Missing key fallback via an explicit `undefined` injection (test 6) — this is the exact defensive pattern the hook's contract promises
- `mode` field accuracy (test 7)
- Full map exposure (test 8)
- Reactive re-render on store change (test 9)

Test 6 is the best in the file — it simulates a pre-migration backend returning an incomplete map, which is the scenario the author explicitly called out in the request.

### Service — `adminSettingsService.ts` ✅
- `TenantModeSettings` and `TenantModePayload` are strictly typed (lines 199–215). Zero `any`.
- `getModeSettings()` and `updateModeSettings()` hit `/tenants/settings/` (admin-only) and always return the full shape via `?? {}` fallbacks — defensive against partial responses.
- `getTenantModeForUser()` hits `/tenants/me/` — correctly uses the non-admin endpoint. Good judgement on endpoint selection.
- JSDoc blocks clearly state auth requirements and describe the `mode_label_overrides` merge contract.

### App bootstrap — `App.tsx` ✅
Lines 377–393:
- Gated on `isAuthenticated && user?.role !== 'SUPER_ADMIN'` — correct; SUPER_ADMIN is cross-tenant.
- Merges server labels with `EDUCATION_DEFAULTS` on the client (line 386) — double defense with the hook-level fallback.
- Silent `.catch(() => {})` is acceptable for a progressive enhancement path (pre-migration tenants return no `mode_labels` and fall to defaults).
- `eslint-disable-next-line react-hooks/exhaustive-deps` — acceptable because Zustand selector refs are stable, but prefer `useRef` or referencing `useTenantStore.getState` to avoid the suppression for future maintainers. Minor.

### Settings page — `ModeSwitchSection` (SettingsPage.tsx lines 1788–2018) ✅
- New "Mode & Labels" tab registered (line 210) and conditionally rendered (line 2384).
- Mode radio cards + 12-row overrides table + Save button — matches the described UI.
- `setModeLabels(data.mode, merged)` in `saveMutation.onSuccess` (line 1823) — live update works, no page reload needed. ✅
- `queryClient.invalidateQueries({ queryKey: ['tenantModeSettings'] })` in `onSuccess` (line 1824) — prevents stale reads. ✅
- `handleOverrideChange` (line 1842): intelligently removes the override when the value is empty or equals the default — produces the minimal payload the backend expects. ✅
- `previewLabels` (line 1834): local real-time preview column before save — nice UX.

### TeacherSidebar integration ✅
- Line 33: `import { useModeLabels } from '../../hooks/useModeLabels';`
- Line 114: `const { label } = useModeLabels();`
- Line 173: `{label('learner')}` — renders "Teacher" (education) or "Employee" (corporate) or tenant override.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Redundant fetch on mount in `ModeSwitchSection`** (SettingsPage.tsx lines 1798–1816)
   Both a `useQuery({ queryKey: ['tenantModeSettings'], queryFn: ... })` AND a bare `useEffect(() => { adminSettingsService.getModeSettings().then(...) })` exist on mount. The `useQuery` `data` is never consumed (only `isLoading` is read); the effect duplicates the fetch. Net effect: ~2× API calls on every tab open.
   **Fix:** drop the effect, read `data` from `useQuery` and populate local state in a `useEffect` keyed on `data`, or drop the `useQuery` entirely (the effect does the job). Choosing `useQuery` is cleaner because `invalidateQueries` in `onSuccess` will then actually refetch authoritatively.

2. **`handleModeChange` clears user's in-flight overrides** (line 1839)
   If the user has typed custom strings for education and then clicks "Corporate" to preview, their in-flight overrides vanish. Intentional per the code comment, but I'd flag this in the UI ("Switching modes clears unsaved overrides") to set expectations. Not blocking — could be a follow-up UX polish.

3. **`SettingsPage.tsx` is now 2000+ lines.** `ModeSwitchSection`, the `MODE_LABEL_META` constant, and related types would live more naturally in `src/pages/admin/settings/ModeSwitchSection.tsx`. Not required — just flagging the growing file. Do not block on it.

4. **App.tsx effect eslint-disable** (line 392)
   Suppression is correct, but future readers won't know why. Either (a) use `useTenantStore.getState().setModeLabels` inside the effect body (no dependency needed, so no suppression needed), or (b) add an inline comment explaining "Zustand action refs are stable". The author already wrote "setModeLabels is stable (Zustand)" — perfect; keep that comment.

5. **CORPORATE_DEFAULTS / EDUCATION_DEFAULTS duplicated from backend** — author flagged. For UX strings this is acceptable. If a future task adds more label keys, a codegen script from the backend's `MODE_LABEL_DEFAULTS` would prevent drift. Noted for future.

## Positive Observations

- **Zero `any` in new types** — `TenantModeSettings`, `TenantModePayload`, `ModeLabels`, `ModeLabelKey` are all strict unions/records.
- **Three layers of label-key safety**: backend merge → client merge in App.tsx → fallback in `label()` hook. Great defensive design.
- **Clear scope** — TeacherSidebar as the single proof-of-concept integration keeps the PR reviewable, and the follow-up list (FE-016 sweep, leaderboard labels, MAIC wizard) is explicit.
- **Live update path works**: `saveMutation.onSuccess → setModeLabels(...)` means admins see the label flip immediately in the sidebar without a reload.
- **JSDoc hygiene** on the service methods clearly documents auth requirements — saves future maintainers a trip to the backend.
- **Test 6 (missing-key fallback)** is unusually thorough for a frontend hook test — it asserts the hook's most valuable contract under real failure conditions.

## Recommended Next Steps

- Approve and merge.
- Open FE-015-FOLLOWUP: consolidate the `useQuery` + `useEffect` in `ModeSwitchSection` (minor issue #1).
- Open FE-016 as author proposed: sweep hard-coded label strings across 10+ pages to wire `useModeLabels`.
- Consider adding a toast or aria-live note when the mode radio is flipped to warn about override reset (minor issue #2).

— lp-reviewer
