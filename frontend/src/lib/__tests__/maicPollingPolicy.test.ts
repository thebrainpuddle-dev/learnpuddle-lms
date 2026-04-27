// src/lib/__tests__/maicPollingPolicy.test.ts
//
// SPRINT-2-BATCH-5-F8 — Unit tests for the canonical computeRefetchInterval
// helper extracted from MAICPlayerPage.tsx into lib/maicPollingPolicy.ts.
//
// These tests import the production function directly — not a copy of it.
// If the production logic changes, these tests catch the divergence
// immediately, which is exactly what SPRINT-2-BATCH-5-F8 asked for.
//
// Coverage:
//   - All status branches (FAILED, READY+pending, READY, GENERATING, DRAFT)
//   - Stall detection at exactly 10-min boundary (just-under → 5000, just-over → false)
//   - GENERATING progress decay (fresh/warm/cool/stalled)
//   - F7 stale updated_at cases (>10min → stop, <10min → 5000)

import { describe, test, expect } from 'vitest';
import {
  computeRefetchInterval,
  DEFAULT_IMAGES_STALL_TIMEOUT_MS,
  GENERATING_STALL_TIMEOUT_MS,
} from '../maicPollingPolicy';

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Return a `now()` override that reports `Date.now() - offsetMs` has passed. */
function nowAt(offsetMs: number) {
  const base = Date.now();
  return () => base + offsetMs;
}

// ─── FAILED status ────────────────────────────────────────────────────────────

describe('computeRefetchInterval — FAILED status', () => {
  test('returns false for FAILED regardless of images_pending=true', () => {
    expect(computeRefetchInterval({ status: 'FAILED', images_pending: true })).toBe(false);
  });

  test('returns false for FAILED with images_pending=false', () => {
    expect(computeRefetchInterval({ status: 'FAILED', images_pending: false })).toBe(false);
  });

  test('returns false for FAILED with no images_pending', () => {
    expect(computeRefetchInterval({ status: 'FAILED' })).toBe(false);
  });
});

// ─── READY + images_pending ───────────────────────────────────────────────────

describe('computeRefetchInterval — READY + images_pending', () => {
  test('returns 5000 when READY + images_pending=true + updated_at is recent', () => {
    const recentUpdatedAt = new Date(Date.now() - 30_000).toISOString(); // 30s ago
    expect(
      computeRefetchInterval({
        status: 'READY',
        images_pending: true,
        updated_at: recentUpdatedAt,
      }),
    ).toBe(5000);
  });

  test('returns 5000 when READY + images_pending=true + no updated_at (cannot stall-check)', () => {
    expect(
      computeRefetchInterval({ status: 'READY', images_pending: true }),
    ).toBe(5000);
  });

  // F7: stall boundary — just under 10min should keep polling
  test('returns 5000 when READY + images_pending=true + updated_at is just under 10min (599999ms)', () => {
    const justUnderStall = new Date(
      Date.now() - (DEFAULT_IMAGES_STALL_TIMEOUT_MS - 1),
    ).toISOString();
    expect(
      computeRefetchInterval({
        status: 'READY',
        images_pending: true,
        updated_at: justUnderStall,
      }),
    ).toBe(5000);
  });

  // F7: stall boundary — just over 10min should stop polling
  test('returns false when READY + images_pending=true + updated_at is just over 10min (600001ms)', () => {
    const justOverStall = new Date(
      Date.now() - (DEFAULT_IMAGES_STALL_TIMEOUT_MS + 1),
    ).toISOString();
    expect(
      computeRefetchInterval({
        status: 'READY',
        images_pending: true,
        updated_at: justOverStall,
      }),
    ).toBe(false);
  });

  // F7: explicit >10min case
  test('returns false when READY + images_pending=true + updated_at is 15min ago (stalled)', () => {
    const staleUpdatedAt = new Date(Date.now() - 15 * 60 * 1000).toISOString();
    expect(
      computeRefetchInterval({
        status: 'READY',
        images_pending: true,
        updated_at: staleUpdatedAt,
      }),
    ).toBe(false);
  });

  // F7: custom stallTimeoutMs via opts
  test('respects custom stallTimeoutMs opt', () => {
    const updatedAt = new Date(Date.now() - 3 * 60 * 1000).toISOString(); // 3min ago
    // With default 10min timeout: should keep polling
    expect(
      computeRefetchInterval(
        { status: 'READY', images_pending: true, updated_at: updatedAt },
      ),
    ).toBe(5000);
    // With custom 2min timeout: should stop
    expect(
      computeRefetchInterval(
        { status: 'READY', images_pending: true, updated_at: updatedAt },
        { stallTimeoutMs: 2 * 60 * 1000 },
      ),
    ).toBe(false);
  });

  // F7: now() override works correctly
  test('uses opts.now() override for stall computation', () => {
    const updatedAt = new Date(0).toISOString(); // epoch — very old
    // Override now to be "just after epoch + 9min" so ageMs < 10min
    const nineMinAfterEpoch = () => 9 * 60 * 1000;
    expect(
      computeRefetchInterval(
        { status: 'READY', images_pending: true, updated_at: updatedAt },
        { now: nineMinAfterEpoch },
      ),
    ).toBe(5000);
    // Override now to be "epoch + 11min" so ageMs > 10min
    const elevenMinAfterEpoch = () => 11 * 60 * 1000;
    expect(
      computeRefetchInterval(
        { status: 'READY', images_pending: true, updated_at: updatedAt },
        { now: elevenMinAfterEpoch },
      ),
    ).toBe(false);
  });

  test('returns false when READY + images_pending=false', () => {
    expect(
      computeRefetchInterval({ status: 'READY', images_pending: false }),
    ).toBe(false);
  });

  test('returns false when READY + images_pending absent', () => {
    expect(computeRefetchInterval({ status: 'READY' })).toBe(false);
  });
});

// ─── GENERATING — exp-backoff decay ──────────────────────────────────────────

describe('computeRefetchInterval — GENERATING progress decay', () => {
  test('returns 3000 when GENERATING with no heartbeat yet', () => {
    expect(computeRefetchInterval({ status: 'GENERATING' })).toBe(3000);
  });

  test('returns 3000 when GENERATING with heartbeat <30s ago (fresh)', () => {
    const fresh = new Date(Date.now() - 10_000).toISOString();
    expect(
      computeRefetchInterval({ status: 'GENERATING', progress: { last_progress_at: fresh } }),
    ).toBe(3000);
  });

  test('returns 3000 at exactly 30s boundary (exclusive)', () => {
    const at30s = new Date(Date.now() - 30_000).toISOString();
    // ageMs = 30_000 which is NOT > 30_000, so stays at 3000
    expect(
      computeRefetchInterval({ status: 'GENERATING', progress: { last_progress_at: at30s } }),
    ).toBe(3000);
  });

  test('returns 10000 when GENERATING with heartbeat 31s ago (warm)', () => {
    const warm = new Date(Date.now() - 31_000).toISOString();
    expect(
      computeRefetchInterval({ status: 'GENERATING', progress: { last_progress_at: warm } }),
    ).toBe(10_000);
  });

  test('returns 10000 when GENERATING with heartbeat 60s ago', () => {
    const warm = new Date(Date.now() - 60_000).toISOString();
    expect(
      computeRefetchInterval({ status: 'GENERATING', progress: { last_progress_at: warm } }),
    ).toBe(10_000);
  });

  test('returns 10000 at exactly 2min boundary (exclusive)', () => {
    const at2min = new Date(Date.now() - 2 * 60 * 1000).toISOString();
    // ageMs = 120_000 which is NOT > 120_000, so stays at 10_000
    expect(
      computeRefetchInterval({ status: 'GENERATING', progress: { last_progress_at: at2min } }),
    ).toBe(10_000);
  });

  test('returns 30000 when GENERATING with heartbeat 121s ago (cool)', () => {
    const cool = new Date(Date.now() - 121_000).toISOString();
    expect(
      computeRefetchInterval({ status: 'GENERATING', progress: { last_progress_at: cool } }),
    ).toBe(30_000);
  });

  test('returns false when GENERATING stalled (>5min heartbeat)', () => {
    const stale = new Date(
      Date.now() - (GENERATING_STALL_TIMEOUT_MS + 1),
    ).toISOString();
    expect(
      computeRefetchInterval({ status: 'GENERATING', progress: { last_progress_at: stale } }),
    ).toBe(false);
  });

  test('returns false at exactly 5min+1ms boundary (stalled)', () => {
    const stale = new Date(Date.now() - 6 * 60 * 1000).toISOString();
    expect(
      computeRefetchInterval({ status: 'GENERATING', progress: { last_progress_at: stale } }),
    ).toBe(false);
  });
});

// ─── DRAFT status ─────────────────────────────────────────────────────────────

describe('computeRefetchInterval — DRAFT status', () => {
  test('returns 3000 for DRAFT with no heartbeat', () => {
    expect(computeRefetchInterval({ status: 'DRAFT' })).toBe(3000);
  });

  test('returns 10000 for DRAFT with warm heartbeat (30s+)', () => {
    const warm = new Date(Date.now() - 60_000).toISOString();
    expect(
      computeRefetchInterval({ status: 'DRAFT', progress: { last_progress_at: warm } }),
    ).toBe(10_000);
  });
});

// ─── Undefined / other statuses ──────────────────────────────────────────────

describe('computeRefetchInterval — undefined / other statuses', () => {
  test('returns false for undefined data', () => {
    expect(computeRefetchInterval(undefined)).toBe(false);
  });

  test('returns false for ARCHIVED status', () => {
    expect(computeRefetchInterval({ status: 'ARCHIVED' })).toBe(false);
  });

  test('returns false for unknown status string', () => {
    expect(computeRefetchInterval({ status: 'UNKNOWN_STATUS_XYZ' })).toBe(false);
  });
});
