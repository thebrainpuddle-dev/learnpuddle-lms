# TASK-019 — Puddle Coins: Review Request

**Author:** backend-engineer
**Date:** 2026-04-20
**Status:** review
**Phase:** 4 Gamification — completes the XP / MP / Coins trio called out in the
platform master strategy (lines 120-121).

## Summary

Adds a **Puddle Coins** virtual currency that sits alongside XP (effort) and
Mastery Points (competence). Coins are earnable from level-up, challenge
completion, league promotion, and every-N-day streak milestones; spendable on
streak-freeze tokens (MVP endpoint, future: cosmetic tiers, corporate-mode
storefront).

## Files changed

**New**
- `docs/coordination/TASK-019-puddle-coins.md` — design & risks.
- `backend/apps/progress/coin_engine.py` — `earn_coins`, `spend_coins`,
  `get_balance`, `recompute_balance`, `InsufficientCoinsError`.
- `backend/apps/progress/coin_views.py` — balance / history / purchase
  endpoints.
- `backend/apps/progress/tests_puddle_coins.py` — **22 tests** across
  models / engine / signals / API.
- `backend/apps/progress/migrations/0020_puddle_coins.py` — additive
  migration.

**Modified**
- `backend/apps/progress/gamification_models.py` — 5 new
  `GamificationConfig` fields, `CoinTransaction`, `TeacherCoinBalance`, coin
  grant hook in `TeacherStreak._maybe_grant_milestone_token`.
- `backend/apps/progress/gamification_engine.py` — level-up coin grant in
  `award_xp` (UUIDv5 reference per (teacher, level) for idempotency).
- `backend/apps/progress/challenge_engine.py` — coin grant in
  `issue_challenge_rewards`.
- `backend/apps/progress/league_engine.py` — coin grant in promote branch
  of `close_league_week`.
- `backend/apps/progress/gamification_serializers.py` —
  `CoinTransactionSerializer`, `TeacherCoinBalanceSerializer`.
- `backend/apps/progress/gamification_urls.py` — 3 new routes.

## Design highlights

1. **Separate ledger (`CoinTransaction`)** rather than extending XP: cleanest
   independence, future-proofs per-currency admin tools, matches the MP
   pattern shipped in TASK-018.
2. **Signed `amount`** — positive=earn, negative=spend. Single append-only
   table.
3. **Idempotency for earns only** via partial unique constraint
   `UniqueConstraint(fields=[teacher, reason, reference_type, reference_id],
   condition=Q(amount__gt=0, reference_id__isnull=False))`. Spends may
   repeat (e.g. multiple freeze-token purchases).
4. **Concurrency-safe spend** — `transaction.atomic()` +
   `select_for_update()` on `TeacherCoinBalance`. Two simultaneous spends
   can never double-debit (test
   `test_spend_coins_serialises_under_concurrent_access` asserts this).
5. **Denormalized `TeacherCoinBalance`** for O(1) reads, updated in the
   same transaction as the ledger write. `recompute_from_transactions()`
   is a safety-net repair helper.

## Earn wiring

| Trigger site                            | Hook                                        | Reason              | Reference                              |
|-----------------------------------------|---------------------------------------------|---------------------|----------------------------------------|
| `gamification_engine.award_xp`          | detect `summary.level` delta                 | `level_up`          | UUIDv5(NAMESPACE_OID, teacher+level)   |
| `challenge_engine.issue_challenge_rewards` | alongside XP + badge                       | `challenge_reward`  | `challenge.id`                          |
| `league_engine.close_league_week` (promote branch) | per promoted member                | `league_promote`    | `league.id`                             |
| `TeacherStreak._maybe_grant_milestone_token` | every N consecutive streak days         | `streak_milestone`  | UUIDv5(teacher+streak_days)             |

Each earn is defensive — wrapped in `try/except` so a coin failure never
breaks its parent flow (XP grant, badge award, league close, streak bump).

## Spend endpoint

`POST /api/v1/gamification/coins/purchase/streak-freeze/`
- Price: `GamificationConfig.coin_price_streak_freeze` (default 50).
- Checks inventory cap (`freeze_token_max_inventory`) **before** debiting to
  avoid refund flows.
- Raises `InsufficientCoinsError` → HTTP 400 with `{ balance, price }`
  payload (no DB side-effects).
- On success: mints token via existing `earn_streak_freeze_token(source='purchase')`.

## Tests

22 tests in 4 classes:
- **CoinModelTest (5)**: tenant isolation, signed amount, EARN unique
  constraint raises IntegrityError on dup, spends may repeat,
  `recompute_from_transactions` reconciles.
- **CoinEngineTest (6)**: earn happy path, earn idempotency, opt-out
  blocks, spend happy path, overdraft raises, `get_balance` matches ledger,
  concurrent spend serialization.
- **CoinSignalTest (5)**: challenge completion earns, streak milestone
  earns, level-up earns, level-up idempotent on repeat award, league
  promotion earns.
- **CoinApiTest (5)**: balance GET, history GET, purchase success +
  token minted, purchase insufficient (400 with balance/price body),
  cross-tenant history isolation.

## Migration

`0020_puddle_coins.py` is additive only — 5 new config fields (defaults
applied), 2 new tables (`coin_transactions`, `teacher_coin_balances`), 4
indexes, 1 partial unique constraint. Reversible.

## Open questions for reviewer

1. **Level-up multi-jump**: a single large XP grant that crosses two levels
   (e.g. 600 XP L1→L3) mints **two** level-up coin rows — one per level
   crossed. Intentional (teacher "sees" each level-up), but flag if you'd
   prefer collapsing to one.
2. **Streak-milestone coin when at freeze-cap**: if the teacher is at
   `freeze_token_max_inventory`, the token grant is a no-op but the coin
   still fires. This is the "streak discipline always rewards" design —
   confirmed with test `test_streak_milestone_earns_coins`.
3. **No admin-side coin adjust endpoint yet** — the ledger supports
   `admin_adjust` reason but there's no URL. Follow-up task when admin UI
   is in scope.

## Manual verification checklist

- [ ] `python manage.py makemigrations --check --dry-run apps.progress` reports no drift.
- [ ] `pytest apps/progress/tests_puddle_coins.py -q` — 22 passed.
- [ ] Existing `tests_streak_freeze_tokens.py`, `tests_leagues.py`,
      `tests_challenges.py`, `tests_mastery_points.py`,
      `tests_gamification_signals.py` still green (coin hooks guarded with
      try/except).
