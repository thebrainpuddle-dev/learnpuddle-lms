---
tags: [review, task/TASK-019, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-019 — Puddle Coins virtual currency

## Verdict: APPROVE

## Summary
Clean, idiomatic implementation of a third gamification currency that mirrors
the mastery-points ledger pattern from TASK-018. Concurrency guards are
correct, tenant isolation is enforced at every layer, earn triggers are
defensively wrapped, and the 22-test suite covers models / engine / signals /
API (including a serialization-under-contention assertion). Additive migration
chains cleanly off `0019_mastery_points`. Ship it.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues / Follow-up Notes
1. **Admin-side coin adjust endpoint is absent.** The `admin_adjust` reason
   exists in the enum and ledger supports it, but no URL/view. The task doc
   flags this as a known follow-up — fine for MVP.
2. **Streak-milestone coin always fires even when freeze-token is at cap.**
   Confirmed intentional in task doc ("streak discipline always rewards") and
   explicitly asserted by `test_streak_milestone_earns_coins`. Worth a note in
   the admin-facing copy when that UI lands so teachers don't perceive it as a
   loophole.
3. **Level-up multi-jump mints one row per level.** e.g. a 600-XP grant that
   crosses L1→L3 creates two `level_up` rows with distinct UUIDv5 refs
   (`coin-levelup:{teacher}:{level}`). This is correct: each level is a
   distinct milestone the teacher "sees", deterministic refs make it idempotent
   across re-runs, and the unique partial constraint prevents
   double-granting.  Approve as-is.

## Positive Observations
- **Concurrency**: `spend_coins` uses `transaction.atomic()` +
  `select_for_update()` on the `TeacherCoinBalance` row and the read-check-debit
  sequence is inside the same lock. `test_spend_coins_serialises_under_
  concurrent_access` explicitly exercises the race path. Correct.
- **Idempotency**: partial unique constraint
  `UniqueConstraint(fields=[teacher, reason, reference_type, reference_id],
  condition=Q(amount__gt=0, reference_id__isnull=False))` is the right
  conditional — covers earns with refs, lets spends (amount<0) and
  ref-less grants (cap-ledger style) repeat. `earn_coins` swallows
  `IntegrityError` and returns `None` so callers never see a crash on
  duplicate dispatch.
- **Defensive earn guards**: All four trigger sites
  (`gamification_engine.award_xp` level-up, `challenge_engine.issue_challenge_
  rewards`, `league_engine.close_league_week` promote branch,
  `TeacherStreak._maybe_grant_milestone_token`) each wrap the `earn_coins`
  call in `try/except Exception` + `logger.exception`. A coin-system failure
  can never regress XP/badge/streak/league core flows.
- **Tenant isolation**: both `CoinTransaction` and `TeacherCoinBalance` carry
  a `tenant` FK and `objects = TenantManager()` (with `all_objects` escape
  hatch). `test_tenant_manager_isolates_ledger` and
  `test_cross_tenant_isolation_on_history` guard this at model and API layer
  respectively.
- **Migration**: `0020_puddle_coins.py` depends on `progress.0019_mastery_points`,
  `tenants.0001_initial`, `users.0001_initial`. Additive only — 5 config
  fields with sane defaults, 2 new tables, 4 indexes, 1 partial unique
  constraint. Fully reversible.
- **Purchase endpoint ordering**: inventory-cap check runs **before** the
  spend so we never need a refund flow. `InsufficientCoinsError` branch
  returns 400 with `{balance, price}` body as spec'd; the transaction.atomic
  in `spend_coins` guarantees no ledger side-effects on overdraft.
- **Denormalized balance hygiene**: `recompute_from_transactions` provides a
  safety-net reconciliation path and is exercised by
  `test_balance_recompute_from_ledger`.
- **Engine API surface is minimal and well-named**: `earn_coins`,
  `spend_coins`, `get_balance`, `recompute_balance`,
  `InsufficientCoinsError`. No leaky abstractions.

## Verification notes
- Migration dependency chain confirmed (0019 → 0020).
- All four earn trigger sites grep-verified to be inside `try/except Exception`
  with `logger.exception`.
- Test count: 22 across 4 classes (`CoinModelTest`, `CoinEngineTest`,
  `CoinSignalTest`, `CoinApiTest`) matches brief.
- URL routes registered in `gamification_urls.py` at lines 114, 119, 124.
- Both new models have `objects = TenantManager()` + `all_objects = Manager()`.

## Files reviewed
- `backend/apps/progress/coin_engine.py`
- `backend/apps/progress/coin_views.py`
- `backend/apps/progress/gamification_models.py` (lines 211-245, 614-660, 1024-1156)
- `backend/apps/progress/gamification_engine.py` (lines 116-138)
- `backend/apps/progress/challenge_engine.py` (lines 246-262)
- `backend/apps/progress/league_engine.py` (lines 347-366)
- `backend/apps/progress/gamification_urls.py`
- `backend/apps/progress/migrations/0020_puddle_coins.py`
- `backend/apps/progress/tests_puddle_coins.py` (567 lines)
