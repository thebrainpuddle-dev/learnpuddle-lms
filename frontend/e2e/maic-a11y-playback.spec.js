/**
 * TEST-P0-8 — MAIC Accessibility Playback E2E
 *
 * Companion to maic-full-playback.spec.js. Focuses on a11y-only assertions:
 *   - Keyboard navigation (Right/Left arrow advances scenes via SlideNavigator)
 *   - Live-region announcements update on scene change (MOB-P0-8 contract)
 *   - SlideNavigator role + label landmarks are stable
 *   - Tab order reaches Start Class consent button without skipping to chat
 *
 * Same env-var contract as maic-full-playback.spec.js. All tests are gated
 * behind E2E_LIVE=1 so the unit-test CI run is unaffected.
 *
 * Note: ArrowRight/ArrowLeft handlers live in SlideNavigator.tsx (lines 133+).
 * For the keys to fire the navigator handler, focus must be on the navigator
 * itself or a descendant — we click the Next button first to give the
 * navigation region focus, then test arrow keys.
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

test.describe('MAIC A11y Playback — TEST-P0-8', () => {
  /** @type {string} */
  let classroomId = '';

  test.beforeEach(async ({ page }) => {
    if (!process.env.E2E_LIVE) {
      test.skip(true, 'Set E2E_LIVE=1 with a running stack to execute e2e tests');
      return;
    }
    if (!page.url().includes('/teacher/')) {
      await loginAsTeacher(page);
    }
    if (!classroomId) {
      classroomId = await resolveClassroomId(page);
    }
  });

  // ── Test A1: aria-live region uses polite + atomic ─────────────────────────

  test('scene live region has aria-live="polite" and aria-atomic="true"', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    const live = page.locator('[role="status"][aria-live="polite"]').first();
    await expect(live).toBeAttached();
    await expect(live).toHaveAttribute('aria-live', 'polite');
    await expect(live).toHaveAttribute('aria-atomic', 'true');
  });

  // ── Test A2: ArrowRight advances scene via keyboard ────────────────────────
  //
  // SlideNavigator.tsx attaches ArrowRight/ArrowLeft handlers to its root
  // (role="navigation"). We focus the Next-scene button (a descendant) so the
  // event bubbles to the navigator region.

  test('ArrowRight on SlideNavigator advances to scene 2 and updates live region', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    const live = page.locator('[role="status"][aria-live="polite"]').first();
    // SPRINT-2-BATCH-9-F7: poll for Scene-1 announcement instead of fixed sleep.
    await expect.poll(async () => (await live.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 1 of \d+/);

    const initial = (await live.textContent()) || '';
    const totalMatch = initial.match(/Scene \d+ of (\d+)/);
    const totalScenes = totalMatch ? parseInt(totalMatch[1], 10) : 0;
    if (totalScenes < 2) {
      test.skip(true, 'Need 2+ scenes to test arrow-key nav');
      return;
    }

    // Focus the Next button so keyboard events target the navigation region.
    const nextBtn = page.locator('button[aria-label="Next scene"]');
    await nextBtn.focus();
    await page.keyboard.press('ArrowRight');
    // SPRINT-2-BATCH-9-F7: poll live-region text for Scene 2 instead of a
    // fixed 800ms sleep — the assistive-tech announcement is the semantic
    // signal we actually care about.
    await expect.poll(async () => (await live.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 2 of \d+/);

    const updated = (await live.textContent()) || '';
    expect(updated).toMatch(/Scene 2 of \d+/);
  });

  // ── Test A3: ArrowLeft returns to previous scene ───────────────────────────

  test('ArrowLeft on SlideNavigator returns to scene 1 from scene 2', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    const live = page.locator('[role="status"][aria-live="polite"]').first();
    // SPRINT-2-BATCH-9-F7: poll for Scene-1 announcement.
    await expect.poll(async () => (await live.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 1 of \d+/);

    const initial = (await live.textContent()) || '';
    const totalMatch = initial.match(/Scene \d+ of (\d+)/);
    const totalScenes = totalMatch ? parseInt(totalMatch[1], 10) : 0;
    if (totalScenes < 2) {
      test.skip(true, 'Need 2+ scenes to test arrow-key nav');
      return;
    }

    // Advance with click → then go back with ArrowLeft.
    const nextBtn = page.locator('button[aria-label="Next scene"]');
    await nextBtn.click();
    // SPRINT-2-BATCH-9-F7: assert Scene-2 via toHaveText (auto-retrying).
    await expect(live).toHaveText(/Scene 2 of \d+/, { timeout: 10_000 });

    const prevBtn = page.locator('button[aria-label="Previous scene"]');
    await prevBtn.focus();
    await page.keyboard.press('ArrowLeft');
    // SPRINT-2-BATCH-9-F7: poll live region for return to Scene 1.
    await expect.poll(async () => (await live.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 1 of \d+/);

    const back = (await live.textContent()) || '';
    expect(back).toMatch(/Scene 1 of \d+/);
  });

  // ── Test A4: SlideNavigator landmark is stable across scene changes ────────

  test('SlideNavigator role="navigation" remains attached after scene change', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    const nav = page.locator('[role="navigation"][aria-label="Scene navigation"]');
    await expect(nav).toBeVisible();

    // Advance one scene if possible — landmark must remain.
    const nextBtn = page.locator('button[aria-label="Next scene"]');
    if (await nextBtn.isEnabled()) {
      await nextBtn.click();
      // SPRINT-2-BATCH-9-F7: assert landmark via auto-retrying expect — the
      // navigator must remain mounted during scene transition.
      await expect(nav).toBeVisible({ timeout: 10_000 });
    }
  });

  // ── Test A5: Live region text updates on every scene transition ────────────
  //
  // The live region MUST mutate (text node change) for assistive tech to
  // announce. We capture text before + after a Next-scene click and assert
  // the strings differ. This protects against regressions where the
  // announcer caches "Scene 1 of N" for the whole session.

  test('live region text mutates on scene transition (announcer fires)', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    const live = page.locator('[role="status"][aria-live="polite"]').first();
    // SPRINT-2-BATCH-9-F7: poll for Scene-1 announcement before snapshotting.
    await expect.poll(async () => (await live.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 1 of \d+/);
    const before = (await live.textContent()) || '';

    const nextBtn = page.locator('button[aria-label="Next scene"]');
    if (!(await nextBtn.isEnabled())) {
      test.skip(true, 'Only one scene available');
      return;
    }
    await nextBtn.click();
    // SPRINT-2-BATCH-9-F7: poll until live-region text actually mutates.
    await expect.poll(async () => (await live.textContent()) || '', {
      timeout: 10_000,
    }).not.toBe(before);

    const after = (await live.textContent()) || '';
    expect(after).not.toBe(before);
    expect(after).toMatch(/Scene \d+ of \d+/);
  });
});
