// e2e/tests/admin.spec.ts
// Admin portal functional E2E tests

import { test, expect } from '@playwright/test';
import { clearBrowserAuthState, loginAsAdmin } from './helpers/auth';

test.describe('Admin Portal', () => {
  test.beforeEach(async ({ page }) => {
    await clearBrowserAuthState(page);
    await loginAsAdmin(page);
  });

  test('loads dashboard', async ({ page }) => {
    const isMobileViewport = (page.viewportSize()?.width ?? 1280) < 1024;

    await expect(page.getByRole('heading', { name: /hello, admin/i })).toBeVisible();

    if (isMobileViewport) {
      await expect(page.getByRole('button', { name: /create course/i })).toBeVisible();
    } else {
      await expect(page.getByRole('link', { name: /^teachers$/i })).toBeVisible();
      await expect(page.getByRole('link', { name: /^courses$/i })).toBeVisible();
    }
  });

  test('opens teachers page', async ({ page }) => {
    await page.goto('/admin/teachers');
    await expect(page).toHaveURL(/.*\/admin\/teachers/);
    await expect(page.getByRole('heading', { name: /^teachers$/i })).toBeVisible();
  });

  test('opens courses page and create form', async ({ page }) => {
    await page.goto('/admin/courses');
    await expect(page).toHaveURL(/.*\/admin\/courses/);
    await expect(page.getByRole('heading', { name: /^courses$/i })).toBeVisible();

    await page.getByRole('button', { name: /create course/i }).click();
    await expect(page).toHaveURL(/.*\/admin\/courses\/new/, { timeout: 10000 });
    await expect(page.locator('input[name="title"]')).toBeVisible();
  });

  test('opens announcements page', async ({ page }) => {
    await page.goto('/admin/announcements');
    await expect(page).toHaveURL(/.*\/admin\/announcements/);
    await expect(page.getByRole('heading', { name: /^announcements$/i })).toBeVisible();
  });

  test('opens settings page', async ({ page }) => {
    await page.goto('/admin/settings');
    await expect(page).toHaveURL(/.*\/admin\/settings/);
    await expect(page.getByRole('heading', { name: /^settings$/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /^branding$/i })).toBeVisible();
  });
});
