# Backend Follow-up Fixes — Ready for Review

**From:** backend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-20

Worked through all approved-task inbox items and non-blocking follow-ups.
Requesting a quick review pass on four small changes.

---

## Changes Made

### 1. `TeacherCoinBalanceSerializer` — expose `price_streak_freeze`

**File:** `backend/apps/progress/gamification_serializers.py`
**Origin:** `FOLLOWUP-coins-price-exposure-2026-04-20.md` (Option A)

Added `price_streak_freeze: int` as a `SerializerMethodField` backed by
`get_or_create_config(obj.tenant).coin_price_streak_freeze`. The frontend
wallet page can now drop `DEFAULT_STREAK_FREEZE_PRICE = 100` and read the
server value.

Response before:
```json
{ "teacher_id", "balance", "lifetime_earned", "lifetime_spent", "last_txn_at", "updated_at" }
```

Response after:
```json
{ "teacher_id", "balance", "lifetime_earned", "lifetime_spent", "last_txn_at", "updated_at", "price_streak_freeze": 50 }
```

Existing tests are additive-safe (`data["balance"] == 200` still passes;
new field is additional). QA recommended to add: `self.assertIn("price_streak_freeze", data)` to `test_get_balance_endpoint`.

---

### 2. `GamificationConfigSerializer` — add 7 freeze/coin config fields

**File:** `backend/apps/progress/gamification_serializers.py`
**Origin:** TASK-015 non-blocking follow-up (reviewer note)

Added to `GamificationConfigSerializer.Meta.fields`:
- `grace_period_hours`
- `weekend_mode_available`
- `freeze_token_earn_every_n_days`
- `freeze_token_expires_days`
- `freeze_token_max_inventory`
- `coins_per_streak_milestone`
- `coin_price_streak_freeze`

Admin UI can now tune these via the config endpoint without a shell.

---

### 3. Reminders PII log scrub + in-app failure surfacing

**Files:** `backend/apps/reminders/views.py`, `backend/apps/reminders/services.py`
**Origin:** TASK-020

- `views.py:129`: `logger.info(f"..., data={data}")` → `logger.debug(...)`.
  PII (`teacher_ids`) out of INFO logs.
- `DispatchResult` dataclass: added `in_app_sent: int = 0`, `in_app_failed: int = 0`.
- `dispatch_campaign`: sets `result.in_app_sent = len(recipients)` on success,
  `result.in_app_failed = len(recipients)` on exception.
- `reminder_send` view response: now includes `"in_app_sent"` and
  `"in_app_failed"` keys. INFO log at completion uses `%d` format
  (no PII exposure).

Backward-compatible: `DispatchResult` fields have defaults of 0;
existing callers that only read `.sent` and `.failed` are unaffected.

---

### 4. Billing — payment-failed charge retrieval logger.debug → logger.warning

**File:** `backend/apps/billing/webhook_handlers.py` (line 210)
**Origin:** TASK-022 + QA billing coverage review

`logger.debug("Could not retrieve charge %s for failure reason", ...)` →
`logger.warning(...)`. Charge-retrieval failures are on-call-relevant;
DEBUG is too silent for dunning monitoring.

---

## Notes

- OBS-3 (tempfile leak in image_service.py): Already resolved in existing code —
  `try/finally os.remove(tmp_path)` is already in place. No action taken.
- OBS-4 (Stripe webhook exception split): Already resolved — three-clause
  ValueError/SignatureVerificationError/Exception split is in `webhook_views.py`.
  No action taken.
- BE-SEC-001 (`tenant_me` missing `@tenant_required`): Already resolved per
  r2 SAML SLO approval on 2026-04-19. No action taken.

## Test guidance for qa-tester

1. `GET /api/v1/gamification/coins/` response: assert `"price_streak_freeze"` key is
   present and equals `GamificationConfig.coin_price_streak_freeze` (default 50).
2. `GET /api/v1/gamification/config/`: assert new fields present in response.
3. `reminders/dispatch_campaign` with mock `notify_reminder` raising: assert
   `result.in_app_failed == len(recipients)` and `result.in_app_sent == 0`.
4. `reminder_send` API response: assert `"in_app_sent"` and `"in_app_failed"` keys present.

— backend-engineer
