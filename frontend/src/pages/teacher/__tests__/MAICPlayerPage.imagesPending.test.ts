// src/pages/teacher/__tests__/MAICPlayerPage.imagesPending.test.ts
//
// SPRINT-2-BATCH-3-F2 — Polling state-machine tests for the teacher
// MAICPlayerPage.
//
// SPRINT-2-BATCH-5-F8 — Tests now import `computeRefetchInterval` directly
// from `lib/maicPollingPolicy.ts` (the production module) instead of
// re-implementing the decision logic in a local copy.
// Before this change, a divergence between the production component's
// logic and the test's copy would go undetected.  Now it can't.

import { describe, test, expect } from 'vitest';
import { computeRefetchInterval } from '../../../lib/maicPollingPolicy';

// ─── Tests ────────────────────────────────────────────────────────────────

describe('MAICPlayerPage refetchInterval — images_pending state machine (SPRINT-2-BATCH-3-F2)', () => {
  test('READY classroom with images_pending=true returns 5000ms (keeps polling)', () => {
    const interval = computeRefetchInterval({
      status: 'READY',
      images_pending: true,
    });
    expect(interval).toBe(5000);
  });

  test('READY classroom with images_pending=false returns false (stops polling)', () => {
    const interval = computeRefetchInterval({
      status: 'READY',
      images_pending: false,
    });
    expect(interval).toBe(false);
  });

  test('READY classroom with images_pending absent returns false (stops polling)', () => {
    const interval = computeRefetchInterval({ status: 'READY' });
    expect(interval).toBe(false);
  });

  test('GENERATING classroom with no heartbeat returns 3000ms (tight poll)', () => {
    const interval = computeRefetchInterval({ status: 'GENERATING' });
    expect(interval).toBe(3000);
  });

  test('GENERATING classroom with recent heartbeat (<30s) returns 3000ms', () => {
    const recent = new Date(Date.now() - 10_000).toISOString();
    const interval = computeRefetchInterval({
      status: 'GENERATING',
      progress: { last_progress_at: recent },
    });
    expect(interval).toBe(3000);
  });

  test('GENERATING classroom with warm heartbeat (30-120s) returns 10000ms', () => {
    const warm = new Date(Date.now() - 60_000).toISOString();
    const interval = computeRefetchInterval({
      status: 'GENERATING',
      progress: { last_progress_at: warm },
    });
    expect(interval).toBe(10_000);
  });

  test('GENERATING classroom stalled (>5min heartbeat) returns false', () => {
    const stale = new Date(Date.now() - 6 * 60 * 1000).toISOString();
    const interval = computeRefetchInterval({
      status: 'GENERATING',
      progress: { last_progress_at: stale },
    });
    expect(interval).toBe(false);
  });

  test('FAILED classroom returns false regardless of images_pending', () => {
    expect(computeRefetchInterval({ status: 'FAILED', images_pending: true })).toBe(false);
    expect(computeRefetchInterval({ status: 'FAILED', images_pending: false })).toBe(false);
  });

  // ─── F7: stall detection for images_pending ─────────────────────────────

  test('READY + images_pending=true + updated_at <10min ago → keeps polling (5000)', () => {
    const recent = new Date(Date.now() - 5 * 60 * 1000).toISOString(); // 5min ago
    expect(
      computeRefetchInterval({
        status: 'READY',
        images_pending: true,
        updated_at: recent,
      }),
    ).toBe(5000);
  });

  test('READY + images_pending=true + updated_at >10min ago → stops polling (false)', () => {
    const stale = new Date(Date.now() - 11 * 60 * 1000).toISOString(); // 11min ago
    expect(
      computeRefetchInterval({
        status: 'READY',
        images_pending: true,
        updated_at: stale,
      }),
    ).toBe(false);
  });
});
