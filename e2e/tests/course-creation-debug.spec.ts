// e2e/tests/course-creation-debug.spec.ts
// Debug course creation with network monitoring

import { test, expect } from '@playwright/test';

const ADMIN_EMAIL = 'admin@demo.learnpuddle.com';
const ADMIN_PASSWORD = 'Admin123!';

test.describe('Course Creation - Debug with Network Monitoring', () => {
  
  test('Create course and monitor network calls', async ({ page, context }) => {
    console.log('\n=== COURSE CREATION DEBUG TEST ===\n');
    
    // Monitor network requests
    const requests: any[] = [];
    const responses: any[] = [];
    
    page.on('request', request => {
      if (request.url().includes('/api/') || request.url().includes('/courses')) {
        requests.push({
          url: request.url(),
          method: request.method(),
          postData: request.postData()
        });
      }
    });
    
    page.on('response', async response => {
      if (response.url().includes('/api/') || response.url().includes('/courses')) {
        try {
          const body = await response.text();
          responses.push({
            url: response.url(),
            status: response.status(),
            statusText: response.statusText(),
            body: body.substring(0, 500) // First 500 chars
          });
        } catch (e) {
          // Ignore
        }
      }
    });
    
    // Monitor console logs
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.log(`  [BROWSER ERROR] ${msg.text()}`);
      }
    });
    
    // Clear session and login
    await context.clearCookies();
    await page.goto('http://localhost:3000/login');
    await page.waitForLoadState('networkidle');
    await page.getByLabel(/email/i).fill(ADMIN_EMAIL);
    await page.getByLabel(/password/i).fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    console.log('✓ Logged in\n');
    
    // Clear previous requests/responses
    requests.length = 0;
    responses.length = 0;
    
    // Navigate to courses and open create form
    await page.goto('http://localhost:3000/admin/courses');
    await page.waitForLoadState('networkidle');
    
    const createButton = page.getByRole('button', { name: /create.*course/i });
    await createButton.click();
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    
    console.log('Course Creation Form:');
    console.log('  URL:', page.url());
    
    // Fill form with all required data
    const titleField = page.locator('input[name="title"], input[placeholder*="title" i]').first();
    await titleField.fill('Introduction to Web Development - Test');
    
    const descField = page.locator('textarea[name="description"], textarea[placeholder*="description" i]').first();
    await descField.fill('A comprehensive course covering HTML, CSS, and JavaScript fundamentals.');
    
    const hoursField = page.locator('input[name="estimatedHours"], input[type="number"]').first();
    await hoursField.clear();
    await hoursField.fill('40');
    
    console.log('  ✓ Form filled\n');
    
    await page.screenshot({ path: 'test-results/course-debug-01-filled.png', fullPage: true });
    
    // Clear requests/responses before submission
    requests.length = 0;
    responses.length = 0;
    
    // Submit form
    console.log('Submitting form...');
    const submitButton = page.getByRole('button', { name: /create course/i }).first();
    await submitButton.click();
    
    // Wait for network activity to complete
    await page.waitForTimeout(5000);
    
    console.log('\nNetwork Activity:');
    console.log('=================\n');
    
    // Log requests
    if (requests.length > 0) {
      console.log('Requests sent:');
      requests.forEach((req, i) => {
        console.log(`  ${i + 1}. ${req.method} ${req.url}`);
        if (req.postData) {
          console.log(`     Data: ${req.postData.substring(0, 200)}`);
        }
      });
      console.log('');
    } else {
      console.log('No API requests captured\n');
    }
    
    // Log responses
    if (responses.length > 0) {
      console.log('Responses received:');
      responses.forEach((res, i) => {
        console.log(`  ${i + 1}. ${res.status} ${res.statusText} - ${res.url}`);
        if (res.body) {
          console.log(`     Body: ${res.body}`);
        }
      });
      console.log('');
    } else {
      console.log('No API responses captured\n');
    }
    
    // Check current state
    await page.screenshot({ path: 'test-results/course-debug-02-after-submit.png', fullPage: true });
    
    const currentUrl = page.url();
    console.log('After Submission:');
    console.log(`  URL: ${currentUrl}`);
    
    // Check for messages
    const errorMsg = await page.locator('[role="alert"], .error, .text-red-500, .text-red-600').allTextContents();
    const successMsg = await page.locator('.success, .text-green-500, .text-green-600').allTextContents();
    
    if (errorMsg.length > 0) {
      console.log(`  ⚠️ Error messages:`, errorMsg);
    }
    if (successMsg.length > 0) {
      console.log(`  ✓ Success messages:`, successMsg);
    }
    
    // Verify in courses list
    console.log('\nVerifying in courses list...');
    await page.goto('http://localhost:3000/admin/courses');
    await page.waitForTimeout(3000);
    await page.waitForLoadState('networkidle');
    
    const hasNewCourse = await page.locator('text=/Introduction to Web Development.*Test/i').count();
    console.log(`  Course in list: ${hasNewCourse > 0 ? 'YES ✓' : 'NO ⚠️'}`);
    
    await page.screenshot({ path: 'test-results/course-debug-03-list.png', fullPage: true });
    
    console.log('\n=== DEBUG TEST COMPLETE ===\n');
    expect(true).toBe(true);
  });
});
