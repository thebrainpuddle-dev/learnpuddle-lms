// e2e/tests/teacher-courses.spec.ts
// Teacher portal functional E2E tests

import { test, expect } from '@playwright/test';
import { clearBrowserAuthState, loginAsTeacher } from './helpers/auth';

test.describe('Teacher Course Experience', () => {
  test.beforeEach(async ({ page }) => {
    await clearBrowserAuthState(page);
    await loginAsTeacher(page);
  });

  test('loads dashboard', async ({ page }) => {
    await page.goto('/teacher/dashboard');
    await expect(page).toHaveURL(/.*\/teacher\/dashboard/);
    await expect(page.getByRole('heading', { name: /welcome back/i })).toBeVisible();
  });

  test('loads my courses page', async ({ page }) => {
    await page.goto('/teacher/courses');
    await expect(page).toHaveURL(/.*\/teacher\/courses/);
    await expect(page.getByRole('heading', { name: /^my courses$/i })).toBeVisible();
  });

  test('loads assignments page', async ({ page }) => {
    await page.goto('/teacher/assignments');
    await expect(page).toHaveURL(/.*\/teacher\/assignments/);
    await expect(page.getByRole('heading', { name: /^assignments$/i })).toBeVisible();
  });

  test('opens first course detail when available', async ({ page }) => {
    await page.goto('/teacher/courses');
    await page.waitForLoadState('networkidle');

    const courseLink = page.locator('a[href*="/teacher/courses/"]').first();
    if (await courseLink.count()) {
      await courseLink.click();
      await expect(page).toHaveURL(/.*\/teacher\/courses\/.+/, { timeout: 10000 });
    } else {
      await expect(page.getByText(/no courses|not assigned|empty/i).first()).toBeVisible();
    }
  });
});
