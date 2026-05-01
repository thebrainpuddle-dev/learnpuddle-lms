---
tags: [review, task/QA-BE-FOLLOWUPS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: QA-BE-FOLLOWUPS-COVERAGE-2026-04-20 — 18 Tests for Backend Follow-ups

## Verdict: APPROVE

## Summary
18 new tests covering all four items in `BE-FOLLOWUPS-2026-04-20`. Coverage is complete, assertions are behaviour-focused, and the new test file is scoped and well-named. Non-regression checks (core fields, pre-existing keys) included. No production code touched.

## Verification

### Item 1 — `price_streak_freeze` on coin balance endpoint
**File:** `backend/apps/progress/tests_puddle_coins.py` lines 548–575
- `test_get_balance_includes_price_streak_freeze_field` asserts key present (line 565), default value 50 (line 567), and that the field tracks a live config mutation (lines 569–575). ✅
- Three assertions, not one — this is exactly the "mutate and re-fetch" pattern that catches a hard-coded literal regression. Good.

### Item 2 — `GamificationConfigSerializer` new fields
**File:** `backend/apps/progress/tests_gamification_config_fields.py` (new, 286 lines)
- `NEW_FREEZE_COIN_FIELDS` constant (lines 67–77) matches exactly the 7 fields added to the serializer. ✅
- `CORE_FIELDS` list (lines 80–94) is a non-regression guard — matches the pre-existing serializer fields. ✅
- `GamificationConfigFieldsGetTest`:
  - `test_config_get_includes_all_new_freeze_coin_fields` — loops all 7 fields. ✅
  - `test_config_get_new_field_default_values` — verifies defaults (`coin_price_streak_freeze=50`, `freeze_token_max_inventory=3`, `weekend_mode_available=False`). ✅
  - Auth matrix: 401 (anon), 403 (teacher), 200 (admin). ✅
  - `test_config_get_cross_tenant_isolation` — admin of tenant B hits tenant A subdomain → expects 403. Good tenant-isolation smoke test.
- `GamificationConfigFieldsPatchTest`:
  - One round-trip test per field (7 tests) + atomic multi-field update + partial-preserve + role guard. ✅
  - `test_patch_partial_update_preserves_other_fields` (lines 260–273) is the gold-standard assertion for partial updates — seeds two fields, patches one, asserts the other survives. Catches "update clobbers unrelated fields" bugs.
  - URL tested: `/api/v1/gamification/admin/config/update/` — confirmed in `gamification_urls.py` line 17. ✅

### Item 3 — `dispatch_campaign` in-app counters (service layer)
**File:** `backend/tests/reminders/test_reminders_services.py` lines 496–544
- `test_dispatch_sets_in_app_sent_when_notify_reminder_succeeds` — asserts `in_app_sent == 2, in_app_failed == 0`. ✅
- `test_dispatch_sets_in_app_failed_when_notify_reminder_raises` — asserts `in_app_failed == 2, in_app_sent == 0` AND that `sent/failed` from the email channel are not contaminated (lines 543–544). ✅ This non-contamination assertion is crucial and was not required by the request — bonus point.
- Uses module-level patch of `apps.notifications.services.notify_reminder` — which is the correct target because `dispatch_campaign` does a runtime `from ... import` (line 205 of services.py), so the patched attr is re-read each call. ✅

### Item 4 — `reminder_send` view response includes in_app keys
**File:** `backend/tests/reminders/test_reminders_views.py` lines 315–376
- `test_send_response_includes_in_app_keys` — presence of `in_app_sent`/`in_app_failed`, type + non-negative int, and non-regression of `sent`/`failed`/`campaign`. ✅
- `test_send_response_in_app_failed_when_notify_raises` — patches `notify_reminder` to raise, asserts `in_app_sent == 0 AND in_app_failed > 0`. ✅

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Silent-skip on 400 risks false-pass** (lines 337, 373 of `test_reminders_views.py`)
   Both view tests guard with `if response.status_code == 200:` and no `else: pytest.fail(...)`. If the `teacher_user` fixture ever stops populating the tenant with an eligible teacher, these tests silently become no-ops and continue to "pass" while no assertions execute. Two fixes, either acceptable:
   - Add `assert response.status_code == 200, response.data` before the guard (converts a no-op pass into a hard fail surfacing the fixture bug).
   - Or call `pytest.fail("no teacher in tenant — fixture regression")` in the `else` branch.
   The QA author flagged this as a caveat in the handoff — approving but worth hardening in a follow-up QA pass.

2. **`_u()` counter is a module-level singleton** (`tests_gamification_config_fields.py` lines 30–35)
   Works fine, but a `uuid4().hex[:6]` suffix is more robust under parallel test execution (`pytest-xdist`). Non-blocking — pattern matches existing tests in the suite.

3. **Cross-tenant config test does not also assert the body is empty / error-shaped** (line 174)
   Just checks `status_code == 403`. A stronger assertion would also confirm no config data leaked in the response body. Not required — tenant middleware returns a bare 403 with no body, which is safe — but adding `self.assertIn("error", resp.json())` would document intent.

## Positive Observations
- **Non-regression guards are explicit**: `CORE_FIELDS` list (Item 2), non-contamination assertions on `sent/failed` (Item 3), `campaign`/`sent`/`failed` key presence in Item 4 view test.
- **Mutation-tracking assertion** on `price_streak_freeze` (75 after config bump) catches the most likely regression: frontend-style hard-coded literal in the serializer.
- **One test per field** in `GamificationConfigFieldsPatchTest` + one multi-field atomic test is the right granularity — granular failures tell you which field's writable-field list is wrong.
- **Auth matrix (401/403/200)** explicit per endpoint — makes role-gate regressions immediate.
- **QA author included the patch-target correctness check implicitly** by choosing `apps.notifications.services.notify_reminder` (module attr) rather than `apps.reminders.services.notify_reminder` (re-bound name). This is the right choice given the runtime import in `dispatch_campaign`.

## Recommended Next Steps
- Approve and merge.
- Open a small follow-up: harden the two silent-skip guards in `test_reminders_views.py` so a fixture regression can't mask them.
- `pytest execution blocked in QA sandbox` — please run the combined command in CI on merge:
  ```bash
  cd backend && pytest \
    apps/progress/tests_gamification_config_fields.py \
    apps/progress/tests_puddle_coins.py::CoinApiTest::test_get_balance_includes_price_streak_freeze_field \
    tests/reminders/test_reminders_services.py::TestDispatchCampaign \
    tests/reminders/test_reminders_views.py::TestReminderSend \
    -v
  ```

— lp-reviewer
