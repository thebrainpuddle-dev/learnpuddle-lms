// e2e/tests/auth.spec.ts
// Authentication flow E2E tests

import { test, expect } from '@playwright/test';
import {
  clearBrowserAuthState,
  credentials,
  dismissTourIfPresent,
  ensureCredentialsConfigured,
} from './helpers/auth';

async function fillTenantLogin(page: any, email: string, password: string) {
  const emailInput = page.locator('input[name="email"]').first();
  const passwordInput = page.locator('input[name="password"]').first();
  await emailInput.fill(email);
  await passwordInput.fill(password);
}

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    await clearBrowserAuthState(page);
  });

  test('shows login form', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
    await expect(page.getByLabel(/remember me/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
  });

  test('shows error on invalid credentials', async ({ page }) => {
    await fillTenantLogin(page, 'invalid@example.com', 'wrong-password');
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/.*\/login/, { timeout: 10000 });
  });

  test('logs in teacher successfully', async ({ page }) => {
    ensureCredentialsConfigured('teacher');
    await fillTenantLogin(page, credentials.teacher.email, credentials.teacher.password);
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 15000 });
  });

  test('logs in successfully even when stale tokens exist in storage', async ({ page }) => {
    ensureCredentialsConfigured('teacher');
    await page.evaluate(() => {
      localStorage.setItem('access_token', 'stale-access-token');
      localStorage.setItem('refresh_token', 'stale-refresh-token');
      sessionStorage.setItem('access_token', 'stale-access-token');
      sessionStorage.setItem('refresh_token', 'stale-refresh-token');
    });

    await fillTenantLogin(page, credentials.teacher.email, credentials.teacher.password);
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 15000 });
  });

  test('logs in admin successfully', async ({ page }) => {
    ensureCredentialsConfigured('admin');
    await fillTenantLogin(page, credentials.admin.email, credentials.admin.password);
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 15000 });
  });

  test('stores tokens in localStorage with Remember Me', async ({ page }) => {
    ensureCredentialsConfigured('teacher');
    await fillTenantLogin(page, credentials.teacher.email, credentials.teacher.password);
    await page.getByLabel(/remember me/i).check();
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 15000 });

    const storageState = await page.evaluate(() => ({
      local: !!localStorage.getItem('access_token'),
      session: !!sessionStorage.getItem('access_token'),
    }));
    expect(storageState.local).toBe(true);
    expect(storageState.session).toBe(false);
  });

  test('stores tokens in sessionStorage without Remember Me', async ({ page }) => {
    ensureCredentialsConfigured('teacher');
    await fillTenantLogin(page, credentials.teacher.email, credentials.teacher.password);
    await page.getByRole('button', { name: /sign in/i }).click();

    await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 15000 });

    const storageState = await page.evaluate(() => ({
      local: !!localStorage.getItem('access_token'),
      session: !!sessionStorage.getItem('access_token'),
    }));
    expect(storageState.local).toBe(false);
    expect(storageState.session).toBe(true);
  });

  test('logs out successfully', async ({ page }) => {
    ensureCredentialsConfigured('teacher');
    await fillTenantLogin(page, credentials.teacher.email, credentials.teacher.password);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 15000 });
    await dismissTourIfPresent(page);

    const logoutButton = page.getByRole('button', { name: /logout|sign out/i }).first();
    if (!(await logoutButton.isVisible().catch(() => false))) {
      const mobileMenuButton = page.locator('button.lg\\:hidden').first();
      if (await mobileMenuButton.isVisible().catch(() => false)) {
        await mobileMenuButton.click();
      }
    }

    await expect(logoutButton).toBeVisible({ timeout: 5000 });
    await logoutButton.click();
    await expect(page).toHaveURL(/.*\/login/, { timeout: 10000 });

    const hasTokens = await page.evaluate(() => {
      return !!localStorage.getItem('access_token') || !!sessionStorage.getItem('access_token');
    });
    expect(hasTokens).toBe(false);
  });

  test('redirects unauthenticated access to login', async ({ page }) => {
    await page.goto('/teacher/dashboard', { waitUntil: 'domcontentloaded' }).catch(() => {});
    await expect(page).toHaveURL(/.*\/login/, { timeout: 10000 });
  });

  test('supports forgot-password navigation', async ({ page }) => {
    await page.getByText(/forgot password/i).click();
    await expect(page).toHaveURL(/.*\/forgot-password/, { timeout: 10000 });
    await expect(page.getByText(/forgot|reset password/i)).toBeVisible();
  });

  test('forces idle-timeout logout when stale session becomes active again', async ({ page }) => {
    ensureCredentialsConfigured('admin');
    await fillTenantLogin(page, credentials.admin.email, credentials.admin.password);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 15000 });
    await dismissTourIfPresent(page);

    await page.evaluate(() => {
      const staleTs = Date.now() - (31 * 60 * 1000);
      localStorage.setItem('auth:last_activity_at', String(staleTs));
    });

    await page.mouse.move(5, 5);
    await expect(page).toHaveURL(/.*\/login\?reason=idle_timeout/, { timeout: 15000 });
  });
});
