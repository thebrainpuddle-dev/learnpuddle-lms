// @ts-check
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://keystone.localhost:3000';
const TEACHER_EMAIL = process.env.E2E_TEACHER_EMAIL ?? 'priya.sharma@keystoneeducation.in';
const TEACHER_PASSWORD = process.env.E2E_TEACHER_PASSWORD ?? 'Teacher@123';
const TOPIC =
  process.env.E2E_MAIC_TOPIC ??
  `Water quality PBL evidence lab ${new Date().toISOString().slice(0, 19)}`;

test.describe('AI Classroom live teacher v2 generation', () => {
  test.skip(
    !process.env.E2E_LIVE_MAIC_GENERATION,
    'Set E2E_LIVE_MAIC_GENERATION=1 with web/asgi/worker/redis/db and real tenant AI config running.',
  );

  test('teacher creates a PBL-first classroom and starts playback', async ({ page }) => {
    test.setTimeout(15 * 60 * 1000);
    const issues = [];
    attachTelemetry(page, 'teacher-ai-classroom-create', issues);

    await loginAsTeacher(page);
    await page.goto(`${BASE_URL}/teacher/ai-classroom/new`, { waitUntil: 'domcontentloaded' });

    await page.locator('#maic-topic').fill(TOPIC);
    await page.locator('#maic-grade-level').selectOption('Grade 6');
    await page.locator('#maic-subject').fill('Science');
    await page.locator('#maic-syllabus-board').selectOption('CBSE');
    await setRangeValue(page.locator('#maic-scenes'), '5');

    await page.getByRole('button', { name: /meet your classroom/i }).click();
    await page.locator('[data-testid="maic-class-guide"]').fill([
      `Audience: Grade 6 Science class using ${TOPIC}.`,
      'Learning arc: concrete local water sample mystery, evidence collection, misconception check, and synthesis.',
      'PBL: students choose roles, inspect an issue board, create a school water-safety recommendation, and defend it with evidence.',
      'Agent choreography: teacher frames the investigation, curious student asks for evidence, skeptic challenges unsupported claims.',
      'Visual direction: use spotlight or laser only to direct attention to data, process steps, or role handoffs.',
      'Assessment: include one formative checkpoint and a final discussion prompt.',
    ].join('\n'));

    await page.locator('[data-testid="agent-inline-grid"]').waitFor({ timeout: 90_000 });
    const continueReveal = page.getByRole('button', { name: /^continue$/i });
    if (await continueReveal.isVisible({ timeout: 1500 }).catch(() => false)) {
      await continueReveal.click();
    }
    await page.getByRole('button', { name: /looks good/i }).click();

    await expect(page.getByText(/Classroom Ready!/i)).toBeVisible({
      timeout: 12 * 60 * 1000,
    });
    await page.getByRole('button', { name: /open classroom/i }).click();
    await expect(page).toHaveURL(/\/teacher\/ai-classroom\/[0-9a-f-]+/i, {
      timeout: 30_000,
    });

    await page.waitForLoadState('networkidle', { timeout: 30_000 }).catch(() => {});
    const bodyText = await page.locator('body').innerText({ timeout: 10_000 });
    expect(bodyText).not.toMatch(/Classroom Draft|no slides to display|Image unavailable/i);
    await sweepRenderableScenes(page, issues);

    const startButton = page.locator('button[aria-label^="Start playback"][aria-label*="scene"]');
    if (await startButton.isVisible({ timeout: 10_000 }).catch(() => false)) {
      await startButton.click();
      await page.waitForFunction(() => {
        const body = document.body?.innerText || '';
        const engine = window.__maicEngine?.playbackEngine;
        const state =
          engine && typeof engine.getState === 'function' ? engine.getState() : null;
        return (
          /Pause playback|Playing|Audio active/i.test(body) ||
          Boolean(state?.isPlaying) ||
          Number(state?.currentTimeMs || 0) > 0 ||
          Number(state?.currentSlideIndex || 0) > 0
        );
      }, undefined, { timeout: 20_000 });
      const playbackText = await page.locator('body').innerText({ timeout: 10_000 });
      expect(playbackText).not.toMatch(/Audio unavailable|Reading along/i);
    }

    const severe = issues.filter((issue) => {
      if (issue.type === 'console-warning') return false;
      if (issue.type === 'requestfailed' && isExpectedRequestAbort(issue.url || '', issue.failure || '')) {
        return false;
      }
      if (issue.type === 'http' && isMaicHttpContractFailure(issue)) {
        return true;
      }
      if (issue.type === 'runtime-contract') return true;
      if (issue.status && issue.status < 500) return false;
      return true;
    });
    console.log(JSON.stringify({ topic: TOPIC, issues }, null, 2));
    expect(severe).toEqual([]);
  });
});

async function loginAsTeacher(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.locator('#identifier, input[name="identifier"], input[name="email"], input[type="email"]').first().fill(TEACHER_EMAIL);
  await page.locator('#password, input[name="password"], input[type="password"]').first().fill(TEACHER_PASSWORD);
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.waitForURL('**/teacher/**', { timeout: 30_000 });
}

async function setRangeValue(locator, value) {
  await locator.evaluate((element, nextValue) => {
    element.value = String(nextValue);
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }, value);
}

function attachTelemetry(page, label, issues) {
  page.on('console', (message) => {
    if (['error', 'warning'].includes(message.type())) {
      issues.push({ label, type: `console-${message.type()}`, text: message.text().slice(0, 500) });
    }
  });
  page.on('pageerror', (error) => {
    issues.push({ label, type: 'pageerror', text: String(error).slice(0, 500) });
  });
  page.on('requestfailed', (request) => {
    const url = redactUrl(request.url());
    const failure = request.failure()?.errorText ?? '';
    if (isExpectedRequestAbort(url, failure)) return;
    issues.push({ label, type: 'requestfailed', method: request.method(), url, failure });
  });
  page.on('response', (response) => {
    const status = response.status();
    const url = response.url();
    if (status >= 400 && /\/api\/|\/ws\/|\.m3u8|\.mp3|\.ts/.test(url)) {
      issues.push({
        label,
        type: 'http',
        status,
        method: response.request().method(),
        url: redactUrl(url),
      });
    }
  });
  page.on('websocket', (ws) => {
    let sent = 0;
    let received = 0;
    ws.on('framesent', () => { sent += 1; });
    ws.on('framereceived', () => { received += 1; });
    ws.on('close', () => {
      const url = redactUrl(ws.url());
      if (isExpectedLifecycleWebSocketClose(url)) return;
      issues.push({ label, type: 'websocket-close', url, sent, received });
    });
  });
}

async function sweepRenderableScenes(page, issues) {
  const chips = page.locator('[data-testid="scene-chip"]');
  const count = await chips.count().catch(() => 0);
  const limit = Math.min(count || 1, 8);
  for (let index = 0; index < limit; index += 1) {
    if (count > 0) {
      await chips.nth(index).click();
      await page.waitForTimeout(500);
    }
    const result = await inspectCurrentRenderableScene(page);
    if (!result.ok) {
      issues.push({
        label: 'teacher-ai-classroom-create',
        type: 'runtime-contract',
        sceneIndex: index,
        ...result,
      });
    }
  }
}

async function inspectCurrentRenderableScene(page) {
  return page.evaluate(() => {
    const bodyText = document.body?.innerText || '';
    const promptLeak = /output pure json|aspect ratio 16:9|provided generated image ids/i.test(bodyText);
    const fillerLeak = /\bPoint One\b|\bPoint Two\b|\bAcknowledgments\b|\bAdditional Resources\b/i.test(bodyText);
    const missingMedia = /Image unavailable|No keyword|placeholder|placehold\.co/i.test(bodyText);
    const canvas = document.querySelector('[data-testid="slide-design-canvas"]');
    if (!canvas) {
      return {
        ok: !(promptLeak || fillerLeak || missingMedia || /no slides to display/i.test(bodyText)),
        skipped: 'no-slide-canvas',
        promptLeak,
        fillerLeak,
        missingMedia,
      };
    }
    const rect = canvas.getBoundingClientRect();
    const children = Array.from(canvas.children).map((child) => {
      const childRect = child.getBoundingClientRect();
      return {
        tag: child.tagName,
        text: (child.textContent || '').trim().slice(0, 80),
        left: Math.round(childRect.left - rect.left),
        top: Math.round(childRect.top - rect.top),
        width: Math.round(childRect.width),
        height: Math.round(childRect.height),
        right: Math.round(childRect.right - rect.left),
        bottom: Math.round(childRect.bottom - rect.top),
      };
    }).filter((child) => child.width > 2 && child.height > 2);
    const overflows = children.filter((child) => (
      child.left < -2 ||
      child.top < -2 ||
      child.right > rect.width + 2 ||
      child.bottom > rect.height + 2
    ));
    const tinyCanvas = rect.width < 500 || rect.height < 250;
    const almostEmpty = children.length === 0 && !/quiz|project|discussion|submit/i.test(bodyText);
    return {
      ok: !(promptLeak || fillerLeak || missingMedia || overflows.length || tinyCanvas || almostEmpty),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      childCount: children.length,
      overflows,
      promptLeak,
      fillerLeak,
      missingMedia,
      tinyCanvas,
      almostEmpty,
    };
  });
}

function redactUrl(url) {
  return url.replace(/([?&](?:token|access|refresh|code|key)=)[^&]+/gi, '$1<redacted>');
}

function isExpectedLifecycleWebSocketClose(url) {
  try {
    const parsed = new URL(url);
    if (parsed.pathname === '/ws/notifications/') return true;
    return parsed.port === '3000' && parsed.pathname === '/' && parsed.searchParams.has('token');
  } catch {
    return false;
  }
}

function isExpectedRequestAbort(url, failure) {
  if (!/net::ERR_ABORTED|NS_BINDING_ABORTED|Load failed/i.test(failure)) return false;
  try {
    const parsed = new URL(url);
    if (!parsed.pathname.startsWith('/api/')) return true;
    return parsed.pathname.startsWith('/api/tenants/')
      || parsed.pathname.startsWith('/api/notifications/');
  } catch {
    return false;
  }
}

function isMaicHttpContractFailure(issue) {
  const status = Number(issue.status || 0);
  if (status < 400) return false;
  try {
    const parsed = new URL(issue.url || '');
    const path = parsed.pathname;
    return path.startsWith('/api/maic/v2/')
      || path.startsWith('/api/v1/teacher/maic/')
      || path.startsWith('/api/v1/student/maic/');
  } catch {
    return /\/api\/(?:maic\/v2|v1\/(?:teacher|student)\/maic)\//.test(issue.url || '');
  }
}
