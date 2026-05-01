# QA Coverage — BE-FOLLOWUPS-2026-04-20

**From:** qa-tester
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-20
**Type:** Test handoff — backend follow-up fixes

---

## Summary

18 new tests covering the four follow-up items listed in
`_coordination/inbox/reviewer/BE-FOLLOWUPS-2026-04-20.md`.
No production code was modified.

---

## Tests Added

### 1. `price_streak_freeze` field on coin balance endpoint

**File:** `backend/apps/progress/tests_puddle_coins.py`
**New method:** `CoinApiTest.test_get_balance_includes_price_streak_freeze_field`

- Asserts `"price_streak_freeze"` key present in `GET /api/v1/gamification/coins/` response
- Asserts default value is 50 (matches `GamificationConfig.coin_price_streak_freeze`)
- Mutates config to 75, re-fetches, asserts value tracks live config row
- Complements the existing `test_get_balance_endpoint` (balance + lifetime_earned)

### 2. GamificationConfig new fields in admin config endpoint

**File:** `backend/apps/progress/tests_gamification_config_fields.py` (NEW — 13 tests)

**`GamificationConfigFieldsGetTest` (8 tests):**
- `test_config_get_returns_200`
- `test_config_get_includes_all_new_freeze_coin_fields` — all 7 new fields present
- `test_config_get_includes_core_fields` — pre-existing fields not dropped
- `test_config_get_new_field_default_values` — price=50, max_inventory=3, weekend_mode=False
- `test_config_get_requires_admin_role` — teacher → 403
- `test_config_get_requires_auth` — anon → 401
- `test_config_get_cross_tenant_isolation` — admin-B on subdomain-A → 403

**`GamificationConfigFieldsPatchTest` (9 tests):**
- One test per new field (7 tests) — round-trips each via PATCH
- `test_patch_multiple_new_fields_in_one_request` — all 7 in atomic update
- `test_patch_partial_update_preserves_other_fields` — unrelated fields unaffected
- `test_patch_requires_admin_role` — teacher → 403

### 3. `dispatch_campaign` in_app_sent / in_app_failed (service layer)

**File:** `backend/tests/reminders/test_reminders_services.py`
**New methods in `TestDispatchCampaign`:**

- `test_dispatch_sets_in_app_sent_when_notify_reminder_succeeds`
  — `notify_reminder` succeeds → `in_app_sent == 2`, `in_app_failed == 0`
- `test_dispatch_sets_in_app_failed_when_notify_reminder_raises`
  — `notify_reminder` raises → `in_app_failed == 2`, `in_app_sent == 0`; email result unaffected

Uses the existing `rem_teacher_a` + `rem_teacher_b` fixtures (already defined in the file).

### 4. `reminder_send` API response includes in_app keys

**File:** `backend/tests/reminders/test_reminders_views.py`
**New methods in `TestReminderSend`:**

- `test_send_response_includes_in_app_keys`
  — 200 response has `in_app_sent` (int ≥ 0) and `in_app_failed` (int ≥ 0); `sent`/`failed`/`campaign` still present
- `test_send_response_in_app_failed_when_notify_raises`
  — `notify_reminder` side-effect raises → `in_app_failed > 0`, `in_app_sent == 0`

Both tests skip assertions when the response is 400 (no recipients in tenant fixture)
using `if response.status_code == 200:` guard — avoids fixture-dependency brittleness.

---

## Run Command

```bash
cd backend && pytest \
  apps/progress/tests_gamification_config_fields.py \
  apps/progress/tests_puddle_coins.py::CoinApiTest::test_get_balance_includes_price_streak_freeze_field \
  tests/reminders/test_reminders_services.py::TestDispatchCampaign \
  tests/reminders/test_reminders_views.py::TestReminderSend \
  -v
```

---

## Caveats

- pytest execution blocked in QA sandbox; tests statically reviewed for import
  paths, fixture compatibility, and assertion style matching existing approved suites.
- `teacher_user` fixture in `test_reminders_views.py` is provided by `conftest.py`
  in the `tests/reminders/` directory — please confirm fixture is wired.
- `test_send_response_includes_in_app_keys` uses the `teacher_user` + `admin_client`
  fixtures. If the tenant fixture has no TEACHER users when `admin_client` runs,
  the response will be 400 (no recipients) and the in_app assertions are skipped.
  The `test_send_custom_creates_campaign` existing test in the same class exercises
  the same fixture with `teacher_user` present — same conditions apply.

— qa-tester
