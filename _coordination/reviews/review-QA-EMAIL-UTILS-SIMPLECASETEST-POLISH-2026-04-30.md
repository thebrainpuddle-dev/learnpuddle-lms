---
tags: [review, qa, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: QA Email Utils SimpleTestCase Polish + Tenant Emails Redundant-Save Fix

## Verdict: APPROVE

## Summary
Two minor non-blocking polish items from the prior review verdict applied
correctly. Test base-class swap is justified (no DB usage in the file) and
the redundant `save()` removal is genuinely a no-op cleanup. No test logic
changes; no risk to coverage.

## Verification performed
- `backend/tests/notifications/test_email_utils.py`
  - Line 20: import is now `from django.test import SimpleTestCase, override_settings`.
  - All 7 test classes (`GetBaseSenderAddressTestCase`, `BuildSchoolSenderEmailTestCase`,
    `BuildTenantReplyToTestCase`, `BuildBucketHeadersTestCase`, `GetBaseContextTestCase`,
    `BuildTenantUrlTestCase`, `BuildLoginUrlTestCase`) inherit from `SimpleTestCase`
    (lines 52, 85, 128, 163, 211, 236, 289).
  - No bare `TestCase` references remain in the file (grep confirmed).
  - Spot-checked: tests use `SimpleNamespace` for tenant, `@override_settings`,
    and `@patch`. No `@pytest.mark.django_db`, no ORM, no fixtures —
    `SimpleTestCase` is the correct base.

- `backend/tests/tenants/test_tenant_emails.py`
  - `test_context_first_name_fallback_when_empty` (line 106) no longer
    contains the redundant `admin_no_name.first_name = ""` + `.save()`
    sequence. It now flows directly from `_make_admin(..., first_name="")`
    (line 109) into `send_onboard_welcome_email(...)` (line 114).
  - `_make_admin` definition (line 36) accepts and applies `first_name=""`
    on the create call (line 41), so the removed lines were genuinely
    redundant.
  - Assertion `context["first_name"] == "there"` retained on line 116 —
    the fallback path is still under test.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None.

## Positive Observations
- `SimpleTestCase` swap gives a real benefit: it raises `AssertionError`
  if any future edit accidentally adds DB access to a pure-helper test
  file. That's a fail-loud guardrail, not just a perf tweak.
- The redundant-save cleanup makes the test more honest about what
  `_make_admin` already does — a future reader won't wonder whether the
  explicit `save()` was load-bearing.
- Behaviour-only verification used; no production code touched.

## Action
- Mark related QA notes as **done**.
- No follow-ups required.

— lp-reviewer
