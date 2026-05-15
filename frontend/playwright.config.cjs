/**
 * Playwright configuration for LearnPuddle LMS end-to-end tests.
 *
 * Uses CommonJS (.cjs) so the config can be loaded regardless of the project
 * "type": "module" setting in package.json. Playwright 1.59 + Node 20 +
 * ESM project requires this workaround.
 *
 * Only Chromium is in scope for now (Safari / Firefox are out of scope per TEST-P0-8).
 *
 * The entire e2e suite is guarded by E2E_LIVE=1 inside each spec file so that
 * `npm test` (vitest) never accidentally picks these up. This config is invoked
 * only via the separate `npm run e2e` script.
 *
 * Required env vars (see each spec for full list):
 *   E2E_LIVE=1                     — must be set to allow tests to run
 *   E2E_BASE_URL                   — defaults to http://localhost:3000
 *   E2E_TEACHER_EMAIL              — teacher account email (seeded by create_demo_tenant)
 *   E2E_TEACHER_PASSWORD           — teacher account password
 *   E2E_CLASSROOM_ID               — UUID of a READY classroom to play
 *
 * Prerequisites:
 *   docker compose up -d           — full backend stack (web, worker, redis, db)
 *   npm run dev (frontend)         — Vite dev server on :3000
 */

'use strict';

const { defineConfig, devices } = require('@playwright/test');

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:3000';

module.exports = defineConfig({
  testDir: './e2e',
  // Each test file must explicitly opt-in via test.skip(!process.env.E2E_LIVE)
  // so unit-test CI passes without a running dev server.
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // The live teacher/student harnesses intentionally sweep multiple real
  // routes in one browser session; keep the per-test budget above the default
  // 30s so the runner does not close pages mid-sweep.
  timeout: 120000,
  // TODO(F8): workers is set to 1 because it is unknown whether the e2e tests
  // share state (same classroom UUID, same teacher session) in a way that would
  // cause races under parallel execution.  Before raising this value, verify
  // that the F9 CI workflow is stable and that tests either use isolated
  // classrooms or are stateless enough to run concurrently.
  // Prerequisite: SPRINT-2-BATCH-4-F9 CI workflow must pass reliably first.
  // See _coordination/_BACKLOG.md → F8 for tracking.
  workers: 1,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'e2e-report' }]],
  use: {
    baseURL: BASE_URL,
    // Headless in CI; headed locally if PWDEBUG=1.
    headless: !process.env.PWDEBUG,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    // Generous timeouts: MAIC player loads IndexedDB + API before rendering.
    actionTimeout: 15000,
    navigationTimeout: 30000,
  },
  // No webServer block — the dev server must be started externally.
  // (Using webServer would re-launch Vite on every playwright invocation,
  //  which is slow and conflicts with existing dev sessions.)
  projects: [
    // SPRINT-2-BATCH-9-F6: split into desktop + mobile projects so the mobile
    // spec runs with the full iPhone 13 device profile (userAgent, isMobile,
    // hasTouch, deviceScaleFactor, viewport) instead of just a viewport-size
    // tweak. Components that branch on `(pointer: coarse)` or
    // `'ontouchstart' in window` (e.g. the chat FAB) now see the mobile
    // branch in M1–M5.  Desktop spec files still run with Desktop Chrome.
    {
      name: 'chromium-desktop',
      use: Object.assign({}, devices['Desktop Chrome']),
      // Desktop project explicitly skips the mobile spec.
      testIgnore: /maic-mobile-.*\.spec\.js/,
    },
    {
      name: 'mobile-iphone',
      use: Object.assign({}, devices['iPhone 13'], { browserName: 'chromium' }),
      // Mobile project runs ONLY the mobile-named spec files.
      testMatch: /maic-mobile-.*\.spec\.js/,
    },
  ],
  // HTML report output — keeps e2e artefacts out of the src tree.
  outputDir: 'e2e-results',
});
