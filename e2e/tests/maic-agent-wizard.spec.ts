// e2e/tests/maic-agent-wizard.spec.ts
//
// Covers the new "Meet your classroom" wizard step (WS-C):
//   - agents are generated on entry
//   - voice preview can play a clip
//   - a single card can be edited inline
//   - "Looks good →" advances to the outline review step
//
// The test is resilient to localisation/text drift: we rely on
// data-testid="agent-card" and aria-label attributes on action buttons.

import { test, expect } from '@playwright/test';

test.describe('Teacher AI classroom wizard — agent step', () => {
  test('teacher wizard generates and edits agents', async ({ page }) => {
    // Login
    await page.goto('/login');
    await page.fill('input[name="email"]', 'teacher@demo.test');
    await page.fill('input[name="password"]', 'demo1234');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/teacher/**');

    // Start a new classroom
    await page.goto('/teacher/ai-classroom/new');
    await page.fill('input#maic-topic', 'Photosynthesis');

    // Step 1 → Step 2 (agents)
    await page.click('button:has-text("Meet your classroom")');

    // Four agent cards should appear within 30 s. Backend pre-gen is capped
    // around 10 s but we give plenty of slack for cold LLM calls.
    const cards = page.locator('[data-testid="agent-card"]');
    await expect(cards).toHaveCount(4, { timeout: 30000 });

    // Sanity-check: at least two agents should use a formal prefix (Dr./Prof./Ms./Mr.)
    const names = await cards.locator('h3').allTextContents();
    expect(names.filter((n) => /^(Dr\.|Prof\.|Ms\.|Mr\.)/.test(n)).length)
      .toBeGreaterThanOrEqual(2);

    // Voice preview — click ▶ on the first card; we don't assert audio plays
    // (jsdom / Playwright can't reliably probe Audio()), only that the button
    // toggles its aria-pressed state.
    const firstPreview = cards.first().locator('button[aria-label="Preview voice"]');
    await firstPreview.click();
    await expect(firstPreview).toHaveAttribute('aria-pressed', 'true', {
      timeout: 5000,
    });

    // Stop the preview before we open the edit modal.
    await firstPreview.click();

    // Edit the first card — modal uses role="dialog".
    await cards.first().locator('button:has-text("Edit")').click();
    const modal = page.locator('[role="dialog"]');
    await expect(modal).toBeVisible();
    await modal.locator('input').first().fill('Dr. Test Agent');
    await modal.locator('button:has-text("Save")').click();

    await expect(page.locator('text=Dr. Test Agent')).toBeVisible();

    // Proceed to outline review
    await page.click('button:has-text("Looks good")');
    await page.waitForURL(/\/teacher\/ai-classroom\/new/);
    await expect(page.locator('text=/Review outline/i')).toBeVisible({ timeout: 45000 });
  });
});
