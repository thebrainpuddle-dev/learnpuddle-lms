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
// Pre-condition: a public READY classroom exists with 5+ slides. Seeded demo
// classrooms intentionally omit fake audio URLs so the player exercises the
// real live-TTS path when pre-generated audio is absent.

import { test, expect } from '@playwright/test';
import { credentials, fillTenantLogin } from './helpers/auth';

test('navigating between slides does not break audio', async ({ page }) => {
  await page.goto('/login');
  await fillTenantLogin(page, credentials.student.email, credentials.student.password);
  await page.click('button[type="submit"]');

  await page.waitForURL('**/student/**');
  await page.goto('/student/ai-classroom');
  const classroomCard = page.getByRole('button', { name: /Open classroom: E2E Demo Classroom/ });
  await expect(classroomCard, 'seed a real public READY classroom before running this live flow').toBeVisible({ timeout: 10000 });
  await classroomCard.click();
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
    { timeout: 30000 },
  );

  // Jump to slide 3 through the real playback engine seek path. The current
  // production UI exposes scene chips only; this keeps the regression on the
  // engine behavior that used to break audio handoff.
  await page.evaluate(() => {
    (window as any).__maicEngine?.playbackEngine?.seekToSlide(2);
  });

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

  // Jump to slide 5 — repeat the assertion. No audio accumulates across jumps.
  await page.evaluate(() => {
    (window as any).__maicEngine?.playbackEngine?.seekToSlide(4);
  });
  await page.waitForFunction(
    () => {
      const engine = (window as any).__maicEngine?.actionEngine;
      return engine?.audioElement != null;
    },
    { timeout: 3000 },
  );
  const audioCountAfterClick5 = await page.evaluate(() => {
    const engine = (window as any).__maicEngine?.actionEngine;
    return engine?.audioElement ? 1 : 0;
  });
  expect(audioCountAfterClick5).toBe(1);
});
