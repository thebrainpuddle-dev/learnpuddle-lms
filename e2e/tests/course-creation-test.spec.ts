// e2e/tests/course-creation-test.spec.ts
// Admin course creation E2E workflow

import { test, expect } from '@playwright/test';
import { clearBrowserAuthState, loginAsAdmin, uniqueCourseTitle } from './helpers/auth';

test.describe('Course Creation Workflow', () => {
  test.beforeEach(async ({ page }) => {
    await clearBrowserAuthState(page);
    await loginAsAdmin(page);
  });

  test('creates a course and redirects to editor', async ({ page }) => {
    const title = uniqueCourseTitle('Introduction to Web Development');

    await page.goto('/admin/courses');
    await expect(page).toHaveURL(/.*\/admin\/courses/);

    await page.getByRole('button', { name: /create course/i }).click();
    await expect(page).toHaveURL(/.*\/admin\/courses\/new/, { timeout: 10000 });

    await page.locator('input[name="title"]').fill(title);
    await page.locator('textarea[name="description"]').fill('E2E generated course for workflow validation.');
    await page.locator('input[name="estimated_hours"]').fill('8');

    await page.getByRole('button', { name: /create course/i }).click();

    await expect(page).toHaveURL(/.*\/admin\/courses\/.+\/edit/, { timeout: 15000 });
    await expect(page.getByRole('heading', { name: /^edit course$/i })).toBeVisible();

    await page.goto('/admin/courses');
    await expect(page.getByText(title)).toBeVisible({ timeout: 10000 });
  });
});
