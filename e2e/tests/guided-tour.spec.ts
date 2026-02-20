import { expect, test, type Page } from '@playwright/test';
import { clearBrowserAuthState, loginAsAdmin, loginAsSuperAdmin, loginAsTeacher } from './helpers/auth';
import { setupTourApiMocks } from './helpers/tourMocks';

interface ExpectedStep {
  title: string;
  selector?: string;
  optional?: boolean;
}

const SUPERADMIN_STEPS: ExpectedStep[] = [
  { title: 'Command Navigation', selector: '[data-tour="superadmin-sidebar"]' },
  { title: 'Onboard New School', selector: '[data-tour="superadmin-dashboard-onboard"]' },
  { title: 'Platform Health Snapshot', selector: '[data-tour="superadmin-dashboard-stats"]' },
  { title: 'Plan Mix', selector: '[data-tour="superadmin-dashboard-plan-distribution"]' },
  { title: 'Recent School Onboards', selector: '[data-tour="superadmin-dashboard-recent-onboards"]' },
  { title: 'Limit Alerts', selector: '[data-tour="superadmin-dashboard-near-limits"]' },
  { title: 'Schools Workspace', selector: '[data-tour="superadmin-nav-schools"]' },
  { title: 'School Search', selector: '[data-tour="superadmin-schools-search"]' },
  { title: 'Tenant Operations Table', selector: '[data-tour="superadmin-schools-table"]' },
  { title: 'Launch Onboarding Flow', selector: '[data-tour="superadmin-schools-onboard"]' },
  { title: 'School Detail Console', selector: '[data-tour="superadmin-school-header"]', optional: true },
  { title: 'Overview, Plan, Features', selector: '[data-tour="superadmin-school-tabs"]', optional: true },
  { title: 'Usage Visibility', selector: '[data-tour="superadmin-school-overview-usage"]', optional: true },
  { title: 'Plan and Limits Control', selector: '[data-tour="superadmin-school-plan-card"]', optional: true },
  { title: 'Feature Flags', selector: '[data-tour="superadmin-school-features-grid"]', optional: true },
  { title: 'Replay Anytime', selector: '[data-tour="superadmin-tour-replay"]' },
];

const ADMIN_STEPS: ExpectedStep[] = [
  { title: 'Admin Navigation', selector: '[data-tour="admin-sidebar"]' },
  { title: 'Daily Command Header', selector: '[data-tour="admin-dashboard-hero"]' },
  { title: 'Core Metrics', selector: '[data-tour="admin-dashboard-stats"]' },
  { title: 'Activity Timeline', selector: '[data-tour="admin-dashboard-activity"]' },
  { title: 'Quick Actions', selector: '[data-tour="admin-dashboard-quick-actions"]' },
  { title: 'Courses', selector: '[data-tour="admin-nav-courses"]' },
  { title: 'Course Filters and Views', selector: '[data-tour="admin-courses-filters"]' },
  { title: 'Course Inventory', selector: '[data-tour="admin-courses-list"]' },
  { title: 'Create Course', selector: '[data-tour="admin-courses-create"]' },
  { title: 'Course Editor Tabs', selector: '[data-tour="admin-course-editor-tabs"]' },
  { title: 'Details Setup', selector: '[data-tour="admin-course-details-panel"]' },
  { title: 'Content Builder', selector: '[data-tour="admin-course-content-panel"]', optional: true },
  { title: 'Assignment Targeting', selector: '[data-tour="admin-course-assignment-panel"]' },
  { title: 'Media Library', selector: '[data-tour="admin-media-grid"]' },
  { title: 'Teacher Management', selector: '[data-tour="admin-teachers-table"]' },
  { title: 'Groups', selector: '[data-tour="admin-groups-members"]', optional: true },
  { title: 'Reminders', selector: '[data-tour="admin-reminders-composer"]', optional: true },
  { title: 'Announcements', selector: '[data-tour="admin-announcements-compose"]' },
  { title: 'Analytics', selector: '[data-tour="admin-analytics-summary"]' },
  { title: 'Brand Settings', selector: '[data-tour="admin-settings-branding"]' },
  { title: 'Security Controls', selector: '[data-tour="security-2fa-section"]' },
  { title: 'Replay Anytime', selector: '[data-tour="admin-tour-replay"]' },
];

const TEACHER_STEPS: ExpectedStep[] = [
  { title: 'Teacher Navigation', selector: '[data-tour="teacher-sidebar"]' },
  { title: 'Progress Snapshot', selector: '[data-tour="teacher-dashboard-stats"]' },
  { title: 'Continue Learning', selector: '[data-tour="teacher-dashboard-continue"]' },
  { title: 'Upcoming Deadlines', selector: '[data-tour="teacher-dashboard-deadlines"]' },
  { title: 'My Courses', selector: '[data-tour="teacher-courses-grid"]' },
  { title: 'Course Filters', selector: '[data-tour="teacher-courses-filters"]' },
  { title: 'Course Player', selector: '[data-tour="teacher-course-player"]', optional: true },
  { title: 'Module Navigator', selector: '[data-tour="teacher-course-structure"]', optional: true },
  { title: 'Assignments', selector: '[data-tour="teacher-assignments-list"]' },
  { title: 'Reminders Inbox', selector: '[data-tour="teacher-reminders-list"]' },
  { title: 'Profile and Preferences', selector: '[data-tour="teacher-profile-sections"]' },
  { title: 'Replay Anytime', selector: '[data-tour="teacher-profile-tour-replay"]' },
];

const overlay = (page: Page) => page.locator('[data-tour-overlay="true"]');

async function runAndAssertTour(page: Page, steps: ExpectedStep[], replaySelector: string) {
  await expect(overlay(page)).toBeVisible({ timeout: 20000 });

  const seenTitles: string[] = [];
  const expectedByTitle = new Map(steps.map((s) => [s.title, s]));

  for (let i = 0; i < 80; i++) {
    await expect(overlay(page)).toBeVisible({ timeout: 15000 });
    const title = (await page.locator('[data-tour-overlay-title="true"]').first().innerText()).trim();

    if (seenTitles[seenTitles.length - 1] !== title) {
      seenTitles.push(title);
    }

    const expectedStep = expectedByTitle.get(title);
    expect(expectedStep, `Unexpected tour step title "${title}"`).toBeTruthy();

    if (expectedStep?.selector) {
      const target = page.locator(expectedStep.selector).first();
      if (expectedStep.optional) {
        if (await target.count()) {
          await expect(target).toBeVisible({ timeout: 10000 });
        }
      } else {
        await expect(
          target,
          `Expected selector "${expectedStep.selector}" to be visible for step "${title}"`
        ).toBeVisible({ timeout: 10000 });
      }
    }

    const nextButton = overlay(page).getByRole('button', { name: /next|finish/i });
    const buttonText = (await nextButton.innerText()).trim().toLowerCase();
    await nextButton.click();

    if (buttonText === 'finish') {
      break;
    }

    if (i === 79) {
      throw new Error('Tour did not reach a finish step within 80 clicks.');
    }
  }

  await expect(overlay(page)).toBeHidden({ timeout: 10000 });

  const required = steps.filter((s) => !s.optional).map((s) => s.title);
  for (const title of required) {
    expect(seenTitles, `Missing required tour step "${title}"`).toContain(title);
  }

  // Once per login: should not auto-open again after reload in the same session.
  await page.reload();
  await expect(overlay(page)).toBeHidden({ timeout: 6000 });

  // Manual replay trigger should always reopen the tour.
  await page.locator(replaySelector).first().click();
  await expect(overlay(page)).toBeVisible({ timeout: 10000 });
  await overlay(page).getByRole('button', { name: /skip tour/i }).click();
  await expect(overlay(page)).toBeHidden({ timeout: 6000 });
}

test.describe('Guided Tours', () => {
  test.beforeEach(async ({ page }) => {
    await setupTourApiMocks(page);
    await clearBrowserAuthState(page);
  });

  test('superadmin tour covers required steps and selectors', async ({ page, browserName, isMobile }) => {
    test.skip(browserName !== 'chromium' || isMobile, 'Tour coverage is validated on desktop Chromium.');

    await loginAsSuperAdmin(page);
    await runAndAssertTour(page, SUPERADMIN_STEPS, '[data-tour="superadmin-tour-replay"]');
  });

  test('admin tour covers required steps and selectors', async ({ page, browserName, isMobile }) => {
    test.skip(browserName !== 'chromium' || isMobile, 'Tour coverage is validated on desktop Chromium.');

    await loginAsAdmin(page);
    await runAndAssertTour(page, ADMIN_STEPS, '[data-tour="admin-tour-replay"]');
  });

  test('teacher tour covers required steps and selectors', async ({ page, browserName, isMobile }) => {
    test.skip(browserName !== 'chromium' || isMobile, 'Tour coverage is validated on desktop Chromium.');

    await loginAsTeacher(page);
    await runAndAssertTour(page, TEACHER_STEPS, '[data-tour="teacher-profile-tour-replay"]');
  });
});
