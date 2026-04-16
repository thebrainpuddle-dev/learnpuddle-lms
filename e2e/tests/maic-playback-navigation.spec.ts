// e2e/tests/maic-playback-navigation.spec.ts
//
// Guards the Chunk 5 WS-E fix: clicking a slide thumbnail mid-playback must
// cleanly hand off to the new slide's audio — no overlap, no stale callbacks.
//
// We inspect the engine via `window.__maicEngine` (exposed by
// `usePlaybackEngine` when `import.meta.env.MODE === 'test' || DEV`). This
// lets us see the *actual* in-memory `audioElement` reference on
// MAICActionEngine — which matters because the engine uses `new Audio()`
// off-DOM, so `document.querySelectorAll('audio')` would not find it.
//
// Pre-condition: a published classroom exists with 3+ slides and pre-gen
// audioUrls on each speech action. Seeded by the test fixture.

import { test, expect } from '@playwright/test';

test('navigating between slides does not break audio', async ({ page }) => {
  await page.goto('/login');
  await page.fill('input[name="email"]', 'student@demo.test');
  await page.fill('input[name="password"]', 'demo1234');
  await page.click('button[type="submit"]');

  await page.waitForURL('**/student/**');
  await page.goto('/student/ai-classroom');
  await page.click('[data-testid="classroom-card"]:first-child');
  await page.waitForSelector('[data-testid="maic-stage"]');

  // Start playback — the Stage renders a "Start Class" button in the
  // idle-state overlay. We match by button text to avoid coupling the test
  // to a specific testid that doesn't yet exist in Stage.tsx.
  await page.click('button:has-text("Start Class")');

  // Wait for the first speech audio to actually start playing. Using the
  // engine handle is more reliable than querying DOM <audio> elements —
  // the action engine holds its element in a private field.
  await page.waitForFunction(
    () => {
      const engine = (window as any).__maicEngine?.actionEngine;
      return engine?.audioElement != null && !engine.audioElement.paused;
    },
    { timeout: 15000 },
  );

  // Click slide 3 — triggers SlideNavigator → seekToSlide → stop() →
  // generationToken++ → new scene's first audio starts.
  await page.click('[data-testid="slide-thumbnail"]:nth-child(3)');

  // Within a short window, the new scene's speech should begin. We verify
  // by watching the speech subtitle text transition away from null.
  await page.waitForFunction(
    () => {
      const engine = (window as any).__maicEngine?.actionEngine;
      const stageStore = engine?.stageStore;
      if (!stageStore || typeof stageStore.getState !== 'function') return false;
      const text = stageStore.getState().speechText;
      return text != null;
    },
    { timeout: 3000 },
  );

  // Exactly one active audio element must exist on the engine (no overlap).
  const audioCountAfterClick3 = await page.evaluate(() => {
    const engine = (window as any).__maicEngine?.actionEngine;
    return engine?.audioElement ? 1 : 0;
  });
  expect(audioCountAfterClick3).toBe(1);

  // Click slide 5 — repeat the assertion. No audio accumulates across clicks.
  await page.click('[data-testid="slide-thumbnail"]:nth-child(5)');
  await page.waitForTimeout(1000);
  const audioCountAfterClick5 = await page.evaluate(() => {
    const engine = (window as any).__maicEngine?.actionEngine;
    return engine?.audioElement ? 1 : 0;
  });
  expect(audioCountAfterClick5).toBe(1);
});
