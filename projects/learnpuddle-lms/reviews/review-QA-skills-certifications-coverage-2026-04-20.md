---
tags: [review, task/QA-COVERAGE-skills-certifications, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: QA Coverage — Skills & Certification Views

## Verdict: APPROVE

## Summary

Two large, previously-untested view modules (`skills_views.py` 456 lines,
`certification_views.py` 407 lines, both at 0% coverage) now have thorough
behavioral coverage. Happy path, validation errors, auth (401/403), role gating,
cross-tenant isolation, and a pair of noteworthy side effects (expiry-check
auto-marking, `last_assessed` auto-stamp) are asserted. Tests follow the
existing pattern of `setUpTestData` class-level fixtures plus per-test
throwaways for mutating operations, which keeps the suite fast and isolated.

## Scope Verified

| Concern | Result |
|---------|--------|
| Test counts match request (54 skills + 49 certs = 103) | OK — counted by inspection: skills 9+7+4+7+6+9+3+7+2=54; certs 6+7+5+7+5+4+4+8+3=49 |
| No production code modified | OK — both files are pure additions under `apps/progress/tests_*.py` |
| Cross-tenant isolation is asserted, not just implied | OK — `SkillCrossTenantIsolationTests` and `CertCrossTenantIsolationTests` assert both 404 (UUID access) and 403 (host mismatch) paths |
| Auth guards asserted at both 401 and 403 layers | OK — every endpoint has a teacher→403 and anon→401 case |
| Side-effect regressions pinned | OK — `test_expiry_check_catches_already_expired` asserts `status='expired'` is written back, `test_teacher_skill_update_sets_last_assessed` asserts the auto-stamp |
| Tests verify behavior, not implementation | OK — all assertions target HTTP status + response body / DB state; no mocks |
| `all_objects` vs `objects` usage in fixtures | OK — `all_objects` used only for setup/cleanup to bypass TenantManager; test assertions use the real API which goes through `objects` |

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

**m1. Cross-tenant 403/404 assertions accept either status.**
`SkillCrossTenantIsolationTests.test_admin_b_on_tenant_a_host_sees_tenant_a_skills_only`
(L698–706) and `CertCrossTenantIsolationTests.test_admin_b_on_primary_host_gets_403`
(L670–673) use `self.assertIn(resp.status_code, [403, 404])`. The actual
behavior is deterministic — `@tenant_required` raises 403 when
`request.user.tenant_id != request.tenant.id`. Pinning to a single expected
status would catch a future behavior-change bug (e.g., a refactor that silently
swaps 403→404) that the current assertion would accept. Non-blocking, but
worth tightening next touch.

**m2. Unused `HOST_OTHER` constant in both files.**
`HOST_OTHER = "other.lms.com"` / `"rival.lms.com"` is defined but never
referenced. The cross-tenant tests all hit the primary `HOST`. Dead code —
either wire it into a test that hits the rival tenant's subdomain with
admin_b (the complementary-direction case) or drop the constant.

**m3. `CertDetailTests.test_cert_detail_cross_tenant_returns_404` (L418–429)
creates `cert_b` with `teacher=self.admin_b`.**
`admin_b` has `role='SCHOOL_ADMIN'`, not `TEACHER`. The test only checks HTTP
404 so it passes, but the fixture is semantically odd and would be misleading
if someone reads it to understand the data model. Should use `teacher2` or a
new tenant-B teacher. Cosmetic.

**m4. List-result extraction uses permissive fallback.**
Several tests use `data.get("results", data.get("data", []))` or
`data.get("results", data)`. The Skills and Certifications endpoints appear to
use DRF pagination, so `results` should always be present. The fallback
silently hides a regression if pagination is ever removed (tests would still
"pass" against an unpaginated list). Non-blocking.

## Positive Observations

- **Design notes in the QA request are accurate and useful.** Calling out the
  `all_objects` duplicate-check path and the `POST /expiry-check/` side effect
  tells a future reader why the tests look the way they do.
- **`test_cert_renew_extends_expiry` uses `refresh_from_db()` before comparing
  `expires_at`.** Avoids the classic stale-Python-object gotcha.
- **`test_bulk_update_unknown_id_returns_error_entry`** is the exact shape of
  test I'd hope to see for a bulk endpoint — the 200 with `errors[]` contract
  is easy to accidentally break and hard to re-derive from the view code.
- **Gap analysis test inspects `recommended_courses`**, which is the only
  interesting field of that endpoint — not just status code.
- **Fast**: `setUpTestData` at the base class means the tenant/admin/teacher/
  skill/course fixture is created once per test class, not per method.
- **No git ops by the author.**

## Verification Note

Unable to run `docker compose exec web pytest` in this sandbox. Please execute
the author-supplied command before closing the task:

```bash
docker compose exec web pytest \
  apps/progress/tests_skills_views.py \
  apps/progress/tests_certification_views.py -v
```

Expected: **103 passed**. If any fail, the likely culprits are:
1. `api/v1/skills/...` vs `api/skills/...` URL routing (v1 prefix assumed here).
2. `results` envelope shape — pagination config differences.

— lp-reviewer
