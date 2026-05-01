---
tags: [review, task/BE-FOLLOWUPS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: BE-FOLLOWUPS-2026-04-20 — Backend Follow-up Fixes

## Verdict: APPROVE

## Summary
Four small, well-scoped, low-risk backend changes. All four are confirmed in source and line up exactly with the request description. Backward-compatible, no migrations needed, no test regressions anticipated. Good engineering hygiene — the author flagged three items as already-resolved upstream rather than redoing work.

## Verification

### 1. `TeacherCoinBalanceSerializer.price_streak_freeze` — APPROVED
`backend/apps/progress/gamification_serializers.py`
- Line 286: `price_streak_freeze = serializers.SerializerMethodField()` ✅
- Lines 296–300: `get_price_streak_freeze` reads `get_or_create_config(obj.tenant).coin_price_streak_freeze` and coerces to `int`. ✅
- Field listed in `Meta.fields` (line 293) and `read_only_fields = fields` (line 294). ✅
- Docstring (lines 276–283) clearly explains the contract (frontend drops `DEFAULT_STREAK_FREEZE_PRICE`).

**Nit (non-blocking):** `get_or_create_config(obj.tenant)` runs per row. For single-row `/coins/` responses this is fine; if the serializer is ever used in a list endpoint, cache on `self.context` or a `_config` instance attr. Not worth changing now — flagging for FE-014/FOLLOWUP follow-on only.

### 2. `GamificationConfigSerializer` — 7 new fields — APPROVED
`backend/apps/progress/gamification_serializers.py` lines 33–38
- All 7 fields present: `grace_period_hours`, `weekend_mode_available`, `freeze_token_earn_every_n_days`, `freeze_token_expires_days`, `freeze_token_max_inventory`, `coins_per_streak_milestone`, `coin_price_streak_freeze`. ✅
- Comments (`# Streak-freeze token config (TASK-015)`, `# Puddle Coin config (TASK-019)`) keep the origin traceable. ✅
- `read_only_fields` unchanged — fields are writable via PATCH, which is the requirement. ✅

### 3. Reminders — PII log scrub + in-app failure surfacing — APPROVED
`backend/apps/reminders/views.py`, `backend/apps/reminders/services.py`

**views.py:**
- Line 129 comment + line 130 `logger.debug(...)`: PII-bearing `data` dict (includes `teacher_ids`) demoted from INFO to DEBUG with explanatory comment. ✅
- Lines 216–217: response now emits `in_app_sent` / `in_app_failed` keys. ✅
- Lines 219–222: completion log uses `%d` format — no PII. ✅

**services.py:**
- Line 39 `@dataclass DispatchResult` with `in_app_sent: int = 0, in_app_failed: int = 0`. ✅
- Defaults of 0 preserve backward-compat with `run_automated_course_deadline_reminders` (line 286–288) which only reads `.sent`/`.failed`. ✅
- `dispatch_campaign` atomic all-or-nothing semantics (lines 204–218): single `notify_reminder(...)` call; on success set `in_app_sent = len(recipients)`, on exception set `in_app_failed = len(recipients)`. Matches the request's contract.

### 4. Billing — charge retrieval log level — APPROVED
`backend/apps/billing/webhook_handlers.py` line 210
- Confirmed `logger.warning("Could not retrieve charge %s for failure reason", invoice.charge)`. ✅
- Uses lazy `%s` formatting (not f-string) — correct logging style. ✅
- Bare `except Exception` is narrow in scope (only the Stripe retrieve path) — acceptable because Stripe client can raise many classes.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
1. **`reminder_send` still logs `teacher_ids` at INFO level (line 174)** — `logger.info(f"[REMINDER_SEND] Filtered to teacher_ids: {teacher_ids}")` was not in scope for this PR but is the same class of PII exposure the line-130 scrub was meant to address. Teacher UUIDs are less sensitive than email/name, but consistent treatment would downgrade this too. *(Follow-up candidate, not blocking.)*
2. **Line 109 `logger.info` includes `request.user.email`** — same concern, same class, pre-existing. Not in scope here; flag for a broader "reminders logging PII sweep" follow-up.
3. **`get_price_streak_freeze` does a DB read per serialization** — negligible on the current `/coins/` endpoint (singleton), but if the serializer is reused in future aggregate endpoints, cache on `self.context`. Noted only.

## Positive Observations
- **Atomic in-app semantics** (`len(recipients)` on success/failure) keep the new fields truthful without leaking per-teacher granularity — good match for the current `notify_reminder` API surface.
- **Backward-compat via dataclass defaults** is the right design — existing automation callers need no change.
- **Author proactively confirmed OBS-3, OBS-4, BE-SEC-001 were already resolved** rather than duplicating work. Excellent hygiene.
- **PII comment on line 129** explains the intent for future readers — this is exactly the kind of inline documentation that saves a future maintainer from re-adding the INFO log.
- **Field comments with task IDs** in `GamificationConfigSerializer.Meta.fields` make origin traceable at a glance.

## Recommended Next Steps
- Merge as-is. QA coverage handoff (QA-BE-FOLLOWUPS-COVERAGE-2026-04-20.md) covers all four items; reviewing that separately.
- Open a tiny `FOLLOWUP-reminders-info-log-pii-sweep` issue covering views.py lines 109 and 174 for consistency with the line-130 scrub.

— lp-reviewer
