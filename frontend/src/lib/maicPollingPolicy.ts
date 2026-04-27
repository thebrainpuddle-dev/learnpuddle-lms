// src/lib/maicPollingPolicy.ts
//
// SPRINT-2-BATCH-5-F8 — Extracted polling-interval decision logic.
//
// Previously, MAICPlayerPage.tsx inlined the `refetchInterval` callback
// and the test file re-implemented the same logic in a local copy.  Any
// production change would leave the test's copy stale with no detection.
//
// This module exports `computeRefetchInterval` so both the production
// component and the test file import from the same source of truth.
// A divergence between production behaviour and tests is now impossible
// unless someone edits this file deliberately.
//
// SPRINT-2-BATCH-5-F7 — Stall detector for `images_pending=true` polling.
//
// If the Celery `fill_classroom_images` task crashes before flipping
// `images_pending=False`, the FE would previously poll every 5s forever.
// This module enforces a 10-minute stall timeout (configurable via opts)
// keyed on `data.updated_at` — a proxy for when the task last touched the
// row.  After 10 minutes without a flip the caller receives `false` (stop
// polling) and should surface a stall-banner to the user.

/**
 * Shape of the classroom data object that drives the polling decision.
 * All fields are optional so the caller can pass partial API shapes.
 */
export type PollingClassroomData = {
  status?: string;
  images_pending?: boolean;
  /** ISO-8601 timestamp.  Used as a staleness proxy for images_pending. */
  updated_at?: string;
  progress?: {
    last_progress_at?: string | null;
  };
};

/**
 * Options for `computeRefetchInterval`.
 *
 * @property now             - Override `Date.now()` for deterministic tests.
 * @property stallTimeoutMs  - How long (ms) to wait for images_pending to
 *                             flip before stopping polls.  Default 600_000
 *                             (10 minutes).
 */
export type PollingPolicyOpts = {
  now?: () => number;
  stallTimeoutMs?: number;
};

/** Default stall timeout for the READY+images_pending case: 10 minutes. */
export const DEFAULT_IMAGES_STALL_TIMEOUT_MS = 10 * 60 * 1000;

/** Default stall timeout for the GENERATING case: 5 minutes. */
export const GENERATING_STALL_TIMEOUT_MS = 5 * 60 * 1000;

/**
 * Compute the React Query `refetchInterval` value for MAIC classroom polling.
 *
 * This is the canonical implementation.  Both `MAICPlayerPage.tsx` (teacher)
 * and `pages/student/MAICPlayerPage.tsx` import and call this function
 * instead of inlining the logic.
 *
 * Return semantics:
 *   - `false`           → stop polling
 *   - `number` (ms)     → poll again after this many milliseconds
 *
 * State machine:
 *
 *   FAILED                      → false  (terminal)
 *   READY + images_pending=true → 5000   (keep polling for image fill)
 *                                 OR false if updated_at is >stallTimeoutMs old (stalled)
 *   READY / any non-gen status  → false  (terminal)
 *   GENERATING + no heartbeat   → 3000   (tight poll, waiting for first progress)
 *   GENERATING + fresh (<30s)   → 3000
 *   GENERATING + warm  (30-120s)→ 10000
 *   GENERATING + cool  (120-300s)→ 30000
 *   GENERATING + stalled (>5min)→ false  (terminal)
 *   DRAFT                       → 3000   (same tight poll as GENERATING)
 */
export function computeRefetchInterval(
  data: PollingClassroomData | undefined,
  opts: PollingPolicyOpts = {},
): number | false {
  const now = opts.now ?? Date.now;
  const stallTimeoutMs = opts.stallTimeoutMs ?? DEFAULT_IMAGES_STALL_TIMEOUT_MS;

  const status = data?.status;

  // ── READY + images_pending ──────────────────────────────────────────────
  // CG-P0-3: READY classroom with images still filling — keep a moderate
  // 5s poll so users see real images arrive promptly without hammering the
  // API.  Stop if the task appears stalled (SPRINT-2-BATCH-5-F7).
  if (status === 'READY' && data?.images_pending === true) {
    // Stall detection: use `updated_at` as a proxy for when the Celery task
    // last wrote to this row.  If it's older than stallTimeoutMs the worker
    // is probably dead and we should stop polling to avoid infinite load.
    if (data?.updated_at) {
      const ageMs = now() - new Date(data.updated_at).getTime();
      if (ageMs > stallTimeoutMs) return false; // stalled — stop
    }
    return 5000;
  }

  // ── Non-generating / non-drafting statuses ──────────────────────────────
  if (status !== 'GENERATING' && status !== 'DRAFT') return false;

  // ── GENERATING / DRAFT ──────────────────────────────────────────────────
  // PERF-P0-2: exponential backoff keyed on last server-stamped progress.
  const lastProgressIso = data?.progress?.last_progress_at;
  // No heartbeat yet — short interval so we catch the first one quickly.
  if (!lastProgressIso) return 3000;

  const ageMs = now() - new Date(lastProgressIso).getTime();
  if (ageMs > GENERATING_STALL_TIMEOUT_MS) return false; // stalled — stop
  if (ageMs > 2 * 60 * 1000) return 30_000;
  if (ageMs > 30 * 1000) return 10_000;
  return 3000;
}
