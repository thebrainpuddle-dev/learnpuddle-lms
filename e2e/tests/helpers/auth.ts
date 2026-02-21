import { expect, Page } from '@playwright/test';

type RoleKey = 'teacher' | 'admin' | 'superAdmin';

export const credentials = {
  teacher: {
    email: (process.env.E2E_TEACHER_EMAIL || '').trim(),
    password: (process.env.E2E_TEACHER_PASSWORD || '').trim(),
  },
  admin: {
    email: (process.env.E2E_ADMIN_EMAIL || '').trim(),
    password: (process.env.E2E_ADMIN_PASSWORD || '').trim(),
  },
  superAdmin: {
    email: (process.env.E2E_SUPERADMIN_EMAIL || '').trim(),
    password: (process.env.E2E_SUPERADMIN_PASSWORD || '').trim(),
  },
};

export function ensureCredentialsConfigured(...roles: RoleKey[]) {
  for (const role of roles) {
    const cred = credentials[role];
    if (!cred.email || !cred.password) {
      throw new Error(
        `Missing E2E credentials for ${role}. Set env vars for email/password before running tests.`
      );
    }
  }
}

export async function dismissTourIfPresent(page: Page) {
  const overlay = page.locator('[data-tour-overlay="true"]').first();
  const skipButton = page.getByRole('button', { name: /skip tour/i });
  if (await overlay.isVisible({ timeout: 1500 }).catch(() => false)) {
    if (await skipButton.isVisible({ timeout: 1000 }).catch(() => false)) {
      await skipButton.click();
    }
    await overlay.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {});
  }
}

export async function clearBrowserAuthState(page: Page) {
  await page.context().clearCookies();
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => {
    try {
      localStorage.clear();
      sessionStorage.clear();
    } catch {
      // no-op
    }
  });
}

export async function loginAsAdmin(page: Page) {
  ensureCredentialsConfigured('admin');
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.getByLabel(/email/i).fill(credentials.admin.email);
  await page.getByLabel(/password/i).fill(credentials.admin.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 15000 });
  await dismissTourIfPresent(page);
}

export async function loginAsTeacher(page: Page) {
  ensureCredentialsConfigured('teacher');
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await page.getByLabel(/email/i).fill(credentials.teacher.email);
  await page.getByLabel(/password/i).fill(credentials.teacher.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 15000 });
  await dismissTourIfPresent(page);
}

export async function loginAsSuperAdmin(page: Page) {
  ensureCredentialsConfigured('superAdmin');
  await page.goto('/super-admin/login', { waitUntil: 'domcontentloaded' });
  await page.locator('input[type="email"], input[name="email"]').first().fill(credentials.superAdmin.email);
  await page.locator('input[type="password"], input[name="password"]').first().fill(credentials.superAdmin.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/.*\/super-admin\/dashboard/, { timeout: 15000 });
  await dismissTourIfPresent(page);
}

export function uniqueCourseTitle(prefix = 'E2E Course') {
  return `${prefix} ${Date.now()}`;
}
