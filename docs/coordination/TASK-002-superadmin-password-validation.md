# TASK-002: Add Password Validation to Super Admin Password Reset

**Priority:** P1 (Security)
**Phase:** 1
**Status:** done
**Assigned:** backend-security
**Estimated:** 30 minutes

## Problem

In `backend/apps/tenants/superadmin_views.py` (lines ~342-345), the super admin password reset endpoint directly calls `set_password()` without Django's `validate_password()`, allowing weak/common passwords.

```python
new_password = request.data.get("new_password")
if new_password:
    admin_user.set_password(new_password)  # No validation!
    admin_user.save()
```

Compare to `backend/apps/users/views.py` line ~427 which correctly calls `validate_password()`.

## Fix Required

1. Import `validate_password` from `django.contrib.auth.password_validation`
2. Call `validate_password(new_password, user=admin_user)` before `set_password()`
3. Handle `ValidationError` and return 400 with error messages
4. Add test for weak password rejection

## Files to Modify

- `backend/apps/tenants/superadmin_views.py` — Add validation call
- `backend/apps/tenants/tests.py` — Add test case

## Acceptance Criteria

- [ ] `validate_password()` called before `set_password()`
- [ ] Weak passwords (e.g., "password", "12345678") are rejected with 400
- [ ] Strong passwords still work correctly
- [ ] Error response includes Django's validation messages
- [ ] Test covers weak password rejection
