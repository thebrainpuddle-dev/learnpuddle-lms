# Implementation Plan: TASK-002 + TASK-003

## TASK-002: Password Validation for Super Admin Tenant Onboarding

**Actual issue found:** The `tenant_reset_admin_password` endpoint already has `validate_password()`. The real gap is in `OnboardTenantSerializer` used by super admin `tenant_list_create` POST — it doesn't validate admin passwords.

### Changes Required

**File: `backend/apps/tenants/superadmin_serializers.py`**
- Add import: `from django.contrib.auth.password_validation import validate_password as django_validate_password`
- Add `validate_admin_password()` method to `OnboardTenantSerializer`
- Optionally add `min_length=8` to the field definition

### Tests
- Weak password rejected (400)
- Numeric password rejected (400)
- Short password rejected (400)
- Strong password accepted (201)

---

## TASK-003: Rate Limiting + Password Validation for Invitation Accept

### Changes Required

**File: `backend/apps/users/admin_views.py`**
- Import `throttle_classes`, `ScopedRateThrottle`
- Create `InvitationAcceptThrottle` class with scope `'invitation_accept'`
- Apply `@throttle_classes([InvitationAcceptThrottle])` to `invitation_accept_view`
- Replace `len(password) < 8` with `validate_password()` using temp User object
- Note: `invitation_accept` scope already configured in settings.py at 5/minute

**File: `frontend/src/pages/auth/AcceptInvitationPage.tsx`**
- Update error display to show `details` array from password validation
- Update placeholder text from "At least 8 characters" to "Choose a strong password"

### Tests
- Empty password → 400
- Common password → 400
- Numeric password → 400
- Short password → 400
- Password similar to email → 400
- Strong password → 201
- Rate limiting → 429 after 5 attempts
