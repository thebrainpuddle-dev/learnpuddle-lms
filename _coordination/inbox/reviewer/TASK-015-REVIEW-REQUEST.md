# Review Request: TASK-015 — Streak Freeze Tokens + Grace Period + Weekend Mode

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-20
**Priority:** P2 (Phase 4 Gamification)

## TL;DR

Extended the existing streak system with a proper **token inventory**, an
**immutable ledger**, a **grace period**, and a **weekend mode** — fulfilling
the master-strategy item:

> "Streak freeze tokens + grace period + weekend mode"
> (`docs/superpowers/research/2026-03-25-platform-powerup-master-strategy.md`
> line 114)

Task doc: `docs/coordination/TASK-015-streak-freeze-tokens.md`

## What Changed

### New models
1. **`StreakFreezeToken`** — individual earnable/spendable token. Sources:
   `streak_milestone`, `admin_grant`, `challenge_reward`, `purchase`. Has
   `earned_at`, `consumed_at`, `expires_at`.
2. **`StreakFreezeLedger`** — append-only audit log of earn/spend/expire events
   with `balance_after` snapshot.

### Field additions (all additive, zero-downtime)
- `TeacherStreak.weekend_mode_enabled` (BooleanField, default False)
- `TeacherStreak.grace_period_ends_at` (DateTimeField, nullable)
- `GamificationConfig.grace_period_hours` (default 24)
- `GamificationConfig.weekend_mode_available` (default True)
- `GamificationConfig.freeze_token_earn_every_n_days` (default 7)
- `GamificationConfig.freeze_token_expires_days` (default 90)
- `GamificationConfig.freeze_token_max_inventory` (default 5)

### New endpoints (under `/api/v1/gamification/streak-freeze/`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `inventory/` | Token count, weekend/grace state |
| POST | `use/` | Consume 1 token (FIFO by `earned_at`) |
| POST | `weekend-mode/` | Toggle weekend mode |
| GET | `ledger/` | Paginated earn/spend history |

The legacy `POST /streak-freeze/` endpoint is preserved and now **prefers** the
token inventory, falling back to the monthly-counter behaviour when inventory
is empty.

### Engine helpers (new)
- `earn_streak_freeze_token(teacher, source, ...)` — caps inventory,
  writes ledger row.
- `spend_streak_freeze_token(teacher, ...)` — FIFO consumption, skips
  expired tokens, writes ledger row.

### Auto-earn
`TeacherStreak.record_activity` now grants a milestone token every
`freeze_token_earn_every_n_days` days.

### Weekend mode
`record_activity` walks the missed day range; if every missed day is Sat or
Sun and `weekend_mode_enabled=True`, the gap collapses to 1 (consecutive).

## Files Changed

| File | Lines | Notes |
|------|-------|-------|
| `backend/apps/progress/gamification_models.py` | +150 / -2 | 2 models, 7 field additions, helper fn, extended `record_activity` |
| `backend/apps/progress/gamification_engine.py` | +135 / -0 | earn/spend helpers, `_count_available_tokens`, `models_q_unexpired` |
| `backend/apps/progress/gamification_serializers.py` | +30 / -0 | Token + ledger serializers |
| `backend/apps/progress/gamification_teacher_views.py` | +145 / -15 | 4 new views, legacy endpoint prefers inventory |
| `backend/apps/progress/gamification_urls.py` | +20 / -0 | 4 new routes |
| `backend/apps/progress/migrations/0016_streak_freeze_tokens.py` | new | 2 CreateModel, 7 AddField, 1 AlterField (help_text only), 4 AddIndex |
| `backend/apps/progress/tests_streak_freeze_tokens.py` | new | 25 tests |
| `docs/coordination/TASK-015-streak-freeze-tokens.md` | new | Task doc |

## Tests (25 total)

- **Model (6):** model existence, tenant isolation, field defaults
- **Engine (7):** earn creates token + ledger, inventory cap, FIFO spend,
  no-tokens returns None, expired-skip, auto-earn-on-milestone,
  weekend-mode gap collapse
- **API (7):** inventory empty/populated, use consumes token, use 400 no
  tokens, weekend mode toggle on/off, weekend mode disabled at config
  level returns 400, ledger returns events
- **Tenant isolation (2):** teacher B cannot see teacher A tokens or ledger
- **Regression:** existing `record_activity` same-day, gap=1, gap=2+frozen
  paths untouched

### Execution

I was unable to run `pytest` in this environment (no Docker, no python CLI in
sandbox). Please run:

```bash
docker compose exec web pytest apps/progress/tests_streak_freeze_tokens.py -v
```

## Tenant Isolation Review Points

- `StreakFreezeToken` and `StreakFreezeLedger` both have `tenant` FK +
  `TenantManager`.
- All `get_or_create(teacher=request.user, ...)` calls include
  `defaults={'tenant': request.tenant}`.
- All queries in views filter by `teacher=request.user` (implicitly scoped).
- Tests `test_teacher_b_cannot_see_teacher_a_tokens` and
  `test_teacher_b_cannot_see_teacher_a_ledger` exercise cross-tenant paths.

## Migration Safety

- Additive only — `CreateModel` + `AddField` with safe defaults.
- One `AlterField` purely to update `help_text` on `streak_freeze_max`
  (no schema change).
- No data migration required. Existing teachers start with zero tokens and
  accrue via `record_activity`.

## Risks / Open Questions

1. **Auto-earn on every N days** — current logic grants a token whenever
   `current_streak % N == 0`. If a teacher at streak=14 uses a freeze, next
   activity brings them to streak=15 (not a multiple of 7), so no
   double-grant. Safe.
2. **Grace-period task integration** — the daily Celery task
   (`process_daily_streaks`) was *not* modified in this PR; grace-period
   enforcement via task is deferred to TASK-015b to keep this PR focused on
   model + API surface. The grace-period *field* and *grace-period read*
   are shipped; the task-side consumption is a follow-up.
3. **Legacy endpoint behaviour change** — `POST /streak-freeze/` now
   prefers tokens. If token inventory is empty, it falls back to the
   legacy monthly counter. Backwards-compatible response shape
   (`freezes_remaining` retained, `tokens_remaining` added).

## Ready for review

Status set to `review` in `docs/coordination/TASK-015-streak-freeze-tokens.md`.
