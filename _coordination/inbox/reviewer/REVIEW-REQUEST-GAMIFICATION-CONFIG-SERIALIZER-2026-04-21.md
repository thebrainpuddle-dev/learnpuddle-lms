# Review Request — GamificationConfigSerializer: add missing model fields

**From:** backend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-21
**Tag:** TASK-015b (non-blocking follow-up from TASK-015 review)
**Priority:** Low — polish, no security impact

---

## Context

TASK-015 review (verdict 2026-04-20) noted:
> "`GamificationConfigSerializer.Meta.fields` omits the 7 new fields — add them
> so the Admin Gamification page can tune freeze behaviour without a shell."

Additionally, subsequent tasks (TASK-018 Mastery Points, TASK-019 Puddle Coins)
added more tunable fields to `GamificationConfig` that were never added to the
serializer. This change adds all missing fields in a single pass.

---

## Change

**`backend/apps/progress/gamification_serializers.py`** — `GamificationConfigSerializer`

Fields added:

| Field | Task | Purpose |
|-------|------|---------|
| `xp_per_lesson_reflection` | Base model | Lesson reflection XP rate |
| `mp_quiz_threshold_percent` | TASK-018 | Min quiz score % for MP award |
| `mp_quiz_weight` | TASK-018 | MP multiplier for quiz score |
| `mp_assignment_threshold_percent` | TASK-018 | Min assignment score % for MP |
| `mp_assignment_weight` | TASK-018 | MP multiplier for assignment grade |
| `mp_course_bonus` | TASK-018 | Flat MP bonus on course completion |
| `coins_per_level_up` | TASK-019 | Coins granted on level-up |
| `coins_per_challenge` | TASK-019 | Coins granted on challenge completion |
| `coins_per_league_promote` | TASK-019 | Coins granted on league promotion |

The existing streak-freeze fields from TASK-015 were already present and are unchanged.

---

## Risk

Low. These are additive `read_only=False` fields on an existing `ModelSerializer`.
No migrations needed (all fields already exist in the DB). No existing behavior changes.
Admin UI that currently uses this serializer will now see 9 additional fields in
GET and accept them in PATCH.

---

## No dedicated tests added

This is a field-list change on `ModelSerializer` — DRF validates field names at
startup. If any field name is misspelled, Django raises `ImproperlyConfigured`
on boot. Integration coverage via the existing gamification config admin tests
is sufficient. qa-tester can add explicit serializer key-presence tests if desired.

— backend-engineer
