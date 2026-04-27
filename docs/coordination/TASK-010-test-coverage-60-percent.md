# TASK-010: Raise Backend Test Coverage to 60%

**Priority:** P1 (Quality)
**Phase:** 2
**Status:** in-progress
**Assigned:** qa-tester
**Estimated:** 6-8 hours (ongoing)
**Last updated:** 2026-04-20 (178 tests added, est. 58-62% coverage)

## Problem

CI threshold has been raised from 35% to 60% in `.github/workflows/ci.yml`, but actual coverage may not yet meet this target. Several critical paths lack test coverage:

- Video processing pipeline tasks (4 of 6 untested)
- Cross-tenant isolation scenarios
- Error edge cases in views

## Current Test State

| App | Has Tests | Estimated Coverage |
|-----|-----------|-------------------|
| courses | ✅ | Medium (views covered, tasks partially) |
| users | ✅ | Medium |
| tenants | ✅ | Medium |
| progress | ✅ | Low-Medium |
| notifications | ✅ | Low |
| discussions | ✅ | Has tests (698 lines) |
| media | ✅ | Has tests (512 lines) |
| webhooks | ✅ | Has tests (725 lines, HMAC/SSRF) |
| uploads | ✅ | Low |
| reports | ✅ | Low |
| reminders | ✅ | Low |

## Priority Test Areas

### 1. Video Processing Pipeline (High Impact)
```python
# backend/apps/courses/tasks.py — test each stage:
- test_validate_duration_accepts_valid
- test_validate_duration_rejects_long
- test_transcode_to_hls_success
- test_generate_thumbnail_success
- test_transcribe_video_success
- test_pipeline_failure_marks_error
```

### 2. Cross-Tenant Isolation Tests
```python
# Verify TenantManager filtering works:
- test_course_query_filters_by_tenant
- test_progress_query_filters_by_tenant
- test_notification_query_filters_by_tenant
- test_all_tenants_bypass_returns_all
```

### 3. Missing Edge Cases
- Soft-delete + restore flows
- Rate limiting responses (429)
- File upload validation (size, type, MIME)
- Quiz submission scoring

### 4. Setup: factory-boy
Consider adding `factory-boy` for consistent test data generation:
```python
# backend/apps/courses/factories.py
class CourseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Course
    tenant = factory.SubFactory(TenantFactory)
    title = factory.Faker('sentence')
    created_by = factory.SubFactory(UserFactory)
```

## Files to Modify/Create

- `backend/apps/courses/test_tasks.py` — Video pipeline tests
- `backend/apps/*/factories.py` — Test data factories (optional)
- `backend/apps/*/tests.py` — Expand existing tests
- `backend/conftest.py` — Shared fixtures

## Acceptance Criteria

- [x] Backend test discovery fixed — `tests_*.py` pattern added to `pyproject.toml` (was missing!)
- [x] `conftest.py` created with reusable fixtures (tenant, admin_user, teacher_user, api_client_for, course, module, content)
- [x] P0 security tests written: `apps/tenants/tests_security.py` (contextvars isolation, middleware lifecycle, cross-tenant 403, password no-double-hash, TenantManager isolation)
- [x] Cross-tenant E2E spec written: `e2e/tests/cross-tenant-isolation.spec.ts`
- [ ] Backend test coverage ≥ 60% (current: 43.7% per coverage.xml)
- [ ] CI passes with new threshold
- [x] Video pipeline stages tested: `tests_video_pipeline_extended.py` covers transcode_to_hls (5), generate_thumbnail (5), transcribe_video (6), finalize_video_asset (5)
- [x] Cross-tenant isolation verified in tests ← tests_security.py (24 tests)
- [x] Quiz/Teacher test robustness: added explicit `tenant=` to Assignment/Quiz/QuizQuestion/QuizSubmission/TeacherProgress in tests_quiz_api.py + tests_teacher_mvp.py
- [ ] No flaky tests

## Progress Notes (2026-03-25)

### Fixed: pytest discovery bug
`pyproject.toml` `python_files` pattern was missing `tests_*.py`, meaning these files
were NOT being discovered:
- `tests_video_pipeline.py`, `tests_tenant_isolation.py`, `tests_video_tenant_isolation.py`
- `tests_quiz_api.py`, `tests_teacher_mvp.py`, `tests_course_creation_flow.py`
- `tests_assignment_admin_api.py`, `tests_assignment_notifications.py`

**Fix:** Added `"tests_*.py"` to the pattern list.

### New files created
- `backend/conftest.py` — shared fixtures (tenant, users, clients, course hierarchy)
- `backend/apps/tenants/tests_security.py` — 5 test classes, 24 test methods covering P0 security fixes
- `e2e/tests/cross-tenant-isolation.spec.ts` — 8 E2E tests for cross-tenant API isolation

## Progress Notes (2026-03-26)

### Video pipeline tests (TASK-010 Phase 2)

Created `backend/apps/courses/tests_video_pipeline_extended.py`:
- **TranscodeToHlsTestCase** (5 tests): success sets hls_master_url + updates Content.file_url; skips pre-failed; marks FAILED on missing source, ffmpeg not found, CalledProcessError
- **GenerateThumbnailTestCase** (5 tests): success sets thumbnail_url; skips pre-failed; marks FAILED on missing source, ffmpeg not found, CalledProcessError (uses side_effect to create real thumb file)
- **TranscribeVideoTestCase** (6 tests): graceful skip if faster-whisper not installed; creates VideoTranscript; updates existing on re-run; non-fatal on transcription exception; skips pre-failed; skips missing source
- **FinalizeVideoAssetTestCase** (5 tests): READY with HLS; FAILED without HLS; skips already-failed; READY without thumbnail (warning logged); clears stale error_message

All tasks tested via `.run()` pattern (no Celery broker needed). All subprocess/storage I/O mocked.

### Test robustness fixes

Fixed `tests_quiz_api.py` and `tests_teacher_mvp.py` to pass explicit `tenant=self.tenant` when creating
Assignment, Quiz, QuizQuestion, QuizSubmission, TeacherProgress. Previously relied on `null=True`; now
robust against TenantManager filtering changes.

### Extended tests for low-coverage apps

Created (or in progress):
- `backend/apps/uploads/tests_extended.py` — auth (401), admin-only (403), oversized files, JPEG/WebP/DOCX/PPTX valid types, editor-image endpoint (full coverage of untested endpoint)
- `backend/apps/reports/tests_extended.py` — auth (401), missing params (400), status/search filters, assignment submission report with data, CSV export with feature flag
- `backend/apps/reminders/tests_extended.py` — auth (401), ASSIGNMENT_DUE type, send to all teachers, no recipients (400), history with campaigns, automation status with upcoming courses

## Progress Notes (2026-04-20)

### Coverage push: 178 new tests targeting lowest-coverage views

**Goal:** Close the 43.7% → 60% gap by targeting the highest-impact untested views.

**Files created (178 total tests):**
- `backend/apps/users/tests_admin_views.py` (30 tests) — teachers_list, detail, deleted, restore, bulk import, bulk action
- `backend/apps/courses/tests_teacher_course_views.py` (16 tests) — teacher_course_list, course_detail, video transcript
- `backend/apps/progress/tests_progress_views.py` (49 tests) — dashboard, calendar, search, progress start/update/complete, assignment list/submit, quiz detail/start/submit
- `backend/apps/tenants/tests_views_extended.py` (26 tests) — theme, me, config, stats, analytics, settings
- `backend/apps/tenants/tests_superadmin_views.py` (20 tests) — platform stats, tenant list/create, tenant detail, tenant usage
- `backend/apps/courses/tests_admin_course_views.py` (21 tests) — course list/create, course detail CRUD, module CRUD, content create
- `backend/apps/notifications/tests_services.py` (16 tests) — service functions with mocked WebSocket (0% → ~80%)

**Key coverage modules targeted:**
- `progress/teacher_views.py`: 21.7% → estimated ~65%
- `users/admin_views.py`: 26.1% → estimated ~75%
- `courses/views.py`: 30.0% → estimated ~60%
- `tenants/superadmin_views.py`: 31.1% → estimated ~60%
- `notifications/services.py`: 0.0% → estimated ~80%

**Estimated total coverage: ~58-62%** (conservative; requires `pytest --cov` run to confirm)

**Still low-coverage (needs future work):**
- `notifications/consumers.py` (0%) — needs channels test layer
- `courses/tasks.py` (12.4%) — Celery mocking needed
- `tenants/tasks.py` (0%), `webhooks/services.py` (0%), `webhooks/tasks.py` (0%)
- `users/sso_pipeline.py` (0%), `users/twofa_views.py` (26%)
- `courses/learning_path_views.py` (32%), `courses/video_views.py` (36%)
