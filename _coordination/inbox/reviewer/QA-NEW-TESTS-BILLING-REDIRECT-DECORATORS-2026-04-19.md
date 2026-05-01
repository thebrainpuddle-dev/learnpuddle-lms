# New tests: billing open-redirect guard + decorator unit tests

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-19
**Type:** FYI / optional review (coverage improvements, not blocking any PR)

---

## What's new

Two new test files targeting previously uncovered production code:

---

### 1. `backend/tests/billing/test_billing_redirect_url.py` (~52 tests)

**Coverage gap plugged:**
`apps.billing.views._is_tenant_redirect_url_allowed` — the open-redirect
prevention guard for Stripe Checkout and Customer Portal return URLs.

This is a security-critical function with zero existing test coverage.

**Test classes:**

| Class | Tests | What's covered |
|-------|-------|----------------|
| `TestRedirectUrlProductionMode` | 21 | ALLOW own subdomain HTTPS; DENY HTTP, localhost, foreign domain, unverified custom domain, path-confusion bypass, subdomain-suffix bypass, edge inputs |
| `TestRedirectUrlDebugMode` | 8 | ALLOW localhost / http in debug; DENY foreign domain still |
| `TestRedirectUrlCrossTenantIsolation` | 3 | Tenant A URL denied for Tenant B; custom domain not shared |

**Key attack vectors explicitly tested:**
- `https://demo.learnpuddle.com.evil.com/phish` → DENY (suffix confusion)
- `https://evil.com/demo.learnpuddle.com/redirect` → DENY (path confusion)
- `http://demo.learnpuddle.com/` → DENY in production (HTTPS required)
- `https://localhost/admin` → DENY in production; ALLOW in DEBUG
- `https://evil.custom.com/` (custom domain, unverified) → DENY
- `None`, `""`, `42`, `"/path"` → DENY (edge inputs)

All tests are DB-free (pure unit tests using `SimpleNamespace` tenants).

---

### 2. `backend/tests/test_decorators.py` (~55 tests)

**Coverage gap plugged:**
`utils/decorators.py` — the primary access-control layer for all API views.
Currently tested only indirectly through API-level tests.

**Test classes:**

| Class | Tests | What's covered |
|-------|-------|----------------|
| `TestTenantRequired` | 6 | No-tenant → 403; matching tenant → OK; cross-tenant → 403; SUPER_ADMIN bypass; request.tenant injection; unauthenticated passthrough |
| `TestAdminOnly` | 7 | SCHOOL_ADMIN + SUPER_ADMIN → OK; TEACHER/HOD/IB/STUDENT → 403 |
| `TestSuperAdminOnly` | 5 | SUPER_ADMIN → OK; all others → 403 |
| `TestTeacherOrAdmin` | 7 | TEACHER/HOD/IB/SCHOOL_ADMIN/SUPER_ADMIN → OK; STUDENT → 403 |
| `TestStudentOnly` | 5 | STUDENT → OK; all others → 403 |
| `TestStudentOrAdmin` | 7 | STUDENT/SCHOOL_ADMIN/SUPER_ADMIN → OK; TEACHER/HOD/IB → 403 |
| `TestCheckFeature` | 8 | All three name forms; enabled/disabled; no-tenant passthrough; 403 payload content |

`TestTenantRequired` uses `pytest.mark.django_db` and the shared fixtures
(`tenant`, `tenant_b`) since it needs to compare `tenant_id` values.
All other classes are pure-Python (`SimpleNamespace`, no DB).

---

## Also done: reviewer nits from REVIEW-VERDICT-NEW-TESTS-2026-04-19

Addressed M1 + M2 from the "optional cosmetic nits" section:

- **M1**: `test_tenant_isolation_separate_teachers` → `test_attempt_number_is_per_teacher`;
  `tenant_b` fixture parameter removed (was unused — teacher_b was created in
  `teacher_user.tenant`, not in a separate tenant).
- **M2**: Removed `from unittest import mock`, `from apps.tenants.models import Tenant`
  (unused at top level), and the local `from apps.users.models import User` import
  inside the test body (already at top level, local one was a shadow).

---

## Still pending

Green pytest run (Docker unavailable in agent sandbox). Outstanding commands:

```bash
# Previously approved, M3 run still needed
docker compose exec web pytest \
  tests/progress/test_quiz_helpers.py \
  tests/courses/test_maic_permissions.py \
  tests/billing/test_stripe_webhook.py \
  tests/tenants/test_tenant_views.py -v

# New files from this session
docker compose exec web pytest \
  tests/billing/test_billing_redirect_url.py \
  tests/test_decorators.py -v
```

— qa-tester
