// e2e/tests/auth.spec.ts
// Authentication flow E2E tests

import { test, expect, Page } from '@playwright/test';

// Test credentials (should be configured via environment variables in CI)
const TEST_TEACHER_EMAIL = process.env.E2E_TEACHER_EMAIL || 'teacher@demo.com';
const TEST_TEACHER_PASSWORD = process.env.E2E_TEACHER_PASSWORD || 'demo123';
const TEST_ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL || 'admin@demo.com';
const TEST_ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'demo123';

test.describe('Authentication', () => {
  test.beforeEach(async ({ page }) => {
    // Clear any existing auth state
    await page.context().clearCookies();
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
  });

  test.describe('Login Page', () => {
    test('should display login form', async ({ page }) => {
      await page.goto('/login');
      
      await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible();
      await expect(page.getByLabel(/email/i)).toBeVisible();
      await expect(page.getByLabel(/password/i)).toBeVisible();
      await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible();
      await expect(page.getByText(/forgot password/i)).toBeVisible();
      await expect(page.getByLabel(/remember me/i)).toBeVisible();
    });

    test('should show error on invalid credentials', async ({ page }) => {
      await page.goto('/login');
      
      await page.getByLabel(/email/i).fill('invalid@example.com');
      await page.getByLabel(/password/i).fill('wrongpassword');
      await page.getByRole('button', { name: /sign in/i }).click();
      
      // Should show error message
      await expect(page.getByText(/invalid|error|incorrect/i)).toBeVisible({ timeout: 10000 });
    });

    test('should login as teacher successfully', async ({ page }) => {
      await page.goto('/login');
      
      await page.getByLabel(/email/i).fill(TEST_TEACHER_EMAIL);
      await page.getByLabel(/password/i).fill(TEST_TEACHER_PASSWORD);
      await page.getByRole('button', { name: /sign in/i }).click();
      
      // Should redirect to teacher dashboard
      await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 10000 });
      await expect(page.getByText(/dashboard|welcome/i)).toBeVisible();
    });

    test('should login as admin successfully', async ({ page }) => {
      await page.goto('/login');
      
      await page.getByLabel(/email/i).fill(TEST_ADMIN_EMAIL);
      await page.getByLabel(/password/i).fill(TEST_ADMIN_PASSWORD);
      await page.getByRole('button', { name: /sign in/i }).click();
      
      // Should redirect to admin dashboard
      await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 10000 });
    });

    test('should persist session with Remember Me', async ({ page }) => {
      await page.goto('/login');
      
      await page.getByLabel(/email/i).fill(TEST_TEACHER_EMAIL);
      await page.getByLabel(/password/i).fill(TEST_TEACHER_PASSWORD);
      await page.getByLabel(/remember me/i).check();
      await page.getByRole('button', { name: /sign in/i }).click();
      
      await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 10000 });
      
      // Verify token is in localStorage (not sessionStorage)
      const hasLocalToken = await page.evaluate(() => {
        return localStorage.getItem('access_token') !== null;
      });
      expect(hasLocalToken).toBe(true);
    });

    test('should use session storage without Remember Me', async ({ page }) => {
      await page.goto('/login');
      
      await page.getByLabel(/email/i).fill(TEST_TEACHER_EMAIL);
      await page.getByLabel(/password/i).fill(TEST_TEACHER_PASSWORD);
      // Do NOT check Remember Me
      await page.getByRole('button', { name: /sign in/i }).click();
      
      await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 10000 });
      
      // Verify token is in sessionStorage (not localStorage)
      const hasSessionToken = await page.evaluate(() => {
        return sessionStorage.getItem('access_token') !== null;
      });
      expect(hasSessionToken).toBe(true);
    });
  });

  test.describe('Logout', () => {
    test('should logout successfully', async ({ page }) => {
      // First login
      await page.goto('/login');
      await page.getByLabel(/email/i).fill(TEST_TEACHER_EMAIL);
      await page.getByLabel(/password/i).fill(TEST_TEACHER_PASSWORD);
      await page.getByRole('button', { name: /sign in/i }).click();
      
      await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 10000 });
      
      // Click logout (usually in header or sidebar)
      await page.getByRole('button', { name: /logout|sign out/i }).click();
      
      // Should redirect to login
      await expect(page).toHaveURL(/.*\/login/, { timeout: 10000 });
      
      // Tokens should be cleared
      const hasTokens = await page.evaluate(() => {
        return sessionStorage.getItem('access_token') !== null ||
               localStorage.getItem('access_token') !== null;
      });
      expect(hasTokens).toBe(false);
    });
  });

  test.describe('Protected Routes', () => {
    test('should redirect to login when accessing protected route', async ({ page }) => {
      await page.goto('/teacher/dashboard');
      
      // Should redirect to login
      await expect(page).toHaveURL(/.*\/login/, { timeout: 10000 });
    });

    test('should redirect to admin dashboard after login', async ({ page }) => {
      // Start at protected route
      await page.goto('/admin/courses');
      
      // Should redirect to login
      await expect(page).toHaveURL(/.*\/login/);
      
      // Login as admin
      await page.getByLabel(/email/i).fill(TEST_ADMIN_EMAIL);
      await page.getByLabel(/password/i).fill(TEST_ADMIN_PASSWORD);
      await page.getByRole('button', { name: /sign in/i }).click();
      
      // Should go to admin dashboard (or originally requested page)
      await expect(page).toHaveURL(/.*\/admin/, { timeout: 10000 });
    });
  });

  test.describe('Password Reset', () => {
    test('should navigate to forgot password page', async ({ page }) => {
      await page.goto('/login');
      
      await page.getByText(/forgot password/i).click();
      
      await expect(page).toHaveURL(/.*\/forgot-password/);
      await expect(page.getByText(/reset.*password|forgot.*password/i)).toBeVisible();
    });

    test('should submit password reset request', async ({ page }) => {
      await page.goto('/forgot-password');
      
      await page.getByLabel(/email/i).fill('test@example.com');
      await page.getByRole('button', { name: /reset|send|submit/i }).click();
      
      // Should show success message
      await expect(page.getByText(/email.*sent|check.*inbox|success/i)).toBeVisible({ timeout: 10000 });
    });
  });
});
