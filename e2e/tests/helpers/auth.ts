import { expect, Page } from '@playwright/test';

type RoleKey = 'teacher' | 'admin' | 'student' | 'superAdmin';

const localDefault = (value: string) => (process.env.CI ? '' : value);

export const credentials = {
  teacher: {
    email: (process.env.E2E_TEACHER_EMAIL || localDefault('teacher@demo.learnpuddle.com')).trim(),
    password: (process.env.E2E_TEACHER_PASSWORD || localDefault('Teacher@123')).trim(),
  },
  admin: {
    email: (process.env.E2E_ADMIN_EMAIL || localDefault('admin@demo.learnpuddle.com')).trim(),
    password: (process.env.E2E_ADMIN_PASSWORD || localDefault('Admin@123')).trim(),
  },
  student: {
    email: (process.env.E2E_STUDENT_EMAIL || localDefault('student@demo.learnpuddle.com')).trim(),
    password: (process.env.E2E_STUDENT_PASSWORD || localDefault('Student@123')).trim(),
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

export function tenantIdentifierInput(page: Page) {
  return page.locator('#identifier, input[name="identifier"], input[name="email"], input[type="email"]').first();
}

export function tenantPasswordInput(page: Page) {
  return page.locator('#password, input[name="password"], input[type="password"]').first();
}

export async function fillTenantLogin(page: Page, email: string, password: string) {
  await tenantIdentifierInput(page).fill(email);
  await tenantPasswordInput(page).fill(password);
}

export async function loginAsAdmin(page: Page) {
  ensureCredentialsConfigured('admin');
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await fillTenantLogin(page, credentials.admin.email, credentials.admin.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 15000 });
  await dismissTourIfPresent(page);
}

export async function loginAsTeacher(page: Page) {
  ensureCredentialsConfigured('teacher');
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await fillTenantLogin(page, credentials.teacher.email, credentials.teacher.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 15000 });
  await dismissTourIfPresent(page);
}

export async function loginAsStudent(page: Page) {
  ensureCredentialsConfigured('student');
  await page.goto('/login', { waitUntil: 'domcontentloaded' });
  await fillTenantLogin(page, credentials.student.email, credentials.student.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/.*\/student\/dashboard/, { timeout: 15000 });
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
