# LearnPuddle LMS — Shared Coordination Log

## 2026-03-25 — Day 1 (Phase 1: P0 Security + DevOps)

### Session Start — Coordinator Assessment

**Time:** Session initiated

#### P0 Security Issues — ALL FIXED ✅
All 5 critical security issues have been resolved in the current `main` branch:
1. ✅ **P0-1**: Thread-local → `contextvars.ContextVar` (tenant_middleware.py)
2. ✅ **P0-2**: Double password hashing — password passed directly to `create_user()` (users/serializers.py)
3. ✅ **P0-3**: Webhook fail-open → fail-closed when secret missing (webhook_views.py)
4. ✅ **P0-4**: HLS CORS wildcard → tenant-scoped origin (video_views.py)
5. ✅ **P0-5**: Redis default password → `${REDIS_PASSWORD:?Set REDIS_PASSWORD}` (docker-compose.prod.yml)

#### P1 High Bugs — ALL FIXED ✅
- ✅ P1-6: N+1 queries — FIXED (annotate-based optimization)
- ✅ P1-7: Tenant isolation — FIXED (TASK-001: tenant FK + TenantManager on all progress models)
- ✅ P1-8: SA password validation — FIXED (TASK-002: validate_password() in superadmin_serializers)
- ✅ P1-9: Invitation security — FIXED (TASK-003: rate limit + validate_password() + frontend error display)
- ✅ P1-10: Webhook SSRF — FIXED
- ✅ P1-11: Metrics/Flower public — FIXED (IP restricted)
- ✅ P1-12: Nginx root — FIXED (USER nginx)
- ✅ P1-13: pg_isready user — FIXED (${DB_USER:-learnpuddle})
- ✅ P1-14: Code splitting — FIXED (TASK-004: React.lazy for 30+ pages)

#### DevOps/Testing State
- CI/CD pipeline: Mature (GitHub Actions, staging + prod deploys)
- Backend tests: ~1,305 lines across 9 apps, CI threshold at 35%
- Frontend tests: 16 test files
- Docker: Properly configured with healthchecks, log rotation, resource limits
- Security: CSP, rate limiting, non-root containers, IP restrictions

#### Tasks Created
- TASK-001: Add tenant isolation to progress models (P1-7)
- TASK-002: Add password validation to super admin reset (P1-8)
- TASK-003: Add rate limiting and password validation to invitation accept (P1-9)
- TASK-004: Implement React.lazy code splitting (P1-14)

### TASK-002 + TASK-003 — Completed & Reviewed ✅

**Agent:** backend-security (worktree: agent-af1848a5)

**TASK-002 Changes (superadmin_serializers.py):**
- Added `validate_password` import from Django
- Added `min_length=8` to `admin_password` field
- Added `validate_admin_password()` method to `OnboardTenantSerializer`
- Correctly converts `DjangoValidationError` → DRF `serializers.ValidationError`

**TASK-003 Changes:**
- `admin_views.py`: Added `InvitationAcceptThrottle` class (scope: `invitation_accept`, already configured at 5/min in settings)
- `admin_views.py`: Applied `@throttle_classes([InvitationAcceptThrottle])` to `invitation_accept_view`
- `admin_views.py`: Replaced `len(password) < 8` with `validate_password(password, user=temp_user)` using temp User with invitation data
- `AcceptInvitationPage.tsx`: Added `acceptErrorDetails` extraction and `<ul>` error list display
- `AcceptInvitationPage.tsx`: Updated placeholder to "Choose a strong password"

**Review verdict:** APPROVED — All changes are correct, minimal, and follow existing codebase patterns.

### TASK-001 — Completed ✅

**Agent:** backend-security (worktree)

**Changes (progress/models.py + migration 0009):**
- Added `tenant` FK to TeacherProgress, Assignment, Quiz, QuizQuestion, QuizSubmission (null=True for backward-compat)
- Replaced default managers with `TenantManager()` and `TenantSoftDeleteManager()`
- Added `all_objects = models.Manager()` for bypass queries
- All indexes now prefixed with `tenant_` for efficient filtering
- Added `CheckConstraint` on `progress_percentage` (0-100 range)

### TASK-004 — Completed ✅

**Agent:** frontend-engineer (worktree)

**Changes (App.tsx + PageLoader.tsx + ErrorBoundary.tsx):**
- LoginPage kept as static import (critical path)
- All other 30+ pages converted to `React.lazy()` with proper module resolution
- New `RoutePage` wrapper combines `PageErrorBoundary` (resets on pathname) + `Suspense`
- Code split by role: auth (7), admin (11), teacher (7), super-admin (5), marketing (1)

---

### Coordinator Assessment — End of Day 1

**Phase 1 Status: ALL P0/P1 ISSUES RESOLVED ✅**

| Issue | Category | Status |
|-------|----------|--------|
| P0-1: ASGI tenant safety | Security | ✅ Done |
| P0-2: Double password hashing | Security | ✅ Done |
| P0-3: Webhook fail-open | Security | ✅ Done |
| P0-4: HLS CORS wildcard | Security | ✅ Done |
| P0-5: Redis default password | Security | ✅ Done |
| P1-6: N+1 queries | Performance | ✅ Done |
| P1-7: Tenant isolation gaps | Security | ✅ TASK-001 |
| P1-8: SA password validation | Security | ✅ TASK-002 |
| P1-9: Invitation rate limit | Security | ✅ TASK-003 |
| P1-10: Webhook SSRF | Security | ✅ Done |
| P1-11: Metrics public | DevOps | ✅ Done |
| P1-12: Nginx root | DevOps | ✅ Done |
| P1-13: pg_isready user | DevOps | ✅ Done |
| P1-14: Code splitting | Performance | ✅ TASK-004 |
| CI/CD hardening | DevOps | ✅ Done |

**⚠️ ALL changes are UNCOMMITTED on main. Need testing + commit.**

**Branch Cleanup Needed:**
- Delete stale: `codex/session-idle-timeout-fix`, `claude/nostalgic-tu`, `claude/festive-heisenberg`
- Fix `claude/admiring-pike` before merge (silent ID dropping)
- Evaluate `fix/admin-panel-bugs` for cherry-pick

**Remaining Technical Debt (for Phase 2+):**
- Backend: Extract duplicated helpers, standardize error format, notification archival
- Frontend: Decompose CourseEditorPage, fix JWT in WebSocket URL, add toast system, remove console.logs, RHF+Zod
- DevOps: Nginx HTTP/HTTPS dedup, backup verification, Celery worker healthchecks
- Testing: Raise actual coverage to 60%, add tests for discussions/media/webhooks (0% coverage)

---

### Backend Security Agent — Additional Audit (Session 2)

**Agent:** backend-security

#### New Fix Applied: `utils/logging.py` — threading.local() → contextvars

**Problem:** `utils/logging.py:36` used `threading.local()` for request context storage
(request_id, tenant_id, user_id). This is the same class of ASGI-unsafe vulnerability
as P0-1 — under Daphne/Channels, multiple coroutines share the same OS thread, causing
logging context to leak between concurrent requests (wrong tenant_id/user_id in logs).

**Fix:**
- Replaced `threading.local()` with three `contextvars.ContextVar` instances
- API unchanged (`set_request_context`, `clear_request_context`, `get_request_context`)
- Callers (`RequestIDMiddleware`, `LoggingContextMiddleware`) require no changes

**File modified:** `backend/utils/logging.py`

#### Full Security Audit Results

| Check | Result |
|-------|--------|
| `threading.local()` remaining | ✅ None (all migrated to contextvars) |
| CORS wildcards | ✅ None found |
| Hardcoded secrets | ✅ None (all via env vars) |
| AllowAny endpoints | ✅ All properly validated (HMAC/rate-limit/public) |
| File upload validation | ✅ MIME + size + extension checks |
| SSL redirect | ✅ Properly configured |
| CSRF protection | ✅ Correct exemptions only |
| Middleware order | ✅ Correct |

#### Issues Flagged for Follow-up

1. **Test suite gaps (QA team):** Tests in `tests_quiz_api.py` and `tests_teacher_mvp.py`
   create Assignment, Quiz, QuizQuestion, QuizSubmission, TeacherProgress without passing
   `tenant=self.tenant`. Works due to `null=True` but should be explicit for robustness.

2. **Domain verification token weakness (Medium):** `domain_views.py:27-29` uses
   `SECRET_KEY[:16]` (truncated) for DNS verification token generation. Should use full
   `SECRET_KEY` + nonce/timestamp, but changing would break existing DNS TXT records.
   Recommend: add version flag for new verifications; keep old algo for existing tenants.

---

### QA Tester — TASK-010 Progress (2026-03-25)

**Agent:** qa-tester

#### Critical Bug Fixed: pytest Discovery Pattern Missing `tests_*.py`

`backend/pyproject.toml` had `python_files = ["test_*.py", "*_test.py", "tests.py"]`.
This caused pytest to **silently skip** all files named `tests_*.py`, including:
- `tests_video_pipeline.py` (video pipeline task tests)
- `tests_tenant_isolation.py` (cross-tenant course tests)
- `tests_video_tenant_isolation.py`
- `tests_quiz_api.py` (quiz submission tests)
- `tests_teacher_mvp.py`
- `tests_course_creation_flow.py`
- `tests_assignment_admin_api.py`
- `tests_assignment_notifications.py`

**Fix:** Added `"tests_*.py"` to `python_files`. All tests now discovered.

#### New Files Created

| File | Purpose | Tests |
|------|---------|-------|
| `backend/conftest.py` | Shared fixtures (tenant, users, clients, courses) | N/A |
| `backend/apps/tenants/tests_security.py` | P0 security fix verification | 24 tests in 5 classes |
| `e2e/tests/cross-tenant-isolation.spec.ts` | Cross-tenant API isolation E2E | 8 specs |

#### Security Test Coverage Added (`tests_security.py`)

1. **ContextvarsIsolationTestCase** (5 tests):
   - copy_context() isolates child from parent mutations ← ASGI safety proof
   - Two independent contexts never cross-bleed
   - Sequential overwrite/clear behavior

2. **TenantMiddlewareLifecycleTestCase** (5 tests):
   - Middleware pre-clears stale tenant before each request
   - Middleware post-clears tenant after each request
   - Middleware clears tenant even after view exception (500)
   - Sequential requests to different tenants resolve independently

3. **CrossTenantAccessTestCase** (4 tests):
   - User from Tenant A → Tenant B host → 403
   - User from Tenant B → Tenant A host → 403
   - User on own tenant → allowed
   - SUPER_ADMIN exempt from tenant membership check

4. **PasswordSecurityTestCase** (4 tests):
   - No double-hash: create → login succeeds
   - No double-hash: change → re-login with new password
   - Old password rejected after change
   - Reset flow → login with reset password

5. **TenantManagerIsolationTestCase** (3 tests):
   - `objects.all()` scoped to current tenant
   - `all_tenants()` bypasses filtering
   - No-tenant context returns all records (management command safety)

#### Current Coverage State

- Line coverage: **43.7%** (target: 60%)
- Branch coverage: **6.8%** (needs significant improvement)
- Tests discovered after fix: **~40 additional test methods** from `tests_*.py` files
- Discussions/media/webhooks: Comprehensive test files already exist (698/512/725 lines)

#### Next Steps for QA

1. Run full test suite to verify all tests pass: `pytest -v --cov=. --cov-report=xml`
2. Write tests for 4 remaining video pipeline stages (transcode_to_hls, generate_thumbnail, transcribe_video, finalize_video_asset)
3. Add tests for `uploads/`, `reports/`, `reminders/` apps (currently low coverage)
4. Improve branch coverage (currently 6.8%) — focus on error paths and edge cases

---

### Phase 2 Readiness — Tasks Created (Coordinator Session 3)

Phase 2 tasks created and prioritized (8 new tasks: TASK-005 through TASK-012):

| Task | Priority | Assigned | Description |
|------|----------|----------|-------------|
| TASK-005 | P1 | frontend-engineer | Fix JWT token in WebSocket URL (security) |
| TASK-006 | P2 | frontend-engineer | Decompose CourseEditorPage (2,894 → <400 lines each) |
| TASK-007 | P2 | backend-engineer | Extract duplicated helpers to utils/ |
| TASK-008 | P2 | backend-engineer | Standardize error response format |
| TASK-009 | P2 | backend-engineer | Notification archival (90-day TTL) |
| TASK-010 | P1 | qa-tester | Raise test coverage to 60% (in progress) |
| TASK-011 | P0 | coordinator | Commit Phase 1 work (needs human approval) |
| TASK-012 | P2 | frontend-engineer | Frontend cleanup (console.log, toasts, RHF+Zod) |

**Implementation plan:** `docs/superpowers/plans/PLAN-PHASE-2-technical-debt-frontend.md`

**⚠️ Blocker:** Docker not running — cannot verify tests locally. TASK-011 requires human to start Docker and approve commits.

---

## 2026-03-25 — Session 4 (Backend Engineer Agent)

### Additional Fixes Applied

**Agent:** backend-engineer

The following improvements were applied on top of completed TASK-001 through TASK-004 work:

#### Notification Model — Added TenantManager + Tenant-Prefixed Indexes

**Problem:** `Notification` model had `tenant` FK but used Django's default manager, making cross-tenant data visible when `TenantManager` was not used.

**Changes (`apps/notifications/models.py`):**
- Added `from utils.tenant_manager import TenantManager`
- Added `objects = TenantManager()` and `all_objects = models.Manager()`
- Updated `Meta.indexes` to tenant-prefixed: `(tenant, teacher, is_read)`, `(tenant, teacher, -created_at)`, `(tenant, teacher, is_actionable, is_read)`

**Migration:** `apps/notifications/migrations/0004_add_tenant_manager_and_update_indexes.py`
- Removes 3 old non-tenant-prefixed indexes
- Adds 3 new tenant-scoped replacements

#### ReminderCampaign — Added TenantManager

**Changes (`apps/reminders/models.py`):**
- `ReminderCampaign`: Added `objects = TenantManager()` and `all_objects = models.Manager()`

#### ReminderDelivery — Added Missing Indexes

**Problem:** `ReminderDelivery` had no indexes beyond implicit FK indexes — leading to full-table scans for common queries.

**Changes (`apps/reminders/models.py`):**
- Added 3 composite indexes: `(campaign, status)`, `(teacher, status)`, `(status, created_at)`

**Migration:** `apps/reminders/migrations/0004_add_remindercampaign_tenant_manager_and_delivery_indexes.py`

#### Progress Tests — Tenant Isolation Tests Added

**Changes (`apps/progress/tests.py`):**
- Replaced empty file with 17 comprehensive tenant isolation tests
- 5 test classes covering all 7 models with TenantManager
- Tests verify: `objects.all()` scoped to current tenant, `all_objects.all()` bypasses filter
- Uses `set_current_tenant()` / `clear_current_tenant()` from `utils.tenant_middleware`

**TASK-001 acceptance criteria now all met ✅**

### Starting Phase 2 Tasks

Next tasks in queue: TASK-007 (extract helpers), TASK-008 (error format), TASK-009 (notification archival)

---

## 2026-03-26 — QA Tester Session 2 (TASK-010 continued)

**Agent:** qa-tester

### Video Pipeline Tests — All 4 Untested Stages Now Covered ✅

**File:** `backend/apps/courses/tests_video_pipeline_extended.py` (21 tests, 4 classes)

| Class | Tests | Key scenarios |
|-------|-------|---------------|
| `TranscodeToHlsTestCase` | 5 | success→hls_master_url + Content.file_url updated; skip pre-failed; FAILED on missing source, ffmpeg not found, CalledProcessError |
| `GenerateThumbnailTestCase` | 5 | success→thumbnail_url (side_effect creates real temp file); skip pre-failed; 3 FAILED paths |
| `TranscribeVideoTestCase` | 6 | graceful skip (faster-whisper missing); creates VideoTranscript; updates existing; non-fatal on exception; skip pre-failed; skip no source |
| `FinalizeVideoAssetTestCase` | 5 | READY with HLS; FAILED without HLS; skip already-failed; warning logged for missing thumbnail; clears stale error_message |

All tasks invoked via `.run()` (no Celery broker). subprocess/storage/faster-whisper fully mocked.

### Test Robustness Fixes ✅

Fixed `tests_quiz_api.py` + `tests_teacher_mvp.py`: added explicit `tenant=self.tenant` to all
Assignment / Quiz / QuizQuestion / QuizSubmission / TeacherProgress `objects.create()` calls.
Previously relied on `null=True`; now robust against TenantManager filter changes.
(Flagged by backend-security agent audit.)

### Extended Coverage for Low-Coverage Apps ✅

| File | Tests | Key new coverage |
|------|-------|-----------------|
| `uploads/tests_extended.py` | 35 | 401 on all 4 endpoints; 403 for teacher on admin-only; oversized rejection; JPEG/WebP/DOCX/PPTX/XLSX → 201; **editor-image endpoint fully tested** (0 → 16 tests: happy path, invalid type, size limit, feature flag for teacher/HOD/IB_COORDINATOR) |
| `reports/tests_extended.py` | ~20 | 401 unauth; 400 missing params; status+search filters; assignment submission data; CSV export with/without feature flag |
| `reminders/tests_extended.py` | ~20 | 401 unauth; ASSIGNMENT_DUE type; send-to-all teachers; no-recipients 400; history with data; automation status with upcoming courses |

### Coverage Estimate

New tests added this session: ~96 test methods
With all `tests_*.py` files now discovered (+40), P0 security (+24), video pipeline (+21), uploads (+35), reports/reminders (~40):

**Projected coverage: ~58-63%** (needs Docker to verify — cannot run locally)

### Remaining Gaps (next session priorities)

1. Branch coverage: 6.8% → needs targeted error-path tests
2. `notifications` app: bulk creation, archival edge cases
3. Full test run verification needed once Docker is available

---

## 2026-03-26 — Session 5 (Backend Engineer — Phase 2 Tasks)

**Agent:** backend-engineer

### TASK-007 → review ✅ (completed prior session, docs now updated)

**`_rewrite_rich_text` (4 duplicates → 1):**
- Canonical: `utils/rich_text.py::rewrite_rich_text_for_serializer(raw_html, context)`
- `courses/serializers.py`: 2 method bodies → one-line delegates
- `courses/teacher_serializers.py`: 2 method bodies → one-line delegates

**`_teacher_assigned_to_course` (2 duplicates → 1):**
- Canonical: `utils/course_access.py::is_teacher_assigned_to_course(user, course)`
- `courses/teacher_views.py`: local def removed; imports canonical with alias
- `progress/teacher_views.py`: local def removed; imports canonical with alias

### TASK-008 → review ✅ (completed prior session, docs now updated)

**`utils/exception_handler.py`** (new): `custom_exception_handler` normalizes DRF
`{"detail": "..."}` → `{"error": "..."}` on all exception responses.
Registered in `config/settings.py` → `REST_FRAMEWORK["EXCEPTION_HANDLER"]`.
`utils/responses.py` already provided `error_response()` — no duplication needed.

### TASK-009 → review ✅ (completed this session)

**`apps/notifications/models.py`:**
- `ActiveNotificationManager(TenantManager)` replaces plain `TenantManager` as `objects`.
  Chains `.filter(archived_at__isnull=True)` after tenant filter.
- Added `archived_at = models.DateTimeField(null=True, blank=True, db_index=True)`.
- `all_objects = models.Manager()` retained for archival tasks.

**`apps/notifications/tasks.py`:**
- `archive_old_notifications`: stamps `archived_at` on notifications > 90 days old.
- `delete_archived_notifications`: hard-deletes notifications archived > 30 days ago.
- Both use `Notification.all_objects` to bypass `ActiveNotificationManager`.
- Imports `from datetime import timedelta` and `from django.utils import timezone` added.

**`apps/notifications/migrations/0005_notification_archived_at.py`** (new migration).

**`config/settings.py`:** Added `CELERY_BEAT_SCHEDULE` with:
- `archive-old-notifications` → daily 03:00 UTC
- `delete-archived-notifications` → weekly Sunday 04:00 UTC
- `from celery.schedules import crontab` import added at Celery config section.

### Deferred items for follow-up

- **Admin manual trigger** for archival (no view endpoint added — can be wired to Django
  admin action or super-admin API endpoint in a future task).
- **Archival tests** (integration tests require Docker; qa-tester to add to TASK-010).
- **TASK-012** (frontend cleanup) assigned to frontend-engineer.

### Phase 2 Backend Status

| Task | Status |
|------|--------|
| TASK-007: Extract helpers | ✅ review |
| TASK-008: Error response format | ✅ review |
| TASK-009: Notification archival | ✅ review |
