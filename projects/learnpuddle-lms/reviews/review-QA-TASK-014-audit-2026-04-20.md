---
tags: [review, task/TASK-014, task/QA-AUDIT, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: QA Audit — TASK-014 Badge Rarity Tiers

## Verdict: APPROVE

## Summary

QA follow-up to the (already approved) TASK-014 implementation. The audit
correctly reconciles a test-count discrepancy noted in the original request
(claimed 18, delivered 15) and adds the three missing teacher-API tests.
Backfill is consistent with the existing TDD-red style and covers the
previously under-tested paths: earned-badge nesting, multi-rarity round-trip,
and cross-tenant isolation of teacher badge definitions. No production files
touched.

## Scope Verified

| Concern | Result |
|---------|--------|
| Static audit items match the on-disk code | OK — re-verified BADGE_RARITY_CHOICES has 6 tiers, BADGE_CATEGORY_CHOICES has 6 (incl. `social_learning`), `rarity` on both `BadgeDefinitionSerializer` and `BadgeDefinitionCreateSerializer`, migration 0015 depends on 0014 |
| Three new teacher-API tests actually present in `tests_badge_rarity.py` | OK — `test_teacher_earned_badges_include_rarity` (L283–302), `test_teacher_badge_definitions_multiple_rarities` (L304–318), `test_teacher_cannot_see_other_tenant_badge_definitions` (L320–337) |
| File count now 18 as claimed | OK — Model 8 + AdminAPI 6 + TeacherAPI 4 = 18 |
| `TeacherBadge` imported when needed for earned-badge fixture | OK — line 20 |
| No production files modified | OK — only `tests_badge_rarity.py` changed in this round |
| Tests consistent with TASK-014 review intent | OK — TASK-014 verdict was APPROVE; these additions shore up the "comprehensive teacher-path coverage" bullet |

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

**m1. `test_badge_list_includes_rarity` and `test_teacher_badge_definitions_include_rarity`
guard the assertion with `if isinstance(results, list) and results:`.**
If the response envelope changes or the list happens to be empty, the test
silently passes instead of failing. Since the setup creates a badge
immediately before the GET, `results` will always be non-empty in practice —
but a stricter `self.assertTrue(results); self.assertIn("rarity", results[0])`
would make regressions noisier. Cosmetic.

**m2. `test_teacher_badge_definitions_multiple_rarities` creates 3 badges and
asserts `len(results) == 3`.**
This is correct today because the `TenantManager` scopes to this tenant and
the test uses a freshly-created tenant in `setUp`. If a future fixture change
seeded baseline badges, the strict equality would flake. The set-equality
assertion on `actual_rarities` is the actual correctness check; the `len == 3`
is defensive only. Fine to leave.

**m3. Shared fixture with `TestCase` (non-transactional cleanup expectations).**
`BadgeRarityTeacherApiTest` uses `setUp` (per-method), so each test gets a
fresh tenant + teacher, avoiding cross-method bleed. Good. Just worth noting
that cross-file parallel test runs would need tenant subdomains to stay unique
— `rarityteacher` + `rarityschoolb` are unique within the file, fine.

## Positive Observations

- **`test_teacher_earned_badges_include_rarity` asserts the exact string
  value**, not just presence of the key (`self.assertEqual(nested_badge["rarity"], "epic")`).
  That catches a bug where the serializer emits the field but drops the value
  (e.g., wrong `source=` after a refactor).
- **Cross-tenant isolation test at the teacher endpoint** complements the
  existing admin-path cross-tenant test from the original file, closing the
  matrix.
- **QA author self-corrected the 15→18 count** before sending, rather than
  hand-waving around it. Exactly the right posture.
- **Checklist for reviewer explicitly calls out pending manual steps**
  (pytest run, Swagger visibility, migration order in prod) — that's
  honest about what static review can and can't cover.

## Verification Note

Docker still unavailable in this sandbox. Re-confirming the author-supplied
verification step before closing:

```bash
docker compose exec web pytest apps/progress/tests_badge_rarity.py -v
```

Expected: **18 passed**.

Post-merge spot checks (from the QA checklist):
- [ ] `rarity` field in Swagger/`/api/docs/` after 0015 is applied.
- [ ] `python manage.py showmigrations progress` confirms 0015 lands
  immediately after 0014.

— lp-reviewer
