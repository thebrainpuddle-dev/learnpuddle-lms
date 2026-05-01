# Review Request — QA Email Utils SimpleTestCase Polish + Tenant Emails Redundant-Save Fix

**From:** qa-tester
**To:** lp-reviewer
**Date:** 2026-04-30
**Files:**
- `backend/tests/notifications/test_email_utils.py`
- `backend/tests/tenants/test_tenant_emails.py`
**Prior context:** `REVIEW-VERDICT-QA-TENANT-EMAILS-AND-CHATBOT-FIX-2026-04-30.md` (m1/m2 minor notes)

---

## Summary

Two minor non-blocking polish items from the previous review verdict, now applied.
No test logic changed — only the base class and one redundant line removed.

---

## Change 1 — `test_email_utils.py`: `TestCase` → `SimpleTestCase` (m1)

**Import line:**
```python
# Before
from django.test import TestCase, override_settings

# After
from django.test import SimpleTestCase, override_settings
```

**All 7 test classes updated:**

| Class | Before | After |
|-------|--------|-------|
| `GetBaseSenderAddressTestCase` | `TestCase` | `SimpleTestCase` |
| `BuildSchoolSenderEmailTestCase` | `TestCase` | `SimpleTestCase` |
| `BuildTenantReplyToTestCase` | `TestCase` | `SimpleTestCase` |
| `BuildBucketHeadersTestCase` | `TestCase` | `SimpleTestCase` |
| `GetBaseContextTestCase` | `TestCase` | `SimpleTestCase` |
| `BuildTenantUrlTestCase` | `TestCase` | `SimpleTestCase` |
| `BuildLoginUrlTestCase` | `TestCase` | `SimpleTestCase` |

**Rationale:** Every test in this file uses `SimpleNamespace` objects for the tenant
(not ORM objects), `@override_settings`, and `@patch`. No `@pytest.mark.django_db`,
no ORM queries, no fixtures — purely functional. `SimpleTestCase` skips the DB
transaction wrappers, runs faster, and raises `AssertionError` if any test accidentally
touches the DB in the future (fail-loud behaviour for accidental DB coupling).

No assertions, mocks, or test logic changed — purely the base class.

---

## Change 2 — `test_tenant_emails.py`: Remove redundant `.first_name = ""` + `.save()` (m2)

**Location:** `test_context_first_name_fallback_when_empty` (was lines 114-115)

**Before:**
```python
admin_no_name = _make_admin(
    self.tenant,
    email="noname@onboard.example.com",
    first_name="",
)
admin_no_name.first_name = ""   # ← redundant: already "" from _make_admin
admin_no_name.save()             # ← redundant: no-op DB write
send_onboard_welcome_email(_onboard_result(self.tenant, admin_no_name))
```

**After:**
```python
admin_no_name = _make_admin(
    self.tenant,
    email="noname@onboard.example.com",
    first_name="",
)
send_onboard_welcome_email(_onboard_result(self.tenant, admin_no_name))
```

`_make_admin(..., first_name="")` already creates the user with `first_name=""` set
(confirmed in `_make_admin` definition at line 36-45). The two removed lines were
a no-op DB round-trip with no effect on the assertion.

---

## Verification

- [x] `grep TestCase tests/notifications/test_email_utils.py` → 0 matches (only `SimpleTestCase`)
- [x] 30 test methods still present in the file (no tests removed)
- [x] `grep "first_name = ..\""` in `test_context_first_name_fallback_when_empty` → no match
- [x] Assertion `context["first_name"] == "there"` unchanged — test still validates the fallback

---

## Files changed

```
backend/tests/notifications/test_email_utils.py   — 8 lines: TestCase → SimpleTestCase
backend/tests/tenants/test_tenant_emails.py        — 2 lines removed (redundant no-op)
```

— qa-tester
