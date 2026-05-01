# Review Request — SCIM User PUT/PATCH Polish

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-27
**Type:** Non-blocking follow-up polish (from TASK-023 M2 + SCIM M3-M4 review)
**File:** `backend/apps/users/scim_views.py`

---

## What changed

Two small behavioural improvements per your review observations:

### Change 1 — PUT replace semantics (your TASK-023 M2 comment)

**Before:**
```python
user.first_name = (name_obj.get("givenName") or user.first_name).strip()
user.last_name  = (name_obj.get("familyName") or user.last_name).strip()
```

**After:**
```python
if "givenName" in name_obj:
    user.first_name = str(name_obj.get("givenName") or "").strip()
if "familyName" in name_obj:
    user.last_name = str(name_obj.get("familyName") or "").strip()
```

Uses `"key in dict"` semantics: present (even null/empty) → overwrite; absent → retain.
Added an inline comment quoting RFC 7644 §3.5.1 and noting the lenient interpretation.

### Change 2 — PATCH conditional save (your SCIM M3-M4 observation)

Added `_user_changed = False` flag, set to `True` only when a `replace` op is processed.
`user.save()` is now guarded by `if _user_changed:`.

Eliminates one wasted UPDATE when every op in the PATCH batch is unrecognised (e.g. an IdP
sends an `add` op that LearnPuddle doesn't yet support). Existing `test_patch_unknown_op_type_logs_debug_and_returns_200` still passes — no DB write for unknown ops means `updated_at` stays the same (test checks `first_name` and `is_active`, both still correct).

---

## What was NOT addressed

1. **`run_tests.sh` deletion** — sandbox restriction blocked `rm`. File contains `exit 1` and deprecation notice; safe to leave until manually deleted.

2. **Path-less `add`/`remove` ops** — intentionally deferred, as you noted in the M3-M4 verdict. Azure AD uses `replace`; this is a future ticket.

---

## Tests

Regression tests requested from qa-tester at:
`_coordination/inbox/qa-tester/SCIM-POLISH-REGRESSION-TESTS-2026-04-27.md`

Existing test suite (42 user tests + 4 M3/M4 tests) all still valid.

---

— backend-engineer
