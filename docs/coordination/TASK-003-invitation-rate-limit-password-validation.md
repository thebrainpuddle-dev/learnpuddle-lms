# TASK-003: Add Rate Limiting and Password Validation to Invitation Accept

**Priority:** P1 (Security)
**Phase:** 1
**Status:** done
**Assigned:** backend-security
**Estimated:** 1 hour

## Problem

In `backend/apps/users/admin_views.py` (lines ~532-576), the invitation accept endpoint has two security issues:

1. **No rate limiting** — Missing `@throttle_classes()` decorator. Attackers can brute-force invitation tokens.
2. **Weak password validation** — Only checks `len(password) < 8`. No call to Django's `validate_password()`.

```python
@api_view(["POST"])
@permission_classes([AllowAny])
def invitation_accept_view(request, token):  # NO @throttle_classes!
    if not password or len(password) < 8:  # Too weak!
        return Response({"error": "Password must be at least 8 characters."}, ...)
```

Compare to login endpoint which has `@throttle_classes([LoginThrottle])`.

## Fix Required

1. Add `@throttle_classes([InvitationThrottle])` or reuse existing throttle
2. Replace `len(password) < 8` check with `validate_password(password)`
3. Handle `ValidationError` properly
4. Add tests for both rate limiting and password validation

## Files to Modify

- `backend/apps/users/admin_views.py` — Add throttle + validation
- `backend/apps/users/tests.py` — Add test cases

## Acceptance Criteria

- [ ] Rate limiting applied (e.g., 5 attempts/hour per IP)
- [ ] `validate_password()` used instead of length-only check
- [ ] Weak passwords rejected with descriptive errors
- [ ] Brute-force attempts get HTTP 429
- [ ] Valid invitation acceptance still works
- [ ] Tests cover both rate limiting and weak password rejection
