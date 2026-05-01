# QA Audit: TASK-014 Badge Rarity Tiers

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-20
**Re:** `reviews/review-request-TASK-014-badge-rarity.md`

## QA verdict: APPROVE (pending Docker pytest run)

Static audit of the full TASK-014 implementation is complete. Everything
checks out. Details below.

---

## Implementation verified

### Model (`gamification_models.py`)
- `BADGE_RARITY_CHOICES` — exactly 6 tiers: common, uncommon, rare, epic,
  legendary, mythic ✅
- `BADGE_CATEGORY_CHOICES` — exactly 6 categories, including new
  `social_learning` ✅
- `BadgeDefinition.rarity` — `CharField(max_length=20, choices=..., default='common')` ✅
- `BadgeDefinition.all_objects = models.Manager()` present (test helper
  uses it) ✅
- `__str__` includes `[category/rarity]` — good for debug logging ✅

### Serializers (`gamification_serializers.py`)
- `rarity` present in `BadgeDefinitionSerializer.fields` (read endpoint) ✅
- `rarity` present in `BadgeDefinitionCreateSerializer.fields` (write endpoint) ✅
- `TeacherBadgeSerializer` nests `BadgeDefinitionSerializer` → rarity flows
  to `/gamification/badges/` endpoint automatically ✅

### Migration (`0015_badge_rarity_tiers.py`)
- `AddField` only — zero-downtime ✅
- `default='common'` — existing badges silently inherit base tier ✅
- Depends on `0014_rubrics` — dependency chain correct ✅
- `social_learning` category addition is a Django-level choice only — no
  DB schema change needed, no migration operation required ✅

### Views
- Admin: `badge_list`, `badge_create`, `badge_update`, `badge_delete` all
  decorated with `@admin_only @tenant_required` ✅
- Teacher: `teacher_badge_definitions` filters `is_active=True`, uses
  `BadgeDefinitionSerializer` ✅
- Teacher: `teacher_badges` filters by `request.user`, nests
  `BadgeDefinitionSerializer` ✅

---

## Test file correction

The review request claimed **18 tests** (8 model + 6 admin + 4 teacher
API), but the submitted file had only **15 tests** (1 teacher API test
instead of 4). Three missing teacher API tests have been added:

| New test | What it covers |
|----------|---------------|
| `test_teacher_earned_badges_include_rarity` | `/gamification/badges/` — rarity in nested `TeacherBadgeSerializer.badge` |
| `test_teacher_badge_definitions_multiple_rarities` | All 3 asserted tiers survive the endpoint round-trip |
| `test_teacher_cannot_see_other_tenant_badge_definitions` | Cross-tenant isolation guard for teacher badge definitions |

Also added `TeacherBadge` to the import block (needed for the earned-badge
test fixture). No production files modified.

**File now has 18 tests** — matches the review request.

---

## Test run command

Docker still unavailable in the qa-tester sandbox. Run to confirm green:

```bash
docker compose exec web pytest apps/progress/tests_badge_rarity.py -v
```

Expected: 18 passed.

---

## Checklist for reviewer

- [ ] Run the pytest command above and confirm 18 passed
- [ ] Confirm `rarity` field appears in Swagger docs (`/api/docs/`) after
  migration is applied
- [ ] Confirm migration order is correct in prod (after `0014_rubrics`)

— qa-tester
