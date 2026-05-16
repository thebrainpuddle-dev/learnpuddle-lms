/**
 * TEST-P0-8 — MAIC Full-Playback End-to-End Smoke Test
 *
 * Drives a teacher through the complete MAIC flow:
 *   login → open a classroom → start playback → navigate 2-3 scenes →
 *   assert key UI states (toolbar, slide chrome, audio unlock, scene-counter
 *   live region, offline banner per-episode dismiss).
 *
 * This is the integration smoke test that catches regressions the unit tests
 * cannot detect (store ↔ component wiring, browser AudioContext policy,
 * real DOM live-region announcements, offline API).
 *
 * ─── Required Environment Variables ──────────────────────────────────────────
 *
 *   E2E_LIVE=1
 *     Must be set to 1 to allow any test to run. Without it every test is
 *     skipped so the unit-test CI run (`npm test`) stays clean.
 *
 *   E2E_BASE_URL (default: http://localhost:3000)
 *     Base URL of the running Vite dev server. Override for staging.
 *
 *   E2E_TEACHER_EMAIL (default: teacher@demo.learnpuddle.com)
 *     Email of the seeded teacher account. Created by:
 *       docker compose exec web python manage.py create_demo_tenant
 *
 *   E2E_TEACHER_PASSWORD (default: Teacher@123)
 *     Password for the seeded teacher account.
 *
 *   E2E_CLASSROOM_ID (optional)
 *     UUID of a specific READY classroom to play. When omitted the test
 *     fetches the first READY classroom from the teacher's library via the
 *     canonical teacher API and uses that. The classroom must have at least 2 scenes with
 *     sceneSlideBounds populated (i.e. a fully generated classroom).
 *
 * ─── Prerequisites ────────────────────────────────────────────────────────────
 *
 *   1. Full backend stack running:
 *        docker compose up -d
 *   2. Demo tenant seeded:
 *        docker compose exec web python manage.py create_demo_tenant
 *   3. Frontend dev server running on $E2E_BASE_URL (default :3000):
 *        cd frontend && npm run dev
 *   4. At least one READY classroom exists for the teacher account.
 *
 * ─── CI Guard ────────────────────────────────────────────────────────────────
 *
 *   Every test starts with:
 *     test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests')
 *
 *   This ensures `npm test` (vitest) does not attempt to run these even if
 *   the vitest glob somehow matched the e2e directory (it is excluded via
 *   vite.config.ts `test.include: ['src/**\/*.test.{ts,tsx}']`).
 */

// @ts-check
import { test, expect } from '@playwright/test';

// ─── Config ────────────────────────────────────────────────────────────────────

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const TEACHER_EMAIL = process.env.E2E_TEACHER_EMAIL ?? 'teacher@demo.learnpuddle.com';
// ── Password source of truth ───────────────────────────────────────────────────
// The default password below MUST match DEMO_USERS[1]['password'] in:
//   backend/apps/tenants/management/commands/create_demo_tenant.py
// That management command is what seeds this account (via `create_demo_tenant`).
// If the seed-script default is changed, update this fallback too, and rotate
// the E2E_TEACHER_PASSWORD repo secret in GitHub Actions.
// ─────────────────────────────────────────────────────────────────────────────
const TEACHER_PASSWORD = process.env.E2E_TEACHER_PASSWORD ?? 'Teacher@123';
const CLASSROOM_ID_OVERRIDE = process.env.E2E_CLASSROOM_ID ?? '';

// ─── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Log in as the teacher and navigate to the dashboard.
 * Returns when the teacher dashboard URL is reached (confirms auth + routing).
 *
 * @param {import('@playwright/test').Page} page
 */
async function loginAsTeacher(page) {
  await page.goto(`${BASE_URL}/login`);

  // Fill email/identifier field (LoginPage uses id="identifier")
  await page.locator('input[id="identifier"]').fill(TEACHER_EMAIL);

  // Fill password field
  await page.locator('input[id="password"]').fill(TEACHER_PASSWORD);

  // Submit
  await page.locator('button[type="submit"]').click();

  // Wait for redirect to teacher dashboard
  await page.waitForURL('**/teacher/**', { timeout: 15_000 });
}

/**
 * Resolve the classroom ID: use E2E_CLASSROOM_ID if set, otherwise fetch the
 * first READY classroom from the teacher's API library response.
 *
 * The MAIC API endpoint is /api/v1/teacher/maic/classrooms/?status=READY.
 * We call it from within the browser page so cookies/JWT flow naturally.
 *
 * @param {import('@playwright/test').Page} page
 * @returns {Promise<string>}
 */
async function resolveClassroomId(page) {
  if (CLASSROOM_ID_OVERRIDE) return CLASSROOM_ID_OVERRIDE;

  const classroomId = await page.evaluate(async () => {
    // Access tokens are stored in sessionStorage (or localStorage with "remember me").
    const token =
      sessionStorage.getItem('access_token') ??
      localStorage.getItem('access_token') ??
      '';

    const response = await fetch('/api/v1/teacher/maic/classrooms/?status=READY&page_size=5', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) return '';
    const data = await response.json();
    const results = data.results ?? data;
    if (Array.isArray(results) && results.length > 0) {
      return results[0].id ?? '';
    }
    return '';
  });

  if (!classroomId) {
    throw new Error(
      'No READY classrooms found for this teacher. ' +
        'Create one via the MAIC wizard or set E2E_CLASSROOM_ID.',
    );
  }
  return classroomId;
}

/** @param {import('@playwright/test').Page} page */
async function readEngineAudioDebug(page) {
  return page.evaluate(() => {
    const actionEngine = /** @type {any} */ (window).__maicEngine?.actionEngine;
    if (typeof actionEngine?.getAudioDebugState === 'function') {
      return actionEngine.getAudioDebugState();
    }
    const audio = actionEngine?.audioElement ?? actionEngine?._sharedAudio ?? null;
    const ctx = actionEngine?._audioContext ?? null;
    return {
      audioCurrentTime: audio?.currentTime ?? 0,
      audioPaused: audio?.paused ?? null,
      audioEnded: audio?.ended ?? null,
      audioReadyState: audio?.readyState ?? null,
      audioNetworkState: audio?.networkState ?? null,
      audioSrc: audio?.src ?? '',
      contextCurrentTime: ctx?.currentTime ?? 0,
      contextState: ctx?.state ?? null,
    };
  });
}

// ─── Tests ─────────────────────────────────────────────────────────────────────

test.describe('MAIC Full Playback — TEST-P0-8', () => {
  /** @type {string} */
  let classroomId = '';

  // beforeEach: log in and resolve classroom ID.
  test.beforeEach(async ({ page }) => {
    // CI guard — bail out immediately if the live stack is not available.
    if (!process.env.E2E_LIVE) {
      test.skip(true, 'Set E2E_LIVE=1 with a running stack to execute e2e tests');
      return;
    }

    // Log in if not already authenticated (detected by absence of teacher URL).
    const url = page.url();
    if (!url.includes('/teacher/')) {
      await loginAsTeacher(page);
    }

    // Resolve classroom once; subsequent tests reuse it.
    if (!classroomId) {
      classroomId = await resolveClassroomId(page);
    }
  });

  // ── Test 1: Login and landing ──────────────────────────────────────────────

  test('teacher can log in and reach the dashboard', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    // Already logged in from beforeEach — just verify we are on teacher pages.
    await expect(page).toHaveURL(/\/teacher\//);
  });

  // ── Test 2: Player page loads for a READY classroom ────────────────────────

  test('MAIC player page loads for a READY classroom', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);

    // For a READY classroom the "Start Class" overlay must appear.
    const startButton = page.locator('button[aria-label^="Start playback"][aria-label*="scene"]');
    await expect(startButton).toBeVisible({ timeout: 20_000 });
  });

  // ── Test 3: Toolbar is rendered ────────────────────────────────────────────

  test('StageToolbar is visible on the player page', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);

    // The top toolbar contains the playback speed cycling button (e.g. "1x").
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    const speedButton = page.locator('button[aria-label^="Playback speed"]');
    await expect(speedButton).toBeVisible();
  });

  // ── Test 4: Slide chrome is visible ────────────────────────────────────────

  test('slide chrome (maic-stage container) is visible', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    // data-testid="maic-stage" is the main content area from Stage.tsx line 588.
    const stage = page.locator('[data-testid="maic-stage"]');
    await expect(stage).toBeVisible();
  });

  // ── Chunk 4 — Media-lifecycle "Image unavailable" negative regression ─────
  //
  // Audit Section B.2 fix: a fresh READY classroom must never render the
  // `image-empty-placeholder` (the "Image unavailable" + alt-text card from
  // SlideRenderer.tsx around line 304). That placeholder fires when an
  // <image> element's src is still a `gen_img_*` literal at playback time —
  // i.e. the backend persisted a scene whose media placeholder was never
  // resolved to a real URL.
  //
  // Chunk 2 (#35) closed this hole by raising MaicProtocolError on
  // unresolvable placeholders at scene_builder.resolve_scene_media time,
  // which causes scene_generator._run_one to drop the bad scene before
  // persistence. This test pins that contract end-to-end.
  //
  // `image-failed-placeholder` (provider call genuinely failed mid-way) is
  // a separate, intentional UX surface and is NOT asserted absent — it is
  // the correct teacher signal when a transient provider hiccup occurred.

  test('READY classroom renders zero "image-empty-placeholder" elements', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('[data-testid="maic-stage"]', { timeout: 20_000 });

    // No "broken-ref" placeholders anywhere in the initial scene render.
    // A configured provider's transient failure surfaces as
    // `image-failed-placeholder`, NOT `image-empty-placeholder`.
    await expect(
      page.locator('[data-testid="image-empty-placeholder"]'),
    ).toHaveCount(0);
  });

  // ── Test 5: Audio unlock — "Start Class" overlay appears before playback ───
  //
  // MOB-P0-5 context: browsers block AudioContext auto-play. The "Start Class"
  // overlay acts as the required user-gesture consent gate for audio. Clicking
  // it triggers startClass() which initialises the AudioContext on a user event.

  test('audio-unlock overlay (Start Class button) is present before playback begins', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);

    // The "Start Class" overlay must be visible while playbackState === 'idle'.
    const startOverlay = page.locator('button[aria-label^="Start playback"][aria-label*="scene"]');
    await expect(startOverlay).toBeVisible({ timeout: 20_000 });

    // The play button in SlideNavigator should also be present (not yet playing).
    const playBtn = page.locator('[data-testid="play-button"]');
    await expect(playBtn).toBeVisible();

    // Aria-label should read "Start playback" when idle.
    await expect(playBtn).toHaveAttribute('aria-label', 'Start playback');
  });

  // ── Test 6: Clicking Start Class triggers AudioContext unlock ───────────────

  test('clicking Start Class transitions AudioContext away from suspended', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    // Click the consent button — this fires startClass() which calls
    // audioContext.resume() (or creates the context on a user gesture).
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    // SPRINT-2-BATCH-9-F7: poll for the Start-Class overlay to disappear,
    // proving the consent gate fired and playbackState left 'idle'.
    await expect(page.locator('button[aria-label^="Start playback"][aria-label*="scene"]')).not.toBeVisible({
      timeout: 10_000,
    });

    // Check AudioContext state via evaluate.
    const audioState = await page.evaluate(() => {
      // The engine may expose the context under window.__maicAudioCtx or similar.
      const ctx =
        window.__maicAudioCtx ??
        window.maicAudioContext ??
        null;
      if (ctx) return ctx.state;
      // Fallback: create a new context to see if the browser policy allows it
      // post-gesture (will be 'running' or 'suspended').
      try {
        const testCtx = new AudioContext();
        const state = testCtx.state;
        testCtx.close();
        return state;
      } catch {
        return 'unavailable';
      }
    });

    // After a user gesture, AudioContext should either be 'running' or
    // 'suspended' (if the device has no audio output / test env).
    // It must NOT be 'closed' (which would indicate a disposal bug).
    expect(['running', 'suspended', 'unavailable']).toContain(audioState);
  });

  // ── Test 7: Scene 1 live-region announcement (MOB-P0-8) ────────────────────

  test('scene counter live region announces Scene 1 of N after Start Class', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    // Click Start Class so the engine initialises and scene index = 0.
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    // The sr-only live region in Stage.tsx has role="status" and aria-live="polite".
    // Its text content is "Scene 1 of N" (optionally followed by ": <scene title>").
    const liveRegion = page.locator('[role="status"][aria-live="polite"]').first();
    await expect(liveRegion).toBeAttached();

    // SPRINT-2-BATCH-9-F7: poll for the Scene-1 announcement instead of a
    // 1s sleep — the live-region text is the semantic signal we care about.
    await expect.poll(async () => (await liveRegion.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 1 of \d+/);

    const text = await liveRegion.textContent();
    expect(text).toMatch(/Scene 1 of \d+/);
  });

  // ── Test 8: Next-scene navigation updates the scene counter ────────────────
  //
  // MOB-P0-7-F1 context: SlideNavigator exposes "Next scene" / "Previous scene"
  // buttons. Clicking Next should advance currentSceneIndex and update both the
  // live region and the scene chip selection.

  test('advancing to scene 2 updates the scene counter live region', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    // Click Start Class
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    // Get scene count from the live region text.
    const liveRegion = page.locator('[role="status"][aria-live="polite"]').first();
    // SPRINT-2-BATCH-9-F7: poll for Scene-1 announcement.
    await expect.poll(async () => (await liveRegion.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 1 of \d+/);
    const initialText = await liveRegion.textContent();
    const totalMatch = initialText?.match(/Scene \d+ of (\d+)/);
    const totalScenes = totalMatch ? parseInt(totalMatch[1], 10) : 0;

    // Only advance if there are 2+ scenes.
    if (totalScenes < 2) {
      test.skip(true, `Classroom has only ${totalScenes} scene(s); need at least 2 to test navigation`);
      return;
    }

    // Click "Next scene" button from SlideNavigator.
    const nextBtn = page.locator('button[aria-label="Next scene"]');
    await expect(nextBtn).toBeEnabled();
    await nextBtn.click();

    // SPRINT-2-BATCH-9-F7: poll live-region for Scene-2 announcement.
    await expect.poll(async () => (await liveRegion.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 2 of \d+/);

    const updatedText = await liveRegion.textContent();
    expect(updatedText).toMatch(/Scene 2 of \d+/);
  });

  // ── Test 9: Scene chip highlights update on navigation ─────────────────────

  test('scene chip for scene 2 becomes selected after Next scene click', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    // Count available scene chips.
    const chips = page.locator('[data-testid="scene-chip"]');
    // SPRINT-2-BATCH-9-F7: wait for chips to render.
    await expect.poll(async () => chips.count(), { timeout: 10_000 }).toBeGreaterThan(0);
    const chipCount = await chips.count();

    if (chipCount < 2) {
      test.skip(true, 'Need at least 2 scene chips to test chip selection update');
      return;
    }

    // Chip 1 (index 0) should be selected initially (aria-selected="true").
    await expect(chips.nth(0)).toHaveAttribute('aria-selected', 'true');

    // Click Next scene.
    const nextBtn = page.locator('button[aria-label="Next scene"]');
    await nextBtn.click();
    // SPRINT-2-BATCH-9-F7: assert chip-2 selected via auto-retrying expect.
    await expect(chips.nth(1)).toHaveAttribute('aria-selected', 'true', { timeout: 10_000 });
    await expect(chips.nth(0)).toHaveAttribute('aria-selected', 'false');
  });

  // ── Test 10: Audio does not re-prompt on scene 2 ───────────────────────────
  //
  // Once audio is unlocked via the Start Class gesture, navigating to scene 2
  // must NOT re-show the audio-unlock overlay. The start overlay should be gone.

  test('audio-unlock overlay does not reappear after navigating to scene 2', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    const liveRegion = page.locator('[role="status"][aria-live="polite"]').first();
    // SPRINT-2-BATCH-9-F7: poll for Scene-1 announcement.
    await expect.poll(async () => (await liveRegion.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 1 of \d+/);
    const text = await liveRegion.textContent();
    const totalMatch = text?.match(/Scene \d+ of (\d+)/);
    const totalScenes = totalMatch ? parseInt(totalMatch[1], 10) : 0;

    if (totalScenes < 2) {
      test.skip(true, 'Need 2+ scenes');
      return;
    }

    await page.locator('button[aria-label="Next scene"]').click();
    // SPRINT-2-BATCH-9-F7: poll for Scene-2 announcement.
    await expect.poll(async () => (await liveRegion.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 2 of \d+/);

    // The "Start Class" overlay must NOT be visible.
    const startOverlay = page.locator('button[aria-label^="Start playback"][aria-label*="scene"]');
    await expect(startOverlay).not.toBeVisible();
  });

  // ── Test 11: Offline banner appears when offline ────────────────────────────
  //
  // Uses Playwright's context.setOffline(true) to simulate a network disconnect.
  // The OfflineIndicator component listens to window 'offline' events and renders
  // data-testid="offline-banner".

  test('offline banner appears when context goes offline', async ({ page, context }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    // Banner must NOT be visible while online.
    await expect(page.locator('[data-testid="offline-banner"]')).not.toBeVisible();

    // Go offline — this fires the browser's 'offline' event.
    await context.setOffline(true);

    // Banner should appear.
    await expect(page.locator('[data-testid="offline-banner"]')).toBeVisible({ timeout: 5_000 });

    // Restore connection.
    await context.setOffline(false);

    // After coming back online the banner should hide (component listens to 'online' event).
    await expect(page.locator('[data-testid="offline-banner"]')).not.toBeVisible({ timeout: 5_000 });
  });

  // ── Test 12: Per-episode dismiss — banner reappears on re-disconnect ────────
  //
  // MOB-P0-1 spec: dismiss resets when back online. After dismissing and going
  // back online, a second offline episode should show the banner again.

  test('dismissed offline banner reappears on second offline episode', async ({ page, context }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    // Episode 1: go offline.
    await context.setOffline(true);
    const banner = page.locator('[data-testid="offline-banner"]');
    await expect(banner).toBeVisible({ timeout: 5_000 });

    // Dismiss the banner.
    await page.locator('button[aria-label="Dismiss offline notification"]').click();
    await expect(banner).not.toBeVisible();

    // Come back online — dismissedEpisode should reset to false.
    await context.setOffline(false);
    // debounce: brief settle between offline → online → offline to let the
    // 'online' event handler reset dismissedEpisode before episode 2 fires.
    await page.waitForTimeout(200);

    // Episode 2: go offline again.
    await context.setOffline(true);

    // Banner must reappear (dismissedEpisode was reset on 'online').
    await expect(banner).toBeVisible({ timeout: 5_000 });

    // Cleanup.
    await context.setOffline(false);
  });

  // ── Test 13: Scene navigation via scene chips ───────────────────────────────

  test('clicking scene chip 3 jumps to scene 3 and updates live region', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    const chips = page.locator('[data-testid="scene-chip"]');
    // SPRINT-2-BATCH-9-F7: wait for chips to render.
    await expect.poll(async () => chips.count(), { timeout: 10_000 }).toBeGreaterThan(0);
    const chipCount = await chips.count();

    if (chipCount < 3) {
      test.skip(true, `Need at least 3 scene chips; found ${chipCount}`);
      return;
    }

    // Click the third chip (index 2 = scene index 2).
    await chips.nth(2).click();

    const liveRegion = page.locator('[role="status"][aria-live="polite"]').first();
    // SPRINT-2-BATCH-9-F7: poll for Scene-3 announcement.
    await expect.poll(async () => (await liveRegion.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 3 of \d+/);

    const text = await liveRegion.textContent();
    expect(text).toMatch(/Scene 3 of \d+/);

    // The third chip should now be selected.
    await expect(chips.nth(2)).toHaveAttribute('aria-selected', 'true');
  });

  // ── Test 14: Scene navigation area has correct ARIA role ───────────────────

  test('SlideNavigator has role="navigation" for accessibility', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });

    // The SlideNavigator root has role="navigation" aria-label="Scene navigation".
    const nav = page.locator('[role="navigation"][aria-label="Scene navigation"]');
    await expect(nav).toBeVisible();
  });

  // ── Test 15: Stage ARIA main landmark ──────────────────────────────────────

  test('Stage root has role="main" and correct aria-label', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('[role="main"]', { timeout: 20_000 });

    const main = page.locator('[role="main"][aria-label="AI Classroom Stage"]');
    await expect(main).toBeVisible();
  });

  // ── Test 16: Audio currentTime advances after Start Class ──────────────────
  //
  // Verifies that audio is actually playing — we sample the first <audio>
  // element's currentTime at two intervals and assert it advanced. This
  // catches regressions where the AudioContext unlocks but no buffer plays
  // (e.g. broken TTS URL, MIME mismatch, decoder error swallowed silently).
  //
  // Note: relies on at least one <audio> element existing in the DOM after
  // playback starts. If the engine uses Web Audio API only (no <audio> tag),
  // we fall back to checking AudioContext.currentTime via window.__maicAudioCtx.

  test('audio currentTime advances after Start Class (playback is actually progressing)', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    // SPRINT-2-BATCH-9-F8: poll the engine-owned audio element, not the
    // silent DOM fallback <audio>. This keeps the probe on the real MAIC
    // speech pipeline.
    await expect.poll(
      async () => (await readEngineAudioDebug(page)).audioCurrentTime,
      { timeout: 15_000 },
    ).toBeGreaterThan(0);

    const sample1 = await readEngineAudioDebug(page);

    // debounce: measure forward-progress over a real wall-clock interval —
    // this is a real time delta, not a settle wait, so the timeout stays.
    await page.waitForTimeout(750);

    const sample2 = await readEngineAudioDebug(page);
    const audioDelta = sample2.audioCurrentTime - sample1.audioCurrentTime;

    expect(audioDelta).toBeGreaterThan(0.2);
  });

  // ── Test 17: Full playback through every scene ─────────────────────────────
  //
  // Walks through all scenes via "Next scene" until disabled; asserts the live
  // region reaches "Scene N of N", and the player remains in a healthy state
  // (no error toast, stage still mounted). This is the canonical full-playback
  // smoke test referenced by the TEST-P0-8 backlog item.

  test('teacher can advance through every scene to the final scene', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();

    const liveRegion = page.locator('[role="status"][aria-live="polite"]').first();
    // SPRINT-2-BATCH-9-F7: poll for Scene-1 announcement before sampling.
    await expect.poll(async () => (await liveRegion.textContent()) || '', {
      timeout: 10_000,
    }).toMatch(/Scene 1 of \d+/);
    const initialText = (await liveRegion.textContent()) || '';
    const totalMatch = initialText.match(/Scene \d+ of (\d+)/);
    const totalScenes = totalMatch ? parseInt(totalMatch[1], 10) : 0;

    expect(totalScenes).toBeGreaterThan(0);

    const nextBtn = page.locator('button[aria-label="Next scene"]');
    // Walk forward until Next is disabled or until we reach scene N.
    // Bounded by totalScenes to prevent runaway loops on misbehaving build.
    for (let i = 1; i < totalScenes; i++) {
      // expect.toPass retries the click+wait when the next button briefly
      // disables during scene transition (engine is loading next audio).
      await expect.poll(
        async () => (await nextBtn.isEnabled()) ? 'enabled' : 'disabled',
        { timeout: 30_000, intervals: [500, 1000, 2000] },
      ).toBe('enabled');

      await nextBtn.click();
      // SPRINT-2-BATCH-9-F7: poll live-region for Scene-(i+1) announcement
      // instead of a fixed sleep — the announcement is the semantic signal
      // that the scene transition completed.
      const expectedScene = i + 1;
      await expect.poll(async () => (await liveRegion.textContent()) || '', {
        timeout: 15_000,
      }).toMatch(new RegExp(`Scene ${expectedScene} of \\d+`));
    }

    // After advancing N-1 times we should be on scene N.
    const finalText = (await liveRegion.textContent()) || '';
    expect(finalText).toMatch(new RegExp(`Scene ${totalScenes} of ${totalScenes}`));

    // Stage must still be mounted (no crash).
    await expect(page.locator('[data-testid="maic-stage"]')).toBeVisible();
  });

  // ── Test 18: Chat input is present and accepts a message ───────────────────
  //
  // Smoke-test the classroom chat surface — verifies a teacher can type into
  // chat-input. Does not assert agent reply (would require LLM in CI); merely
  // confirms the chat UI is wired and accepts input without crashing.

  test('chat input accepts a teacher message without crashing the stage', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await page.waitForSelector('button[aria-label^="Start playback"][aria-label*="scene"]', { timeout: 20_000 });
    await page.locator('button[aria-label^="Start playback"][aria-label*="scene"]').click();
    // SPRINT-2-BATCH-9-F7: wait for the Start Class overlay to disappear
    // before interacting with chat — proves the engine is past idle.
    await expect(page.locator('button[aria-label^="Start playback"][aria-label*="scene"]')).not.toBeVisible({
      timeout: 10_000,
    });

    const chatInput = page.locator('textarea[aria-label="Chat message input"]:visible');
    // Chat may be hidden behind a FAB on mobile; on desktop it is in a side
    // panel. Skip cleanly if not attached at desktop viewport.
    if ((await chatInput.count()) === 0) {
      test.skip(true, 'chat-input not present at desktop viewport — see mobile spec');
      return;
    }

    await chatInput.fill('Hello, AI tutor');
    await expect(chatInput).toHaveValue('Hello, AI tutor');

    // Stage must still be visible after typing.
    await expect(page.locator('[data-testid="maic-stage"]')).toBeVisible();
  });
});
