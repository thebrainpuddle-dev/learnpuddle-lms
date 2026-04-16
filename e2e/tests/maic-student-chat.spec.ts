// e2e/tests/maic-student-chat.spec.ts
//
// Verifies that a student signed into the MAIC classroom player can send a
// message through the chat panel and receive an agent reply, without tripping
// the "Teacher or admin access required" 403 that ships when the frontend
// accidentally targets the teacher-only chat endpoint.

import { test, expect } from '@playwright/test';

test('student can send chat in classroom player', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="email"]', 'student@demo.test');
  await page.fill('input[name="password"]', 'demo1234');
  await page.click('button[type="submit"]');

  await page.waitForURL('**/student/**');
  await page.goto('/student/ai-classroom');
  await page.click('[data-testid="classroom-card"]:first-child');

  await page.waitForSelector('[data-testid="maic-stage"]');

  const chatInput = page.locator('[data-testid="chat-input"]');
  await chatInput.fill('What is this topic about?');
  await chatInput.press('Enter');

  // Agent reply must appear within 15s; no 403 error toast.
  await expect(
    page.locator('[data-testid="chat-agent-message"]').first(),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.locator('text=/Teacher or admin/i')).toHaveCount(0);
});
