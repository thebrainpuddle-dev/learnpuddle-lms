---
tags: [review, task/QA-OPS-VIEWS-COVERAGE, verdict/approve, reviewer/lp-reviewer, area/ops, area/tests]
created: 2026-04-21
---

# Review: QA — apps/ops/views.py coverage (`tests_ops_views.py`, 44 tests)

## Verdict: APPROVE

## Summary
Well-scoped coverage push for a previously under-tested 861-line file.
The existing `apps/ops/tests.py` (143 lines, 4 tests) covered only a
handful of happy paths and zero auth walls. The new
`tests_ops_views.py` adds 44 tests that pin auth walls on 6 endpoints,
the full incident lifecycle (including idempotence and invalid
transitions), error-list default-filter semantics, and row-shape
contracts across incidents/tenants/errors. Test style matches the
existing file, and every view response shape the tests assert against is
verifiable line-by-line in `apps/ops/views.py`.

## Critical Issues
None.

## Major Issues
None. Cannot execute pytest in sandbox (same Docker limitation
backend-security and QA hit elsewhere today), but static verification
traces cleanly — see table below.

## Minor Issues

### m1. `TestOpsAuthWalls` per-class count mismatch (doc only)
The inbox note / shared-log table claims `TestOpsAuthWalls | 9`, but the
file has 6 test methods:

- `test_anonymous_requests_return_401` (1 method, subTest loop over 6 URLs
  — pytest's default reporter treats this as 1 test, not 6)
- `test_school_admin_requests_return_403` (1 method, subTest loop)
- `test_super_admin_can_access_overview` / `tenants` / `incidents` / `errors`
  (4 methods)

Total = 6 methods. That means the per-class column sums to 47
(9+2+4+6+9+9+3+2+3) while the headline count is 44 (6+2+4+6+9+9+3+2+3).
Pytest will correctly report **44 collected**. The 6+2+4+6+9+9+3+2+3 = 44
arithmetic is the one that matches the file. **Non-blocking**; only the
table in the inbox note is slightly off. Fix the table on next touch.

### m2. `TestOpsAuthWalls` omits SUPER_ADMIN happy-path for two endpoints
`test_super_admin_can_access_*` only covers `overview`, `tenants`,
`incidents`, `errors` — skips `replay-cases/` and `actions/catalog/`
(each of which *does* get a dedicated 200 test in their own
`TestOpsReplayCases` / `TestOpsActionsCatalog` classes, so coverage is
not lost; just not symmetric in the auth-walls class). Either add two
more methods to `TestOpsAuthWalls` or remove the other four for
symmetry. **Non-blocking** — the coverage fact is preserved.

### m3. `TestOpsIncidentsList` row-shape assertion uses `results[0]` without sort control
`test_incident_row_has_required_keys` (line 303) reads `results[0]` but
the view orders by `-started_at`. Since the setUp creates three
incidents in quick succession with auto-now timestamps, "first" is
whichever insert the DB happens to return last — fine in practice, but
an equivalent iteration over all `results` would be more robust. **Not
blocking** — the keys asserted are on every row by construction of the
view serializer.

## Positive Observations

### Static verification traces cleanly

| Test assertion | View line | Match |
|---------------|-----------|------|
| `overview.totals` keys `tenants/healthy/degraded/down/maintenance` | `views.py:194–200` | ✅ exact keys |
| `overview.open_incidents[*].id` is string | `:169` `str(i.id)` | ✅ |
| `tenants.results[*]` keys (`tenant_id,name,subdomain,status,failures_week`) | `:269–281` | ✅ all present |
| `incidents.results[*]` keys (`id,severity,status,title,started_at,last_seen_at`) | `:379–395` | ✅ all present |
| `incidents?status=OPEN` filter | `:373–374` | ✅ exact |
| `incidents?severity=P1` filter | `:375–376` | ✅ exact |
| `ops_incident_acknowledge` on RESOLVED → 400 + `{error: ...}` | `:408–409` | ✅ exact |
| `ops_incident_resolve` on RESOLVED → 200 `{ok: true}` idempotent | `:422–423` | ✅ exact |
| `ops_errors` default `status_code__in=[429, 500]` | `:549` | ✅ exact |
| `ops_errors?status_codes=429` filter | `:543–545` (parses comma-list) | ✅ |
| `ops_errors?tenant_id=` filter | `:530–531` | ✅ |
| `ops_error_detail` 200 shape `{error_group, recent_replay_steps}` | `:560–575` | ✅ |
| `ops_tenant_timeline` 404 on unknown tenant id | `:294` `get_object_or_404` | ✅ |

### Design quality

- **Auth-wall breadth via subTest**: two loop-methods over
  `PROTECTED_ENDPOINTS` are the right ergonomic — adding a future ops
  endpoint to the list picks up 401 + 403 coverage for free. The trade-off
  is subTest failures report inside a single test name; acceptable given
  the domain (auth regressions should be rare and loud).
- **Incident determinism**: every lifecycle test calls `_make_incident`
  fresh with `uuid.uuid4()` in the dedupe key, so tests don't cross-
  contaminate. Matches the advertised design note; verified at the
  factory (line 84).
- **Error-filter semantics**: `test_errors_default_excludes_non_500_429`
  creates a fresh 403-code error and asserts it's absent from the default
  response. This directly pins the `qs.filter(status_code__in=[429, 500])`
  default at `views.py:549`. If someone widens the default in a future
  refactor (a very plausible regression), this test catches it.
- **Idempotent resolve**: `test_resolve_already_resolved_is_idempotent`
  pins the early-exit branch at `views.py:422–423`, which is otherwise
  dead code in the happy path. Good defensive test.
- **URL mount verified**: `/api/v1/super-admin/ops/...` resolves through
  `config/urls.py:141` → `api_v1` → `_api_patterns` →
  `'super-admin/'` → `apps.tenants.superadmin_urls` → `'ops/'` →
  `apps.ops.urls`. Tests' `SUPER_ADMIN_PREFIX = "/api/v1/super-admin/ops"`
  is correct.
- **Factories conform to model contract**: verified `OpsIncident`
  (`models.py:109`) has fields `severity, scope, dedupe_key, status` used
  by `_make_incident`, and `OpsRouteError` (`:278`) accepts the
  factory's `status_code, fingerprint, total_count, count_1h, count_24h`.

### Style discipline

- No production code touched — pure test addition.
- `@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")`
  applied consistently at class level, and the `OpsBaseTestCase` avoids
  per-test setUp duplication.
- Comment header at the top names every endpoint family covered, which
  makes the file grep-friendly for future contributors hunting coverage.

## Outstanding (not owed by qa-tester)

- **Live pytest run** — `docker compose exec web pytest apps/ops/tests_ops_views.py -v`.
  Route to devops (same ticket as BE-SEC-P0 + BE-SEC-P1 test runs — one
  session covers all three). Expected output: `44 passed`.

## Recommendation

Approved. Safe to merge once the live pytest run confirms 44/44 green.
Minor items (m1–m3) are doc/symmetry and do not require a round-trip.

— reviewer (lp-reviewer)
