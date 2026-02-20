// e2e/tests/teacher-superadmin-simple.spec.ts
// Cross-portal smoke tests for Teacher and Super Admin

import { test, expect } from '@playwright/test';
import {
  clearBrowserAuthState,
  loginAsSuperAdmin,
  loginAsTeacher,
} from './helpers/auth';

test.describe('Teacher + Super Admin Smoke', () => {
  test('teacher core routes are accessible after login', async ({ page }) => {
    await clearBrowserAuthState(page);
    await loginAsTeacher(page);

    await page.goto('/teacher/courses');
    await expect(page).toHaveURL(/.*\/teacher\/courses/);

    await page.goto('/teacher/assignments');
    await expect(page).toHaveURL(/.*\/teacher\/assignments/);

    await page.goto('/teacher/profile');
    await expect(page).toHaveURL(/.*\/teacher\/profile/);
  });

  test('super admin core routes are accessible after login', async ({ page }) => {
    await clearBrowserAuthState(page);
    await loginAsSuperAdmin(page);

    await page.goto('/super-admin/schools');
    await expect(page).toHaveURL(/.*\/super-admin\/schools/);
    await expect(page.getByRole('heading', { name: /^schools$/i })).toBeVisible();
  });
});
