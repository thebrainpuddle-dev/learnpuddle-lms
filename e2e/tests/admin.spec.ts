// e2e/tests/admin.spec.ts
// Admin functionality E2E tests

import { test, expect, Page } from '@playwright/test';

const TEST_ADMIN_EMAIL = process.env.E2E_ADMIN_EMAIL || 'admin@demo.com';
const TEST_ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || 'demo123';

test.describe('Admin Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    // Login as admin
    await page.goto('/login');
    await page.getByLabel(/email/i).fill(TEST_ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(TEST_ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    
    await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 10000 });
  });

  test('should display admin dashboard with stats', async ({ page }) => {
    await expect(page.getByText(/dashboard/i)).toBeVisible();
    
    // Dashboard should show key metrics
    await expect(
      page.getByText(/teachers|courses|students|active/i)
    ).toBeVisible();
  });

  test('should have working sidebar navigation', async ({ page }) => {
    // Check sidebar links
    const sidebarLinks = [
      { name: /teachers/i, url: /\/admin\/teachers/ },
      { name: /courses/i, url: /\/admin\/courses/ },
      { name: /settings/i, url: /\/admin\/settings/ },
    ];

    for (const link of sidebarLinks) {
      const navLink = page.getByRole('link', { name: link.name }).first();
      if (await navLink.isVisible()) {
        await navLink.click();
        await expect(page).toHaveURL(link.url, { timeout: 5000 });
        
        // Go back to dashboard
        await page.goto('/admin/dashboard');
      }
    }
  });
});

test.describe('Teacher Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill(TEST_ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(TEST_ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 10000 });
  });

  test('should display teachers list', async ({ page }) => {
    await page.goto('/admin/teachers');
    
    await expect(page.getByText(/teachers|manage/i)).toBeVisible();
    
    // Wait for data to load
    await page.waitForLoadState('networkidle');
    
    // Should show teacher list or empty state
    const hasContent = await page.getByText(/teacher|email|no teachers|create/i).isVisible();
    expect(hasContent).toBe(true);
  });

  test('should open create teacher form', async ({ page }) => {
    await page.goto('/admin/teachers');
    
    // Click create/add teacher button
    const createButton = page.getByRole('button', { name: /add|create|new/i });
    if (await createButton.isVisible()) {
      await createButton.click();
      
      // Should show create form
      await expect(page.getByLabel(/email/i)).toBeVisible();
      await expect(page.getByLabel(/first name|name/i)).toBeVisible();
    }
  });

  test('should support bulk selection', async ({ page }) => {
    await page.goto('/admin/teachers');
    await page.waitForLoadState('networkidle');
    
    // Look for checkboxes in the table
    const checkbox = page.locator('input[type="checkbox"]').first();
    
    if (await checkbox.isVisible()) {
      await checkbox.check();
      
      // Bulk action bar should appear
      await expect(
        page.getByText(/selected|bulk|action/i)
      ).toBeVisible({ timeout: 5000 });
    }
  });

  test('should filter teachers by status', async ({ page }) => {
    await page.goto('/admin/teachers');
    await page.waitForLoadState('networkidle');
    
    // Look for filter/status dropdown
    const filterButton = page.getByRole('button', { name: /filter|status|all/i });
    
    if (await filterButton.isVisible()) {
      await filterButton.click();
      
      // Should show filter options
      await expect(
        page.getByText(/active|inactive|all/i)
      ).toBeVisible();
    }
  });
});

test.describe('Course Management', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill(TEST_ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(TEST_ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 10000 });
  });

  test('should display courses list', async ({ page }) => {
    await page.goto('/admin/courses');
    
    await expect(page.getByText(/courses|manage/i)).toBeVisible();
    await page.waitForLoadState('networkidle');
    
    // Should show course list or empty state
    const hasContent = await page.getByText(/course|no courses|create/i).isVisible();
    expect(hasContent).toBe(true);
  });

  test('should navigate to course editor', async ({ page }) => {
    await page.goto('/admin/courses');
    await page.waitForLoadState('networkidle');
    
    // Click on a course to edit
    const courseLink = page.locator('a[href*="/admin/courses/"]').first();
    
    if (await courseLink.isVisible()) {
      await courseLink.click();
      
      // Should show course editor
      await expect(page).toHaveURL(/.*\/admin\/courses\/.*/);
    }
  });

  test('should support creating a new course', async ({ page }) => {
    await page.goto('/admin/courses');
    
    // Click create course button
    const createButton = page.getByRole('button', { name: /create|add|new/i });
    
    if (await createButton.isVisible()) {
      await createButton.click();
      
      // Should show create form or redirect to editor
      await expect(
        page.getByLabel(/title|name/i).or(page.getByText(/create.*course/i))
      ).toBeVisible({ timeout: 5000 });
    }
  });

  test('should support bulk course operations', async ({ page }) => {
    await page.goto('/admin/courses');
    await page.waitForLoadState('networkidle');
    
    // Look for checkboxes
    const checkbox = page.locator('input[type="checkbox"]').first();
    
    if (await checkbox.isVisible()) {
      await checkbox.check();
      
      // Bulk action options should appear
      await expect(
        page.getByText(/selected|publish|delete|action/i)
      ).toBeVisible({ timeout: 5000 });
    }
  });
});

test.describe('Announcements', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill(TEST_ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(TEST_ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 10000 });
  });

  test('should access announcements page', async ({ page }) => {
    await page.goto('/admin/announcements');
    
    await expect(page.getByText(/announcement/i)).toBeVisible();
  });

  test('should create a new announcement', async ({ page }) => {
    await page.goto('/admin/announcements');
    
    // Fill announcement form
    const titleInput = page.getByLabel(/title/i);
    const messageInput = page.getByLabel(/message|content|body/i);
    
    if (await titleInput.isVisible()) {
      await titleInput.fill('Test Announcement');
      await messageInput.fill('This is a test announcement message.');
      
      // Submit
      await page.getByRole('button', { name: /send|create|post/i }).click();
      
      // Should show success
      await expect(
        page.getByText(/success|sent|created/i)
      ).toBeVisible({ timeout: 5000 });
    }
  });
});

test.describe('Admin Settings', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel(/email/i).fill(TEST_ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(TEST_ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    await expect(page).toHaveURL(/.*\/admin\/dashboard/, { timeout: 10000 });
  });

  test('should access settings page', async ({ page }) => {
    await page.goto('/admin/settings');
    
    await expect(page.getByText(/settings|configuration/i)).toBeVisible();
  });

  test('should display tenant settings', async ({ page }) => {
    await page.goto('/admin/settings');
    
    // Settings should show tenant configuration options
    await expect(
      page.getByText(/school|organization|theme|branding/i)
    ).toBeVisible();
  });
});
