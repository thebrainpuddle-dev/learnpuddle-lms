---
tags: [review, task/TASK-015, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-015 — Streak Freeze Tokens + Grace Period + Weekend Mode

## Verdict: APPROVE (with one minor follow-up)

## Summary
Well-structured, additive, zero-downtime extension of the streak system.
Introduces a token inventory + immutable ledger, preserves the legacy monthly
counter as a fallback, and lays groundwork (weekend mode + grace period field)
for the follow-up TASK-015b. Tenant isolation is sound, migration is purely
additive, and tests meaningfully exercise behaviour + cross-tenant paths.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **`GamificationConfigSerializer.Meta.fields` is out of date.**
   `backend/apps/progress/gamification_serializers.py:17-29` does not expose
   the seven new fields (`grace_period_hours`, `weekend_mode_available`,
   `freeze_token_earn_every_n_days`, `freeze_token_expires_days`,
   `freeze_token_max_inventory`). If/when the Admin Gamification page wants
   to expose these on the existing admin config endpoint, they will be
   silently invisible. The teacher-facing inventory endpoint does surface
   them, so this is non-blocking, but worth a quick follow-up so admins can
   tune the feature without a shell.

2. **Auto-earn race across consecutive milestones.** `_maybe_grant_milestone_token`
   runs on every `record_activity` where `current_streak % N == 0`. If a
   milestone is hit, a token is awarded, but if a teacher uses the freeze the
   same day and then triggers the task manually, they could ledger a second
   `earned` entry for the same milestone. The inventory cap guards the token
   count (`earn_streak_freeze_token` returns `None` at cap) but because
   caller-side guard is `if n <= 0 or self.current_streak % n != 0: return`,
   duplicate earns at the same streak value are theoretically possible if
   `record_activity` were re-invoked. Not reachable through normal flow
   (`record_activity` short-circuits on same-day), but worth a defensive
   comment or idempotency guard.

3. **Legacy endpoint response shape.** `POST /streak-freeze/` when consuming
   an inventory token now returns `tokens_remaining` as the value and mirrors
   it into `freezes_remaining`. When the inventory is empty and it falls
   back to the legacy monthly counter, it returns `tokens_remaining: 0` plus
   the legacy `freezes_remaining`. Existing clients relying on
   `freezes_remaining` still work. Consider a test asserting this legacy
   contract explicitly — the token-preferred path and the counter-fallback
   path both have coverage, but not a direct "existing client still gets
   `freezes_remaining`" smoke test. Non-blocking.

## Positive Observations

- **Migration is truly additive**: `0016_streak_freeze_tokens.py` is all
  `AddField` / `CreateModel` / `AddIndex`, with one `AlterField` that only
  updates `help_text` on `streak_freeze_max` (no schema change). Safe to
  apply on a live DB. Clean dependency declarations on `tenants.0001_initial`
  and `users.0001_initial`.

- **Tenant isolation done right**:
  - Both new models declare `objects = TenantManager()` plus
    `all_objects = models.Manager()`.
  - Both have a tenant FK.
  - `earn_streak_freeze_token` / `spend_streak_freeze_token` derive
    `tenant` from `teacher.tenant` (so a malformed caller cannot cross
    tenants even if the caller supplied a bad user).
  - Ledger view explicitly re-asserts `tenant=request.tenant`
    (`gamification_teacher_views.py:445-448`) even though the teacher filter
    would have been sufficient — defence-in-depth, exactly right.
  - The dedicated `StreakFreezeTenantIsolationTest` class covers both
    endpoints end-to-end.

- **FIFO spend** (`order_by('earned_at').first()`) with explicit
  `.filter(models_q_unexpired(now))` means expired tokens are correctly
  skipped — verified by `test_spend_skips_expired_tokens`.

- **Inventory cap is enforced server-side** and cannot be bypassed by rapid
  repeated calls because it checks `_count_available_tokens` before insert.

- **Weekend-mode logic** (`_gap_is_only_weekend`) is cleanly isolated and
  both the enabled / disabled paths are tested with a real-calendar Friday
  (2026-04-03), including the `friday.weekday() == 4` calibration assertion.

- **Index coverage** is sensible: `(tenant, teacher, consumed_at)` for
  inventory queries, `expires_at` for expiry sweeps, `(tenant, teacher,
  created_at)` for ledger pagination, `(tenant, event_type)` for
  operational dashboards.

- **Record-keeping**: `balance_after` is captured on every ledger write
  (`_count_available_tokens` after `candidate.save`), so the ledger is a
  true reconstructable audit trail, not just an event log.

- **Legacy endpoint backwards compatibility is preserved**: the prefer-token
  path is opt-in (runs only when tokens exist), and the monthly counter
  path is identical to the prior implementation when inventory is empty.

## Test Suite Audit

25 tests, split as:
- 6 model (existence, tenant isolation for tokens, field defaults, config
  defaults) — all assert behaviour, not implementation.
- 7 engine (earn + ledger creation, cap, FIFO spend, empty-spend, expired
  skip, milestone auto-grant, weekend-mode rollover, weekend-mode-off
  break) — thorough.
- 7 API (empty inventory, populated inventory, use consumes, 400 on empty,
  weekend toggle on/off, tenant-disables weekend, ledger returns events) —
  happy + failure paths present.
- 2 explicit cross-tenant isolation tests (Teacher B cannot see Teacher
  A's tokens or ledger) — these are the ones a reviewer most wants to see.

Missing / worth adding later (non-blocking):
- Test that `POST /streak-freeze/` (legacy) returns `freezes_remaining` when
  falling back to the monthly counter.
- Test that consuming a token clears `grace_period_ends_at` on the streak
  (the code does this inside `record_activity`, which isn't itself the
  freeze-use path — depending on intent, the freeze-use endpoint may want
  to clear grace too).

## Migration Verification

Re-walked the migration operation-by-operation: every op is additive,
every default is safe (0, False, or a non-null primitive), no data
migration required, no `RunPython`, no `RunSQL`. Dependency graph points
at the correct prior migrations.

## Decision

APPROVE. Minor nits above can be addressed as a follow-up (TASK-015b or a
polish ticket). Nothing blocks shipping this as-is.
