# TASK-019 Puddle Coins — Review Verdict: APPROVE

**Reviewer:** lp-reviewer
**Date:** 2026-04-20
**Full review:** `projects/learnpuddle-lms/reviews/review-TASK-019-puddle-coins-2026-04-20.md`

## Verdict: APPROVE — ship it

No critical or major issues. Concurrency guards, idempotency, tenant
isolation, defensive earn wiring, and migration chain all validated.

## Confirmations
- Migration 0020 depends on 0019_mastery_points — additive only, reversible.
- Partial unique constraint on `CoinTransaction` is the right conditional
  (`amount__gt=0, reference_id__isnull=False`) — earns dedup, spends repeat.
- `spend_coins` uses `transaction.atomic()` + `select_for_update()` on the
  balance row with check-then-debit inside the lock. `test_spend_coins_
  serialises_under_concurrent_access` exercises the race path.
- All four earn trigger sites (level-up, challenge, league promote, streak
  milestone) wrap `earn_coins` in `try/except Exception` + `logger.exception`.
- `CoinTransaction` and `TeacherCoinBalance` both carry `tenant` FK and
  `objects = TenantManager()` with `all_objects` escape hatch.
- Purchase endpoint: inventory cap check BEFORE `spend_coins`, no refund flow
  needed. `InsufficientCoinsError` → HTTP 400 with `{balance, price}`.
- Test count: 22 in 4 classes — matches brief.
- Level-up multi-jump: one row per level crossed with deterministic
  UUIDv5 refs — confirmed intentional per task doc, approved as-is.

## Follow-ups (non-blocking)
1. Admin-side coin adjust endpoint — add when admin UI lands.
2. Once admin-facing copy ships, note the "streak milestone always earns
   coins even at freeze-cap" behaviour so teachers understand it.

## Next actions
- Task status updated to `done`.
- Proceed to merge / integrate.
