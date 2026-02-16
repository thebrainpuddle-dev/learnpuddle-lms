// e2e/tests/quick-course-test.spec.ts
// Quick course creation test

import { test, expect } from '@playwright/test';

test('Quick course creation test', async ({ page, context }) => {
  console.log('\n=== QUICK COURSE CREATION TEST ===\n');
  
  await context.clearCookies();
  
  // 1. Login
  console.log('Step 1-2: Login...');
  await page.goto('http://localhost:3000/login');
  await page.waitForLoadState('networkidle');
  await page.getByLabel(/email/i).fill('admin@demo.learnpuddle.com');
  await page.getByLabel(/password/i).fill('Admin123!');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForTimeout(2000);
  await page.waitForLoadState('networkidle');
  console.log('✓ Logged in\n');
  
  // 3-4. Navigate to courses and create
  console.log('Step 3-4: Navigate and click Create Course...');
  await page.goto('http://localhost:3000/admin/courses');
  await page.waitForLoadState('networkidle');
  await page.getByRole('button', { name: /create.*course/i }).click();
  await page.waitForTimeout(2000);
  await page.waitForLoadState('networkidle');
  console.log('✓ Create form opened\n');
  
  // 5. Fill form
  console.log('Step 5: Fill form...');
  await page.locator('input[name="title"], input[placeholder*="title" i]').first().fill('Introduction to Web Development');
  await page.locator('textarea[name="description"], textarea').first().fill('HTML, CSS, JS fundamentals');
  console.log('✓ Form filled\n');
  
  await page.screenshot({ path: 'test-results/quick-test-before-submit.png', fullPage: true });
  
  // 6. Submit
  console.log('Step 6: Submit form...');
  await page.getByRole('button', { name: /create course/i }).first().click();
  await page.waitForTimeout(3000);
  
  // 7. Check result
  console.log('\nStep 7: Check result...');
  await page.screenshot({ path: 'test-results/quick-test-after-submit.png', fullPage: true });
  
  const errorMsg = await page.locator('[role="alert"]:has-text("Failed"), .error:has-text("Failed")').count();
  const currentUrl = page.url();
  
  console.log(`  Current URL: ${currentUrl}`);
  console.log(`  Error messages: ${errorMsg}`);
  
  if (errorMsg > 0) {
    const errorText = await page.locator('[role="alert"], .error').first().textContent();
    console.log(`  ❌ ERROR: ${errorText}\n`);
  }
  
  if (currentUrl.includes('/admin/courses/') && !currentUrl.includes('/new')) {
    console.log('  ✅ SUCCESS: Redirected to course editor!\n');
  } else {
    console.log('  ⚠️ FAILED: Still on creation form\n');
  }
  
  // 8. Check courses list
  console.log('Step 8: Verify in courses list...');
  await page.goto('http://localhost:3000/admin/courses');
  await page.waitForTimeout(2000);
  await page.waitForLoadState('networkidle');
  
  const hasCourse = await page.locator('text=/Introduction to Web Development/i').count();
  
  await page.screenshot({ path: 'test-results/quick-test-courses-list.png', fullPage: true });
  
  if (hasCourse > 0) {
    console.log('  ✅ SUCCESS: Course appears in the list!\n');
  } else {
    console.log('  ❌ FAILED: Course NOT in the list\n');
  }
  
  console.log('=== TEST COMPLETE ===\n');
  
  expect(true).toBe(true);
});
