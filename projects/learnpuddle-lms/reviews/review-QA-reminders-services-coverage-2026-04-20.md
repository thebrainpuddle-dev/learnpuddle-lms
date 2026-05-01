---
tags: [review, qa/reminders-services, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: QA Coverage — reminders services (backend)

## Verdict: APPROVE

## Summary
High-quality service-layer test suite that targets the unexercised gap in
`apps/reminders/services.py` rather than duplicating existing view coverage.
27 tests across 8 classes; mocks patch the correct import paths; tenant
isolation uses two distinct tenants; automation idempotency is directly
asserted via the `automation_key` guard. The two code smells qa-tester
flagged are real and worth a small follow-up TASK but not blockers.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
1. **Flagged smells are worth a follow-up TASK.** Both are real:
   - `views.py:129` — `logger.info(f"[REMINDER_SEND] Type={reminder_type}, data={data}")`
     emits the full validated serializer data at INFO. `data` includes
     `teacher_ids` (and, for custom types, subject/body the admin typed). This
     is PII-leak-prone in production log aggregation. Drop to DEBUG or redact
     `teacher_ids` before logging.
   - `services.py:213-214` — `notify_reminder` exception is caught and logged
     at WARNING; caller has no way to know in-app delivery failed, so the
     campaign still reports all recipients as "sent". Not a bug per se
     (email still succeeded), but the DispatchResult should surface an
     `in_app_failed` counter so admins see the partial-failure state.
   - I've drafted `docs/coordination/TASK-020-reminders-pii-log-followup.md`
     capturing both — backend-engineer can pick it up when priorities allow.

## Positive Observations
- **Correct mock targets**: `patch("apps.reminders.services.send_templated_email")`
  and `patch("apps.notifications.services.notify_reminder")` — patches at the
  consumer import site, not the definition site. Tests will not silently
  false-pass if the caller switches send helpers.
- **Tenant isolation test** (`test_tenant_manager_auto_filters_by_current_tenant`)
  creates two tenants (`rem_tenant`, `rem_tenant_other`), writes a campaign
  under each via `all_objects`, then verifies `ReminderCampaign.objects.all()`
  under `set_current_tenant(rem_tenant)` returns only the local one and the
  `all_objects` escape hatch sees both. Clean pattern, properly cleans up
  thread-local state in `finally`.
- **Automation idempotency** (`test_idempotent_within_same_day_via_automation_key`)
  invokes `run_automated_course_deadline_reminders` twice on the same day
  and asserts the second run creates zero new campaigns — exercising the
  `uniq_auto_reminder_campaign_per_tenant_key` partial-index guarantee
  end-to-end, not just the constraint in isolation.
- **Lead-day parser coverage**: four branches (empty, valid-dedup-sorted,
  out-of-range/invalid filtered, flag respected) match the four decision
  points in `get_course_reminder_lead_days`.
- **Email-disabled path**: `TestDispatchCampaignEmailDisabled` exercises the
  branch where `REMINDER_EMAIL_ENABLED=False` short-circuits the send call
  but still marks delivery `SENT` (in-app only). Non-obvious branch, well
  covered.
- **Recipient filtering**: `test_completed_teachers_are_excluded` verifies
  the `get_completed_teacher_ids_for_course` filter — a regression-sensitive
  branch because a refactor could easily send reminders to teachers who
  already finished.
- **Coverage delta estimate** looks credible: +35–45pp on `services.py` is
  consistent with the surface area claimed (email send, dispatch, lead-day
  parser, automation runner, recipient filter).

## Execution caveat
qa-tester couldn't execute the suite due to sandbox restrictions. I spot-
checked imports (`from apps.reminders.services import …`, `set_current_tenant`
from `utils.tenant_middleware`, `Tenant` fixture with `feature_reminders=True`)
— all resolve against the current tree. Collection should succeed. Backend-
engineer should run:

```bash
cd backend && pytest tests/reminders/test_reminders_services.py -v
```

before landing.

## Follow-up
Created `docs/coordination/TASK-020-reminders-pii-log-followup.md` capturing
both the PII log and swallowed-notification smells.

## Files reviewed
- `backend/tests/reminders/test_reminders_services.py` (704 lines, 27 tests)
- `backend/apps/reminders/views.py` (line 129 — PII log)
- `backend/apps/reminders/services.py` (lines 197-216 — dispatch & swallow)
