// @ts-check
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://keystone.localhost:3000';
const TEACHER_EMAIL = process.env.E2E_TEACHER_EMAIL ?? 'priya.sharma@keystoneeducation.in';
const TEACHER_PASSWORD = process.env.E2E_TEACHER_PASSWORD ?? 'Teacher@123';

const ROUTES = [
  ['/teacher/dashboard', 'dashboard'],
  ['/teacher/courses', 'courses'],
  ['/teacher/assignments', 'assignments'],
  ['/teacher/growth', 'growth'],
  ['/teacher/achievements', 'achievements'],
  ['/teacher/my-classes', 'my-classes'],
  ['/teacher/discussions', 'discussions'],
  ['/teacher/ai-classroom', 'ai-classroom'],
  ['/teacher/chatbots', 'ai-tutor'],
  ['/teacher/certifications', 'certifications'],
  ['/teacher/study-notes', 'study-notes'],
  ['/teacher/reminders', 'reminders'],
  ['/teacher/profile', 'profile'],
];

test.describe('Teacher portal live harness', () => {
  test.skip(!process.env.E2E_LIVE, 'Set E2E_LIVE=1 with the local stack running.');

  test('Priya teacher portal loads core sections in parallel tabs', async ({ browser }) => {
    const context = await browser.newContext({ baseURL: BASE_URL });
    const issues = [];
    const loginPage = await context.newPage();
    attachTelemetry(loginPage, 'login', issues);

    await loginAsTeacher(loginPage);
    const authState = await readStorage(loginPage);

    const pages = await Promise.all(
      ROUTES.map(async ([path, label]) => {
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
        return { page, label, path, ms: Date.now() - started, title };
      }),
    );

    const sectionId = await firstTeacherSectionId(loginPage);
    if (sectionId) {
      const page = await context.newPage();
      attachTelemetry(page, 'section-dashboard', issues);
      await hydrateStorage(page, authState);
      await page.goto(`${BASE_URL}/teacher/my-classes/section/${sectionId}`, {
        waitUntil: 'domcontentloaded',
      });
      await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
      const bodyText = (await page.locator('body').innerText({ timeout: 10_000 })).trim();
      if (/something went wrong|server error|traceback|not found/i.test(bodyText) || bodyText.length < 40) {
        issues.push({ label: 'section-dashboard', type: 'visible-error', sample: bodyText.slice(0, 240) });
      }
      pages.push({ page, label: 'section-dashboard', path: `/teacher/my-classes/section/${sectionId}`, ms: 0, title: await page.title() });
    } else {
      issues.push({ label: 'my-classes', type: 'missing-data', message: 'No teacher section id returned.' });
    }

    const readyClassroomId = await firstReadyClassroomId(loginPage);
    if (readyClassroomId) {
      const page = await context.newPage();
      attachTelemetry(page, 'ai-classroom-player', issues);
      await hydrateStorage(page, authState);
      await page.goto(`${BASE_URL}/teacher/ai-classroom/${readyClassroomId}`, {
        waitUntil: 'domcontentloaded',
      });
      await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
      const bodyText = (await page.locator('body').innerText({ timeout: 10_000 })).trim();
      if (/Classroom Draft|no slides to display|audio unavailable/i.test(bodyText)) {
        issues.push({ label: 'ai-classroom-player', type: 'player-friction', sample: bodyText.slice(0, 300) });
      }
      const startButton = page.getByRole('button', { name: 'Start Class' });
      if (await startButton.isVisible({ timeout: 2500 }).catch(() => false)) {
        await startButton.click();
        await page.waitForTimeout(2500);
        const afterStart = (await page.locator('body').innerText({ timeout: 5000 })).trim();
        if (/audio unavailable|failed to fetch|no slides to display/i.test(afterStart)) {
          issues.push({ label: 'ai-classroom-player', type: 'playback-friction', sample: afterStart.slice(0, 300) });
        }
      }
      pages.push({ page, label: 'ai-classroom-player', path: `/teacher/ai-classroom/${readyClassroomId}`, ms: 0, title: await page.title() });
    } else {
      issues.push({ label: 'ai-classroom', type: 'missing-data', message: 'No READY classroom found.' });
    }

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

async function loginAsTeacher(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'domcontentloaded' });
  await page.locator('input[id="identifier"]').fill(TEACHER_EMAIL);
  await page.locator('input[id="password"]').fill(TEACHER_PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/teacher/**', { timeout: 20_000 });
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
    issues.push({
      label,
      type: 'requestfailed',
      method: request.method(),
      url: redactUrl(request.url()),
      failure: request.failure()?.errorText ?? '',
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
      issues.push({ label, type: 'websocket-close', url: redactUrl(ws.url()), sent, received });
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

async function firstTeacherSectionId(page) {
  return page.evaluate(async () => {
    const token = sessionStorage.getItem('access_token') || localStorage.getItem('access_token') || '';
    const tenant =
      sessionStorage.getItem('tenant_subdomain') ||
      localStorage.getItem('tenant_subdomain') ||
      'keystone';
    const response = await fetch('/api/v1/teacher/chatbots/my-sections/', {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        'X-Tenant-Subdomain': tenant,
      },
    });
    if (!response.ok) return '';
    const sections = await response.json();
    return Array.isArray(sections) && sections[0]?.id ? sections[0].id : '';
  });
}

async function firstReadyClassroomId(page) {
  return page.evaluate(async () => {
    const token = sessionStorage.getItem('access_token') || localStorage.getItem('access_token') || '';
    const tenant =
      sessionStorage.getItem('tenant_subdomain') ||
      localStorage.getItem('tenant_subdomain') ||
      'keystone';
    const response = await fetch('/api/v1/teacher/maic/classrooms/?status=READY', {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        'X-Tenant-Subdomain': tenant,
      },
    });
    if (!response.ok) return '';
    const classrooms = await response.json();
    return Array.isArray(classrooms) && classrooms[0]?.id ? classrooms[0].id : '';
  });
}

function redactUrl(url) {
  return url.replace(/([?&](?:token|access|refresh|code|key)=)[^&]+/gi, '$1<redacted>');
}
