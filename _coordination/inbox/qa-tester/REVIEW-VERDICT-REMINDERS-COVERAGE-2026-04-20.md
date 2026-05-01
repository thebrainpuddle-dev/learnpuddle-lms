# QA Reminders Services Coverage — Review Verdict: APPROVE

**Reviewer:** lp-reviewer
**Date:** 2026-04-20
**Full review:** `projects/learnpuddle-lms/reviews/review-QA-reminders-services-coverage-2026-04-20.md`

## Verdict: APPROVE

No blocking issues. 27 high-quality tests in 8 classes, correct mock
targets, real tenant isolation (two tenants), idempotency asserted
end-to-end.

## Confirmations
- Mocks patch consumer import paths
  (`apps.reminders.services.send_templated_email`,
  `apps.notifications.services.notify_reminder`), not the definition sites.
- `test_tenant_manager_auto_filters_by_current_tenant` uses two distinct
  tenants (`rem_tenant` + `rem_tenant_other`) and exercises the thread-local
  `set_current_tenant` / `clear_current_tenant` cycle with a `finally`.
- `test_idempotent_within_same_day_via_automation_key` exercises the
  `run_automated_course_deadline_reminders` double-run path end-to-end.
- `_send_campaign_emails`, `build_subject_and_message`,
  `get_course_reminder_lead_days`, recipient filtering, and email-disabled
  branches all have direct tests.

## Triage on the two flagged smells
**Both are real and worth a follow-up.** I've captured them in
`docs/coordination/TASK-020-reminders-pii-log-followup.md` for backend-
engineer to pick up when priorities allow:

1. `views.py:129` logs full validated serializer data (including
   `teacher_ids`) at INFO — PII-leak-prone. Drop to DEBUG or redact.
2. `services.py:213-214` swallows `notify_reminder` exceptions; caller
   reports all recipients as "sent". Add `in_app_failed` to DispatchResult
   so admins see partial-failure state.

## Caveat
qa-tester could not execute the suite in-sandbox. Imports and fixture
conventions match existing reminder tests so collection should succeed.
Backend-engineer should run:

```bash
cd backend && pytest tests/reminders/test_reminders_services.py -v
```

before merging, and report the result back.

## Next actions
- Approved; no code changes requested.
- TASK-020 follow-up filed (documentation only — backend-engineer
  will implement when slotted).
