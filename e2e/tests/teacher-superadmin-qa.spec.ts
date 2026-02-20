// e2e/tests/teacher-superadmin-qa.spec.ts
// Comprehensive QA test for Teacher and Super Admin sections

import { test, expect } from '@playwright/test';

const TEACHER_EMAIL = 'teacher@demo.learnpuddle.com';
const TEACHER_PASSWORD = 'Teacher123!';
const SUPERADMIN_EMAIL = 'admin@learnpuddle.com';
const SUPERADMIN_PASSWORD = 'Admin123!';

test.describe.skip('Teacher and Super Admin QA Tests', () => {
  
  test('PART 1: Teacher Section - Complete Walkthrough', async ({ page, context }) => {
    console.log('\n=== PART 1: TEACHER SECTION ===\n');
    
    // Clear any existing session
    console.log('Step 0: Clearing existing session...');
    await context.clearCookies();
    await page.goto('http://localhost:3000/login');
    await page.waitForLoadState('networkidle');
    
    // 1. Navigate to login page
    console.log('Step 1: On login page...');
    await page.screenshot({ path: 'test-results/teacher-qa-01-login-page.png', fullPage: true });
    console.log('✓ Login page - Screenshot saved');
    
    const loginErrors = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600, .text-red-700').count();
    console.log(`  - Visible errors on login page: ${loginErrors}`);
    
    // 2. Login as Teacher
    console.log('\nStep 2: Logging in as Teacher...');
    try {
      await page.getByLabel(/email/i).fill(TEACHER_EMAIL);
      await page.getByLabel(/password/i).fill(TEACHER_PASSWORD);
      await page.getByRole('button', { name: /sign in/i }).click();
      
      // Wait for navigation
      await page.waitForTimeout(3000);
      await page.waitForLoadState('networkidle');
      
      const currentUrl = page.url();
      console.log(`  - Current URL after login: ${currentUrl}`);
      
      // Check if we're on a teacher page or if there's an error
      const pageContent = await page.content();
      const hasError = pageContent.toLowerCase().includes('error') || 
                       pageContent.toLowerCase().includes('invalid') ||
                       pageContent.toLowerCase().includes('incorrect');
      
      if (hasError || currentUrl.includes('/login')) {
        console.log('  ⚠️ Login may have failed - still on login page or error detected');
        await page.screenshot({ path: 'test-results/teacher-qa-02-login-error.png', fullPage: true });
        
        // Check for visible error messages
        const errorMsg = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600').first().textContent().catch(() => 'No error message found');
        console.log(`  - Error message: ${errorMsg}`);
      }
      
    } catch (error) {
      console.log(`  ⚠️ Login error: ${error}`);
      await page.screenshot({ path: 'test-results/teacher-qa-02-login-error.png', fullPage: true });
    }
    
    // 3. Take snapshot of teacher dashboard
    console.log('\nStep 3: Teacher Dashboard...');
    await page.screenshot({ path: 'test-results/teacher-qa-03-dashboard.png', fullPage: true });
    console.log('✓ Teacher dashboard - Screenshot saved');
    
    const currentUrl = page.url();
    console.log(`  - Current URL: ${currentUrl}`);
    
    const dashboardTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title found');
    console.log(`  - Page title: ${dashboardTitle}`);
    
    const dashboardErrors = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600, .text-red-700').count();
    console.log(`  - Visible errors: ${dashboardErrors}`);
    
    const hasTeacherNav = await page.locator('a[href*="/teacher/"]').count();
    console.log(`  - Teacher navigation links found: ${hasTeacherNav}`);
    
    // 4. Navigate to teacher courses
    console.log('\nStep 4: Navigating to Teacher Courses...');
    await page.goto('http://localhost:3000/teacher/courses');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/teacher-qa-04-courses.png', fullPage: true });
    console.log('✓ Teacher courses page - Screenshot saved');
    
    const coursesUrl = page.url();
    console.log(`  - Current URL: ${coursesUrl}`);
    
    const coursesTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title found');
    console.log(`  - Page title: ${coursesTitle}`);
    
    const coursesErrors = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600, .text-red-700').count();
    console.log(`  - Visible errors: ${coursesErrors}`);
    
    const coursesList = await page.locator('[class*="course"], [class*="card"]').count();
    console.log(`  - Course items found: ${coursesList}`);
    
    // 5. Navigate to teacher assignments
    console.log('\nStep 5: Navigating to Teacher Assignments...');
    await page.goto('http://localhost:3000/teacher/assignments');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/teacher-qa-05-assignments.png', fullPage: true });
    console.log('✓ Teacher assignments page - Screenshot saved');
    
    const assignmentsUrl = page.url();
    console.log(`  - Current URL: ${assignmentsUrl}`);
    
    const assignmentsTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title found');
    console.log(`  - Page title: ${assignmentsTitle}`);
    
    const assignmentsErrors = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600, .text-red-700').count();
    console.log(`  - Visible errors: ${assignmentsErrors}`);
    
    const assignmentsList = await page.locator('table, [role="table"], [class*="assignment"]').count();
    console.log(`  - Assignment elements found: ${assignmentsList}`);
    
    // 6. Navigate to teacher profile
    console.log('\nStep 6: Navigating to Teacher Profile...');
    await page.goto('http://localhost:3000/teacher/profile');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/teacher-qa-06-profile.png', fullPage: true });
    console.log('✓ Teacher profile page - Screenshot saved');
    
    const profileUrl = page.url();
    console.log(`  - Current URL: ${profileUrl}`);
    
    const profileTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title found');
    console.log(`  - Page title: ${profileTitle}`);
    
    const profileErrors = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600, .text-red-700').count();
    console.log(`  - Visible errors: ${profileErrors}`);
    
    const profileForm = await page.locator('form, input, [class*="profile"]').count();
    console.log(`  - Profile form elements found: ${profileForm}`);
    
    console.log('\n=== TEACHER SECTION COMPLETE ===\n');
  });
  
  test('PART 2: Super Admin Section - Complete Walkthrough', async ({ page, context }) => {
    console.log('\n=== PART 2: SUPER ADMIN SECTION ===\n');
    
    // Clear any existing session
    console.log('Step 0: Clearing existing session...');
    await context.clearCookies();
    
    // 8. Navigate to super admin login
    console.log('Step 8: Navigating to Super Admin login...');
    await page.goto('http://localhost:3000/super-admin/login');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/superadmin-qa-08-login-page.png', fullPage: true });
    console.log('✓ Super Admin login page - Screenshot saved');
    
    const superAdminLoginUrl = page.url();
    console.log(`  - Current URL: ${superAdminLoginUrl}`);
    
    const loginTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title found');
    console.log(`  - Page title: ${loginTitle}`);
    
    const loginErrors = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600, .text-red-700').count();
    console.log(`  - Visible errors on login page: ${loginErrors}`);
    
    const hasLoginForm = await page.locator('form, input[type="email"], input[type="password"]').count();
    console.log(`  - Login form elements found: ${hasLoginForm}`);
    
    // 9. Login as Super Admin
    console.log('\nStep 9: Logging in as Super Admin...');
    try {
      // Check if email and password fields exist
      const emailField = await page.getByLabel(/email/i).count();
      const passwordField = await page.getByLabel(/password/i).count();
      
      if (emailField === 0 || passwordField === 0) {
        console.log('  ⚠️ Login form fields not found - checking page content...');
        const pageText = await page.locator('body').textContent();
        console.log(`  - Page contains: ${pageText?.substring(0, 200)}...`);
      } else {
        await page.getByLabel(/email/i).fill(SUPERADMIN_EMAIL);
        await page.getByLabel(/password/i).fill(SUPERADMIN_PASSWORD);
        
        const signInButton = await page.getByRole('button', { name: /sign in/i }).count();
        if (signInButton > 0) {
          await page.getByRole('button', { name: /sign in/i }).click();
        } else {
          console.log('  ⚠️ Sign in button not found');
        }
        
        // Wait for navigation
        await page.waitForTimeout(3000);
        await page.waitForLoadState('networkidle');
      }
      
      const currentUrl = page.url();
      console.log(`  - Current URL after login: ${currentUrl}`);
      
      // Check if we're on a super admin page or if there's an error
      const pageContent = await page.content();
      const hasError = pageContent.toLowerCase().includes('error') || 
                       pageContent.toLowerCase().includes('invalid') ||
                       pageContent.toLowerCase().includes('incorrect');
      
      if (hasError || currentUrl.includes('/login')) {
        console.log('  ⚠️ Login may have failed - still on login page or error detected');
        await page.screenshot({ path: 'test-results/superadmin-qa-09-login-error.png', fullPage: true });
        
        // Check for visible error messages
        const errorMsg = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600').first().textContent().catch(() => 'No error message found');
        console.log(`  - Error message: ${errorMsg}`);
      }
      
    } catch (error) {
      console.log(`  ⚠️ Login error: ${error}`);
      await page.screenshot({ path: 'test-results/superadmin-qa-09-login-error.png', fullPage: true });
    }
    
    // 10. Take snapshot of super admin dashboard
    console.log('\nStep 10: Super Admin Dashboard...');
    await page.screenshot({ path: 'test-results/superadmin-qa-10-dashboard.png', fullPage: true });
    console.log('✓ Super Admin dashboard - Screenshot saved');
    
    const dashboardUrl = page.url();
    console.log(`  - Current URL: ${dashboardUrl}`);
    
    const dashboardTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title found');
    console.log(`  - Page title: ${dashboardTitle}`);
    
    const dashboardErrors = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600, .text-red-700').count();
    console.log(`  - Visible errors: ${dashboardErrors}`);
    
    const hasSuperAdminNav = await page.locator('a[href*="/super-admin/"]').count();
    console.log(`  - Super Admin navigation links found: ${hasSuperAdminNav}`);
    
    // 11. Navigate to tenants page
    console.log('\nStep 11: Navigating to Tenants page...');
    await page.goto('http://localhost:3000/super-admin/tenants');
    await page.waitForLoadState('networkidle');
    await page.screenshot({ path: 'test-results/superadmin-qa-11-tenants.png', fullPage: true });
    console.log('✓ Tenants page - Screenshot saved');
    
    const tenantsUrl = page.url();
    console.log(`  - Current URL: ${tenantsUrl}`);
    
    const tenantsTitle = await page.locator('h1, h2').first().textContent().catch(() => 'No title found');
    console.log(`  - Page title: ${tenantsTitle}`);
    
    const tenantsErrors = await page.locator('.error, [role="alert"], .text-red-500, .text-red-600, .text-red-700').count();
    console.log(`  - Visible errors: ${tenantsErrors}`);
    
    const tenantsList = await page.locator('table, [role="table"], [class*="tenant"]').count();
    console.log(`  - Tenant elements found: ${tenantsList}`);
    
    console.log('\n=== SUPER ADMIN SECTION COMPLETE ===\n');
    
    // Final summary
    console.log('\n=== TEST SUMMARY ===');
    console.log('All screenshots saved to test-results/ directory');
    console.log('Review screenshots for visual verification');
  });
});
