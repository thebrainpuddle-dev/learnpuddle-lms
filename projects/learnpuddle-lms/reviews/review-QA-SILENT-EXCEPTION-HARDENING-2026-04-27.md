---
tags: [review, task/QA-SILENT-EXCEPTION-HARDENING, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: QA-SILENT-EXCEPTION-HARDENING — 18 tests for media S3 fallback + password-history logging

## Verdict: APPROVE

## Summary
Eighteen well-scoped tests that lock in the 2026-04-27 backend hardening
(replacement of two silent `except Exception: pass` blocks with
`logger.warning(...)` calls). The patch targets are correct, the
assertions check both *behavioural invariants* (200 response, password
still changed, fallback to X-Accel) and *log invariants* (level, prefix,
user-id correlation), and four bonus tests give first-time direct
coverage of `serve_media_file`'s tenant isolation and path-traversal
defences. No false-positive risk, no flakiness vectors.

## Files reviewed (commit `7e6439b` "feat(sprint-2): MAIC sprint-2 batch ...")

| File | Change |
|------|--------|
| `backend/apps/media/views.py` | `except Exception: pass` → `logger.warning(...)` on S3 presign failure (production change being locked in) |
| `backend/apps/users/views.py` | Same swap on `record_password_history` callsites in `change_password_view` + `confirm_password_reset_view` (production change being locked in) |
| `backend/tests/media/test_media_views.py` | +8 tests (`TestServeMediaFileS3Fallback`, `TestServeMediaFileTenantIsolation`) |
| `backend/tests/users/test_auth_views.py` | +10 tests (`ChangePasswordHistoryFailureTestCase`, `ConfirmPasswordResetHistoryFailureTestCase`) |

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **`from X import Y` patch target rationale could use a one-line
   comment.** The two password-history test classes patch
   `apps.users.password_validators.record_password_history`. This works
   because the production code does `from apps.users.password_validators
   import record_password_history` *inside the function body* — so each
   call re-resolves the attribute from the source module, where the
   patch lives. Future readers may try to patch
   `apps.users.views.record_password_history` and find it missing. A
   single-line comment near `_PW_HISTORY_PATCH = "..."` saying "patched
   at the source module because the import is inside the view" would
   pre-empt that confusion. Non-blocking.

2. **`assertEqual(len(matching), 1)` is strict.** If any unrelated
   middleware or framework code ever logs a warning that *also* contains
   the substring `"password_change: failed to record password history"`,
   the test would over-count. The substring is unique enough today that
   this is essentially zero-risk; flagging only because strict counts
   are slightly more brittle than `>= 1`. Non-blocking.

3. **`test_serve_file_path_traversal_returns_404`** asserts 404 but
   doesn't verify *which* layer rejected the path — it could be Django
   URL routing, or `posixpath.normpath` rejection inside the view. The
   guarantee being locked in (path traversal is rejected) is correct
   either way. If a future refactor switches the URL converter, the
   404 might come from a different layer with the same status code and
   the test still passes. Acceptable as a black-box test of the
   guarantee. Non-blocking.

4. **Heavy use of inline imports** inside test methods (`from
   rest_framework.test import APIClient` repeated 8× in
   `TestServeMediaFileS3Fallback`/`TenantIsolation`, `import django.test`
   repeated). Could be hoisted to module level for readability. Cosmetic.

## Positive Observations

- **Right surface area.** The 8 password-history tests cover the four
  invariants that matter: (a) 200 response, (b) password actually
  changed in DB, (c) WARNING is emitted with the right prefix, (d) user
  ID is in the log line. That's the full contract of "non-fatal
  side-effect failure with observable signal."
- **The `test_confirm_reset_distinct_logger_prefix_from_change_password`
  test is the kind of guard that pays off later** — if someone copies
  the change-password log line into the reset path during a refactor,
  log aggregators stop being able to distinguish the two callsites,
  and that bug would be invisible without this test.
- **Bonus tenant-isolation coverage on `serve_media_file`.** Per the
  request, this endpoint had no direct test coverage before. The four
  cases (teacher-cross-tenant 404, super-admin cross-tenant 200,
  path-traversal 404, missing-file 404) are exactly the right four for
  this view's contract.
- **Storage mocking is correct and minimal.** Patching
  `apps.media.views.default_storage.url` to raise + `.exists` to return
  `True` is the smallest possible mock surface to exercise the new
  except-branch without involving real boto3 or filesystem state.
- **`STORAGE_BACKEND="s3"` + `USE_X_ACCEL_REDIRECT=True`** combination
  in the fallback tests is clever: it forces the code into the S3
  branch, then forces the fallback into a path that doesn't need a
  real file. Result is a focused test that exercises only the
  except-block + the X-Accel response.
- **Production hardening itself is unambiguously good.** Replacing
  `except Exception: pass` with `logger.warning(...)` and a structured
  message including the user ID / file path is the textbook fix for
  silent failures. Both replacements pass the `%s`-deferred-format
  check (no eager `f"..."` inside a `logger.warning(...)`-with-args
  call) so logging.disabled and level filters work correctly.

## Verification performed by reviewer

- Read `serve_media_file` lines 130–211 in `apps/media/views.py`. The
  new except-branch logs at WARNING and returns nothing, so control
  falls through to the X-Accel/dev-serve path on lines 189+. Matches
  test expectation (200 + `X-Accel-Redirect` header).
- Read `change_password_view` and `confirm_password_reset_view` in
  `apps/users/views.py`. Both now log a WARNING with `user.id` after
  catching the `record_password_history` exception. Prefixes are
  distinct: `"password_change:"` vs `"password_reset:"`. Matches the
  prefix-distinction test.
- Confirmed `_PW_HISTORY_PATCH = "apps.users.password_validators.record_password_history"`
  is the correct patch target given the inside-function `from ... import`.
- Confirmed `caplog.at_level(level, logger=...)` and `assertLogs(...)`
  usages capture the right logger names (`apps.media.views`,
  `apps.users.views`) — both match `getLogger(__name__)` in the new
  module-level loggers.
- AST/static-only verification accepted per the BE-SEC-P0 closeout
  sandbox-blocker norm.

## Action for author

None blocking. Mark task `status/done`. The four minor items are
optional polish for a future pass.

— reviewer
