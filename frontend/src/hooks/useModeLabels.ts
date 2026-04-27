// src/hooks/useModeLabels.ts
//
// Provides a `label(key)` helper that substitutes tenant-specific display
// strings driven by the backend's Education vs Corporate mode system
// (TASK-020 / FE-015).
//
// Usage:
//   const { label, mode } = useModeLabels();
//   // In education mode  → label('learner')  === 'Teacher'
//   // In corporate mode  → label('learner')  === 'Employee'
//   // With tenant override → whatever the admin set
//
// The labels are loaded from `GET /api/v1/tenants/me/` after authentication
// and stored in `tenantStore.modeLabels`. Until that call resolves, the hook
// returns the `EDUCATION_DEFAULTS` so the UI is never empty.

import {
  useTenantStore,
  EDUCATION_DEFAULTS,
  type ModeLabelKey,
  type TenantMode,
  type ModeLabels,
} from '../stores/tenantStore';

export interface UseModeLabelsResult {
  /**
   * Look up a display label by key.
   *
   * If the key is missing from the loaded map (e.g. before the API call
   * resolves, or an unexpected future key), the function falls back to the
   * education-mode default so the UI never renders an empty string.
   */
  label: (key: ModeLabelKey) => string;

  /**
   * The active mode for the current tenant.
   * Use this when you need to make structural (not just string) decisions
   * based on mode — e.g. showing/hiding a gamification panel in pure
   * corporate deployments.
   */
  mode: TenantMode;

  /**
   * The full merged label map.  Prefer `label(key)` for single lookups;
   * use this only when you need to enumerate all keys.
   */
  modeLabels: ModeLabels;
}

/**
 * React hook that exposes the tenant's active mode labels.
 *
 * Rendered output automatically updates if `tenantStore.modeLabels` is
 * updated (e.g. after an admin changes the mode and the page re-fetches).
 */
export function useModeLabels(): UseModeLabelsResult {
  const { mode, modeLabels } = useTenantStore();

  const label = (key: ModeLabelKey): string =>
    modeLabels[key] ?? EDUCATION_DEFAULTS[key];

  return { label, mode, modeLabels };
}
