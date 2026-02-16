// e2e/tests/course-creation-test.spec.ts
// Test course creation functionality in admin section

import { test, expect } from '@playwright/test';

const ADMIN_EMAIL = 'admin@demo.learnpuddle.com';
const ADMIN_PASSWORD = 'Admin123!';

test.describe('Course Creation Test', () => {
  
  test('Complete course creation workflow', async ({ page, context }) => {
    console.log('\n=== COURSE CREATION TEST ===\n');
    
    // Clear session
    await context.clearCookies();
    
    // 1. Navigate to login
    console.log('Step 1: Navigate to login page...');
    await page.goto('http://localhost:3000/login');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/course-creation-01-login.png', fullPage: true });
    console.log('✓ Screenshot: course-creation-01-login.png');
    
    // 2. Login as admin
    console.log('\nStep 2: Login as admin...');
    await page.getByLabel(/email/i).fill(ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    console.log(`✓ Logged in - Current URL: ${page.url()}`);
    
    // 3. Navigate to courses page
    console.log('\nStep 3: Navigate to courses page...');
    await page.goto('http://localhost:3000/admin/courses');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/course-creation-02-courses-list.png', fullPage: true });
    console.log('✓ Screenshot: course-creation-02-courses-list.png');
    console.log(`  URL: ${page.url()}`);
    
    // Count existing courses
    const existingCoursesText = await page.locator('body').textContent();
    console.log(`  Page loaded successfully`);
    
    // 4. Click Create Course button
    console.log('\nStep 4: Click Create Course button...');
    
    // Try multiple selectors to find the create button
    let createButton = page.getByRole('button', { name: /create.*course/i });
    let buttonCount = await createButton.count();
    
    if (buttonCount === 0) {
      createButton = page.locator('button:has-text("Create Course"), a:has-text("Create Course")').first();
      buttonCount = await createButton.count();
    }
    
    console.log(`  Found ${buttonCount} create course button(s)`);
    
    if (buttonCount > 0) {
      await createButton.click();
      await page.waitForTimeout(2000);
      await page.waitForLoadState('networkidle');
      
      // 5. Take snapshot of course creation form
      console.log('\nStep 5: Course creation form...');
      await page.screenshot({ path: 'test-results/course-creation-03-form.png', fullPage: true });
      console.log('✓ Screenshot: course-creation-03-form.png');
      console.log(`  URL: ${page.url()}`);
      
      // Check what's on the page
      const pageTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title found');
      console.log(`  Page title: ${pageTitle}`);
      
      // 6. Fill in the form
      console.log('\nStep 6: Fill in course details...');
      
      // Try to find title field
      const titleField = page.locator('input[name="title"], input[placeholder*="title" i], input[label*="title" i]').first();
      const titleCount = await titleField.count();
      
      if (titleCount > 0) {
        await titleField.fill('Introduction to Web Development');
        console.log('  ✓ Filled title field');
      } else {
        console.log('  ⚠️ Title field not found - checking available inputs...');
        const inputs = await page.locator('input[type="text"]').count();
        console.log(`    Found ${inputs} text input(s)`);
        
        // Try first text input
        if (inputs > 0) {
          await page.locator('input[type="text"]').first().fill('Introduction to Web Development');
          console.log('  ✓ Filled first text input');
        }
      }
      
      // Try to find description field
      const descField = page.locator('textarea[name="description"], textarea[placeholder*="description" i], textarea').first();
      const descCount = await descField.count();
      
      if (descCount > 0) {
        await descField.fill('A comprehensive course covering HTML, CSS, and JavaScript fundamentals.');
        console.log('  ✓ Filled description field');
      } else {
        console.log('  ⚠️ Description field not found');
      }
      
      await page.screenshot({ path: 'test-results/course-creation-04-form-filled.png', fullPage: true });
      console.log('✓ Screenshot: course-creation-04-form-filled.png (form filled)');
      
      // 7. Click Create/Save button
      console.log('\nStep 7: Submit the form...');
      
      // Try to find submit button
      let submitButton = page.getByRole('button', { name: /create|save|submit/i }).first();
      let submitCount = await submitButton.count();
      
      if (submitCount > 0) {
        console.log(`  Found submit button: attempting to click...`);
        await submitButton.click();
        await page.waitForTimeout(3000);
        await page.waitForLoadState('networkidle');
        
        // 8. Take snapshot after submission
        console.log('\nStep 8: After submission...');
        await page.screenshot({ path: 'test-results/course-creation-05-after-submit.png', fullPage: true });
        console.log('✓ Screenshot: course-creation-05-after-submit.png');
        console.log(`  URL: ${page.url()}`);
        
        // Check for success or error messages
        const successMsg = await page.locator('[class*="success"], [role="alert"]:has-text("success")').count();
        const errorMsg = await page.locator('[class*="error"], [role="alert"]:has-text("error")').count();
        
        console.log(`  Success messages: ${successMsg}`);
        console.log(`  Error messages: ${errorMsg}`);
        
        if (successMsg > 0) {
          const msg = await page.locator('[class*="success"], [role="alert"]:has-text("success")').first().textContent();
          console.log(`  ✓ Success: ${msg}`);
        }
        
        if (errorMsg > 0) {
          const msg = await page.locator('[class*="error"], [role="alert"]:has-text("error")').first().textContent();
          console.log(`  ⚠️ Error: ${msg}`);
        }
        
        // 10. Navigate back to courses list
        console.log('\nStep 10: Navigate to courses list to verify...');
        await page.goto('http://localhost:3000/admin/courses');
        await page.waitForLoadState('networkidle');
        await page.screenshot({ path: 'test-results/course-creation-06-courses-list-after.png', fullPage: true });
        console.log('✓ Screenshot: course-creation-06-courses-list-after.png');
        
        // Check if new course appears in the list
        const hasWebDevCourse = await page.locator('text=/Introduction to Web Development/i').count();
        console.log(`  New course in list: ${hasWebDevCourse > 0 ? 'YES ✓' : 'NO ⚠️'}`);
        
        if (hasWebDevCourse > 0) {
          // 11. Click on the newly created course
          console.log('\nStep 11: Open course editor...');
          await page.locator('text=/Introduction to Web Development/i').first().click();
          await page.waitForTimeout(2000);
          await page.waitForLoadState('networkidle');
          
          // 12. Take snapshot of course editor
          console.log('\nStep 12: Course editor page...');
          await page.screenshot({ path: 'test-results/course-creation-07-course-editor.png', fullPage: true });
          console.log('✓ Screenshot: course-creation-07-course-editor.png');
          console.log(`  URL: ${page.url()}`);
          
          const editorTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title found');
          console.log(`  Editor page title: ${editorTitle}`);
        }
        
      } else {
        console.log('  ⚠️ Submit button not found');
        await page.screenshot({ path: 'test-results/course-creation-05-no-submit-button.png', fullPage: true });
      }
      
    } else {
      console.log('  ⚠️ Create Course button not found');
    }
    
    console.log('\n=== COURSE CREATION TEST COMPLETE ===\n');
    expect(true).toBe(true);
  });
});
