# Review Request: TASK-014 — Badge Rarity Tiers

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-20
**Priority:** P2 (Phase 4 Gamification)

## What was built

Added 6-tier badge rarity system to `BadgeDefinition` as specified in the master strategy
("Badge taxonomy: 6 rarity tiers, 6 categories, 30+ badges").

## Files to review

| File | Purpose |
|------|---------|
| `backend/apps/progress/gamification_models.py` | Model change — `BADGE_RARITY_CHOICES`, 6th category, `rarity` field |
| `backend/apps/progress/gamification_serializers.py` | Serializer — `'rarity'` added to both badge serializers |
| `backend/apps/progress/migrations/0015_badge_rarity_tiers.py` | Migration |
| `backend/apps/progress/tests_badge_rarity.py` | 18 TDD tests |
| `docs/coordination/TASK-014-badge-rarity-tiers.md` | Task doc |

## Key design decisions

1. **Rarity is display-only** — does not affect `criteria_type`/`criteria_value` award logic
2. **Migration is additive-only** — `AddField(default='common')` — zero-downtime, no backfill
3. **Default='common'** — existing badges silently inherit the base tier
4. **6th category 'social_learning'** — pure Django choice, no DB schema change needed
5. **Both serializers updated** — read (list endpoint) and write (create/update endpoint)

## Test coverage

- 8 model-level tests (choices count, all 6 tiers, all 6 categories, default, round-trip)
- 6 admin API tests (list includes rarity, create with rarity, social_learning category,
  default-to-common, update rarity, invalid rarity → 400)
- 4 teacher API tests (badge definitions include rarity)

## What reviewers should check

1. Migration dependency chain: `0014_rubrics` → `0015_badge_rarity_tiers`
2. No existing views broken by adding optional `rarity` field
3. `BADGE_RARITY_CHOICES` not referenced in engine (correct — it's display-only)
4. Test host headers use `{subdomain}.lms.com` (matches conftest PLATFORM_DOMAIN)
