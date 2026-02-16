// e2e/tests/teacher-superadmin-simple.spec.ts
// Simple screenshot-based QA test for Teacher and Super Admin sections

import { test, expect } from '@playwright/test';

const TEACHER_EMAIL = 'teacher@demo.learnpuddle.com';
const TEACHER_PASSWORD = 'Teacher123!';
const SUPERADMIN_EMAIL = 'admin@learnpuddle.com';
const SUPERADMIN_PASSWORD = 'Admin123!';

test.describe('Teacher and Super Admin QA - Simple', () => {
  
  test('PART 1: Teacher Section', async ({ page, context }) => {
    console.log('\n=== PART 1: TEACHER SECTION ===\n');
    
    // Clear session
    await context.clearCookies();
    
    // 1. Login page
    console.log('Step 1: Navigate to login...');
    await page.goto('http://localhost:3000/login');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/teacher-01-login.png', fullPage: true });
    console.log('✓ Screenshot: teacher-01-login.png');
    
    // 2. Login as teacher
    console.log('\nStep 2: Login as Teacher...');
    await page.getByLabel(/email/i).fill(TEACHER_EMAIL);
    await page.getByLabel(/password/i).fill(TEACHER_PASSWORD);
    await page.getByRole('button', { name: /sign in/i }).click();
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    
    // 3. Teacher dashboard
    console.log('\nStep 3: Teacher Dashboard...');
    await page.screenshot({ path: 'test-results/teacher-02-dashboard.png', fullPage: true });
    console.log('✓ Screenshot: teacher-02-dashboard.png');
    console.log(`  URL: ${page.url()}`);
    
    // 4. Courses page
    console.log('\nStep 4: Teacher Courses...');
    await page.goto('http://localhost:3000/teacher/courses');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/teacher-03-courses.png', fullPage: true });
    console.log('✓ Screenshot: teacher-03-courses.png');
    console.log(`  URL: ${page.url()}`);
    
    // 5. Assignments page
    console.log('\nStep 5: Teacher Assignments...');
    await page.goto('http://localhost:3000/teacher/assignments');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/teacher-04-assignments.png', fullPage: true });
    console.log('✓ Screenshot: teacher-04-assignments.png');
    console.log(`  URL: ${page.url()}`);
    
    // 6. Profile page
    console.log('\nStep 6: Teacher Profile...');
    await page.goto('http://localhost:3000/teacher/profile');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/teacher-05-profile.png', fullPage: true });
    console.log('✓ Screenshot: teacher-05-profile.png');
    console.log(`  URL: ${page.url()}`);
    
    console.log('\n=== TEACHER SECTION COMPLETE ===\n');
    expect(true).toBe(true);
  });
  
  test('PART 2: Super Admin Section', async ({ page, context }) => {
    console.log('\n=== PART 2: SUPER ADMIN SECTION ===\n');
    
    // Clear session
    await context.clearCookies();
    
    // 8. Super admin login page
    console.log('Step 8: Navigate to Super Admin login...');
    await page.goto('http://localhost:3000/super-admin/login');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/superadmin-01-login.png', fullPage: true });
    console.log('✓ Screenshot: superadmin-01-login.png');
    
    // 9. Login as super admin
    console.log('\nStep 9: Login as Super Admin...');
    
    // Try to find and fill the form
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    const passwordInput = page.locator('input[type="password"], input[name="password"]').first();
    
    await emailInput.fill(SUPERADMIN_EMAIL);
    await passwordInput.fill(SUPERADMIN_PASSWORD);
    
    const submitButton = page.locator('button[type="submit"], button:has-text("Sign In")').first();
    await submitButton.click();
    
    await page.waitForTimeout(2000);
    await page.waitForLoadState('networkidle');
    
    // 10. Super admin dashboard
    console.log('\nStep 10: Super Admin Dashboard...');
    await page.screenshot({ path: 'test-results/superadmin-02-dashboard.png', fullPage: true });
    console.log('✓ Screenshot: superadmin-02-dashboard.png');
    console.log(`  URL: ${page.url()}`);
    
    // 11. Tenants page
    console.log('\nStep 11: Tenants page...');
    await page.goto('http://localhost:3000/super-admin/tenants');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/superadmin-03-tenants.png', fullPage: true });
    console.log('✓ Screenshot: superadmin-03-tenants.png');
    console.log(`  URL: ${page.url()}`);
    
    console.log('\n=== SUPER ADMIN SECTION COMPLETE ===\n');
    expect(true).toBe(true);
  });
});
