# TASK-019 — Puddle Coins (Phase 4 Gamification)

## Status
- Phase: 4 (Gamification)
- Owner: backend-engineer
- Assigned: 2026-04-20
- Status: done
- Reviewed: 2026-04-20 by lp-reviewer (APPROVE — see
  `projects/learnpuddle-lms/reviews/review-TASK-019-puddle-coins-2026-04-20.md`)
- Related: TASK-014 (badges), TASK-015 (streak freeze tokens), TASK-016 (leagues),
  TASK-017 (challenges), TASK-018 (mastery points).

## Goal
Introduce **Puddle Coins**, a third gamification currency that sits alongside XP
(effort) and Mastery Points (competence). Coins are earnable from gameplay
milestones (level-up, challenge completion, league promotion, streak
milestones) and **spendable** on cosmetic / utility items (MVP spend target:
streak-freeze tokens). A teacher's coin balance is the authoritative indicator
of engagement-driven virtual wealth and unlocks the Education-vs-Corporate
storefront work called out in the master strategy (lines 120-121).

## Design

### Data model (additive migration `0020_puddle_coins`)

1. **GamificationConfig** — new fields:
   - `coins_per_level_up` (PositiveInt, default **100**)
   - `coins_per_challenge` (PositiveInt, default **25**)
   - `coins_per_league_promote` (PositiveInt, default **50**)
   - `coins_per_streak_milestone` (PositiveInt, default **20**)
   - `coin_price_streak_freeze` (PositiveInt, default **50**)
2. **CoinTransaction** — immutable ledger.
   - `tenant`, `teacher`, `amount` (`IntegerField`, signed), `reason`,
     `description`, `reference_type`, `reference_id`, `created_at`.
   - `TenantManager` + `all_objects`.
   - Unique partial constraint for EARN rows only:
     `UniqueConstraint(fields=[teacher, reason, reference_type, reference_id],
     condition=Q(amount__gt=0, reference_id__isnull=False),
     name='uniq_coin_earn_per_reference')`. Spends (`amount < 0`) can repeat.
   - Indexes: `(tenant, teacher)`, `(tenant, teacher, reason)`, `(created_at)`.
3. **TeacherCoinBalance** — 1:1 cached balance.
   - `tenant`, `teacher` (OneToOne), `balance` (PositiveInt, floor 0),
     `lifetime_earned` (PositiveInt), `lifetime_spent` (PositiveInt),
     `last_txn_at`.
   - Updated by `post_save` signal on `CoinTransaction` (in-process).

### Engine (`coin_engine.py`)
- `earn_coins(teacher, reason, amount=None, reference_id, reference_type, description)` — idempotent via unique EARN constraint; auto-looks up amount from config when omitted. Returns the `CoinTransaction` or `None` (opt-out / inactive / duplicate).
- `spend_coins(teacher, amount, reason, reference_id=None, reference_type='', description='')` — uses `select_for_update()` over `TeacherCoinBalance` inside `transaction.atomic()` to check-and-debit atomically; raises `InsufficientCoinsError` if insufficient. Returns the negative-amount `CoinTransaction`.
- `get_balance(teacher)` — returns cached balance; creates row if missing.
- `recompute_balance(teacher)` — rebuilds the cached row from the ledger.

### Earn triggers (signals into `gamification_signals.py`)
| Trigger | Engine hook | Reason | Reference |
| --- | --- | --- | --- |
| Level-up | `award_xp` → detect `summary.level` delta → `earn_coins` | `level_up` | `level` integer |
| Challenge completion | `challenge_engine.issue_challenge_rewards` | `challenge_reward` | challenge id |
| League promotion | `league_engine.close_league_week` promote branch | `league_promote` | league id |
| Streak milestone | `TeacherStreak._maybe_grant_milestone_token` (every N days) | `streak_milestone` | streak day count |

### Spend endpoint
`POST /api/v1/gamification/coins/purchase/streak-freeze/`
- Teacher-authenticated.
- Price: `GamificationConfig.coin_price_streak_freeze`.
- Respects existing `freeze_token_max_inventory` cap — rejects with 400 when at cap.
- On success: `spend_coins` → `earn_streak_freeze_token(source='purchase')`; returns `{ balance, token }`.
- Insufficient coins → 400 `{ "error": "Insufficient Puddle Coins", "balance": N, "price": M }`.

### Other HTTP surface
- `GET /api/v1/gamification/coins/` → balance + lifetime totals.
- `GET /api/v1/gamification/coins/history/` → paginated ledger.

## Concurrency strategy
- Balance mutation funneled through `spend_coins`, which wraps
  `select_for_update()` + `transaction.atomic()` so two concurrent spend requests
  can't double-debit.
- Earn path is idempotent by DB unique constraint — simultaneous earn
  duplicates collapse to one row (the second raises `IntegrityError` which the
  engine swallows to `None`).

## Tests (`tests_puddle_coins.py`)
1. Model: tenant FK, TenantManager isolation, signed amount, unique constraint
   for earns, repeat-spend allowed.
2. Engine: earn happy path, earn idempotency, spend happy path, overdraft,
   `get_balance` matches ledger, concurrency (simulated via lock).
3. Signals: challenge completion → earn; league promotion → earn; streak
   milestone → earn; level-up → earn; opt-out blocks earn.
4. API: balance GET, history GET, purchase success, purchase insufficient,
   cross-tenant isolation.

## Deliverables
- Backend code changes (models/engine/signals/views/urls/migration).
- Review request at `_coordination/inbox/reviewer/TASK-019-REVIEW-REQUEST.md`.
- Append to `_coordination/shared-log.md`.

## Risks
- Streak-milestone earn path piggy-backs on `_maybe_grant_milestone_token`. If a
  teacher is already at the freeze-token cap we still grant coins (design
  intent — milestones reward even when the token is a no-op). Confirmed in
  tests.
- Two active currencies (MP, Coins) share some earn triggers. Kept ledgers
  fully independent so future rebalancing doesn't require schema change.
