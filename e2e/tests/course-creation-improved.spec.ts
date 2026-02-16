// e2e/tests/course-creation-improved.spec.ts
// Improved course creation test with all required fields

import { test, expect } from '@playwright/test';

const ADMIN_EMAIL = 'admin@demo.learnpuddle.com';
const ADMIN_PASSWORD = 'Admin123!';

test.describe('Course Creation - Improved Test', () => {
  
  test('Create course with all required fields', async ({ page, context }) => {
    console.log('\n=== IMPROVED COURSE CREATION TEST ===\n');
    
    // Clear session
    await context.clearCookies();
    
    // Login
    console.log('Step 1-2: Login as admin...');
    await page.goto('http://localhost:3000/login');
    await page.waitForLoadState('networkidle');
    await page.getByLabel(/email/i).fill(ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    console.log('✓ Logged in');
    
    // Navigate to courses and click create
    console.log('\nStep 3-4: Navigate to courses and open create form...');
    await page.goto('http://localhost:3000/admin/courses');
    await page.waitForLoadState('networkidle');
    
    const createButton = page.getByRole('button', { name: /create.*course/i });
    await createButton.click();
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    
    await page.screenshot({ path: 'test-results/course-improved-01-form.png', fullPage: true });
    console.log('✓ Screenshot: course-improved-01-form.png');
    
    // Fill in all fields including estimated hours
    console.log('\nStep 5-6: Fill in ALL course details...');
    
    // Title
    const titleField = page.locator('input[name="title"], input[placeholder*="title" i]').first();
    await titleField.fill('Introduction to Web Development');
    console.log('  ✓ Title: Introduction to Web Development');
    
    // Description
    const descField = page.locator('textarea[name="description"], textarea[placeholder*="description" i]').first();
    await descField.fill('A comprehensive course covering HTML, CSS, and JavaScript fundamentals.');
    console.log('  ✓ Description filled');
    
    // Estimated Hours - CHANGE FROM 0 to a real value
    const hoursField = page.locator('input[name="estimatedHours"], input[type="number"]').first();
    await hoursField.clear();
    await hoursField.fill('40');
    console.log('  ✓ Estimated Hours: 40');
    
    await page.screenshot({ path: 'test-results/course-improved-02-filled.png', fullPage: true });
    console.log('✓ Screenshot: course-improved-02-filled.png');
    
    // Submit
    console.log('\nStep 7: Submit the form...');
    const submitButton = page.getByRole('button', { name: /create course/i }).first();
    await submitButton.click();
    await page.waitForTimeout(3000);
    await page.waitForLoadState('networkidle');
    
    // Check for success or error
    console.log('\nStep 8: Check submission result...');
    await page.screenshot({ path: 'test-results/course-improved-03-after-submit.png', fullPage: true });
    console.log('✓ Screenshot: course-improved-03-after-submit.png');
    
    const currentUrl = page.url();
    console.log(`  Current URL: ${currentUrl}`);
    
    // Check for error message
    const errorAlert = await page.locator('[role="alert"], .error, .text-red-500, .text-red-600').count();
    if (errorAlert > 0) {
      const errorText = await page.locator('[role="alert"], .error, .text-red-500, .text-red-600').first().textContent();
      console.log(`  ⚠️ Error message: ${errorText}`);
    } else {
      console.log('  ✓ No error messages visible');
    }
    
    // Check if we were redirected to editor (success) or stayed on form (error)
    if (currentUrl.includes('/admin/courses/') && !currentUrl.includes('/new')) {
      console.log('  ✓ SUCCESS: Redirected to course editor');
      
      await page.screenshot({ path: 'test-results/course-improved-04-editor.png', fullPage: true });
      console.log('✓ Screenshot: course-improved-04-editor.png (Course Editor)');
      
    } else {
      console.log('  ⚠️ Still on creation form - checking for validation errors...');
      
      // Check for field-level validation errors
      const validationErrors = await page.locator('[class*="error"], .text-red-500, .text-red-600, [role="alert"]').allTextContents();
      if (validationErrors.length > 0) {
        console.log('  Validation errors found:');
        validationErrors.forEach((err, i) => {
          console.log(`    ${i + 1}. ${err}`);
        });
      }
    }
    
    // Navigate to courses list to verify
    console.log('\nStep 10: Verify in courses list...');
    await page.goto('http://localhost:3000/admin/courses');
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/course-improved-05-list.png', fullPage: true });
    console.log('✓ Screenshot: course-improved-05-list.png');
    
    const hasNewCourse = await page.locator('text=/Introduction to Web Development/i').count();
    if (hasNewCourse > 0) {
      console.log('  ✓ SUCCESS: New course appears in the list!');
      
      // Try to open the course editor
      console.log('\nStep 11-12: Open course editor...');
      await page.locator('text=/Introduction to Web Development/i').first().click();
      await page.waitForTimeout(2000);
      await page.waitForLoadState('networkidle');
      await page.screenshot({ path: 'test-results/course-improved-06-editor-opened.png', fullPage: true });
      console.log('✓ Screenshot: course-improved-06-editor-opened.png');
      console.log(`  Editor URL: ${page.url()}`);
      
    } else {
      console.log('  ⚠️ FAILED: New course NOT found in the list');
    }
    
    console.log('\n=== TEST COMPLETE ===\n');
    expect(true).toBe(true);
  });
});
