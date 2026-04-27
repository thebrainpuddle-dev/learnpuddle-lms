# TASK-020 — Reminders: PII log scrub + in-app failure surfacing

## Status
- Phase: hygiene / follow-up
- Owner: backend-engineer
- Filed: 2026-04-20 by lp-reviewer (via qa-tester audit of reminders services)
- Priority: P2 (non-blocking; cleanup)
- Related: QA-COVERAGE-reminders-2026-04-20
- **Implemented: 2026-04-20** (backend-engineer) — see shared-log.md

## Goal
Address two low-risk-but-real smells surfaced during the qa-tester coverage
audit of `apps/reminders/`:

1. Avoid leaking teacher PII via production logs.
2. Surface in-app notification failures in the dispatch result so admins
   can see partial-delivery state.

## Scope

### 1. PII log at `apps/reminders/views.py:129`

Current:
```python
logger.info(f"[REMINDER_SEND] Type={reminder_type}, data={data}")
```

`data` is the full validated serializer payload. For CUSTOM reminders it
contains admin-typed subject/body. For all types it contains `teacher_ids`,
which in turn can be joined with `users.User` in log aggregation to recover
names / emails — effectively a PII exposure to anyone with log access.

**Required change:** drop to DEBUG **or** redact to only the stable fields:

```python
logger.info(
    "[REMINDER_SEND] type=%s course_id=%s assignment_id=%s recipient_count=%d",
    reminder_type,
    data.get("course_id"),
    data.get("assignment_id"),
    len(data.get("teacher_ids") or []),
)
```

No other log lines in `views.py` emit full `data`; this is the only site.

### 2. Swallowed `notify_reminder` failure at `apps/reminders/services.py:213-214`

Current:
```python
try:
    from apps.notifications.services import notify_reminder
    notify_reminder(...)
except Exception as exc:
    logger.warning("in-app reminder notification failed campaign=%s err=%s", campaign.id, exc)

return result
```

`result` (a `DispatchResult`) is unchanged on in-app failure, so the caller
(`reminder_send` view) reports all recipients as successfully notified even
though the in-app channel silently failed (e.g. Redis/Channels down).

**Required change:** extend `DispatchResult` with `in_app_sent: int` and
`in_app_failed: int` counters, populate them from the try/except above,
and surface them in the view response so admins see the partial-failure
state. Keep the current behaviour of not re-raising (email has already
succeeded; we don't want to mark the whole campaign as failed).

## Acceptance criteria
- [ ] `views.py:129` no longer logs `teacher_ids` or serializer data dict.
- [ ] `DispatchResult` gains `in_app_sent` / `in_app_failed` counters
      (default 0).
- [ ] `dispatch_campaign` increments those counters based on
      `notify_reminder` success / exception.
- [ ] `reminder_send` view response includes the new counters.
- [ ] Tests:
  - Unit: simulate `notify_reminder` raising — assert `in_app_failed ==
    len(recipients)` and `in_app_sent == 0`, email counters unaffected.
  - Unit: happy path — `in_app_sent == len(recipients)`,
    `in_app_failed == 0`.
  - View: response includes the new fields.

## Non-goals
- Retry logic for in-app delivery (existing WARNING-log behaviour is
  sufficient for the operator).
- Back-propagation to `ReminderDelivery` rows (email is the authoritative
  delivery channel; in-app is best-effort).

## Risk
Low. Both changes are additive; log-format change is behind an INFO
statement that no parser should depend on.

## Estimate
~1 hour: views.py edit + services.py DispatchResult extension + 3 tests.
