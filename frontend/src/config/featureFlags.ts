/**
 * Frontend feature flags — env-driven, Vite-native (`import.meta.env`).
 *
 * Backend mirror: each flag here MUST have a matching env var in
 * backend/config/settings.py (config('FLAG_NAME', default=...)). Flag
 * states drift silently otherwise — frontend route mounted, backend
 * route 404, debugger stares for an hour.
 *
 * Add a flag:
 *   1. Add `VITE_FLAG_NAME` to .env.development / .env.production
 *   2. Add `flagName: parseFlag(import.meta.env.VITE_FLAG_NAME)` below
 *   3. Mirror in backend settings.py with the same default
 *   4. Reference via `featureFlags.flagName` (do not read import.meta.env
 *      elsewhere — keep all flag parsing centralized here)
 */

const parseFlag = (raw: string | undefined): boolean => {
  if (raw === undefined) return false;
  const v = String(raw).toLowerCase().trim();
  return v === 'true' || v === '1' || v === 'yes' || v === 'on';
};

export const featureFlags = {
  /**
   * AI Classroom v2 (MAIC v2). Backend mirror:
   * settings.MAIC_V2_ENABLED (default False). When false, the dev
   * probe at /dev/maic-v2 is unmounted and the V2 WS route returns
   * a 404-equivalent at the asgi router.
   */
  maicV2Enabled: parseFlag(import.meta.env.VITE_MAIC_V2_ENABLED),
} as const;

export type FeatureFlags = typeof featureFlags;
