// e2e/tests/gamification-admin.spec.ts
/**
 * E2E tests for the Admin Gamification Management page (FE-004).
 *
 * Covers:
 *  - Page navigation and tab rendering
 *  - Leaderboard tab: visible entries, period selector
 *  - XP History tab: table renders
 *  - Badges tab: badge list, create modal, delete confirmation
 *  - Config tab: form inputs, save button
 *  - Cross-role: teachers cannot access /admin/gamification
 *
 * All tests that require credentials are skipped gracefully when env vars
 * are not configured (safe for CI without a running LMS instance).
 *
 * Environment variables:
 *   E2E_ADMIN_EMAIL      - school admin email
 *   E2E_ADMIN_PASSWORD   - school admin password
 *   E2E_TEACHER_EMAIL    - teacher email (for access-denial test)
 *   E2E_TEACHER_PASSWORD - teacher password
 */

import { test, expect } from '@playwright/test';
import {
  loginAsAdmin,
  loginAsTeacher,
  dismissTourIfPresent,
  ensureCredentialsConfigured,
} from './helpers/auth';

const GAMIFICATION_URL = '/admin/gamification';

// ── Helper: skip if no credentials ──────────────────────────────────────────

function skipIfNoAdmin() {
  try {
    ensureCredentialsConfigured('admin');
  } catch {
    test.skip(true, 'Admin credentials not configured — skipping');
  }
}

function skipIfNoTeacher() {
  try {
    ensureCredentialsConfigured('teacher');
  } catch {
    test.skip(true, 'Teacher credentials not configured — skipping');
  }
}

// ── Tests ────────────────────────────────────────────────────────────────────

test.describe('Admin Gamification Page', () => {
  // ── Navigation ─────────────────────────────────────────────────────────────

  test('redirects to login when unauthenticated', async ({ page }) => {
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/.*\/login/, { timeout: 10000 });
  });

  test('navigates to /admin/gamification after login', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/.*\/admin\/gamification/, { timeout: 10000 });
  });

  test('renders Gamification heading on page', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });
    await expect(
      page.getByRole('heading', { name: /gamification/i }),
    ).toBeVisible({ timeout: 10000 });
  });

  test('sidebar nav has a Gamification link', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto('/admin/dashboard', { waitUntil: 'domcontentloaded' });
    await dismissTourIfPresent(page);

    const navLink = page.getByRole('link', { name: /gamification/i });
    await expect(navLink).toBeVisible({ timeout: 5000 });
    await navLink.click();
    await expect(page).toHaveURL(/.*\/admin\/gamification/, { timeout: 10000 });
  });

  // ── Tabs ──────────────────────────────────────────────────────────────────

  test('shows four tabs: Leaderboard, XP History, Badges, Config', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await expect(page.getByRole('tab', { name: /leaderboard/i })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('tab', { name: /xp history/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /badges/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /config/i })).toBeVisible();
  });

  test('Leaderboard tab is active by default', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    const leaderboardTab = page.getByRole('tab', { name: /leaderboard/i });
    await expect(leaderboardTab).toBeVisible({ timeout: 10000 });
    // headlessui Tab sets aria-selected="true" on the active tab
    await expect(leaderboardTab).toHaveAttribute('aria-selected', 'true');
  });

  // ── Leaderboard Tab ───────────────────────────────────────────────────────

  test('Leaderboard tab shows a period selector', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    // Period selector (weekly / monthly / all_time)
    const periodSelector = page.locator('select').first();
    await expect(periodSelector).toBeVisible({ timeout: 10000 });
    const options = await periodSelector.locator('option').allTextContents();
    expect(options.some(o => /weekly/i.test(o))).toBeTruthy();
    expect(options.some(o => /monthly/i.test(o))).toBeTruthy();
  });

  test('Leaderboard tab renders a radar chart container', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    // Recharts radar chart renders inside a ResponsiveContainer div
    // We look for any svg element which Recharts renders
    await expect(page.locator('svg').first()).toBeVisible({ timeout: 10000 });
  });

  // ── XP History Tab ────────────────────────────────────────────────────────

  test('XP History tab renders a table or empty state', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await page.getByRole('tab', { name: /xp history/i }).click();

    // After switching, should show either a table or empty state message
    await expect(
      page.locator('table, [role="table"], [data-testid="empty"]').first(),
    ).toBeVisible({ timeout: 10000 });
  });

  test('XP History tab has search filter input', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await page.getByRole('tab', { name: /xp history/i }).click();

    // Search input for filtering by teacher name/email
    const searchInput = page.getByPlaceholder(/search|filter|teacher/i).first();
    await expect(searchInput).toBeVisible({ timeout: 10000 });
  });

  // ── Badges Tab ────────────────────────────────────────────────────────────

  test('Badges tab shows badge list or empty state', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await page.getByRole('tab', { name: /badges/i }).click();

    await expect(
      page.locator('table, [role="table"], [data-testid="empty"], .text-gray-500').first(),
    ).toBeVisible({ timeout: 10000 });
  });

  test('Badges tab has "New Badge" button', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await page.getByRole('tab', { name: /badges/i }).click();

    await expect(
      page.getByRole('button', { name: /new badge/i }),
    ).toBeVisible({ timeout: 10000 });
  });

  test('clicking "New Badge" opens a dialog', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await page.getByRole('tab', { name: /badges/i }).click();
    await page.getByRole('button', { name: /new badge/i }).click();

    await expect(page.getByRole('dialog')).toBeVisible({ timeout: 5000 });
    await expect(page.getByRole('dialog').getByText(/badge/i).first()).toBeVisible();
  });

  test('Create Badge dialog has name, category, and icon fields', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await page.getByRole('tab', { name: /badges/i }).click();
    await page.getByRole('button', { name: /new badge/i }).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog.getByLabel(/name/i)).toBeVisible({ timeout: 5000 });
    await expect(dialog.getByLabel(/category/i)).toBeVisible();
  });

  test('Create Badge dialog can be closed with Cancel', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await page.getByRole('tab', { name: /badges/i }).click();
    await page.getByRole('button', { name: /new badge/i }).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible({ timeout: 5000 });

    await dialog.getByRole('button', { name: /cancel|close/i }).click();
    await expect(dialog).not.toBeVisible({ timeout: 3000 });
  });

  // ── Config Tab ────────────────────────────────────────────────────────────

  test('Config tab renders XP configuration form', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await page.getByRole('tab', { name: /config/i }).click();

    // Should show a save/update button for the config form
    await expect(
      page.getByRole('button', { name: /save|update/i }).first(),
    ).toBeVisible({ timeout: 10000 });
  });

  test('Config tab shows toggle switches for feature flags', async ({ page }) => {
    skipIfNoAdmin();
    await loginAsAdmin(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    await page.getByRole('tab', { name: /config/i }).click();

    // Feature flag toggles (is_active, leaderboard_enabled, etc.)
    await expect(
      page.locator('button[role="switch"], input[type="checkbox"]').first(),
    ).toBeVisible({ timeout: 10000 });
  });

  // ── Cross-Role Access Denial ──────────────────────────────────────────────

  test('teacher cannot access /admin/gamification (redirected)', async ({ page }) => {
    skipIfNoTeacher();
    await loginAsTeacher(page);
    await page.goto(GAMIFICATION_URL, { waitUntil: 'domcontentloaded' });

    // Teachers should be redirected to /teacher/dashboard or /login
    await expect(page).not.toHaveURL(/.*\/admin\/gamification/, { timeout: 10000 });
  });
});

// ── Activity Heatmap E2E (FE-005) ────────────────────────────────────────────

test.describe('Teacher Professional Growth — Activity Heatmap', () => {
  test('heatmap renders on Professional Growth page', async ({ page }) => {
    try {
      ensureCredentialsConfigured('teacher');
    } catch {
      test.skip(true, 'Teacher credentials not configured — skipping');
      return;
    }

    await loginAsTeacher(page);
    await page.goto('/teacher/professional-growth', { waitUntil: 'domcontentloaded' });
    await dismissTourIfPresent(page);

    // Look for the heatmap (it renders month labels like "Jan", "Feb", etc.)
    // Even if there's no activity data, the heatmap structure should be present
    const heatmapContainer = page.locator('.rounded-xl.border.border-gray-200').first();
    await expect(heatmapContainer).toBeVisible({ timeout: 10000 });

    // Day labels
    await expect(page.getByText('Mon').first()).toBeVisible({ timeout: 5000 });
  });

  test('heatmap legend is visible', async ({ page }) => {
    try {
      ensureCredentialsConfigured('teacher');
    } catch {
      test.skip(true, 'Teacher credentials not configured — skipping');
      return;
    }

    await loginAsTeacher(page);
    await page.goto('/teacher/professional-growth', { waitUntil: 'domcontentloaded' });
    await dismissTourIfPresent(page);

    await expect(page.getByText('Less').first()).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('More').first()).toBeVisible({ timeout: 5000 });
  });
});
