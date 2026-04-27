# TASK-015: Streak Freeze Tokens + Grace Period + Weekend Mode

**Priority:** P2 (Phase 4 Gamification)
**Phase:** 4
**Status:** done
**Assigned:** backend-engineer
**Estimated:** 2-3 hours
**Reviewer:** lp-reviewer

## Problem

The master strategy (`docs/superpowers/research/2026-03-25-platform-powerup-master-strategy.md`
lines 112-123) requires:

> Streak freeze tokens + grace period + weekend mode

The existing `TeacherStreak` model treats "streak freeze" as a simple monthly counter
(`freeze_count_this_month`, `freeze_used_today`, `streak_frozen_until`). There is:

- **No token inventory** — freezes cannot be earned as a reward, only rationed monthly.
- **No ledger** — nothing records *when* and *why* a freeze was earned or spent.
- **No grace period** — missing a day immediately triggers freeze-or-break logic.
- **No weekend mode** — teachers cannot opt to pause streak counting on Sat/Sun.

## Solution

Transform the freeze mechanic into an inventory-based system while preserving the existing
monthly cap as a fallback for auto-earned tokens.

### 1. New model: `StreakFreezeToken`

An individual, earnable/spendable token. Tokens are awarded on streak milestones and can
be consumed to cover one missed day each.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `tenant` | FK | Tenant isolation |
| `teacher` | FK | Owner |
| `source` | CharField(30) | `streak_milestone`, `admin_grant`, `challenge_reward`, `purchase` |
| `earned_at` | DateTime | When the token entered the teacher's inventory |
| `consumed_at` | DateTime | Null until spent |
| `expires_at` | DateTime | Null = never expires; default 90 days after earned |
| `reference_type` / `reference_id` | CharField / UUID | Provenance pointer |

Manager: `TenantManager`. Indexes on (tenant, teacher, consumed_at) and expires_at.

### 2. New model: `StreakFreezeLedger`

Immutable audit log — one row per event. Mirrors `XPTransaction` pattern.

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | PK |
| `tenant` | FK | Tenant isolation |
| `teacher` | FK | |
| `event_type` | CharField | `earned`, `spent`, `expired`, `granted`, `revoked` |
| `token` | FK nullable | The token this event references (if any) |
| `description` | CharField(255) | Human-readable context |
| `balance_after` | PositiveInteger | Cached inventory count after this event |
| `created_at` | DateTime | |

### 3. `TeacherStreak` field additions

- `weekend_mode_enabled: BooleanField(default=False)` — if true, Sat/Sun activity is
  not required to keep the streak alive.
- `grace_period_ends_at: DateTimeField(null=True)` — when set, streak is in "grace"
  state. Activity before this timestamp auto-recovers without consuming a token.

### 4. `GamificationConfig` field additions

- `grace_period_hours: PositiveInteger(default=24)` — hours after a missed day during
  which activity still counts for the streak.
- `weekend_mode_available: BooleanField(default=True)` — tenant-level opt-in toggle.
- `freeze_token_earn_every_n_days: PositiveInteger(default=7)` — every N consecutive
  streak days, teacher earns 1 token.
- `freeze_token_expires_days: PositiveInteger(default=90)` — token lifetime (0 = never).
- `freeze_token_max_inventory: PositiveInteger(default=5)` — cap on unspent tokens.

### 5. Earn logic

Added to `TeacherStreak.record_activity`: when the updated `current_streak` is a
multiple of `freeze_token_earn_every_n_days` and inventory < cap, grant one token
(source='streak_milestone') and write a ledger row.

### 6. Spend logic

New view `POST /api/v1/gamification/streak-freeze/use/`:
- Finds oldest unexpired unconsumed token owned by the teacher.
- Marks it `consumed_at = now`.
- Sets `streak_frozen_until = today + 1`.
- Writes ledger row (`event_type='spent'`).

### 7. Grace period

Daily Celery task (`process_daily_streaks`) now enters grace instead of immediately
freezing/breaking:
- First day missed: set `grace_period_ends_at = now + grace_period_hours`.
- When a teacher records activity before that timestamp, streak continues without a
  token being consumed. Otherwise the task applies the existing freeze-or-break logic
  once the grace window closes.

### 8. Weekend mode

- `POST /api/v1/gamification/streak-freeze/weekend-mode/` toggles
  `TeacherStreak.weekend_mode_enabled`.
- When enabled, `record_activity()` skips gap computation if the missed day was a
  Saturday or Sunday — the streak "rolls over" the weekend.

### 9. New endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/gamification/streak-freeze/inventory/` | GET | Returns current token count, upcoming expirations, weekend-mode status, grace-period status |
| `/gamification/streak-freeze/use/` | POST | Consume one token to protect today's streak |
| `/gamification/streak-freeze/weekend-mode/` | POST | `{enabled: bool}` — toggle weekend mode |
| `/gamification/streak-freeze/ledger/` | GET | Paginated history of earn/spend events |

The existing `POST /gamification/streak-freeze/` endpoint continues to work for backward
compatibility (now consumes a token if available, else falls back to the legacy monthly
counter).

## Migration strategy — zero-downtime

`progress/migrations/0016_streak_freeze_tokens.py`:
- `CreateModel` for `StreakFreezeToken` and `StreakFreezeLedger` (new tables — safe).
- `AddField` for `TeacherStreak.weekend_mode_enabled` and `grace_period_ends_at`
  (defaults guarantee existing rows are populated).
- `AddField` for 4 new `GamificationConfig` fields (defaults provided).

All additive. No backfill required — existing teachers simply start with zero tokens
and may earn them as their streaks grow.

## Tests Written (TDD — written before implementation)

`apps/progress/tests_streak_freeze_tokens.py`

### Model tests
- `StreakFreezeToken` model exists, tenant-isolated, default `consumed_at=None`
- `StreakFreezeLedger` model exists, tenant-isolated
- `TeacherStreak.weekend_mode_enabled` defaults False
- `TeacherStreak.grace_period_ends_at` nullable
- `GamificationConfig` has grace_period_hours (24), weekend_mode_available, earn_every_n_days, expires_days

### Engine tests
- `earn_streak_freeze_token` creates token + ledger row + caps inventory
- Token expiration task marks tokens expired
- `record_activity` auto-grants token every N days
- `record_activity` skips weekend gap when weekend_mode_enabled

### API tests — tenant isolation + happy paths
- GET inventory returns count, weekend status
- POST use with tokens available: consumes oldest, records ledger
- POST use with no tokens: 400 with message
- POST weekend-mode: toggles flag
- GET ledger: returns events, tenant-scoped
- Cross-tenant isolation: tenant A cannot see tenant B tokens or ledger

### Daily task tests
- `process_daily_streaks` enters grace period instead of immediate break
- Grace window expired + activity not recorded → token auto-spent
- No token and grace expired → streak resets

## Files Changed

| File | Change |
|------|--------|
| `apps/progress/gamification_models.py` | +2 models, +2 TeacherStreak fields, +4 GamificationConfig fields |
| `apps/progress/migrations/0016_streak_freeze_tokens.py` | New migration |
| `apps/progress/gamification_serializers.py` | +StreakFreezeToken, +StreakFreezeLedger serializers |
| `apps/progress/gamification_teacher_views.py` | +4 endpoints |
| `apps/progress/gamification_urls.py` | +4 routes |
| `apps/progress/gamification_engine.py` | +`earn_streak_freeze_token`, +`spend_streak_freeze_token` helpers |
| `apps/progress/tests_streak_freeze_tokens.py` | New — 25+ tests |

## Design Notes

- The legacy `freeze_count_this_month` counter is retained as a *fallback* cap so the
  existing monthly-grant behaviour keeps working for tenants that have not migrated to
  the token flow yet.
- `StreakFreezeLedger.balance_after` is a denormalised counter for fast inventory
  reads — source of truth remains the set of unconsumed tokens.
- Source strings are open-ended (CharField, not choices-enforced) to allow future
  sources (`challenge_reward`, `puddle_coin_purchase`) without migrations.
- Tokens are tenant-scoped and teacher-owned; cross-tenant leakage is impossible
  because `TenantManager` filters every query.
