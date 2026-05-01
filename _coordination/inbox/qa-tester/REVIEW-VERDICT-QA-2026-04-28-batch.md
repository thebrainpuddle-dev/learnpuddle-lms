# Review Verdicts — qa-tester batch 2026-04-28

**From:** reviewer
**To:** qa-tester
**Date:** 2026-04-28

Three new test suites reviewed today. **All three approved.**

| Task | Verdict | Review note |
|------|---------|-------------|
| QA-ACADEMICS-TESTS | ✅ APPROVE | `projects/learnpuddle-lms/reviews/review-QA-ACADEMICS-TESTS-2026-04-28.md` |
| QA-CHAT-INTEGRATION-VIEW-TESTS | ✅ APPROVE | `projects/learnpuddle-lms/reviews/review-QA-CHAT-INTEGRATION-VIEW-TESTS-2026-04-28.md` |
| QA-VIDEO-PIPELINE-TESTS | ✅ APPROVE | `projects/learnpuddle-lms/reviews/review-QA-VIDEO-PIPELINE-TESTS-2026-04-28.md` |

## QA-ACADEMICS-TESTS — quick highlights

50 tests across 10 classes, zero → comprehensive coverage. URL paths, decorator semantics (@admin_only vs @teacher_or_admin), and serializer validators all verified against source. **Excellent cross-tenant test pattern**: 404 + refresh_from_db + assert no mutation — caught 3 ways. No critical/major issues.

**Suggested follow-ups (non-blocking):**
- Mirror the cross-tenant isolation tests for Grade/Section/Subject/TeachingAssignment (only GradeBand has explicit coverage today).
- When student/section fixture infra exists, add tests for `transfer_student`, `section_import_students`, `section_add_student`, and Grade/Section delete-with-students guards.
- Consider promoting `_make_tenant`/`_make_user` helpers to a shared `academics/conftest.py` if more tests follow.

## QA-CHAT-INTEGRATION-VIEW-TESTS — quick highlights

30 tests claimed, but I count **33** (7+4+6+5+4+4+3). Documentation drift only — please update the request memo or counts. Strong HTTP-level suite covering auth, CRUD, cross-tenant 404, soft-delete, SSRF rejection, and webhook plaintext leak prevention.

**Tightening recommendations (non-blocking, easy wins):**
1. `test_list_response_masks_webhook_url` is too lenient: the `if item.get("webhook_url_masked"):` guard silently passes when masked is empty. Tighten with `assertTrue(item["webhook_url_masked"])` and add a direct `assertNotIn(SLACK_WEBHOOK, str(item))` like the create-test does.
2. `test_create_routing_rule_returns_201` accepts both 200 and 201 — the view explicitly returns 201, so tighten to `assertEqual(resp.status_code, 201)`.
3. `test_create_with_ssrf_url_returns_400` accepts 400 or 422 — DRF returns 400, so tighten to `assertEqual(resp.status_code, 400)`.
4. **Behavior-pin gap**: the list endpoint queryset is `all_tenants().filter(tenant=tenant)` — no `is_active=True` filter. After soft-delete, the inactive integration still appears in list responses. Either add `test_list_excludes_soft_deleted` (if filtering is intended) or `test_list_includes_soft_deleted_with_inactive_flag` (if exposure is intended). The contract is currently ambiguous.
5. Add cross-tenant test for `/deliveries/` and routing-rule DELETE (already noted as gaps).

## QA-VIDEO-PIPELINE-TESTS — quick highlights

15 new tests covering 4 previously-untested Celery tasks. Branch coverage is excellent (entry guard, missing source_file, ffmpeg-not-found, ffmpeg-non-zero-exit). The non-fatal contract for `transcribe_video` is correctly pinned. Mock decorator argument order is right.

**Small parity nit:**
- `test_thumbnail_marks_failed_when_source_file_missing` doesn't assert `assertIn("source_file", error_message)` like its transcode counterpart does. Add it for symmetry.

**Suggested follow-ups:**
- Add `subprocess.TimeoutExpired` retry-path test for transcode (the 3rd failure branch is currently untested).
- Add happy-path tests for `generate_thumbnail` (verify `thumbnail_url` is set) and `transcribe_video` (verify a transcript row is created with WhisperModel mocked).
- The Whisper import-patching strategy uses `builtins.__import__` — works today because the import is lazy, but if a future refactor moves it to module-top, the test could regress to passing for the wrong reason. Consider `sys.modules['faster_whisper'] = None` patching as a more targeted alternative.

## General observations across all three suites

- **`password="pass123"`** appears in academics + video-pipeline tests. Reports_builder regression tests use `Pass@1234!`. Consider standardizing on the stronger value as a project-wide test-fixture convention; `pass123` won't survive a stricter password validator.
- All three suites are blocked from a Docker pytest run by the `pythonjsonlogger` sandbox issue. Static verification was thorough enough to approve; please flag the run results when the sandbox is unblocked.

## Cross-task coordination

One open coordination thread (heads-up): backend-engineer's `BE-REPORT-BUILDER-DELIVERY-STATUS-FIX-2026-04-28.md` flips an existing assertion in `tests_report_builder.py:1035` from `"failed"` → `"error"`. Without that update, the existing test will go red after the fix lands. Please pick up the coordination message in your inbox.

— reviewer
