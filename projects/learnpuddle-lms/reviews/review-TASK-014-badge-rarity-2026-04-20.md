---
tags: [review, task/TASK-014, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-014 — Badge Rarity Tiers + Social Learning Category

## Verdict: APPROVE

## Summary

Clean, minimal, additive-only implementation of the 6-tier rarity system and
the 6th `social_learning` badge category. Migration is zero-downtime, serializers
are consistent on both read and write paths, and tests comprehensively cover
model, admin API, and teacher API behavior including cross-tenant isolation.
Rarity is correctly kept display-only — award logic in `gamification_engine.py`
remains untouched.

## Scope Verified

| Concern | Result |
|---------|--------|
| Migration is additive-only (AddField, no data migration) | OK — `migrations/0015_badge_rarity_tiers.py` |
| Migration depends on `0014_rubrics` | OK — confirmed in `dependencies` |
| Default is `'common'` so existing rows survive | OK — `default='common'` at model + migration |
| Both read & write serializers expose `rarity` | OK — `BadgeDefinitionSerializer` (L30, L36) and `BadgeDefinitionCreateSerializer` (L43, L49) |
| `TeacherBadgeSerializer` nests rarity to earned-badge endpoint | OK — line 100 |
| Admin views use `@admin_only @tenant_required` | OK — all four (`badge_list`, `badge_create`, `badge_update`, `badge_delete`) |
| Teacher views filter `is_active=True` + tenant scoping | OK — `teacher_badge_definitions` uses `BadgeDefinition.objects` (TenantManager) + `is_active=True` filter |
| Cross-tenant isolation test creates two tenants, asserts 0 leakage | OK — `test_teacher_cannot_see_other_tenant_badge_definitions` creates tenant B, checks tenant A response does not include B's badge |
| `rarity` not referenced in `gamification_engine.py` | OK — grep confirms no match |

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **`teacher_badges` uses `TeacherBadge.all_objects`** (bypasses TenantManager) and relies on
   `teacher=request.user` for isolation. This is safe (a user belongs to one tenant) but
   inconsistent with `teacher_badge_definitions` which uses the TenantManager. Not introduced by
   this PR; noting as a follow-up housekeeping item, not blocking TASK-014.

2. **`test_badge_list_includes_rarity` uses `if results: ...`** — the assertion only runs when the
   list is non-empty. Since `_create_badge` is called before the GET, the list should be non-empty,
   but the guard makes the test pass vacuously if the list endpoint ever returns `[]`. Consider
   asserting `self.assertTrue(results)` first. Not blocking.

3. **Docker pytest run still outstanding** — qa-tester's audit was static-only (sandbox-blocked).
   Given the implementation's simplicity (new char field with choices + default), the risk of
   a test-only regression is very low, but the reviewer approval is conditional on a green run of:
   `docker compose exec web pytest apps/progress/tests_badge_rarity.py -v` (expected: 18 passed).

## Positive Observations

- **YAGNI-clean**: no speculative rarity-based logic in the engine. Rarity is purely a display
  attribute, exactly matching the spec's "display/prestige attribute" directive.
- **Zero-downtime migration**: `AddField` with `default='common'` is the textbook correct pattern
  for adding a required-with-default field to an existing table.
- **Social-learning category as Django-only choice**: no migration op needed (Django `choices`
  isn't enforced at the DB level), which is the cheapest correct approach.
- **Test fixture helper `_create_badge` uses `BadgeDefinition.all_objects`** — correctly bypasses
  the TenantManager in test scope where no tenant context is set by middleware.
- **Cross-tenant guard test** is real: two distinct tenants are created, and the assertion is
  name-level (not count-level), making it robust against other test data.
- **Model `__str__` returns `[category/rarity]`** — good for Django admin and log readability.

## Follow-ups (non-blocking)

- Run the pytest command above before merge to confirm 18 passed.
- Confirm `rarity` renders in Swagger at `/api/docs/` after migration applied in staging.
- Consider standardizing `teacher_badges` to use `TeacherBadge.objects` (TenantManager) for
  consistency with `teacher_badge_definitions` (separate task).
