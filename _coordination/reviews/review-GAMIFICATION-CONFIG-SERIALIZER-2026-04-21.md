---
tags: [review, task/TASK-015b, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-21
---

# Review: GamificationConfigSerializer — add missing model fields

## Verdict: APPROVE

## Summary

Clean field-list catch-up. All 9 claimed fields exist on the model
(verified against `apps/progress/gamification_models.py:110–240`), and
the previously omitted streak-freeze / mastery-points / coin tunables
are now reachable from the Admin Gamification page without a shell.

## Field-to-model verification

| Serializer field | Model line | Present |
|------------------|------------|---------|
| `xp_per_content_completion` | 110 | ✅ |
| `xp_per_course_completion` | 111 | ✅ |
| `xp_per_assignment_submission` | 112 | ✅ |
| `xp_per_quiz_submission` | 113 | ✅ |
| `xp_per_lesson_reflection` | 114 | ✅ (added this pass) |
| `xp_per_streak_day` | 115 | ✅ |
| `streak_freeze_max` / `grace_period_hours` / `weekend_mode_available` | 116–127 | ✅ |
| `freeze_token_*` (×3) | 128–139 | ✅ |
| `leaderboard_*` / `opt_out_allowed` | 140–148 | ✅ |
| `leagues_*` / `league_*` (×5) | 150–172 | ✅ |
| `mp_quiz_threshold_percent` | 174 | ✅ (TASK-018, added) |
| `mp_quiz_weight` | 181 | ✅ (TASK-018, added) |
| `mp_assignment_weight` | 188 | ✅ (TASK-018, added) |
| `mp_assignment_threshold_percent` | 195 | ✅ (TASK-018, added) |
| `mp_course_bonus` | 202 | ✅ (TASK-018, added) |
| `coins_per_level_up` | 211 | ✅ (TASK-019, added) |
| `coins_per_challenge` | 215 | ✅ (TASK-019, added) |
| `coins_per_league_promote` | 222 | ✅ (TASK-019, added) |
| `coins_per_streak_milestone` | 229 | ✅ |
| `coin_price_streak_freeze` | 236 | ✅ |
| `is_active` / `created_at` / `updated_at` | 240 + auto | ✅ |

`read_only_fields = ['id', 'created_at', 'updated_at']` is correct —
everything else should be editable by SCHOOL_ADMIN.

## Critical / Major / Minor Issues
None. Additive `ModelSerializer` field-list change; no behaviour drift,
no migrations needed.

## Positive Observations

- Comment block groups fields by the originating task (TASK-015/018/019)
  — makes future audits trivial.
- Updated docstring correctly promises XP/streak/MP/coins coverage.
- Author notes DRF's startup-time ImproperlyConfigured guarantees for
  misspelled field names, so no dedicated test is needed. Agreed —
  the existing gamification-config admin tests will catch it implicitly.

## Follow-up

None required. If qa-tester wants belt-and-braces, a single
`assert set(GamificationConfigSerializer.Meta.fields) >= {...}` test
would pin the contract explicitly; not blocking.

— reviewer (lp-reviewer)
