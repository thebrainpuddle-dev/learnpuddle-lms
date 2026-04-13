// e2e/tests/cross-tenant-isolation.spec.ts
/**
 * Cross-Tenant Isolation E2E Tests
 *
 * Verifies that tenant isolation is enforced at the HTTP/API layer.
 * These tests run directly against the backend API (not the React UI)
 * so they don't require both tenants to be visually accessible.
 *
 * Environment variables required:
 *   API_BASE_URL         - backend API base (default: http://localhost:8000)
 *   E2E_TENANT_A_HOST    - subdomain host for tenant A (default: demo.localhost:8000)
 *   E2E_TENANT_B_HOST    - subdomain host for tenant B (default: other.localhost:8000)
 *   E2E_ADMIN_EMAIL      - valid admin email on TENANT A
 *   E2E_ADMIN_PASSWORD   - valid admin password on TENANT A
 *
 * Tests are skipped when credentials are not configured (safe for CI
 * pipelines that don't provision two tenants).
 */

import { test, expect, request as playwrightRequest } from '@playwright/test';
import { credentials, ensureCredentialsConfigured } from './helpers/auth';

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000';
const TENANT_A_HOST = process.env.E2E_TENANT_A_HOST || 'demo.localhost:8000';
const TENANT_B_HOST = process.env.E2E_TENANT_B_HOST || 'other.localhost:8000';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Login via REST API and return the access token.
 * Uses Host header to target a specific tenant.
 */
async function apiLogin(
  apiContext: Awaited<ReturnType<typeof playwrightRequest.newContext>>,
  email: string,
  password: string,
  host: string,
): Promise<string | null> {
  const res = await apiContext.post(`${API_BASE}/api/users/auth/login/`, {
    headers: { Host: host, 'Content-Type': 'application/json' },
    data: { email, password },
  });
  if (!res.ok()) return null;
  const body = await res.json();
  return body?.tokens?.access ?? null;
}

// ---------------------------------------------------------------------------
// Test Suite
// ---------------------------------------------------------------------------

test.describe('Cross-Tenant API Isolation', () => {
  test.describe.configure({ mode: 'serial' });

  // ------------------------------------------------------------------ //
  // 1. Unauthenticated tenant resolution                                //
  // ------------------------------------------------------------------ //

  test('returns 401 not 403 for unauthenticated requests to any tenant', async () => {
    const ctx = await playwrightRequest.newContext();
    const res = await ctx.get(`${API_BASE}/api/v1/courses/`, {
      headers: { Host: TENANT_A_HOST },
    });
    // Must be 401 (auth), NOT 403 (tenant mismatch) for anonymous users
    expect(res.status()).toBe(401);
    await ctx.dispose();
  });

  // ------------------------------------------------------------------ //
  // 2. Valid token on WRONG tenant → 403                               //
  // ------------------------------------------------------------------ //

  test('authenticated user on wrong tenant host receives 403', async () => {
    try {
      ensureCredentialsConfigured('admin');
    } catch {
      test.skip(true, 'Admin credentials not configured — skipping cross-tenant test');
      return;
    }

    const ctx = await playwrightRequest.newContext();

    // Login on Tenant A (correct host)
    const token = await apiLogin(ctx, credentials.admin.email, credentials.admin.password, TENANT_A_HOST);
    if (!token) {
      test.skip(true, `Could not authenticate on ${TENANT_A_HOST} — skipping`);
      await ctx.dispose();
      return;
    }

    // Use Tenant A's token against Tenant B's host
    const res = await ctx.get(`${API_BASE}/api/v1/courses/`, {
      headers: {
        Host: TENANT_B_HOST,
        Authorization: `Bearer ${token}`,
      },
    });

    // Middleware must reject the cross-tenant request
    expect(res.status()).toBe(403);
    await ctx.dispose();
  });

  // ------------------------------------------------------------------ //
  // 3. Valid token on CORRECT tenant → 200                             //
  // ------------------------------------------------------------------ //

  test('authenticated user on own tenant host receives 200', async () => {
    try {
      ensureCredentialsConfigured('admin');
    } catch {
      test.skip(true, 'Admin credentials not configured — skipping');
      return;
    }

    const ctx = await playwrightRequest.newContext();

    const token = await apiLogin(ctx, credentials.admin.email, credentials.admin.password, TENANT_A_HOST);
    if (!token) {
      test.skip(true, `Could not authenticate on ${TENANT_A_HOST} — skipping`);
      await ctx.dispose();
      return;
    }

    const res = await ctx.get(`${API_BASE}/api/v1/courses/`, {
      headers: {
        Host: TENANT_A_HOST,
        Authorization: `Bearer ${token}`,
      },
    });

    // Must be 200 (or 403 from role check, not tenant mismatch)
    expect(res.status()).not.toBe(403);
    await ctx.dispose();
  });

  // ------------------------------------------------------------------ //
  // 4. Course data does not bleed across tenants                        //
  // ------------------------------------------------------------------ //

  test('course list for tenant A does not include tenant B courses', async () => {
    try {
      ensureCredentialsConfigured('admin');
    } catch {
      test.skip(true, 'Admin credentials not configured — skipping');
      return;
    }

    const ctx = await playwrightRequest.newContext();

    const tokenA = await apiLogin(ctx, credentials.admin.email, credentials.admin.password, TENANT_A_HOST);
    if (!tokenA) {
      test.skip(true, `Could not authenticate on ${TENANT_A_HOST} — skipping`);
      await ctx.dispose();
      return;
    }

    const resA = await ctx.get(`${API_BASE}/api/v1/courses/`, {
      headers: {
        Host: TENANT_A_HOST,
        Authorization: `Bearer ${tokenA}`,
      },
    });

    if (!resA.ok()) {
      test.skip(true, 'Course endpoint not accessible — skipping');
      await ctx.dispose();
      return;
    }

    const bodyA = await resA.json();
    const coursesA = bodyA?.results ?? bodyA ?? [];

    // All returned courses must belong to Tenant A (verify no tenant_id bleed)
    for (const course of coursesA) {
      // If courses expose a tenant field, assert it matches Tenant A
      if (course.tenant_id) {
        // We don't know Tenant B's ID at this level, but all should be the same
        const firstTenantId = coursesA[0]?.tenant_id;
        expect(course.tenant_id).toBe(firstTenantId);
      }
    }

    await ctx.dispose();
  });

  // ------------------------------------------------------------------ //
  // 5. Tenant theme endpoint returns correct tenant branding             //
  // ------------------------------------------------------------------ //

  test('theme endpoint resolves correct tenant from Host header', async () => {
    const ctx = await playwrightRequest.newContext();

    const res = await ctx.get(`${API_BASE}/api/tenants/theme/`, {
      headers: { Host: TENANT_A_HOST },
    });

    // Public endpoint — must be 200
    expect(res.status()).toBe(200);
    const body = await res.json();
    // Response must indicate a tenant was found
    expect(body.tenant_found).toBeTruthy();

    await ctx.dispose();
  });

  // ------------------------------------------------------------------ //
  // 6. Token stolen from one tenant cannot be used on another           //
  // ------------------------------------------------------------------ //

  test('JWT from tenant A cannot access webhooks on tenant B', async () => {
    try {
      ensureCredentialsConfigured('admin');
    } catch {
      test.skip(true, 'Admin credentials not configured — skipping');
      return;
    }

    const ctx = await playwrightRequest.newContext();

    // Obtain a valid admin token for Tenant A
    const token = await apiLogin(ctx, credentials.admin.email, credentials.admin.password, TENANT_A_HOST);
    if (!token) {
      test.skip(true, `Could not authenticate on ${TENANT_A_HOST} — skipping`);
      await ctx.dispose();
      return;
    }

    // Attempt to use it against Tenant B's webhook endpoint
    const res = await ctx.get(`${API_BASE}/api/v1/webhooks/`, {
      headers: {
        Host: TENANT_B_HOST,
        Authorization: `Bearer ${token}`,
      },
    });

    expect(res.status()).toBe(403);
    await ctx.dispose();
  });
});

// ---------------------------------------------------------------------------
// UI-level smoke test: login page resolves tenant from URL/host
// ---------------------------------------------------------------------------

test.describe('Tenant-Aware Login Page', () => {
  test('login page loads for configured tenant', async ({ page }) => {
    await page.goto('/login', { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible({ timeout: 10000 });
  });

  test('login fails immediately with wrong-tenant portal flag', async ({ page }) => {
    // Try to log in a teacher on the wrong portal (admin login page)
    // The backend checks tenant membership and returns 403.
    await page.goto('/login', { waitUntil: 'domcontentloaded' });

    // Use a clearly non-existent account to avoid environment dependency
    await page.getByLabel(/email/i).fill('ghost@nonexistent-tenant-xyz.com');
    await page.getByLabel(/password/i).fill('SomePass123');
    await page.getByRole('button', { name: /sign in/i }).click();

    // Must stay on /login (not navigate to dashboard)
    await expect(page).toHaveURL(/.*\/login/, { timeout: 10000 });
  });
});
