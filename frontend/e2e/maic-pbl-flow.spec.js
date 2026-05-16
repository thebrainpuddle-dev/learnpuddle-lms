/**
 * Chunk 6 — MAIC PBL flow smoke test
 *
 * Audit Section B.4: assert the PBL scaffolding renders end-to-end against
 * a seeded READY classroom that contains at least one PBL scene. Covers:
 *
 *   1. Navigate to the PBL scene from the player.
 *   2. Role-selection panel renders with at least one selectable role.
 *   3. Issue board renders with the 3 status columns (Pending / Active / Done).
 *   4. Chat input is reachable + a user message can be typed and submitted.
 *   5. Total issues count is consistent with the rendered issues across columns.
 *
 * Out of scope (deferred):
 *   - LLM-driven issue completion (Judge agent COMPLETE verdict requires real
 *     LLM round-trip; flaky against a local seeded classroom).
 *   - Quiz submit (separate spec — quiz scene assertions belong with the
 *     quiz E2E coverage).
 *
 * The seeded `create_demo_tenant` classroom may or may not include a PBL
 * scene depending on the seed payload version. To stay green in both cases,
 * the spec gracefully skips when no PBL scene is found in the active
 * classroom — that is signalled as a Playwright skip, not a failure, so a
 * minimal seed change cannot regress CI.
 *
 * ─── Required env vars ──────────────────────────────────────────────────────
 *
 *   E2E_LIVE=1                — must be set; spec is skipped otherwise.
 *   E2E_BASE_URL              — defaults to http://localhost:3000.
 *   E2E_TEACHER_EMAIL         — teacher account email (seed defaults below).
 *   E2E_TEACHER_PASSWORD      — teacher account password.
 *   E2E_CLASSROOM_ID          — optional UUID override; otherwise the first
 *                               READY classroom returned by the teacher API.
 *   E2E_PBL_SCENE_INDEX       — optional 0-based scene index to test against.
 *                               When omitted, the spec auto-detects the first
 *                               scene of type='pbl' from the classroom payload.
 */

// @ts-check
import { test, expect } from '@playwright/test';

// ─── Config ────────────────────────────────────────────────────────────────────

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const TEACHER_EMAIL = process.env.E2E_TEACHER_EMAIL ?? 'teacher@demo.learnpuddle.com';
const TEACHER_PASSWORD = process.env.E2E_TEACHER_PASSWORD ?? 'Teacher@123';
const CLASSROOM_ID_OVERRIDE = process.env.E2E_CLASSROOM_ID ?? '';
const PBL_SCENE_INDEX_OVERRIDE = process.env.E2E_PBL_SCENE_INDEX
  ? Number(process.env.E2E_PBL_SCENE_INDEX)
  : null;

// ─── Helpers ───────────────────────────────────────────────────────────────────

/** @param {import('@playwright/test').Page} page */
async function loginAsTeacher(page) {
  await page.goto(`${BASE_URL}/login`);
  await page.locator('input[id="identifier"]').fill(TEACHER_EMAIL);
  await page.locator('input[id="password"]').fill(TEACHER_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/teacher/**', { timeout: 15_000 });
}

/** @param {import('@playwright/test').Page} page */
async function resolveClassroomId(page) {
  if (CLASSROOM_ID_OVERRIDE) return CLASSROOM_ID_OVERRIDE;
  const classroomId = await page.evaluate(async () => {
    const token =
      sessionStorage.getItem('access_token') ??
      localStorage.getItem('access_token') ??
      '';
    const response = await fetch('/api/v1/teacher/maic/classrooms/?status=READY&page_size=5', {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) return '';
    const data = await response.json();
    const results = data.results ?? data;
    if (Array.isArray(results) && results.length > 0) {
      return results[0].id ?? '';
    }
    return '';
  });
  if (!classroomId) {
    throw new Error(
      'No READY classrooms found for this teacher. Create one via the MAIC wizard or set E2E_CLASSROOM_ID.',
    );
  }
  return classroomId;
}

/**
 * Detect a PBL scene in the classroom. Returns the scene index, or null if
 * the classroom has no PBL scene (caller should skip the test).
 *
 * @param {import('@playwright/test').Page} page
 * @param {string} classroomId
 */
async function findPblSceneIndex(page, classroomId) {
  if (PBL_SCENE_INDEX_OVERRIDE !== null) return PBL_SCENE_INDEX_OVERRIDE;
  const idx = await page.evaluate(async (id) => {
    const token =
      sessionStorage.getItem('access_token') ??
      localStorage.getItem('access_token') ??
      '';
    const response = await fetch(`/api/v1/teacher/maic/classrooms/${id}/`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok) return -1;
    const data = await response.json();
    const scenes = data.content?.scenes ?? [];
    for (let i = 0; i < scenes.length; i++) {
      if (scenes[i].type === 'pbl') return i;
    }
    return -1;
  }, classroomId);
  return idx === -1 ? null : idx;
}

/**
 * Navigate to the PBL scene by clicking the scene chip at the given index.
 *
 * @param {import('@playwright/test').Page} page
 * @param {number} sceneIdx
 */
async function navigateToScene(page, sceneIdx) {
  // SceneNavigator chips have role="tab" and are 0-indexed in render order.
  // Wait for the chip strip to appear, then click the target index.
  await page.waitForSelector('[data-testid="maic-stage"]', { timeout: 20_000 });
  const chips = page.locator('[role="tab"]');
  await chips.nth(sceneIdx).click({ timeout: 10_000 });
  await expect(chips.nth(sceneIdx)).toHaveAttribute('aria-selected', 'true', {
    timeout: 10_000,
  });
}

// ─── Tests ─────────────────────────────────────────────────────────────────────

test.describe('MAIC PBL Flow — Chunk 6', () => {
  /** @type {string} */
  let classroomId = '';
  /** @type {number | null} */
  let pblSceneIdx = null;

  test.beforeEach(async ({ page }) => {
    if (!process.env.E2E_LIVE) {
      test.skip(true, 'Set E2E_LIVE=1 with a running stack to execute e2e tests');
      return;
    }
    await loginAsTeacher(page);
    if (!classroomId) {
      classroomId = await resolveClassroomId(page);
    }
    if (pblSceneIdx === null) {
      pblSceneIdx = await findPblSceneIndex(page, classroomId);
    }
    if (pblSceneIdx === null) {
      test.skip(
        true,
        'Seeded classroom has no PBL scene — set E2E_PBL_SCENE_INDEX or seed a PBL-enabled classroom to exercise this flow.',
      );
    }
  });

  test('PBL scene renders the role-selection panel', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await navigateToScene(page, /** @type {number} */ (pblSceneIdx));

    // The role panel is the first <section> inside the PBL renderer with
    // the heading "Select Your Role" (PBLRenderer.tsx line 437-439).
    const roleHeader = page.getByRole('heading', { name: /select your role/i });
    await expect(roleHeader).toBeVisible({ timeout: 10_000 });

    // At least one selectable role button must exist.
    const roleButtons = roleHeader.locator('xpath=ancestor::section[1]').getByRole('button');
    await expect(roleButtons.first()).toBeVisible();
  });

  test('PBL scene renders the issue board with 3 status columns', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await navigateToScene(page, /** @type {number} */ (pblSceneIdx));

    // Issue Board header — PBLRenderer.tsx line 474-477.
    await expect(
      page.getByRole('heading', { name: /issue board/i }),
    ).toBeVisible({ timeout: 10_000 });

    // 3 column labels — "Pending", "Active", "Done" from COLUMNS const
    // at PBLRenderer.tsx line 68-72.
    for (const label of ['Pending', 'Active', 'Done']) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    }

    // Progress summary "N of M tasks done" — PBLRenderer.tsx line 487-489.
    await expect(page.getByText(/\d+ of \d+ tasks done/)).toBeVisible();
  });

  test('PBL chat panel is reachable and accepts a typed user message', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await navigateToScene(page, /** @type {number} */ (pblSceneIdx));

    // Chat input — aria-label="PBL chat input" (PBLRenderer.tsx line 593).
    const chatInput = page.getByLabel('PBL chat input');
    await expect(chatInput).toBeVisible({ timeout: 10_000 });

    await chatInput.fill('What is the first step for the active issue?');
    await expect(chatInput).toHaveValue('What is the first step for the active issue?');

    // Send button is reachable (we do not click + wait for LLM here — that's
    // out of scope for a smoke test; this just proves the user input path
    // and submit affordance are intact).
    const sendBtn = page.getByRole('button', { name: /send message/i });
    await expect(sendBtn).toBeVisible();
    await expect(sendBtn).toBeEnabled();
  });

  test('issue count summary matches issues rendered across columns', async ({ page }) => {
    test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 to run e2e tests');

    await page.goto(`${BASE_URL}/teacher/ai-classroom/${classroomId}`);
    await navigateToScene(page, /** @type {number} */ (pblSceneIdx));

    // Parse "N of M tasks done" — assert M equals the number of issue cards
    // visible across all three columns. IssueCard has
    // aria-label="${issue.title} - ${badge.label}" (PBLRenderer.tsx line 650).
    const summary = await page
      .getByText(/(\d+) of (\d+) tasks done/)
      .first()
      .innerText();
    const match = summary.match(/(\d+) of (\d+) tasks done/);
    expect(match).not.toBeNull();
    const totalFromSummary = Number(match?.[2] ?? '0');

    // Issue cards are listitem-flavored buttons with the title-status
    // aria-label pattern. Count them across all 3 columns.
    const issueCards = page.locator('[aria-label*=" - Pending"], [aria-label*=" - Active"], [aria-label*=" - Done"]');
    const renderedCount = await issueCards.count();

    expect(renderedCount).toBe(totalFromSummary);
  });
});
