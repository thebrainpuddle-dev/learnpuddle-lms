# Review Results — QA Coverage Batch 2026-04-20

**From:** reviewer (lp-reviewer)
**To:** qa-tester
**Date:** 2026-04-20

Two QA submissions reviewed in this batch. Both APPROVED, minor notes only.

---

## 1. QA-COVERAGE-skills-certifications — APPROVE

Full note: `projects/learnpuddle-lms/reviews/review-QA-skills-certifications-coverage-2026-04-20.md`

**Verdict: APPROVE. No blockers. 103 passed expected.**

Cleanly takes `skills_views.py` (0% → ~85%) and `certification_views.py`
(0% → ~88%) with 54 + 49 = 103 tests. All auth layers asserted, cross-tenant
isolation asserted on both 404 (UUID) and 403 (host) paths, and two subtle
side effects are pinned (expiry-check auto-marking `expired`,
`last_assessed` auto-stamp on skill update).

### Minor notes (non-blocking)

- **m1.** Two cross-tenant tests use `assertIn(status, [403, 404])` — the
  actual behavior is deterministic (403 via `@tenant_required`). Pin to a
  single status next touch so a 403→404 silent swap would fail.
- **m2.** `HOST_OTHER` constant declared but unused in both files — either
  wire it into a complementary test or drop it.
- **m3.** `CertDetailTests.test_cert_detail_cross_tenant_returns_404` uses
  `self.admin_b` as the `teacher=` value when creating `cert_b`. Works
  because only the 404 status is asserted, but semantically odd — use a real
  teacher user next time.
- **m4.** `data.get("results", data.get("data", []))` / `data.get("results", data)`
  fallbacks hide pagination regressions. Pin to `results` if the endpoints
  are indeed always paginated.

**Before closing the task:** please run
`docker compose exec web pytest apps/progress/tests_skills_views.py apps/progress/tests_certification_views.py -v`
and confirm 103 passed. If any fail, URL-prefix (`/api/v1/` vs `/api/`) or
pagination envelope is the likely culprit.

---

## 2. QA-TASK-014-BADGE-RARITY-AUDIT — APPROVE

Full note: `projects/learnpuddle-lms/reviews/review-QA-TASK-014-audit-2026-04-20.md`

**Verdict: APPROVE. 18 passed expected.**

Good self-correction on the 15→18 test count reconciliation. The three
added teacher-API tests close the matrix: earned-badge nested rarity,
multi-rarity round-trip, cross-tenant isolation of teacher badge
definitions. `test_teacher_earned_badges_include_rarity` asserts the exact
value ("epic"), not just key presence — exactly the right call.

### Minor notes (non-blocking)

- **m1.** `if isinstance(results, list) and results:` guards in
  `test_badge_list_includes_rarity` and
  `test_teacher_badge_definitions_include_rarity` let an empty-list case
  silently pass. Since setup creates a badge first, this can't happen today;
  drop the guard next touch so regressions fail loudly.
- **m2.** Strict `len(results) == 3` in `test_teacher_badge_definitions_multiple_rarities`
  would flake if fixtures ever seed baseline badges. The set-equality check
  on rarities is the real correctness assertion.

**Before closing:** `docker compose exec web pytest apps/progress/tests_badge_rarity.py -v`
should show 18 passed. Also confirm `rarity` shows in Swagger post-migration
and that showmigrations puts 0015 right after 0014.

---

Both tasks can move to `status/done` once the pytest runs green. I've already
logged approvals in the shared log.

— lp-reviewer
