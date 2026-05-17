/**
 * MAIC Teacher Create — Wizard → outline-generation API contract
 *
 * Phase 1 of the vertical teacher-create-v2-PBL slice (see Obsidian
 * `maic-rebuild/PR41-GREEN-NEXT-SLICE-2026-05-16.md`).
 *
 * What this spec proves:
 *   The teacher-portal AI Classroom wizard, when filled with topic +
 *   grade + subject + syllabus board + class guide, POSTs to the v2-
 *   shaped outline endpoint with the canonical request body the
 *   backend's outline pipeline reads (see
 *   backend/apps/courses/maic_views.py extractor at lines ~84-113).
 *
 * What it deliberately does NOT cover (deferred to later phases):
 *   - Wait for READY (would require real LLM in CI; CI runs in
 *     deterministic-fallback mode per `.github/workflows/e2e.yml`).
 *   - Player audio / active speaker / handoff / overlays / fullscreen
 *     / PBL chat (covered by `maic-full-playback.spec.js` against the
 *     pre-seeded classroom).
 *   - Pedagogy structured fields (learningObjective / misconceptions /
 *     etc.) — those fields aren't present on the current main wizard;
 *     re-introducing them is a separate proposed slice that needs
 *     Codex sign-off first.
 *
 * Test posture:
 *   - Gated on E2E_LIVE=1 like every other blocking spec.
 *   - Uses `page.route()` to intercept the outline-generation POST so
 *     the test is fully deterministic — no LLM call required. The
 *     mock returns 503 so the wizard surfaces an error state (which
 *     we tolerate); we only care that the POST happened with the
 *     correct body.
 *   - Hard-fails (no `test.skip()`) per the no-self-skipping rule
 *     recorded after the PR #41 Codex review.
 */

// @ts-check
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const TEACHER_EMAIL = process.env.E2E_TEACHER_EMAIL ?? 'teacher@demo.learnpuddle.com';
const TEACHER_PASSWORD = process.env.E2E_TEACHER_PASSWORD ?? 'Teacher@123';

const OUTLINES_ENDPOINT_RE = /\/api\/v1\/teacher\/maic\/generate\/outlines\/?$/;
const AGENT_PROFILES_ENDPOINT_RE =
  /\/api\/v1\/teacher\/maic\/generate\/agent-profiles\/?$/;

// Canned agent profile so Step 2 ("Meet your classroom") resolves
// without an LLM round-trip. Matches the MAICAgent type in
// frontend/src/types/maic.ts — minimal required fields only. The role
// 'professor' is a valid enum member.
const STUB_AGENT_PROFILES_RESPONSE = {
  agents: [
    {
      id: 'stub-teacher-agent',
      name: 'Stub Teacher',
      role: 'professor',
      avatar: 'ST',
      color: '#4338CA',
      personality: 'Patient and encouraging.',
      expertise: 'Science education.',
    },
    {
      id: 'stub-student-agent',
      name: 'Stub Curious Student',
      role: 'student',
      avatar: 'SC',
      color: '#0F766E',
      personality: 'Curious and asks for evidence.',
      expertise: 'Asking clarifying questions.',
    },
  ],
};

/** @param {import('@playwright/test').Page} page */
async function loginAsTeacher(page) {
  await page.goto(`${BASE_URL}/login`);
  await page.locator('input[id="identifier"]').fill(TEACHER_EMAIL);
  await page.locator('input[id="password"]').fill(TEACHER_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/teacher/**', { timeout: 15_000 });
}

test.describe('MAIC teacher wizard → outline-generation contract', () => {
  test.beforeEach(async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');
    await loginAsTeacher(page);
  });

  test('wizard POSTs the canonical body to /api/v1/teacher/maic/generate/outlines/', async ({
    page,
  }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    /** @type {{ url: string; method: string; body: any } | null} */
    let captured = null;

    // Stub the agent-profiles endpoint so Step 2 resolves without an
    // LLM round-trip. The agent picker waits on this response before
    // enabling the "Looks good" CTA.
    await page.route(AGENT_PROFILES_ENDPOINT_RE, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(STUB_AGENT_PROFILES_RESPONSE),
      });
    });

    // Intercept the outline-generation POST so the test does not depend
    // on a real LLM round-trip. Respond with 503 — useMAICGeneration
    // handles it as a transient error and shows a toast, which is fine
    // for the contract assertion path.
    await page.route(OUTLINES_ENDPOINT_RE, async (route) => {
      const req = route.request();
      const rawBody = req.postData() ?? '';
      let parsed = null;
      try {
        parsed = JSON.parse(rawBody);
      } catch {
        parsed = rawBody;
      }
      captured = { url: req.url(), method: req.method(), body: parsed };
      await route.fulfill({
        status: 503,
        contentType: 'text/event-stream',
        body: '',
      });
    });

    // ── Drive the wizard ────────────────────────────────────────────────
    await page.goto(`${BASE_URL}/teacher/ai-classroom/new`, {
      waitUntil: 'domcontentloaded',
    });

    // Step 1 — topic + audience shaping
    await page.locator('#maic-topic').fill('Photosynthesis evidence lab');
    await page.locator('#maic-grade-level').selectOption('Grade 6');
    await page.locator('#maic-subject').fill('Science');
    await page.locator('#maic-syllabus-board').selectOption('CBSE');

    // Set the scene count slider via direct value dispatch (range inputs
    // don't accept .fill() reliably in Playwright; mirror the pattern
    // the deleted ai-classroom-live-generation spec used).
    await page.locator('#maic-scenes').evaluate((el, value) => {
      const input = /** @type {HTMLInputElement} */ (el);
      input.value = String(value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }, '5');

    // Step 1 → Step 2 (agent picker + class guide). The "Meet your
    // classroom" CTA is a primary button per GenerationWizard.tsx.
    await page.getByRole('button', { name: /meet your classroom/i }).click();

    // Step 2 — class guide. The textarea is data-testid="maic-class-guide".
    const classGuide = [
      'Audience: Grade 6 Science class.',
      'Learning arc: local water sample mystery → evidence → misconception check → synthesis.',
      'Assessment: one formative checkpoint and a final discussion prompt.',
    ].join('\n');
    await page.locator('[data-testid="maic-class-guide"]').fill(classGuide);

    // The agent picker reveals an "Approve agents" / "Looks good" CTA
    // once the inline agent grid renders. Click whichever exists; both
    // names route to the same handler in the wizard.
    const approveBtn = page.getByRole('button', {
      name: /approve agents|looks good/i,
    });
    await approveBtn.first().waitFor({ timeout: 30_000 });
    await approveBtn.first().click();

    // ── Wait for the intercepted POST + assert the contract ──────────────
    await expect.poll(() => captured, {
      message: 'wizard never POSTed to /api/v1/teacher/maic/generate/outlines/',
      timeout: 15_000,
    }).not.toBeNull();

    const c = /** @type {NonNullable<typeof captured>} */ (captured);
    expect(c.method).toBe('POST');
    expect(c.url).toMatch(OUTLINES_ENDPOINT_RE);

    // Canonical body fields — these are the names the backend extractor
    // and outline generator read (see
    // apps/courses/maic_views.py:84-113 + apps/maic/generation/...).
    expect(c.body).toMatchObject({
      topic: 'Photosynthesis evidence lab',
      language: expect.any(String),
      agentCount: expect.any(Number),
      sceneCount: 5,
      grade_level: 'Grade 6',
      subject: 'Science',
      syllabus_board: 'CBSE',
    });

    // class_guide is threaded via generationContextFromConfig in
    // useMAICGeneration.ts. Assert it carries the teacher's planning
    // input verbatim — empty/missing would silently drop the planning
    // contract from the prompt.
    expect(typeof c.body.class_guide).toBe('string');
    expect(c.body.class_guide).toContain('water sample mystery');
    expect(c.body.class_guide).toContain('formative checkpoint');

    // Either an agents[] payload was sent (preselected roster) OR not
    // — both shapes are allowed today. Just guard against a malformed
    // shape (non-array) sneaking in.
    if (c.body.agents !== undefined) {
      expect(Array.isArray(c.body.agents)).toBe(true);
    }
  });
});
