// @ts-check
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://demo.localhost:3000';
const STUDENT_EMAIL = process.env.E2E_STUDENT_EMAIL ?? 'student@demo.learnpuddle.com';
const STUDENT_PASSWORD = process.env.E2E_STUDENT_PASSWORD ?? 'Student@123';

const ROUTES = [
  ['/student/dashboard', 'dashboard'],
  ['/student/courses', 'courses'],
  ['/student/assignments', 'assignments'],
  ['/student/achievements', 'achievements'],
  ['/student/attendance', 'attendance'],
  ['/student/study-notes', 'study-notes'],
  ['/student/ai-classroom', 'ai-classroom'],
  ['/student/chatbots', 'ai-tutor'],
  ['/student/discussions', 'discussions'],
  ['/student/profile', 'profile'],
  ['/student/settings', 'settings'],
];

test.describe('Student portal live harness', () => {
  test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 with the local stack running.');

  test('student portal loads core sections without render or API regressions', async ({ browser }) => {
    const context = await browser.newContext({ baseURL: BASE_URL });
    const issues = [];
    const loginPage = await context.newPage();
    attachTelemetry(loginPage, 'login', issues);

    await loginAsStudent(loginPage);
    const authState = await readStorage(loginPage);

    const pages = [];
    for (const [path, label] of ROUTES) {
      const page = await context.newPage();
      attachTelemetry(page, label, issues);
      await hydrateStorage(page, authState);
      const started = Date.now();
      await page.goto(`${BASE_URL}${path}`, { waitUntil: 'domcontentloaded' });
      await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
      const bodyText = (await page.locator('body').innerText({ timeout: 10_000 })).trim();
      const title = await page.title();

      if (!bodyText || bodyText.length < 40) {
        issues.push({ label, type: 'blank', path, title });
      }
      if (/something went wrong|server error|traceback|not found/i.test(bodyText)) {
        issues.push({ label, type: 'visible-error', path, title, sample: bodyText.slice(0, 240) });
      }
      pages.push({ page, label, path, ms: Date.now() - started, title });
    }

    await openFirstIfPresent(context, authState, issues, {
      sourcePath: '/student/courses',
      sourceLabel: 'courses',
      targetLabel: 'course-detail',
      selector: 'button:has-text("Student Demo"), button:has-text("Study Skills Lab"), a[href*="/student/courses/"], button:has-text("Continue"), button:has-text("View")',
    });

    await openStudyNotesContent(context, authState, issues);

    await openFirstIfPresent(context, authState, issues, {
      sourcePath: '/student/discussions',
      sourceLabel: 'discussions',
      targetLabel: 'discussion-thread',
      selector: '[data-testid="student-discussion-thread-card"]',
    });

    await openFirstIfPresent(context, authState, issues, {
      sourcePath: '/student/chatbots',
      sourceLabel: 'ai-tutor',
      targetLabel: 'ai-tutor-chat',
      selector: '[role="button"]:has-text("Demo Study Coach"), a[href*="/student/chatbots/"], button:has-text("Chat"), button:has-text("Open")',
    });

    await openFirstIfPresent(context, authState, issues, {
      sourcePath: '/student/ai-classroom',
      sourceLabel: 'ai-classroom',
      targetLabel: 'ai-classroom-player',
      selector: 'button[aria-label^="Open classroom:"], [data-testid="classroom-card"], a[href*="/student/ai-classroom/"]',
    });

    const severe = issues.filter((issue) => {
      if (issue.type === 'console-warning') return false;
      if (issue.type === 'websocket-close') return false;
      if (
        issue.type === 'requestfailed' &&
        issue.failure === 'net::ERR_ABORTED' &&
        /\/api\/tenants\/theme\/$/.test(issue.url || '')
      ) {
        return false;
      }
      if (issue.status && issue.status < 500) return false;
      return true;
    });

    console.log(JSON.stringify({ pages: pages.map(({ label, path, ms, title }) => ({ label, path, ms, title })), issues }, null, 2));
    expect(severe).toEqual([]);
  });
});

async function loginAsStudent(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.locator('#identifier, input[name="identifier"], input[name="email"], input[type="email"]').first().fill(STUDENT_EMAIL);
  await page.locator('#password, input[name="password"], input[type="password"]').first().fill(STUDENT_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/student/**', { timeout: 20_000 });
}

async function openFirstIfPresent(context, authState, issues, config) {
  const { sourcePath, sourceLabel, targetLabel, selector } = config;
  const page = await context.newPage();
  attachTelemetry(page, targetLabel, issues);
  await hydrateStorage(page, authState);
  await page.goto(`${BASE_URL}${sourcePath}`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});

  const target = page.locator(selector).first();
  if (!(await expect(target).toBeVisible({ timeout: 3500 }).then(() => true).catch(() => false))) {
    issues.push({ label: sourceLabel, type: 'missing-data', message: `No ${targetLabel} candidate found.` });
    await page.close();
    return;
  }

  const before = page.url();
  await target.click();
  await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
  const bodyText = (await page.locator('body').innerText({ timeout: 10_000 })).trim();
  if (page.url() === before) {
    issues.push({ label: targetLabel, type: 'navigation', message: 'Click did not change route.' });
  }
  if (!bodyText || bodyText.length < 40) {
    issues.push({ label: targetLabel, type: 'blank', sample: bodyText.slice(0, 240) });
  }
  if (/something went wrong|server error|traceback|not found/i.test(bodyText)) {
    issues.push({ label: targetLabel, type: 'visible-error', sample: bodyText.slice(0, 300) });
  }
  await page.close();
}

async function openStudyNotesContent(context, authState, issues) {
  const page = await context.newPage();
  attachTelemetry(page, 'study-notes-render', issues);
  await hydrateStorage(page, authState);
  await page.goto(`${BASE_URL}/student/study-notes`, { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});

  const courseButton = page
    .locator('button:has-text("Student Demo"), button:has-text("Study Skills Lab")')
    .first();
  if (!(await expect(courseButton).toBeVisible({ timeout: 3500 }).then(() => true).catch(() => false))) {
    issues.push({ label: 'study-notes', type: 'missing-data', message: 'No study-notes course candidate found.' });
    await page.close();
    return;
  }

  await courseButton.click();
  const contentButton = page.locator('button:has-text("How to Build Durable Study Notes")').first();
  if (!(await expect(contentButton).toBeVisible({ timeout: 8000 }).then(() => true).catch(() => false))) {
    issues.push({ label: 'study-notes', type: 'missing-data', message: 'No summarizable study-notes content found.' });
    await page.close();
    return;
  }

  await contentButton.click();
  await expect(page.getByRole('button', { name: /Flashcards/i })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/Durable study notes/i).first()).toBeVisible({ timeout: 10_000 });
  const bodyText = (await page.locator('body').innerText({ timeout: 10_000 })).trim();
  if (/Generate AI Study Materials|No summary available|failed to fetch|server error/i.test(bodyText)) {
    issues.push({ label: 'study-notes-render', type: 'visible-error', sample: bodyText.slice(0, 300) });
  }
  await page.close();
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
    issues.push({
      label,
      type: 'requestfailed',
      method: request.method(),
      url,
      failure,
    });
  });
  page.on('response', (response) => {
    const status = response.status();
    const url = response.url();
    if (status >= 400 && /\/api\/|\/ws\/|\.m3u8|\.mp3|\.ts/.test(url)) {
      issues.push({ label, type: 'http', status, url: redactUrl(url) });
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

async function readStorage(page) {
  return page.evaluate(() => {
    const session = {};
    const local = {};
    for (let i = 0; i < sessionStorage.length; i += 1) {
      const key = sessionStorage.key(i);
      if (key) session[key] = sessionStorage.getItem(key);
    }
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key) local[key] = localStorage.getItem(key);
    }
    return { session, local };
  });
}

async function hydrateStorage(page, state) {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await page.evaluate((next) => {
    for (const [key, value] of Object.entries(next.session || {})) {
      if (value != null) sessionStorage.setItem(key, String(value));
    }
    for (const [key, value] of Object.entries(next.local || {})) {
      if (value != null) localStorage.setItem(key, String(value));
    }
  }, state);
}

function redactUrl(url) {
  return url.replace(/([?&](?:token|access|refresh|code|key)=)[^&]+/gi, '$1<redacted>');
}

function isExpectedLifecycleWebSocketClose(url) {
  try {
    const parsed = new URL(url);
    if (parsed.pathname === '/' && parsed.searchParams.has('token')) {
      return true;
    }
    return parsed.pathname === '/ws/notifications/';
  } catch {
    return false;
  }
}

function isExpectedRequestAbort(url, failure) {
  return failure === 'net::ERR_ABORTED' && (
    /\/api\/tenants\/theme\/$/.test(url || '') ||
    /\.(?:png|jpe?g|webp|svg|gif)(?:$|\?)/i.test(url || '')
  );
}
