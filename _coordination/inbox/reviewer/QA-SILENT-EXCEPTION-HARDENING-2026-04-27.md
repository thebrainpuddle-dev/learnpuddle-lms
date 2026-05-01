# QA Review Request — Silent Exception Hardening Tests

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-27
**Re:** Test coverage for 2026-04-27 backend-engineer hardening (media S3 fallback + password history logging)

---

## Summary

Backend-engineer landed two silent-exception hardening patches on 2026-04-27:

1. **`apps/media/views.py`** — S3 signed-URL generation failure was a bare
   `except Exception: pass`. Now logs `WARNING` with path + exception before
   falling through to local-serve path.

2. **`apps/users/views.py`** — Two `record_password_history()` callsites (in
   `change_password_view` and `confirm_password_reset_view`) were bare `pass`
   blocks. Now both log `WARNING` with user ID + exception.

This review request covers **18 new tests** that lock in these guarantees.

---

## Files changed

| File | Tests added |
|------|-------------|
| `backend/tests/media/test_media_views.py` | +8 (2 new test classes) |
| `backend/tests/users/test_auth_views.py` | +10 (2 new test classes) |

---

## Test coverage details

### `TestServeMediaFileS3Fallback` (4 tests)

These tests patch `default_storage.url` to raise exceptions and verify:
- WARNING log contains the file path (`test_s3_presign_failure_logs_warning`)
- WARNING log contains the exception string (`test_s3_presign_failure_includes_exception_in_log`)
- View falls through to X-Accel path and returns 200 — no crash (`test_s3_presign_failure_falls_through_to_x_accel`)
- Any exception type (incl. RuntimeError) never produces a 500 (`test_s3_presign_failure_response_is_not_500`)

### `TestServeMediaFileTenantIsolation` (4 tests)

First coverage on the `serve_media_file` endpoint in the test suite:
- Teacher using another tenant's UUID in path → 404 (`test_teacher_cannot_serve_other_tenant_file`)
- SUPER_ADMIN cross-tenant path → 200 (`test_super_admin_can_serve_any_tenant_file`)
- Path traversal (`..`) → 404 (`test_serve_file_path_traversal_returns_404`)
- File not in storage → 404 (`test_serve_file_not_found_in_storage_returns_404`)

### `ChangePasswordHistoryFailureTestCase` (5 tests)

Patches `apps.users.password_validators.record_password_history` to raise:
- View still returns 200 (`test_change_password_still_returns_200_when_history_recording_fails`)
- Password change actually applies in DB (`test_change_password_still_updates_password_when_history_recording_fails`)
- WARNING with correct prefix emitted (`test_change_password_logs_warning_when_history_recording_fails`)
- WARNING contains user ID for correlation (`test_change_password_warning_contains_user_id`)
- `must_change_password` flag still cleared (`test_change_password_clears_must_change_flag_despite_history_failure`)

### `ConfirmPasswordResetHistoryFailureTestCase` (5 tests)

Same shape as change_password — full reset flow using uid+token:
- View still returns 200 (`test_confirm_reset_still_returns_200_when_history_recording_fails`)
- Password update persists in DB (`test_confirm_reset_actually_changes_password_when_history_fails`)
- WARNING with correct prefix emitted (`test_confirm_reset_logs_warning_when_history_recording_fails`)
- WARNING contains user ID (`test_confirm_reset_warning_contains_user_id`)
- Uses `"password_reset:"` prefix, NOT `"password_change:"` (`test_confirm_reset_distinct_logger_prefix_from_change_password`)

---

## Verification

- **AST syntax check**: PASS (both files parse cleanly)
- **Patch targets cross-checked against source**:
  - `apps.media.views.default_storage.url` ✓ (S3 branch, line 166)
  - `apps.users.password_validators.record_password_history` ✓ (inside-function import at lines 358, 488)
- **Logger names**: `apps.media.views` and `apps.users.views` match `getLogger(__name__)` ✓
- **Message prefixes**: All three prefixes verified against source code ✓
- **`@tenant_required` fixture setup**: All `serve_media_file` tests set HTTP_HOST to resolve tenant ✓
- **Docker run**: deferred (sandbox blocker accepted at BE-SEC-P0 closeout)

Docker run command:
```bash
docker compose exec web pytest \
  tests/media/test_media_views.py::TestServeMediaFileS3Fallback \
  tests/media/test_media_views.py::TestServeMediaFileTenantIsolation \
  tests/users/test_auth_views.py::ChangePasswordHistoryFailureTestCase \
  tests/users/test_auth_views.py::ConfirmPasswordResetHistoryFailureTestCase \
  -v
# Expected: 18 passed
```

Also confirmed SCIM PATCH M3+M4 tests (4 tests, `apps/users/tests_scim.py::TestSCIMPatchUser`)
are well-structured and implementation is in place — no reviewer action needed beyond
the regular BE-SCIM-M3-M4-PATCH review already filed.

— qa-tester
