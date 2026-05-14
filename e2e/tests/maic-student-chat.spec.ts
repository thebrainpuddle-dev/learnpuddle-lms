// e2e/tests/maic-student-chat.spec.ts
//
// Verifies that a student signed into the MAIC classroom player can send a
// message through the chat panel and receive an agent reply, without tripping
// the "Teacher or admin access required" 403 that ships when the frontend
// accidentally targets the teacher-only chat endpoint.

import { test, expect } from '@playwright/test';
import { credentials, fillTenantLogin } from './helpers/auth';

test('student can send chat in classroom player', async ({ page }) => {
  await page.goto('/login');
  await fillTenantLogin(page, credentials.student.email, credentials.student.password);
  await page.click('button[type="submit"]');

  await page.waitForURL('**/student/**');
  await page.goto('/student/ai-classroom');
  const classroomCard = page.getByRole('button', { name: /Open classroom: E2E Demo Classroom/ });
  await expect(classroomCard, 'seed a real public READY classroom before running this live flow').toBeVisible({ timeout: 10000 });
  await classroomCard.click();

  await page.waitForSelector('[data-testid="maic-stage"]');

  const chatInput = page
    .getByRole('textbox', { name: 'Chat message input' })
    .filter({ visible: true });
  await chatInput.fill('What is this topic about?');
  await chatInput.press('Enter');

  // Agent reply must appear within 15s; no 403 error toast.
  await expect(
    page.locator('[data-testid="chat-agent-message"]').filter({ visible: true }).first(),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.locator('text=/Teacher or admin/i')).toHaveCount(0);
});
