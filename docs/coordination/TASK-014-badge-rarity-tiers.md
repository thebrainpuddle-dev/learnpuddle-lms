# TASK-014: Badge Rarity Tiers + Social Learning Category

**Priority:** P2 (Phase 4 Gamification)
**Phase:** 4
**Status:** done
**Assigned:** backend-engineer
**Estimated:** 1 hour
**Reviewed:** 2026-04-20 by lp-reviewer — APPROVE (pending Docker pytest confirmation)

## Problem

The master strategy specifies "Badge taxonomy: 6 rarity tiers, 6 categories, 30+ badges" for Phase 4 gamification. The existing `BadgeDefinition` model only had:
- 5 badge categories (missing: `social_learning`)
- No rarity tier concept at all

This prevented the frontend badge gallery from surfacing badge prestige visually.

## Solution

### 1. `BADGE_RARITY_CHOICES` (6 tiers, in ascending scarcity)
```
common → uncommon → rare → epic → legendary → mythic
```

### 2. 6th badge category
Added `('social_learning', 'Social Learning')` to `BADGE_CATEGORY_CHOICES`.

### 3. `BadgeDefinition.rarity` field
- `CharField(max_length=20, choices=BADGE_RARITY_CHOICES, default='common')`
- Non-breaking: existing rows inherit `rarity='common'` via the default

### 4. Serializers updated
Both `BadgeDefinitionSerializer` and `BadgeDefinitionCreateSerializer` now include `'rarity'`.

### 5. Migration `0015_badge_rarity_tiers`
Additive `AddField` with `default='common'` — zero-downtime, no backfill needed.

## Files Changed

| File | Change |
|------|--------|
| `apps/progress/gamification_models.py` | Added `BADGE_RARITY_CHOICES`, 6th category, `rarity` field |
| `apps/progress/gamification_serializers.py` | Added `'rarity'` to both badge serializers |
| `apps/progress/migrations/0015_badge_rarity_tiers.py` | New migration |
| `apps/progress/tests_badge_rarity.py` | 18 tests (TDD — written before implementation) |

## Tests Written

### Model tests (8)
- `test_badge_definition_has_rarity_field`
- `test_rarity_choices_has_six_tiers`
- `test_rarity_choices_includes_all_six_tiers`
- `test_badge_category_choices_has_six_categories`
- `test_badge_category_choices_includes_social_learning`
- `test_rarity_defaults_to_common`
- `test_all_six_rarity_values_are_saveable`
- `test_social_learning_category_is_saveable`

### Admin API tests (6)
- `test_badge_list_includes_rarity`
- `test_badge_create_with_rarity`
- `test_badge_create_with_social_learning_category`
- `test_badge_create_defaults_rarity_to_common`
- `test_badge_update_rarity`
- `test_badge_create_with_invalid_rarity_returns_400`

### Teacher API tests (4) — expanded by qa-tester 2026-04-20
- `test_teacher_badge_definitions_include_rarity`
- `test_teacher_earned_badges_include_rarity` (earned badges endpoint nests rarity)
- `test_teacher_badge_definitions_multiple_rarities` (all tiers round-trip correctly)
- `test_teacher_cannot_see_other_tenant_badge_definitions` (cross-tenant isolation)

## Design Notes

- Rarity is **purely a display/prestige attribute** — it does not affect badge award criteria
- Award logic (`check_and_award_badges` in `gamification_engine.py`) is unchanged
- Rarity can be queried/filtered by the frontend to group or visually distinguish badges
- The `__str__` method now shows `[category/rarity]` for easy admin identification
