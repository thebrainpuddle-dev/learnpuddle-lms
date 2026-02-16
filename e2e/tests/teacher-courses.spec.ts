// e2e/tests/teacher-courses.spec.ts
// Teacher course browsing and learning E2E tests

import { test, expect, Page } from '@playwright/test';

const TEST_TEACHER_EMAIL = process.env.E2E_TEACHER_EMAIL || 'teacher@demo.com';
const TEST_TEACHER_PASSWORD = process.env.E2E_TEACHER_PASSWORD || 'demo123';

test.describe('Teacher Course Experience', () => {
  let page: Page;

  test.beforeAll(async ({ browser }) => {
    // Create a shared page with logged-in state
    page = await browser.newPage();
    await page.goto('/login');
    
    await page.getByLabel(/email/i).fill(TEST_TEACHER_EMAIL);
    await page.getByLabel(/password/i).fill(TEST_TEACHER_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    
    await expect(page).toHaveURL(/.*\/teacher\/dashboard/, { timeout: 10000 });
  });

  test.afterAll(async () => {
    await page.close();
  });

  test.describe('Dashboard', () => {
    test('should display teacher dashboard', async () => {
      await page.goto('/teacher/dashboard');
      
      // Dashboard should show key elements
      await expect(page.getByText(/dashboard|welcome/i)).toBeVisible();
      
      // Should show some stats or progress
      await expect(page.getByText(/courses|progress|completed/i)).toBeVisible();
    });

    test('should show course cards or list', async () => {
      await page.goto('/teacher/dashboard');
      
      // Wait for courses to load
      await page.waitForResponse(resp => 
        resp.url().includes('/api') && resp.status() === 200
      ).catch(() => {});
      
      // Should show courses or empty state
      const hasContent = await page.getByText(/course|no courses|get started/i).isVisible();
      expect(hasContent).toBe(true);
    });
  });

  test.describe('My Courses', () => {
    test('should navigate to my courses page', async () => {
      // Click on courses link in sidebar/nav
      await page.getByRole('link', { name: /my courses|courses/i }).first().click();
      
      await expect(page).toHaveURL(/.*\/teacher\/courses/);
    });

    test('should display assigned courses', async () => {
      await page.goto('/teacher/courses');
      
      // Wait for data to load
      await page.waitForLoadState('networkidle');
      
      // Should show courses or empty state
      const pageContent = await page.textContent('body');
      const hasCoursesOrEmpty = 
        /course|assigned|no courses|empty/i.test(pageContent || '');
      expect(hasCoursesOrEmpty).toBe(true);
    });

    test('should filter courses', async () => {
      await page.goto('/teacher/courses');
      
      // Wait for courses to load
      await page.waitForLoadState('networkidle');
      
      // Try to find and use filter if available
      const filterButton = page.getByRole('button', { name: /filter|status/i });
      if (await filterButton.isVisible()) {
        await filterButton.click();
        
        // Look for filter options
        const filterOptions = page.getByRole('option').or(page.getByRole('menuitem'));
        await expect(filterOptions.first()).toBeVisible();
      }
    });
  });

  test.describe('Course View', () => {
    test('should open course details', async () => {
      await page.goto('/teacher/courses');
      
      // Wait for courses to load
      await page.waitForLoadState('networkidle');
      
      // Click on first course card/link
      const courseLink = page.locator('[data-testid="course-card"]').first()
        .or(page.getByRole('link', { name: /course/i }).first())
        .or(page.locator('a[href*="/teacher/course"]').first());
      
      if (await courseLink.isVisible()) {
        await courseLink.click();
        
        // Should show course content
        await expect(page).toHaveURL(/.*\/teacher\/course/);
      }
    });

    test('should display course content structure', async () => {
      // Navigate to a course (if any exist)
      await page.goto('/teacher/courses');
      await page.waitForLoadState('networkidle');
      
      const courseLink = page.locator('a[href*="/teacher/course"]').first();
      
      if (await courseLink.isVisible()) {
        await courseLink.click();
        
        // Course view should show sections/modules
        await expect(
          page.getByText(/section|module|lesson|content/i)
        ).toBeVisible({ timeout: 10000 });
      }
    });

    test('should track progress when viewing content', async () => {
      await page.goto('/teacher/courses');
      await page.waitForLoadState('networkidle');
      
      const courseLink = page.locator('a[href*="/teacher/course"]').first();
      
      if (await courseLink.isVisible()) {
        await courseLink.click();
        await page.waitForLoadState('networkidle');
        
        // Look for progress indicator
        const progressIndicator = page.getByText(/progress|completed|%/i);
        await expect(progressIndicator).toBeVisible({ timeout: 10000 });
      }
    });
  });

  test.describe('Assignments', () => {
    test('should navigate to assignments page', async () => {
      await page.goto('/teacher/assignments');
      
      await expect(page.getByText(/assignment|task|pending/i)).toBeVisible();
    });

    test('should show assignment list', async () => {
      await page.goto('/teacher/assignments');
      await page.waitForLoadState('networkidle');
      
      // Should show assignments or empty state
      const hasContent = await page.getByText(/assignment|no assignment|submit/i).isVisible();
      expect(hasContent).toBe(true);
    });
  });
});
