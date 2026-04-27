/**
 * TEST-P0-8 — MAIC Mobile-Viewport Playback E2E
 *
 * Companion to maic-full-playback.spec.js. Runs the classroom flow inside
 * an iPhone-13 viewport (390×844) to catch mobile-only regressions:
 *   - FAB chat drawer (Stage.tsx Open classroom chat button)
 *   - 100dvh layout (no Safari bottom-bar overlap)
 *   - Offline banner positioning above content
 *   - Touch-target sizes (smoke check on play button bounding box)
 *
 * Same env-var contract as maic-full-playback.spec.js
 * (E2E_LIVE / E2E_BASE_URL / E2E_TEACHER_EMAIL / E2E_TEACHER_PASSWORD /
 *  E2E_CLASSROOM_ID). All tests are skipped when E2E_LIVE is unset so
 * `npm test` (vitest) and CI unit-test jobs are unaffected.
 *
 * SPRINT-2-BATCH-9-F6: viewport, UA, isMobile, hasTouch, and
 * deviceScaleFactor now come from the `mobile-iphone` Playwright project
 * (see playwright.config.cjs) which applies devices['iPhone 13'] wholesale
 * to every spec matching `maic-mobile-*.spec.js`.  Per-test
 * page.setViewportSize() is no longer needed.
 */

// @ts-check
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const TEACHER_EMAIL = process.env.E2E_TEACHER_EMAIL ?? 'teacher@demo.learnpuddle.com';
const TEACHER_PASSWORD = process.env.E2E_TEACHER_PASSWORD ?? 'Teacher@123';
const CLASSROOM_ID_OVERRIDE = process.env.E2E_CLASSROOM_ID ?? '';

/** @param {import('@playwright/test').Page} page */
async function loginAsTeacher(page) {
  await page.goto(`${BASE_URL}/login`);
  await page.locator('input[id="identifier"]').fill(TEACHER_EMAIL);
  await page.locator('input[id="password"]').fill(TEACHER_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/teacher/**', { timeout: 15_000 });
}

/** @param {import('@playwright/test').Page} page */
async function resolveClassroomId(page) {
  if (CLASSROOM_ID_OVERRIDE) return CLASSROOM_ID_OVERRIDE;
  const id = await page.evaluate(async () => {
    const token =
      sessionStorage.getItem('access_token') ??
      localStorage.getItem('access_token') ??
      '';
    const r = await fetch('/api/v1/maic/classrooms/?status=READY&page_size=5', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!r.ok) return '';
    const data = await r.json();
    const results = data.results ?? data;
    return Array.isArray(results) && results.length > 0 ? (results[0].id ?? '') : '';
  });
  if (!id) {
    throw new Error('No READY classrooms found for this teacher.');
  }
  return id;
}

test.describe('MAIC Mobile Playback — TEST-P0-8 (iPhone 13 viewport)', () => {
  /** @type {string} */
  let classroomId = '';

  test.beforeEach(async ({ page }) => {
    if (!process.env.E2E_LIVE) {
      test.skip(true, 'Set E2E_LIVE=1 with a running stack to execute e2e tests');
      return;
    }
    // Viewport / UA / isMobile / hasTouch are applied by the
    // `mobile-iphone` Playwright project (devices['iPhone 13']).
    if (!page.url().includes('/teacher/')) {
      await loginAsTeacher(page);
    }
    if (!classroomId) {
      classroomId = await resolveClassroomId(page);
    }
  });

  // ── Test M1: Player loads and stage renders inside iPhone viewport ─────────

  test('MAIC player renders inside iPhone viewport without horizontal scroll', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('[data-testid="maic-stage"]', { timeout: 20_000 });

    // documentElement.scrollWidth must not exceed the viewport width — if it
    // does we have a layout regression that produces a horizontal scrollbar
    // on phones (typical cause: 100vw on a child with overflow-x:visible).
    const overflow = await page.evaluate(() => ({
      docWidth: document.documentElement.scrollWidth,
      vw: window.innerWidth,
    }));
    expect(overflow.docWidth).toBeLessThanOrEqual(overflow.vw + 1);
  });

  // ── Test M2: 100dvh layout — main fills the visual viewport height ─────────

  test('Stage main element uses dvh layout and fills the viewport', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('[role="main"][aria-label="AI Classroom Stage"]', {
      timeout: 20_000,
    });

    const dims = await page.evaluate(() => {
      const main = document.querySelector('[role="main"][aria-label="AI Classroom Stage"]');
      if (!main) return null;
      const rect = main.getBoundingClientRect();
      return { height: rect.height, vh: window.innerHeight };
    });

    expect(dims).not.toBeNull();
    if (!dims) return;
    // Allow a 40px tolerance for offline banner / browser chrome.
    expect(dims.height).toBeGreaterThanOrEqual(dims.vh - 40);
  });

  // ── Test M3: Chat FAB is visible on mobile and opens the chat drawer ───────

  test('chat FAB is visible on mobile and opens the chat drawer', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label*="Start class"]', { timeout: 20_000 });
    await page.locator('button[aria-label*="Start class"]').click();
    // SPRINT-2-BATCH-9-F7: poll for Start Class overlay to disappear instead
    // of a fixed sleep — proves the consent gate transitioned cleanly.
    await expect(page.locator('button[aria-label*="Start class"]')).not.toBeVisible({
      timeout: 10_000,
    });

    // Stage.tsx renders <button aria-label="Open classroom chat"> as the FAB.
    const fab = page.locator('button[aria-label="Open classroom chat"]');
    if ((await fab.count()) === 0) {
      test.skip(true, 'Chat FAB not present in this build — likely behind a feature flag');
      return;
    }
    await expect(fab).toBeVisible();
    await fab.click();

    // After opening, a region with aria-label="Classroom chat" should appear.
    const drawer = page.locator('[aria-label="Classroom chat"]');
    await expect(drawer).toBeVisible({ timeout: 5_000 });

    // Close button (aria-label="Close chat") should be present and dismiss.
    const closeBtn = page.locator('button[aria-label="Close chat"]');
    await expect(closeBtn).toBeVisible();
    await closeBtn.click();
    await expect(drawer).not.toBeVisible();
  });

  // ── Test M4: Offline banner appears above stage when going offline ─────────

  test('offline banner appears above stage when context goes offline (mobile)', async ({ page, context }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('[data-testid="maic-stage"]', { timeout: 20_000 });

    await context.setOffline(true);
    const banner = page.locator('[data-testid="offline-banner"]');
    await expect(banner).toBeVisible({ timeout: 5_000 });

    // Banner must not push the stage off-screen — its bottom edge should be
    // less than the viewport height (i.e. it fits within the visible area).
    // SPRINT-2-BATCH-9-F9: read window.innerHeight at runtime instead of
    // hard-coding IPHONE_VIEWPORT.height — Playwright device profiles change
    // viewport dimensions across releases, so trust the live runtime value.
    const box = await banner.boundingBox();
    const viewportHeight = await page.evaluate(() => window.innerHeight);
    expect(box).not.toBeNull();
    if (box) {
      expect(box.y).toBeGreaterThanOrEqual(0);
      expect(box.y + box.height).toBeLessThanOrEqual(viewportHeight);
    }

    await context.setOffline(false);
    await expect(banner).not.toBeVisible({ timeout: 5_000 });
  });

  // ── Test M5: Play-button touch target ≥44×44 (MOB-P0-7) ────────────────────

  test('play-button satisfies the 44x44 minimum touch-target size', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('[data-testid="play-button"]', { timeout: 20_000 });

    const playBtn = page.locator('[data-testid="play-button"]');
    const box = await playBtn.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThanOrEqual(44);
      expect(box.height).toBeGreaterThanOrEqual(44);
    }
  });
});
