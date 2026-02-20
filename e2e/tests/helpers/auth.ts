import { expect, Page } from '@playwright/test';

export const credentials = {
  teacher: {
    email: process.env.E2E_TEACHER_EMAIL || 'teacher@demo.learnpuddle.com',
    password: process.env.E2E_TEACHER_PASSWORD || 'Teacher123!',
  },
  admin: {
    email: process.env.E2E_ADMIN_EMAIL || 'admin@demo.learnpuddle.com',
    password: process.env.E2E_ADMIN_PASSWORD || 'Admin123!',
  },
  superAdmin: {
    email: process.env.E2E_SUPERADMIN_EMAIL || 'admin@learnpuddle.com',
    password: process.env.E2E_SUPERADMIN_PASSWORD || 'Admin123!',
  },
};

export async function clearBrowserAuthState(page: Page) {
  await page.context().clearCookies();
  await page.goto('/login');
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
}

export async function loginAsAdmin(page: Page) {
  await page.goto('/login');
  await page.getByLabel(/email/i).fill(credentials.admin.email);
  await page.getByLabel(/password/i).fill(credentials.admin.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 15000 });
}

export async function loginAsTeacher(page: Page) {
  await page.goto('/login');
  await page.getByLabel(/email/i).fill(credentials.teacher.email);
  await page.getByLabel(/password/i).fill(credentials.teacher.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 15000 });
}

export async function loginAsSuperAdmin(page: Page) {
  await page.goto('/super-admin/login');
  await page.locator('input[type="email"], input[name="email"]').first().fill(credentials.superAdmin.email);
  await page.locator('input[type="password"], input[name="password"]').first().fill(credentials.superAdmin.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/.*\/super-admin\/dashboard/, { timeout: 15000 });
}

export function uniqueCourseTitle(prefix = 'E2E Course') {
  return `${prefix} ${Date.now()}`;
}
