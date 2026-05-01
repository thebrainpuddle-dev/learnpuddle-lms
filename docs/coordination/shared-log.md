# LearnPuddle LMS — Shared Coordination Log

## 2026-04-30 — Coordinator Session

**Agent:** coordinator (Opus)

### TASK-013 XP-on-timeout follow-up — CLOSED

The only remaining open follow-up on
`docs/coordination/TASK-013-multiple-quiz-attempts-timed-quizzes.md`
(reviewer's note: `on_quiz_submission` was awarding XP on force-closed
timed quiz attempts) is now closed.

- **Guard already existed** in HEAD at
  `backend/apps/progress/gamification_signals.py:147-167` from sprint-2
  batch work (`7e6439b`). What was missing: structured log + 2 policy-
  clarifying tests.
- **Added** structured `logger.info(..., extra={"metric":
  "quiz_xp_skipped_on_timeout", "attempt_id": ..., "quiz_id": ...,
  "teacher_id": ..., "tenant_id": ..., "attempt_number": ...})` to make
  the skip path discoverable in observability.
- **Tests** in `backend/apps/progress/tests_gamification_signals.py`
  `QuizSubmissionSignalTest`:
  - existing — `test_abandoned_timed_attempt_is_skipped` (timed-out + 0
    ⇒ no XP) and `test_time_expired_with_nonzero_score_still_awards`.
  - NEW — `test_earned_zero_score_not_timed_out_still_awards` (locks in
    policy that earned zeros still earn XP — only force-closes are
    skipped).
  - NEW — `test_abandoned_timed_attempt_emits_structured_log`.
- **Docs** — TASK-013 follow-up bullet struck and a `## Follow-up
  Closeouts (2026-04-30)` section added with file:line + test names.
- **Daily** — `~/ObsidianVault/learnpuddle-lms/daily/2026-04-30.md`.

### Bundle status (unchanged from 2026-04-29)

Wave 5–9 MAIC bundle reported "commit-ready" by yesterday's reviewer
pass. Outstanding gates (all user-blocked):

1. F6 cert (CG-P1-13 + F6-v2) — browser DevTools task.
2. CG-P1-15 production fix — research-only writeup awaiting user
   Option A/B/C decision.
3. Wave 5–9 commit bundle — user controls all git writes.

### TASK-013 verification — 9/9 GREEN

`pytest apps/progress/tests_gamification_signals.py -k "QuizSubmission or
quiz_submission or timed or abandoned or earned_zero or structured_log"`
came back **9 passed, 18 deselected** in 7:13 (host venv). All four
targeted cases pass: `test_abandoned_timed_attempt_is_skipped`,
`test_time_expired_with_nonzero_score_still_awards`,
`test_earned_zero_score_not_timed_out_still_awards` (NEW),
`test_abandoned_timed_attempt_emits_structured_log` (NEW). One
harmless teardown warning (`database "test_lms_db" does not exist` — known
pytest-django host-venv artifact, not a real failure).

### Wave 5–9 bundle verification — 334/4 (4 known-RED, 0 new)

Focused pytest `tests/courses/ + apps/courses/tests_maic_image_fill_meta.py
+ apps/courses/tests_maic_prompts.py` came back **334 passed / 4 failed in
28:34**. The 4 failures are exactly the 4 known-RED CG-P1-15 cases in
`tests/courses/test_image_fill_dedup.py` (gated on user Option A/B/C):

- `test_teacher_scene_content_does_not_inline_fetch_images`
- `test_student_scene_content_does_not_inline_fetch_images`
- `test_service_fill_image_urls_does_not_call_fetch_scene_image`
- `test_defer_image_fill_does_not_leak_across_tenants`

All 4 fail with `mock_fetch.call_count == 1, expected 0` — service-layer
`_fill_image_urls` still inlines `fetch_scene_image` per
`maic_generation_service.py:1838,1845`. Pre-existing contract drift, not
a regression from today's or yesterday's work.

**Verdict: bundle commit-ready.** Zero new reds beyond the documented
CG-P1-15 set; the wave 5–9 + 2026-04-29 R-fixes + today's TASK-013
closeout all hold.

### TASK-010 (60% coverage gate)

Coverage % not measured this session — the focused suite alone ran
28+ min and a full `--cov` pass would have blown the time budget.
TASK-010 status remains `in-progress`; a Docker-based
`pytest --cov --cov-fail-under=60` is the canonical measurement that
matches CI. Recommend running that under
`docker compose exec web pytest --cov` rather than the host venv.

### Subagent dispatch caveat

Specialist subagents (`backend-security`, `backend-engineer`, etc.) are
not registered in this Claude harness — only `general-purpose`, `Explore`,
`Plan`. Two `general-purpose` dispatches paused at ~12 min waiting on
pytest and could not be resumed (`SendMessage` not exposed). One of them
landed its file edits before pausing — that's the TASK-013 work above.
The verification dispatch left no changes and was re-run via direct Bash.

### Hard rules respected

Zero `git commit/add/push` by coordinator or any dispatched subagent.

---

## 2026-04-28 — DevOps Agent Session

**Agent:** devops (Sonnet)

### Audit Findings — Post MAIC CG-P1 Sprint

Performed a comprehensive read-through of all DevOps-owned files and reviewed
recent commits (CG-P1-2 through CG-P1-13) to check for infra regressions or
new requirements. All Phase 1/2/3 tasks remain complete.

### Infrastructure Health Check

| Area | Status | Evidence |
|------|--------|---------|
| Docker Compose (prod) | ✅ OK | All services: log rotation, healthchecks, resource limits |
| Docker Compose (staging) | ✅ OK | Mirrors prod with relaxed limits |
| Docker Compose (dev) | ✅ OK | Minimal infra services, correct learnpuddle defaults |
| nginx/nginx.conf | ✅ OK | Cloudflare origin cert config, shared_locations.conf |
| nginx/production.conf | ✅ OK | Local SSL termination, correct 10M/512M body limits |
| nginx/nginx.staging.conf | ✅ OK | Security headers aligned to production (fixed 2026-04-25) |
| nginx/Dockerfile | ✅ OK | USER nginx, multi-stage frontend bake, chown complete |
| backend/Dockerfile | ✅ OK | Non-root appuser, multi-stage deps layer |
| frontend/Dockerfile | ✅ OK | USER nginx, healthcheck via wget |
| CI/CD (ci.yml) | ✅ OK | E2E blocking, 60% coverage threshold, rollback deploy |
| CI/CD (e2e.yml) | ✅ OK | Full local stack E2E on PR |
| Celery queues | ✅ OK | default, video, notifications (worker), tts (worker-tts) |
| Backup scripts | ✅ OK | Integrity verification with gunzip -t + header check |

### New Backend Development — Infra Impact Assessment

Reviewed uncommitted backend changes (MAIC CG-P1-* sprint + SCIM + billing):

**`backend/config/celery.py`** (backend agent's work):
- Consolidated all Celery beat tasks into single `app.conf.beat_schedule` source
  (fixes "silent drop" bug where settings.py CELERY_BEAT_SCHEDULE was ignored)
- Added `fill_classroom_images` → `default` queue routing (previously unrouted,
  accumulated on unread "celery" queue causing images_pending to stick True)
- Added `semantic_search.*` → `default` queue routing (same root cause)
- **Infra impact**: None — both route to `default`, already drained by `worker` service
  (`-Q default,video,notifications`)

**New app modules** (SCIM2, billing, integrations_chat, integrations_calendar):
- All are Django apps served by existing `web` service via Django URL routing
- **Infra impact**: None — no new Docker services needed

**`backend/requirements.txt`**:
- Added `urllib3>=2.0,<3` floor-pin for SSRF guard (backend security fix)
- **Infra impact**: None — Docker image rebuild picks up on next deploy

### Working Tree Status

| File | Status | Action needed |
|------|--------|--------------|
| `scripts/restore-db.sh` | Has uncommitted fix (postgres→learnpuddle) | Commit when merging current branch |
| `backend/config/celery.py` | Backend agent's beat schedule consolidation | Commit (backend agent owns) |
| `backend/requirements.txt` | urllib3 pin | Commit (backend agent owns) |

### Maintenance Item (non-urgent)

`nginx/nginx.conf` Cloudflare IP ranges (`set_real_ip_from`) should be
periodically verified against https://cloudflare.com/ips-v4. Current list
matches early-2024 snapshot. Cloudflare rarely changes these but an annual
refresh is good practice. Not a blocking issue.

### Outstanding Items (unchanged from prior session)

1. **TASK-010** (`in-progress`, qa-tester): Actual pytest run needed to confirm
   ≥ 60% threshold. Estimated 58–62%; CI will gate any deploy that falls short.
2. **CSP `unsafe-inline`/`unsafe-eval`** (deferred): Present in `production.conf`
   and `nginx.staging.conf`; requires frontend bundle audit before removal.
3. **Uncommitted worktrees**: TASK-005/006/007/008/009/012 and current MAIC work
   need human merge/commit.

---

## 2026-04-25 — DevOps Agent Session

**Agent:** devops (Sonnet)

### Audit Findings

Performed a read-through of all DevOps-owned files to confirm no regressions
and identify any remaining gaps since the 2026-04-20 audit. All Phase 1/2/3
tasks from the master strategy remain complete (no regressions found).

### Gap Found and Fixed: nginx.staging.conf Security Headers

**Cross-comparison of security headers** across all three nginx configs revealed
two inconsistencies between `nginx.staging.conf` and `production.conf` /
`shared_locations.conf`:

| Header | staging (before) | production | shared_locations |
|--------|-----------------|------------|-----------------|
| X-Frame-Options | **DENY** ❌ | SAMEORIGIN | SAMEORIGIN |
| Permissions-Policy | **absent** ❌ | present | present |
| Strict-Transport-Security | absent (OK) | present | absent (HTTP) |

**`DENY` vs `SAMEORIGIN` impact:** `DENY` blocks all iframe embedding including
from the same origin, which would cause QA false failures for any embedded
content (iframes, widget tests) that work correctly in production. The production
value is `SAMEORIGIN`, so staging must match.

**Missing `Permissions-Policy` impact:** Browser camera/microphone/geolocation
permission requests would not be blocked in staging even though they are in
production. This could mask policy-related bugs during QA.

### Changes Made This Session

**`nginx/nginx.staging.conf`** (security headers section):
- Changed `add_header X-Frame-Options DENY` → `SAMEORIGIN` (matches production.conf L41)
- Added `add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=(), magnetometer=(), gyroscope=(), accelerometer=()" always;` (matches production.conf L46)
- Added explanatory comment above X-Frame-Options explaining the SAMEORIGIN rationale

### Verification

Ran `grep -n "add_header" nginx.staging.conf` — confirmed:
- Line 38: `X-Frame-Options SAMEORIGIN always;` ✅
- Line 41: `Permissions-Policy "camera=()..." always;` ✅
- All other header directives unchanged ✅
- File structure intact (gzip block, location blocks unmodified) ✅

`Strict-Transport-Security` intentionally absent from staging (staging runs HTTP
only; HSTS on an HTTP server would be an error and would be ignored anyway).

### Outstanding Items (no change from prior session)

1. **TASK-010** (`in-progress`, qa-tester): Actual pytest coverage run needed
   to confirm ≥ 60% threshold passes in CI.
2. **CSP `unsafe-inline`/`unsafe-eval`** (deferred): Present in `production.conf`
   and `nginx.staging.conf`; requires frontend bundle audit before removal.
3. **Uncommitted worktree changes**: Multiple TASK-005/006/007/008/009/012
   worktrees still need human merge/commit.

---

## 2026-04-20 — DevOps Agent Audit Session

**Agent:** devops (Sonnet)

### Full Infrastructure Audit Findings

Performed a complete read-through of all DevOps-owned files to confirm status of
Phase 1/2/3 tasks from the master strategy. All previously identified DevOps
technical debt has been resolved:

| Task | Status | Evidence |
|------|--------|---------|
| pg_isready healthcheck user `learnpuddle` | ✅ done | All 3 compose files use `${DB_USER:-learnpuddle}` |
| Redis password enforced (`:?` syntax) | ✅ done | Both prod + staging use `${REDIS_PASSWORD:?…}` |
| Metrics/Flower IP-restricted in nginx | ✅ done | All 3 nginx configs have `allow`/`deny all` |
| `USER nginx` in nginx Dockerfile | ✅ done | Line 43 of `nginx/Dockerfile` |
| Docker log rotation | ✅ done | `x-common` anchor in prod; `x-logging` in staging |
| E2E tests blocking in CI | ✅ done | `e2e-test` job gates `docker-build` and `deploy` |
| Coverage threshold at 60% | ✅ done | `COV_FAIL_UNDER: "60"` in `ci.yml` |
| Rollback strategy in CI/CD | ✅ done | Both prod + staging deploy jobs use PREV_SHA + auto-rollback |
| Celery worker healthchecks | ✅ done | Both prod + staging have `celery inspect ping` healthcheck |
| nginx HTTP/HTTPS duplication eliminated | ✅ done | `shared_locations.conf` included by both server blocks |
| `client_max_body_size` 10M global / 512M video | ✅ done | `shared_locations.conf` line 34, video override line 140 |
| Backup integrity verification | ✅ done | `scripts/backup-db.sh` uses `gunzip -t` + header check |
| Notification archival 90-day TTL | ✅ done (TASK-009) | Celery beat tasks + `ActiveNotificationManager` |

### Changes Made This Session

**`nginx/production.conf`** — security header hardening:
- Removed deprecated `add_header X-XSS-Protection "1; mode=block"` (can introduce
  vulnerabilities in older browsers; CSP provides equivalent protection)
- Strengthened `Permissions-Policy`: changed `microphone=(self)` → `microphone=()` to
  block microphone access (matches the stricter `shared_locations.conf` policy)
- Added `Cross-Origin-Opener-Policy: same-origin` (prevents cross-origin window access)
- Added `Cross-Origin-Resource-Policy: same-origin` (prevents cross-origin resource embedding)

**`nginx/nginx.staging.conf`** — security header hardening:
- Added `Cross-Origin-Opener-Policy: same-origin`
- Added `Cross-Origin-Resource-Policy: same-origin`

Both changes align `production.conf` and `nginx.staging.conf` with the security posture
already present in `nginx/includes/shared_locations.conf` (used by the Cloudflare-fronted
`nginx.conf`). All changes verified with `grep` output — no `add_header X-XSS-Protection`
directive present; COOP/CORP headers confirmed at expected lines.

### Outstanding Follow-ups (carried from prior session)

1. **TASK-010** (`in-progress`): Run `docker compose exec web pytest --cov=apps -q` to
   confirm actual coverage ≥ 60%. Estimated 58–62% but unverified in CI without a running
   container. Still assigned to qa-tester.
2. **Uncommitted work**: Multiple TASK-005/006/007/008/009/012 worktrees have uncommitted
   changes. A human or a commit-enabled agent must merge/commit before those tasks are
   truly shipped.
3. **CSP review** (deferred): `production.conf` CSP still has `unsafe-inline` and
   `unsafe-eval` in `script-src` while `shared_locations.conf` does not. Tightening this
   would require verifying no inline scripts remain in the frontend bundle. Deferred to a
   dedicated frontend security pass.

---

## 2026-04-20 — Coordinator Session Summary

**Dispatcher:** coordinator (Sonnet) — parallel fan-out across 3 rounds

### Intake
Confirmed status via task-file status lines: TASK-001/002/003/004/013–020 already `done`. Open queue at session start:
- `todo`: TASK-005, TASK-006, TASK-012 (TASK-011 skipped — git commits outside my mandate)
- `review`: TASK-007, TASK-008, TASK-009
- `in-progress`: TASK-010

### Round 1 — 5 subagents in parallel
| Agent | Task | Result |
|-------|------|--------|
| reviewer (opus) | TASK-007/008/009 | 007 APPROVE → done · 008 REQUEST_CHANGES (two incompatible error shapes) · 009 APPROVE → done |
| backend-security (opus, worktree) | TASK-005 | WebSocket subprotocol pattern; hard-cut query-string token; 6 new tests in `tests_websocket_auth.py` → review |
| frontend-engineer (sonnet, worktree) | TASK-006 | CourseEditor decomposed from 2,894 lines into 23 files; all ≤ 399 lines; `tsc --noEmit` clean → review |
| frontend-engineer (sonnet, worktree) | TASK-012 | sonner added; `useToast` wrapper; 3 `window.confirm` → `ConfirmDialog` migrations; LoginPage already on RHF+Zod → review |
| qa-tester (sonnet, worktree) | TASK-010 | +178 backend tests across 7 files targeting lowest-coverage views (estimated 58–62%, unverified — no Docker/DB in worktree) |

### Round 2 — 2 subagents in parallel
| Agent | Task | Result |
|-------|------|--------|
| reviewer (opus) | TASK-005/006/012 | All three APPROVE → done |
| backend-engineer (sonnet, worktree) | TASK-008 rework | Unified shape `{"error": str, "details": [{field, message}], "code?": str}` in both `exception_handler.py` and `responses.py`; 41 new unit tests; FE helpers updated → review |

### Round 3 — 1 subagent
| Agent | Task | Result |
|-------|------|--------|
| reviewer (opus) | TASK-008 rework | APPROVE → done |

### End-of-session task ledger
- **done (this session):** TASK-005, TASK-006, TASK-007, TASK-008, TASK-009, TASK-012
- **in-progress:** TASK-010 (pytest run needed to confirm ≥ 60%; estimated 58–62%)
- **deferred/out-of-scope:** TASK-011 (branch cleanup — requires `git commit/push`, outside coordinator mandate); TASK-022 (documentation-only backlog item)

### Outstanding follow-ups for next session
1. **Run** `docker compose exec web pytest --cov=apps -q` to pin down TASK-010's actual coverage and either close it out or file targeted gap-fills (notifications/consumers, courses/tasks, webhooks/services, users/sso_pipeline and twofa_views still at 0–26 %).
2. **Commit decision needed** — every completed task in this session has uncommitted work either on `main` or inside `.claude/worktrees/agent-*` worktrees. A human (or an agent with commit rights) must merge/commit; reviewer flagged that new test files are untracked (e.g., `backend/apps/notifications/tests_websocket_auth.py`).
3. **Worktree metadata hygiene** — reviewer noted that the `agent-*` paths recorded in prior log entries were stale at review time. Future dispatches should record the exact `worktreePath` returned in the Agent tool result so reviewers find the code first try.
4. **FE error-shape legacy fallback** — `extractErrorMessage` still reads `detail`/`message` for back-compat. Once all producers are confirmed on the new shape (TASK-008), the fallback can be dropped.

### Rules I held to
- No `git add`/`commit`/`push` performed by coordinator or any dispatched subagent.
- No user-facing questions; entire session fully autonomous.
- Every subagent was briefed to read its `.claude/agents/{role}.md` file and mirror these rules.

---

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

---

## 2026-04-18 — Backend Security Agent — Session (Stripe Billing Hardening)

**Agent:** backend-security
**Status:** uncommitted changes, ready for review

### Verified: All prior P0/P1 fixes still in place
- `utils/tenant_middleware.py` — `contextvars.ContextVar` (ASGI-safe) ✅
- `apps/users/serializers.py::RegisterTeacherSerializer` — single-pass `create_user(password=…)` ✅
- `apps/webhooks/models.py` — webhook secret auto-generated via `secrets.token_hex(32)` ✅
- `config/settings.py` CORS — tenant-scoped regex, no wildcard ✅
- `docker-compose.prod.yml` — Redis uses `${REDIS_PASSWORD:?…}` fail-closed ✅

### New Issues Found & Fixed This Session

#### P1: Open redirect via Stripe Checkout / Customer Portal
**Files:** `backend/apps/billing/views.py`

**Problem:** `create_checkout` accepted arbitrary `success_url` / `cancel_url` and
`create_portal` accepted arbitrary `return_url` from the authenticated admin.
An attacker with SCHOOL_ADMIN access could generate a legitimate Stripe URL whose
post-checkout bounce landed on an attacker-controlled phishing domain, then share
that Stripe URL with another admin. Stripe's URL serves as the trust-transfer
medium for the redirect.

**Fix:**
- New helper `_is_tenant_redirect_url_allowed(url, tenant)` validates scheme
  (https in prod, http allowed in DEBUG) and host against:
  `{tenant.subdomain}.{PLATFORM_DOMAIN}` and `tenant.custom_domain` (if verified).
  Localhost variants allowed only in DEBUG.
- `create_checkout` now rejects non-tenant `success_url` / `cancel_url` with 400.
- `create_portal` now rejects non-tenant `return_url` with 400.

#### P1: Stripe webhook — missing rate limit on signature verification
**Files:** `backend/apps/billing/webhook_views.py`, `backend/config/settings.py`

**Problem:** Public webhook endpoint (`AllowAny` + `csrf_exempt`) had no throttle.
Invalid-signature spam could burn CPU on HMAC verification and flood logs.
Signature verification already fails closed when `STRIPE_WEBHOOK_SECRET` is empty
(verified in `stripe_service.construct_webhook_event`). This adds defense-in-depth.

**Fix:**
- Added `stripe_webhook: 120/minute` throttle scope in `DEFAULT_THROTTLE_RATES`.
- New `StripeWebhookThrottle(ScopedRateThrottle)` class applied via
  `@throttle_classes([StripeWebhookThrottle])` on `stripe_webhook` view.
- Legitimate Stripe traffic easily fits under 120/min/IP; attackers are bounded.

### Files modified (no commits made; awaiting human review)
- `backend/apps/billing/views.py`
- `backend/apps/billing/webhook_views.py`
- `backend/config/settings.py`

### Notes
- Follow-up for QA: add tests asserting 400 on off-domain redirect URLs and 429
  after 120 invalid-sig webhook requests.
- Follow-up for coordinator: update `CheckoutSessionSerializer` docstring or add a
  serializer-level validator if we want the error surfaced as field errors.

---

## 2026-04-18 — Backend Engineer — Phase 3 Session (TASK-013)

**Agent:** backend-engineer

### TASK-013: Multiple Quiz Attempts + Timed Quizzes ✅ (in-progress → review)

**Goal:** Phase 3 enterprise feature — allow configurable quiz attempts and per-attempt time limits.

#### Model Changes (`apps/progress/models.py`)

**Quiz model** — new fields:
- `max_attempts = PositiveIntegerField(default=1)` — 0 = unlimited
- `time_limit_minutes = PositiveIntegerField(null=True, blank=True)` — NULL = no limit

**QuizSubmission model** — multi-attempt support:
- Removed `unique_together = [("quiz", "teacher")]`
- Added `attempt_number = PositiveIntegerField(default=1)` — 1-based
- Added `started_at = DateTimeField(null=True, blank=True)` — when attempt began
- Added `time_expired = BooleanField(default=False)` — auto-submitted on timeout
- New `unique_together = [("quiz", "teacher", "attempt_number")]`
- New index `(quiz, teacher, attempt_number)` for fast lookup

#### Migration (`0013_quiz_attempts_and_time_limit.py`)
- Backward compatible: existing rows get `attempt_number=1` via default
- Existing `unique_together` replaced atomically by Django

#### View Changes

**`teacher_views.py`** — extracted 4 shared helpers:
- `_validate_answers_payload(answers)` — validation moved out of view
- `_grade_quiz_answers(quiz, answers)` → `(score, has_short_answer)`
- `_get_or_start_quiz_attempt(quiz, teacher, tenant)` → creates in-progress row on first GET
- `_serialize_attempt(sub)` — consistent attempt representation

**`quiz_detail` (GET)** — now returns:
```json
{
  "max_attempts": 3, "time_limit_minutes": 30,
  "attempts_used": 1, "attempts_remaining": 2,
  "best_score": 85.0,
  "current_attempt": {"attempt_number": 2, "started_at": "..."},
  "attempt_history": [{"attempt_number": 1, "score": 70.0, ...}],
  "attempts_exhausted": false,
  "questions": [...]
}
```

**`quiz_submit` (POST)** — now:
- Finds in-progress attempt (score IS NULL)
- Returns 400 if no in-progress attempt (teacher must open quiz first)
- Returns 400 if max attempts exhausted
- Checks `time_limit_minutes` → sets `time_expired=True` if exceeded (still saves)
- Response includes `attempt_number` and `time_expired`

**`student_views.py`** — imports shared helpers from teacher_views; same response schema.

#### Cross-Cutting Fixes (all files that use QuizSubmission)
All queries updated to `.exclude(score__isnull=True)` to exclude in-progress attempts:
- `teacher_views.py`: `submitted_quiz_ids`, `quiz_submissions_map`
- `student_views.py`: `submitted_quiz_ids`, `quiz_submissions_map`
- `teacher_serializers.py`, `student_serializers.py`: `_quiz_submission()` returns best completed attempt
- `gamification.py`: `quiz_submission_days`, `quiz_submissions` count
- `gamification_tasks.py`: XP backfill skips in-progress
- `gamification_signals.py`: XP awarded only when `score IS NOT NULL`; deduplication by `reference_id`
- `tenants/services.py`: `student_quiz_subs` excludes in-progress
- `reports/views.py`: `quiz_subs_map` excludes in-progress; keeps best-scoring attempt per teacher

#### Files Changed
- `backend/apps/progress/models.py`
- `backend/apps/progress/migrations/0013_quiz_attempts_and_time_limit.py` (new)
- `backend/apps/progress/teacher_views.py`
- `backend/apps/progress/student_views.py`
- `backend/apps/progress/teacher_serializers.py`
- `backend/apps/progress/student_serializers.py`
- `backend/apps/progress/gamification.py`
- `backend/apps/progress/gamification_signals.py`
- `backend/apps/progress/gamification_tasks.py`
- `backend/apps/tenants/services.py`
- `backend/apps/reports/views.py`
- `docs/coordination/TASK-013-multiple-quiz-attempts-timed-quizzes.md` (new)

**Status:** Changes complete; awaiting QA tests and reviewer approval.

## 2026-04-19

### [qa-tester] 2026-04-19 — ADDED — TASK-013 view-level tests

Wrote the six missing view-level tests flagged by the reviewer for TASK-013
(Multiple Quiz Attempts + Timed Quizzes). Model-level tests already exist in
`backend/tests/progress/test_progress_models.py` (covers
`unique_together(quiz, teacher, attempt_number)`, multi-attempt creation,
`time_expired` default, `max_attempts` default, etc.) — this new suite is
strictly **API/view-level**, hitting `GET /api/teacher/quizzes/<id>/`,
`POST /api/teacher/quizzes/<id>/submit/`, and `GET /api/teacher/assignments/`.

**File:** `backend/apps/progress/tests_quiz_attempts.py` (12 tests, 7 classes)

| # | Class | Tests | xfail? | Pending fix |
|---|---|---|---|---|
| 1 | `TestMaxAttemptsExhausted` | 2 | no | — |
| 2 | `TestTimeLimitEnforcement` | 3 | 1 xfail | M1 (stale `started_at`) |
| 3 | `TestAttemptsRemaining` | 2 | no | — |
| 4 | `TestBestScoreAcrossAttempts` | 2 | no | — |
| 5 | `TestXPDedupAcrossAttempts` | 1 | no | — |
| 6 | `TestQuizDetailGetIdempotency` | 2 | 1 xfail | M3 (POST `/start/`) |
| 7 | `TestAttemptNumberRace` | 2 | 2 xfail | M2 (TOCTOU) |

Total: **12 tests / 7 classes / 4 xfail** (`strict=False` so CI stays green
until M1/M2/M3 land; they flip to XPASS automatically on success).

**xfail rationale:**
- M1 (`test_stale_started_at_resume_does_not_auto_expire`) — today,
  re-opening a quiz after the time window auto-flags `time_expired` on
  submit. Test asserts the post-fix behaviour: resume must refresh the
  clock (or close + start a fresh attempt).
- M2 (`test_stale_count_does_not_500`, `test_two_threads_do_not_raise_
  integrity_error`) — today, racing `_get_or_start_quiz_attempt` calls
  can collide on `unique_together(quiz, teacher, attempt_number)` and
  surface as a 500 / unhandled `IntegrityError`. Tests assert no
  `IntegrityError` bubbles and at most one in-progress row exists.
- M3 (`test_get_is_read_only_post_start_creates_row`) — today, GET
  `quiz_detail` spawns a row. Test asserts the future contract: GET is
  read-only, POST `/api/teacher/quizzes/<id>/start/` mints the row and
  is idempotent on a second call.

**Notable findings / non-findings while writing tests:**
- `gamification_signals.on_quiz_submission` already dedups correctly by
  `reference_id=instance.id`, so re-saves (admin manual grade) do not
  double-award. Two separate attempts earn two separate XP rows — this
  is the documented product intent.
- `_quiz_submission()` in `teacher_serializers.py` already returns the
  best (not latest) attempt via `order_by("-score", "-attempt_number")`.
  Covered by `TestBestScoreAcrossAttempts`.
- Assignment list endpoint score field correctly reflects best score
  across attempts (asserted in `test_best_score_is_highest_not_latest`).

**Run results:** Docker is not installed on this machine so I could not
execute the pytest suite end-to-end. Tests are static-reviewed only.
Once the backend-engineer lands M1/M2/M3 fixes, run:

```
docker compose exec web pytest apps/progress/tests_quiz_attempts.py -v
```

Expected result after all three fixes: 12 passed, 0 xfail (xfail -> xpass).

**Bugs raised to backend-engineer:** none new — the three Major issues
are already captured in the reviewer report and being worked on.

### [reviewer] 2026-04-19 — APPROVE — TASK-013 r2

Re-reviewed TASK-013 after backend-engineer's M1/M2/M3 fixes. **Verdict: APPROVE.**

- **M1** (stale `started_at`): `quiz_helpers.start_quiz_attempt` closes
  elapsed in-progress rows (`time_expired=True, score=0`) and spawns a
  fresh attempt when `max_attempts` permits. Option (b) is the right call.
- **M2** (TOCTOU): `transaction.atomic()` + `select_for_update` scoped to
  `(quiz, teacher)` prior rows. Attempt number derived from
  `max(attempt_number)+1` so it's robust to gaps left by closed-out stale
  rows. No deadlock risk vs. `quiz_submit`'s own lock on the same key.
- **M3** (GET mutation): dedicated `POST /start/` on both teacher and
  student URLs. Grep confirms zero `.create()` / `.save()` on
  `QuizSubmission` inside `quiz_detail` / `student_quiz_detail`. URL wiring
  clean, no pattern conflict.
- **Minors m1/m4/m5 from r1**: all addressed (helpers extracted, seed
  `get_or_create(attempt_number=1)`, legacy `submission` field aligned to
  best-score).

**New minor (non-blocking):** the M1 close-out path saves `score=0,
graded_at=now` which triggers `on_quiz_submission` → `award_xp` (config
awards a fixed XP for `quiz_submission` regardless of score). A teacher
who abandons a timed quiz will silently earn the full submission XP.
Suggest follow-up to guard on `time_expired=True and score == 0` or flag
the save. Not a merge blocker.

**Tests:** pytest can't run in sandbox (Docker unavailable, direct
`python3 -m pytest` blocked). Static trace of the 4 `xfail(strict=False)`
tests against the fix paths — all should XPASS. Asked qa-tester to remove
the markers and run the full suite on Postgres.

Report: `_coordination/reviews/review-TASK-013-r2.md`.
Notifications sent to backend-engineer (APPROVED) and qa-tester
(REMOVE-XFAIL).

---

## 2026-04-19 — DevOps Agent — Infrastructure Audit & Security Fix

**Agent:** devops

### Full Infrastructure Audit — All Phase 1 & Phase 2 Items Verified Complete ✅

Performed a comprehensive audit of all infrastructure files against the devops task list.
All previously-listed Phase 1 and Phase 2 items are confirmed done:

| Item | File | Status |
|------|------|--------|
| pg_isready healthcheck uses `${DB_USER:-learnpuddle}` | docker-compose.prod.yml, staging.yml, backend/docker-compose.yml | ✅ Done |
| Redis password enforced: `${REDIS_PASSWORD:?...}` | docker-compose.prod.yml, staging.yml | ✅ Done |
| IP restrictions for /metrics and /flower/ | nginx/includes/shared_locations.conf, nginx/production.conf | ✅ Done |
| `USER nginx` in nginx Dockerfile | nginx/Dockerfile (line 44) | ✅ Done |
| Docker log rotation (max-size: 10m, max-file: 3) | x-common anchor in prod + x-logging in staging | ✅ Done |
| E2E tests blocking CI | .github/workflows/ci.yml | ✅ Done |
| Coverage threshold at 60% | ci.yml (`COV_FAIL_UNDER: "60"`) | ✅ Done |
| Rollback strategy in deployment | ci.yml (both staging + prod deploy steps) | ✅ Done |
| Celery worker healthchecks | docker-compose.prod.yml + staging.yml | ✅ Done |
| nginx HTTP/HTTPS duplication eliminated | nginx/nginx.conf + includes/shared_locations.conf | ✅ Done |
| `client_max_body_size 10M` global, 512M only for video | shared_locations.conf, production.conf, staging.conf | ✅ Done |
| Backup integrity verification | scripts/backup-db.sh (gunzip -t + pg_dump header check) | ✅ Done |
| Notification archival (90-day TTL) | Done by backend-engineer (TASK-009) | ✅ Done |

### Security Gap Found and Fixed: `nginx/nginx.staging.conf`

**Problem:** The staging nginx config (port 8080 server block) had two security gaps:
1. `/flower/` location had **no IP restriction** — comment explicitly noted this: "staging has no IP restriction"
2. `/metrics` location was **entirely missing** — Prometheus metrics endpoint would fall through to `/api/` catch-all

**Fix:** `nginx/nginx.staging.conf`
- Added `/metrics` location block with `allow 10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.1`, `deny all` before `/flower/`
- Added same `allow`/`deny all` IP restriction to the `/flower/` location block
- Updated comment: "staging has no IP restriction" → "IP restricted to private networks"

**Rationale:** Even in staging environments, Flower (Celery task monitor) and Prometheus metrics expose sensitive operational data (task payloads, queue depths, timing) and should never be publicly accessible. The private-network `allow` rules still permit access from CI runners and VPN-connected developers.

### Files Changed
- `nginx/nginx.staging.conf` — add /metrics + IP-restrict /flower/

### Validation
- Docker not available in sandbox — manual syntax review performed
- nginx config structure and directive placement verified against production reference (nginx/includes/shared_locations.conf)
- All allow/deny directives placed before proxy_pass (nginx processes allow/deny in order, then proxies)

**Status:** Changes ready for review. No other infra tasks remain in Phase 1/2/3 backlog.

---

## 2026-04-20 — DevOps Agent — Critical Staging Nginx Fix

**Agent:** devops

### Audit Performed — All Prior Phase 1/2/3 Items Re-Verified ✅

Re-checked all infrastructure files. All previously-recorded Phase 1/2/3 items remain complete.
The only open item was the previous session's fix to `nginx.staging.conf` (add `/metrics` + IP-restrict `/flower/`), which was confirmed applied.

### Critical Bug Found and Fixed: `nginx/nginx.staging.conf` — API Routing Broken on Port 80

**Root Cause:**

The staging nginx config had two server blocks:
1. **Port 80** — only served the React SPA (`try_files`) and health check. No `/api/`, `/ws/`, `/flower/`, `/metrics/`, or any proxy location.
2. **Port 8080** — had complete API + WebSocket + Flower + metrics routing.

However, `docker-compose.staging.yml` maps only `80:80` and `443:443` — port 8080 was **never reachable from outside Docker**. This means all API calls from the staging browser hit `/api/...` on port 80, which fell through to `try_files $uri $uri/ /index.html` and returned the SPA's `index.html` with HTTP 200. Every API request appeared to silently succeed when in fact it was receiving HTML.

**Additional bugs discovered in the old port 8080 block:**
- Chatbot SSE: `proxy_pass http://web:8000` (hardcoded hostname, bypassed dynamic DNS resolver) → should be `http://$django_upstream`
- OpenMAIC SSE location missing entirely from staging (only in production shared_locations.conf)
- Chatbot SSE missing `proxy_send_timeout 300s`
- Chatbot SSE and MAIC SSE missing rate limiting (`limit_req zone=api`)
- Video upload regex only matched `/api/courses/...` but not `/api/v1/courses/...` (production.conf handles both with `(v1/)?`)

**Fix:** `nginx/nginx.staging.conf` — Complete rewrite

- Removed the broken/incomplete port 80 server block
- Removed the unreachable port 8080 server block
- Replaced both with a **single correct port 80 server block** containing all routing:
  - Static files, media auth-gate, API proxy, Django admin, health check
  - Prometheus metrics with IP restriction (10.x/172.16.x/192.168.x/127.0.0.1 only)
  - Flower with IP restriction (same networks)
  - Video upload: 512M limit, `(v1/)?` regex pattern, no buffering
  - Chatbot SSE: `$django_upstream`, rate limiting, `proxy_send_timeout 300s`
  - OpenMAIC SSE: added (was missing from staging)
  - WebSocket → Daphne ASGI
  - React SPA catch-all with proper no-cache headers for service-worker.js / index.html
- Added commented-out HTTPS block template for when certbot is configured

**Validation:**
- Manual syntax review: all 17 location blocks have balanced braces
- Location order verified: exact matches → regex (in order) → longest-prefix wins
- All `allow`/`deny all` before `proxy_pass` in restricted blocks
- Upstream variables use `$variable` form (required for dynamic DNS resolver)
- Cross-checked against `nginx/includes/shared_locations.conf` and `nginx/production.conf`
- Docker/nginx not available in sandbox — `nginx -t` cannot be run; require review before deploying

### Files Changed
- `nginx/nginx.staging.conf` — complete rewrite (see diff)

**Status:** Changes complete, ready for review. Require `nginx -t` validation before deploying to staging.

---

### [lp-reviewer] TASK-014 Badge Rarity Tiers — APPROVE

**Agent:** reviewer

Closed out TASK-014 (Phase 4 gamification — 6-tier badge rarity system + `social_learning` category).

**Verdict:** APPROVE. Full report at `projects/learnpuddle-lms/reviews/review-TASK-014-badge-rarity-2026-04-20.md`.

**Verified:**
- Migration `0015_badge_rarity_tiers` is additive-only (AddField), depends on `0014_rubrics`, zero-downtime.
- `BadgeDefinition.rarity` defaults to `'common'` — no backfill needed.
- Both read and write serializers expose `rarity`; `TeacherBadgeSerializer` nests it for earned-badge endpoint.
- Admin views carry `@admin_only @tenant_required`; teacher views filter `is_active=True` with TenantManager scoping.
- Cross-tenant isolation test (`test_teacher_cannot_see_other_tenant_badge_definitions`) creates two tenants and asserts no leakage.
- `rarity` is not referenced in `gamification_engine.py` — correctly display-only as designed.
- 18 tests (8 model + 6 admin + 4 teacher) — matches spec after qa-tester expansion.

**Minor follow-ups (non-blocking):** backend-engineer should run `docker compose exec web pytest apps/progress/tests_badge_rarity.py -v` and confirm green. No code changes requested.

**Files touched (review deliverables only — no production code edits):**
- Created: `projects/learnpuddle-lms/reviews/review-TASK-014-badge-rarity-2026-04-20.md`
- Created: `_coordination/inbox/backend-engineer/REVIEW-VERDICT-TASK-014-2026-04-20.md`
- Updated: `docs/coordination/TASK-014-badge-rarity-tiers.md` — status `review` → `done`

---

### [lp-reviewer] TASK-016 + FE-010 — Phase 4 Gamification & Analytics reviews — APPROVE / APPROVE

**Agent:** lp-reviewer
**Scope:** Two Phase 4 review requests filed 2026-04-20.

**TASK-016 — 10-tier League Leaderboards (backend-engineer) — APPROVE**
- Migration `0017_leagues.py` is strictly additive (5 `AddField` on existing tables with defaults, 3 `CreateModel` with indexes/constraint); deps chain back to `0016_streak_freeze_tokens`. Zero-downtime safe.
- All three new models (`League`, `LeagueMembership`, `LeagueRankSnapshot`) carry `tenant` FK + `TenantManager` + `all_objects`; sensible composite indexes on `(tenant, week, tier_rank)` and `(tenant, league, weekly_xp)`.
- Promote/demote math in `close_league_week` verified: top N promote / bottom M demote / middle hold; clamped at Diamond (10) and Bronze I (1); cohorts <3 skip; overlap guard reduces `demote_n` if `promote_n + demote_n > size`. `_scale_count` proportional scaling covered by `test_small_cohort_scales_promote_count`.
- `_is_teacher_eligible` correctly excludes SUPER_ADMIN/SCHOOL_ADMIN and both `opted_out` + `league_opted_out`.
- Tenant-isolation test `test_close_week_is_tenant_scoped` creates a second tenant and asserts the other tenant's league stays open with zero snapshots — pass.
- Celery beat entry `progress-close-league-week-weekly` in `config/celery.py` uses `crontab(hour=0, minute=0, day_of_week="mon")` and task path `progress.close_league_week` matches `@shared_task(name=...)` — no typo.
- API views carry `@permission_classes([IsAuthenticated]) @teacher_or_admin/@admin_only @tenant_required`.
- `GamificationConfigSerializer` exposes all 5 new config fields.
- **Only flagged behaviour (non-blocking):** concurrent `award_xp` → `_bump_league_weekly_xp` race can raise `IntegrityError` on `(teacher, league)` uniqueness; the broad `except` in `award_xp` swallows it. Acceptable; single retry is future polish, not a blocker.

**FE-010 — Admin Skill Radar Page (frontend-engineer) — APPROVE**
- Endpoint `GET /api/reports/manager/skills-overview/` is already guarded `@teacher_or_admin @tenant_required` in `backend/apps/reports/manager_views.py` (line 311-313).
- Route `/admin/analytics/skills` is nested under the SCHOOL_ADMIN `ProtectedRoute` in `App.tsx` (line 444) — gating correct.
- No `any`, no `console.log`, recoverable error state with Retry, empty states for both radar and table.
- Recharts usage standard; no new deps. Category filter re-keys React Query and fires `overview({ category })` — verified by test.
- 5 vitest cases land; author reports 352/352 green and `tsc --noEmit` clean (reviewer did not rerun).

**Blockers:** None across either request.

**Files touched (review deliverables only — no production code edits):**
- Created: `projects/learnpuddle-lms/reviews/review-TASK-016-leagues-2026-04-20.md`
- Created: `projects/learnpuddle-lms/reviews/review-FE-010-skill-radar-2026-04-20.md`
- Created: `_coordination/inbox/backend-engineer/REVIEW-VERDICT-TASK-016-2026-04-20.md`
- Created: `_coordination/inbox/frontend-engineer/REVIEW-VERDICT-FE-010-2026-04-20.md`
- Updated: `docs/coordination/TASK-016-leagues.md` — status `review` → `done`

---

### [lp-reviewer] TASK-018 + FE-012 + QA assessment_views — APPROVE / APPROVE / APPROVE

**Agent:** lp-reviewer
**Scope:** Three review requests filed 2026-04-20 (one backend, one frontend, one QA coverage).

**TASK-018 — Mastery Points (backend-engineer) — APPROVE**
- Migration `0019_mastery_points.py` is strictly additive (5 `AddField` on `gamificationconfig`, 2 `CreateModel`, 5 indexes, 1 partial unique constraint); deps on `0018_challenges`. Zero-downtime safe.
- Partial unique `uniq_mp_txn_per_reference` on `(teacher, reason, reference_type, reference_id) WHERE reference_id IS NOT NULL` — exactly right so `admin_adjust` (null ref) can repeat.
- Both new models (`MasteryPointTransaction`, `TeacherMasterySummary`) carry `tenant` FK + `objects = TenantManager()` + `all_objects = models.Manager()`. Composite indexes on `(tenant, teacher, reason)`, `(tenant, total_mastery_points)`.
- Engine `award_mastery_points` wraps the create in `transaction.atomic()` + catches `IntegrityError` — duplicate awards silently no-op.
- Opt-out shared with XP via `TeacherXPSummary.opted_out` (`_is_teacher_opted_out` reads the XP row). Tested by `test_opt_out_blocks_award`.
- Quiz threshold default 80% + `round(score_percent * weight)`, assignment `raw_score * weight`, course flat `mp_course_bonus=50` when avg ≥ threshold — all match the spec table.
- Signal wiring verified end-to-end: quiz → `award_quiz_mastery(instance)` inside existing XP handler; assignment → separate handler on `status == 'GRADED'` (no `created` gate so late grades still award, dedup by constraint); course → inline call to `award_course_mastery_bonus` inside the existing course-completion XP block.
- No recursion into `award_xp` from the MP path — confirmed by code inspection.
- Cross-tenant leaderboard test `test_admin_leaderboard_is_tenant_scoped` creates a rival tenant + teacher, asserts no leakage.
- API decorators correct: teacher routes `@teacher_or_admin @tenant_required`; admin leaderboard `@admin_only @tenant_required`. Leaderboard clamps `limit` to `[1, 200]`, uses `select_related('teacher')`.
- 20 tests: 5 model / 9 engine / 5 signal / 5 API. All wired to `all_objects` for cross-tenant correctness where needed.
- **Single minor note (non-blocking):** re-grade with a changed score won't update existing MP (unique constraint prevents insert; engine doesn't do `update_or_create`). "First graded score wins" — acceptable now; call out if product ever wants "latest grade wins".

**FE-012 — Teacher Leagues & Challenges UI (frontend-engineer) — APPROVE**
- Zero `any`, zero `console.*` in both new pages, `AchievementsPage.tsx` refactor, and `gamificationService.ts` (verified via grep).
- Typed service interfaces (`StreakFreezeInventory`, `CurrentLeague`, `LeagueMember`, `LeagueHistoryEntry`, `TeacherChallenge`) match backend shapes in `league_views.py`, `challenge_views.py`, and `gamification_teacher_views.py`.
- `is_me` treatment: `ring-2 ring-primary-400` + "You" chip + `data-me` attribute for tests; computed via `String(user.id) === m.teacher_id` (UUID normalization correct).
- Promote/demote zone shading driven by `promote_count` / `demote_count` config in `zoneForIndex` (not hard-coded); handles zero counts cleanly.
- Streak freeze gating: `canUseFreeze = tokenCount > 0 && current_streak > 0`, with `typeof`-check fallback to prevent first-paint flicker. Button relabels "No tokens" and disables when empty.
- `App.tsx` 189-193 lazy routes, 511-512 routes under the teacher `ProtectedRoute` layout (`['TEACHER', 'HOD', 'IB_COORDINATOR']` — matches the existing `/teacher/achievements` pattern and backend `@teacher_or_admin`).
- `TeacherSidebar.tsx` 46-47 adds Challenges + Leagues entries.
- 21/21 new tests pass; pre-existing `App.test.tsx` "shows product landing page at root on platform host" flake confirmed unrelated (this PR does not touch platform-host logic).
- `tsc --noEmit` clean per author.

**QA assessment_views coverage (qa-tester) — APPROVE**
- `_AssessmentViewsBase` uses `setUpTestData` with two tenants (`cov` + `rival`) on distinct subdomains; cross-tenant 404 tests exist for banks, questions, quiz config, quiz attempt start, and course gradebook. Each uses the caller's own tenant host and targets the other tenant's object ID.
- Shape assertions (not just status): `test_start_response_never_leaks_is_correct_or_explanation` iterates questions + choices; `test_submit_strips_is_correct_when_config_disables_reveal` mirrors for submit with `show_correct_answers_after=False`.
- `test_multi_default_is_all_or_nothing`: 2-correct MULTI submit of 1/2 → score == 0 (complements M1 partial-credit test in `tests_assessment.py`).
- `test_submit_with_max_score_zero_does_not_crash`: `points=0` ⇒ `score=0, max_score=0, passed=False`, no ZeroDivision.
- `test_gradebook_ignores_attempts_on_other_courses`: same-tenant second course attempt; original course's row stays zero — catches content→module→course scoping regressions.
- Style parity with `tests_assessment.py` (APIClient, JWT `_login` + faster `_force`, `ALLOWED_HOSTS=["*"]`, `HTTP_HOST = cov.lms.com`).
- Author's two design notes triaged as **follow-ups, not blockers**:
  1. `quiz_config_for_content` creates on GET — minor REST smell; characterization test holds current behaviour.
  2. `my_quiz_attempts` is `@teacher_or_admin` → admins see an empty list (not a leak).

**Blockers:** None across any of the three.

**Files touched (review deliverables only — no production code edits):**
- Created: `projects/learnpuddle-lms/reviews/review-TASK-018-mastery-points-2026-04-20.md`
- Created: `projects/learnpuddle-lms/reviews/review-FE-012-leagues-challenges-2026-04-20.md`
- Created: `projects/learnpuddle-lms/reviews/review-QA-assessment-views-coverage-2026-04-20.md`
- Created: `_coordination/inbox/backend-engineer/REVIEW-VERDICT-TASK-018-2026-04-20.md`
- Created: `_coordination/inbox/frontend-engineer/REVIEW-VERDICT-FE-012-2026-04-20.md`
- Created: `_coordination/inbox/qa-tester/REVIEW-VERDICT-ASSESSMENT-VIEWS-2026-04-20.md`
- Updated: `docs/coordination/TASK-018-mastery-points.md` — status `review` → `done`

---

## 2026-04-20 — [lp-reviewer] Round 3 — Phase 4 close-out

**Agent:** lp-reviewer
**Scope:** Three review requests filed 2026-04-20 — the final Phase 4 batch.

**TASK-021 / spec TASK-020 — Education vs Corporate mode (backend-engineer) — APPROVE**
- Migration `0024_tenant_mode.py` is pure `AddField` (mode + mode_label_overrides), dep `0023_auditlog_calendar_actions`. Zero-downtime; defaults preserve existing `education` behaviour.
- `MODE_LABEL_DEFAULTS` covers all 12 canonical keys for both modes; `get_mode_labels()` merges correctly (string-only non-empty overrides win; defensive fallback to education map on unknown mode).
- `TenantThemeSerializer` exposes `mode` + `mode_labels` on `/me`; `TenantSettingsSerializer` exposes `mode` + `mode_label_overrides` (writable) + `mode_labels` (read-only).
- `tenant_me_view` = `@tenant_required`; `tenant_settings_view` = `@admin_only @tenant_required`. Non-admin PATCH → 403; missing tenant → 403.
- Cross-tenant isolation asserted: admin A on tenant B's subdomain → 403, tenant B mode stays `education` (`TenantModeCrossTenantTests.test_admin_in_a_cannot_flip_mode_on_b_subdomain`).
- Invalid mode → 400 via DRF `ChoiceField`. `validate_mode_label_overrides` silently drops non-string values (reviewer asked for docstring clarification; non-blocking).
- 14 tests across model (6), API (7), cross-tenant (1).
- Numbering collision noted: feature spec = `docs/coordination/TASK-020-education-corporate-mode.md`, reminders follow-up = `TASK-020-reminders-pii-log-followup.md`, review request = `TASK-021`. Coordinator to reconcile.

**FE-014 — Puddle Coins Wallet UI + Purchase Flow (frontend-engineer) — APPROVE**
- `coinsService.ts`: zero `any`, explicit union `CoinReason`, typed `CoinBalance` / `CoinHistoryResponse` / `PurchaseResponse` / `InsufficientCoinsPayload`. `parseInsufficientCoinsError` narrows via `axios.isAxiosError` + 400 + runtime typeof guards on `balance`/`price`.
- `WalletPage.tsx`: hero + lifetime-stat cards + Shop (Buy disabled when `!canAfford || isPending`, variant flips to "Not enough") + paginated history DataTable with formula-injection hardened CSV export (`^[=+\-@]` → `'` prefix).
- Lazy route `App.tsx` L198, mounted `/teacher/wallet` L520 under teacher `ProtectedRoute`.
- Sidebar: Lucide `Coins` icon, under "My Learning", no import collision.
- Purchase flow: bespoke Headless UI `Dialog` (not `ConfirmDialog`) because it renders balance/price/after rows; backdrop-close guarded while mutation pending. On success invalidates `teacherCoinBalance`, `teacherCoinHistory`, `teacherStreakFreezeInventory` (the last one keeps AchievementsPage in sync).
- Price fallback `DEFAULT_STREAK_FREEZE_PRICE = 100` is pragmatic: backend `TeacherCoinBalanceSerializer` doesn't yet expose `price_streak_freeze`. Server still enforces correctly; fallback is UI-only. Follow-up filed to BE.
- 48 files / 393/393 vitest pass; `tsc --noEmit` clean as reported.

**QA billing coverage (qa-tester) — APPROVE**
- `backend/tests/billing/test_billing_views.py` — **50 tests** (qa's handoff estimated ~41; real `grep -c def test_` = 50) across 12 classes.
- All Stripe calls mocked at `apps.billing.stripe_service.*` — no real network. Webhook-handler tests bypass `construct_webhook_event` (signature verification already covered in `test_stripe_webhook.py`).
- `StripeObj(dict)` helper supports both `obj["items"]["data"]` (dict) AND `obj.id` (attr) — correctly mirrors how handlers consume real `stripe.stripe_object.StripeObject`.
- Cross-tenant isolation on `subscription_detail` (admin A → tenant B = 404) AND `payment_history` (tenant A never sees tenant B invoices).
- All six required webhook events covered with happy + missing-metadata + unknown-tenant + idempotency: `checkout.session.completed`, `subscription.created/updated/deleted`, `invoice.paid`, `invoice.payment_failed`.
- Two prod smells filed as **TASK-022 follow-up (docs-only, no implementation)**: (a) `billing_interval='month'` hard-coded at checkout.session.completed create-time; (b) `handle_invoice_payment_failed` swallows `Charge.retrieve` failures at `logger.debug`.

**Blockers:** None across any of the three. **Phase 4 is CLOSED.**

**Files touched (review deliverables only — no production code edits, no git commits):**
- Created: `projects/learnpuddle-lms/reviews/review-TASK-021-education-corporate-mode-2026-04-20.md`
- Created: `projects/learnpuddle-lms/reviews/review-FE-014-puddle-coins-wallet-2026-04-20.md`
- Created: `projects/learnpuddle-lms/reviews/review-QA-billing-coverage-2026-04-20.md`
- Created: `_coordination/inbox/backend-engineer/REVIEW-VERDICT-TASK-021-2026-04-20.md`
- Created: `_coordination/inbox/frontend-engineer/REVIEW-VERDICT-FE-014-2026-04-20.md`
- Created: `_coordination/inbox/qa-tester/REVIEW-VERDICT-BILLING-COVERAGE-2026-04-20.md`
- Created: `_coordination/inbox/backend-engineer/FOLLOWUP-coins-price-exposure-2026-04-20.md`
- Created: `docs/coordination/TASK-022-billing-interval-idempotency-followup.md`
- Updated: `docs/coordination/TASK-020-education-corporate-mode.md` — status `review` → `done`

---

### Reviewer — 2026-04-20 Session

**Agent:** reviewer
**Scope:** Phase 2 technical-debt triage — TASK-007, TASK-008, TASK-009.

**TASK-007 — Extract duplicated helpers — APPROVE**
- `utils/rich_text.py::rewrite_rich_text_for_serializer` is the single canonical
  implementation; all 4 formerly-duplicated copies in `courses/serializers.py`
  and `courses/teacher_serializers.py` are now one-line delegates.
- `utils/course_access.py::is_teacher_assigned_to_course` replaces both local
  definitions; both view files import with a local alias so the 10+ call sites
  are unchanged. Grep confirms zero surviving local defs.
- Status moved `review` → `done`.
- Non-blocking follow-up: two more `_rewrite_rich_text` copies live in
  `apps/courses/student_serializers.py` (L100, L156) — outside the spec but
  worth unifying in a small TASK-007b.

**TASK-008 — Error response standardization — REQUEST_CHANGES**
- `utils/exception_handler.py` converts DRF `{"detail": "..."}` →
  `{"error": "<string>"}` (flat string). Wired in `config/settings.py`
  L314-316 correctly.
- `utils/responses.py::error_response` emits `{"error": {"message": "...",
  "fields": {...}}}` (nested object). Already used by 14+ view files.
- **Blocker:** the two code paths emit incompatible shapes. Frontend code
  doing `err.error.message` crashes on DRF errors; `String(err.error)` yields
  `[object Object]` on manual errors. Spec target was a single
  `{"error": "...", "details": [...]}` shape — neither path matches.
- Asked backend-engineer to pick one shape, align both helpers, add unit
  tests for the exception handler, and document the contract for FE
  (TASK-012). Status stays `review`.

**TASK-009 — Notification archival — APPROVE**
- Migration chain verified (`0005_notification_archived_at`,
  `0006_notification_is_archived`, `0007_rename_*`) — all additive,
  zero-downtime.
- `ActiveNotificationManager(TenantManager)` chains `is_archived=False` +
  `archived_at__isnull=True` on top of tenant filtering.
  `all_objects = models.Manager()` preserved for archival tasks.
- `archive_old_notifications` (daily 03:00 UTC) and
  `delete_archived_notifications` (weekly Sun 04:00 UTC) wired in
  `CELERY_BEAT_SCHEDULE`. Both use `all_objects` to bypass the default
  manager — correct. Task names match `@shared_task(name=...)` decorators.
- 120-day lifecycle matches spec. Tenant isolation preserved end-to-end.
- Status moved `review` → `done`. Deferred items (admin manual-trigger
  endpoint, integration tests) acceptable and already tracked.

**Files updated this session (task specs + shared log only — no production
code edits, no git writes):**
- `docs/coordination/TASK-007-extract-duplicated-helpers.md` — Review
  block + status `review` → `done`.
- `docs/coordination/TASK-008-error-response-standardization.md` — Review
  block (REQUEST_CHANGES); status stays `review`.
- `docs/coordination/TASK-009-notification-archival.md` — Review block +
  status `review` → `done`.
- `docs/coordination/shared-log.md` — this entry.

---

### backend-security — TASK-005 (2026-04-20)

**Task:** Remove JWT access token from WebSocket URL query string to stop
leakage via browser history, proxy access logs, and referer headers.

**Approach:** WebSocket subprotocol pattern (Option A from the spec). Hard
cut — query-string tokens are no longer honoured. No backward-compat path,
because the React bundle ships together with the backend change.

**Files changed:**
- `frontend/src/hooks/useNotifications.ts` — WS URL no longer embeds
  `?token=`; token passed as the subprotocol list:
  `new WebSocket(url, [\`Bearer.${accessToken}\`])`.
- `backend/apps/notifications/middleware.py` (`JWTAuthMiddleware`) —
  reads `scope["subprotocols"]`, picks the first entry prefixed with
  `Bearer.`, validates the JWT, sets `scope["user"]` and
  `scope["accepted_subprotocol"]`. Ignores non-Bearer subprotocols and
  never reads `scope["query_string"]` for tokens.
- `backend/apps/notifications/consumers.py` (`NotificationConsumer.connect`)
  — accepts the handshake with `subprotocol=scope["accepted_subprotocol"]`,
  required by the WS spec for the browser to complete the handshake.
- `backend/apps/notifications/tests_websocket_auth.py` — **new** test
  module covering:
  - `test_middleware_accepts_bearer_subprotocol`
  - `test_middleware_ignores_non_bearer_subprotocol`
  - `test_middleware_rejects_invalid_bearer_token`
  - `test_middleware_does_not_read_query_string_token` (regression guard)
  - `test_consumer_connects_with_valid_bearer_subprotocol` (full Channels
    `WebsocketCommunicator` handshake; asserts echoed subprotocol)
  - `test_consumer_rejects_missing_subprotocol` (close code 4001)
- `docs/coordination/TASK-005-jwt-websocket-security.md` — Status `todo`
  → `review`; Assigned `frontend-engineer` → `backend-security`; all
  Acceptance Criteria checked; added an Implementation Notes section.

**What reviewers should test:**
1. Run `docker compose exec web pytest apps/notifications/tests_websocket_auth.py -v`
   — all six tests should pass. (Not executed in this worktree: Docker is
   unavailable here; code was validated by inspection only.)
2. Run the full notifications suite
   (`docker compose exec web pytest apps/notifications/`) to confirm no
   regression in the existing REST/email/archival tests.
3. Manual smoke: log in as a teacher, open DevTools → Network → WS frame,
   confirm `Sec-WebSocket-Protocol: Bearer.<jwt>` on the request and the
   same value on the response. Confirm the URL contains **no** `?token=`.
4. Manual regression: trigger a notification (e.g. send a reminder) and
   verify it arrives in the UI within ~1s; verify `mark_read` and
   `mark_all_read` still flow through the WS.
5. Token-refresh behaviour: let the access token expire (~15 min) or force
   a refresh; the socket closes, `useNotifications.connect` re-runs with
   the new token, and reconnect succeeds.

**Backward-compat concerns:** Any still-open client that was using
`?token=` at deploy time will be disconnected on the next socket cycle and
reconnect using the new hook code once the frontend bundle is loaded — no
user action required. No mobile or third-party WS clients exist, so no
additional shim is needed.

**Security posture:** The middleware now treats the query string as an
untrusted channel for credentials. The regression test
`test_middleware_does_not_read_query_string_token` will fail loudly if a
future refactor re-introduces the old path.

---

### frontend-engineer — TASK-012 (2026-04-20)

**Phase A — console.log audit:**
- Zero real debug `console.log` statements found in production code. The single match (`SlideEditor.tsx:55`) is intentional template content (default code block text shown to users in the slide editor), not a debug statement. No removals needed.
- `window.confirm` audit: Found 6 usages across `ChatbotListPage`, `MAICLibraryPage`, `DiscussionThreadPage`, `SchoolAccreditationsTab`, `SchoolDetailPage`, `ChatPanel`, and `AgentGenerationStep`. Three high-visibility ones migrated in this task.

**Phase B — Toast system:**
- Existing custom `ToastProvider` + `useToast` hook already fully implemented in `components/common/Toast.tsx` and mounted in `App.tsx`. Comprehensive (success/error/warning/info with auto-dismiss).
- Created `frontend/src/hooks/useToast.ts` as a thin re-export wrapper so call sites can import from `hooks/useToast`.
- Added `sonner: "^1.5.0"` to `frontend/package.json` dependencies per spec.
- Migrated 3 `window.confirm` call sites to use the existing `ConfirmDialog` component (accessible headless UI modal):
  1. `ChatbotListPage.tsx` — delete tutor confirmation
  2. `MAICLibraryPage.tsx` — delete classroom confirmation
  3. `ChatPanel.tsx` — clear chat confirmation

**Phase C — Form validation:**
- Already complete: `react-hook-form`, `zod`, `@hookform/resolvers` are all in `package.json`. `LoginPage` already uses RHF+Zod via `useZodForm` hook. `useZodForm.ts` hook exists. No migration needed.

**Status:** All three phases complete. Remaining `window.confirm` usages in `DiscussionThreadPage`, `SchoolAccreditationsTab`, `SchoolDetailPage`, and `AgentGenerationStep` deferred for future cleanup.

---

### qa-tester — TASK-010 (2026-04-20)

**Coverage before:** 43.7% (3,224 / 7,376 lines per coverage.xml)

**Tests added (178 new tests across 7 files):**

| File | Tests | Target |
|------|-------|--------|
| `apps/users/tests_admin_views.py` | 30 | `admin_views.py` (26.1% → ~75%) |
| `apps/courses/tests_teacher_course_views.py` | 16 | `courses/teacher_views.py` (38.1% → ~70%) |
| `apps/progress/tests_progress_views.py` | 49 | `progress/teacher_views.py` (21.7% → ~65%) |
| `apps/tenants/tests_views_extended.py` | 26 | `tenants/views.py` (40% → ~80%) |
| `apps/tenants/tests_superadmin_views.py` | 20 | `tenants/superadmin_views.py` (31% → ~65%) |
| `apps/courses/tests_admin_course_views.py` | 21 | `courses/views.py` (30% → ~65%) |
| `apps/notifications/tests_services.py` | 16 | `notifications/services.py` (0% → ~80%) |

**Coverage after:** Estimated ~58-62% (cannot run pytest in this env — no DB/Docker available). Impact estimate based on:
- 178 new tests × average ~15 lines covered = ~2,670 additional covered lines
- Total would become ~5,894 / 7,376 = ~79.9% (optimistic; actual excludes already-covered lines and integration weight)
- Conservative estimate accounting for overlap and decorators: **~58-62%**

**Key patterns used:**
- All tests use `override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")` for host resolution
- Tenant isolation verified: 403 responses for cross-tenant requests
- Auth guards verified: 401 for unauthenticated, 403 for wrong role
- Notification service tests use `@patch` to mock WebSocket channel layer

**Remaining low-coverage files (for next session):**
- `notifications/consumers.py` (0%) — requires channels test layer
- `notifications/services.py` likely improved by these tests
- `courses/tasks.py` (12.4%) — partially covered by video_pipeline_extended
- `tenants/tasks.py` (0%) — Celery tasks need mock
- `webhooks/services.py` (0%), `webhooks/tasks.py` (0%)
- `users/sso_pipeline.py` (0%), `users/twofa_views.py` (26%)
- `courses/learning_path_views.py` (32%), `courses/video_views.py` (36%)

**Status:** Coverage gap partially closed. Run `pytest --cov=apps --cov-report=term-missing` to confirm final %.

---

### frontend-engineer — TASK-006 (2026-04-20)

**Task:** Decompose `CourseEditorPage.tsx` (originally 2,894 lines, already partially decomposed to ~508 lines + sub-files) into focused components, with all files under 400 lines.

**Files created (new):**
- `course-editor/contentUtils.tsx` (28 lines) — pure `getContentIcon` utility, breaks circular dep
- `course-editor/useVideoUpload.ts` (125 lines) — video upload state machine + polling loop
- `course-editor/useAssignmentValidation.ts` (71 lines) — assignment form validation + sanitization
- `course-editor/ModuleDescription.tsx` (89 lines) — module description display/edit
- `course-editor/ContentItemRow.tsx` (137 lines) — single content item (display or text-edit mode)
- `course-editor/AddContentForm.tsx` (213 lines) — add-content form trigger and form body
- `course-editor/ContentPreviewModal.tsx` (125 lines) — content preview modal (video/doc/link/text)
- `course-editor/MediaLibraryModal.tsx` (121 lines) — legacy inline media library picker modal

**Files refactored (trimmed):**
- `CourseEditorPage.tsx`: 508 → 235 lines (extracts modals to ContentPreviewModal, MediaLibraryModal)
- `ModuleContentEditor.tsx`: 624 → 66 lines (composes sub-components)
- `useContentState.ts`: 517 → 335 lines (delegates video polling to useVideoUpload)
- `useAssignmentState.ts`: 533 → 294 lines (delegates validation to useAssignmentValidation)

**Result:** All 23 files <= 399 lines. `npx tsc --noEmit` passes with zero errors. No circular imports.

**Status:** review

---

## 2026-04-20 — Backend Engineer — TASK-008 rework

### backend-engineer — TASK-008 rework (2026-04-20)

**Agent:** backend-engineer
**Task:** TASK-008 Error Response Standardization (rework after review rejection)

#### Problem addressed

Two incompatible error shapes coexisted post-first-pass:
- `utils/exception_handler.py` emitted `{"error": "<string>"}` (flat)
- `utils/responses.py::error_response` emitted `{"error": {"message": "...", "fields": {...}}}` (nested object)

Frontend doing `err.error.message` crashed on DRF errors; `String(err.error)` yielded `[object Object]` on manual errors.

#### Resolution — Option B: spec-verbatim flat shape

Canonical shape adopted across **both** paths:

```json
{
  "error": "Human-readable summary",
  "details": [{"field": "email", "message": "..."}, {"field": null, "message": "..."}],
  "code": "optional_snake_case_code"
}
```

- `error` is always a plain string
- `details` is optional, present only when field/extra info is available
- `code` present only for DRF system errors or explicit caller opt-in

#### Files changed

| File | Change |
|------|--------|
| `backend/utils/exception_handler.py` | Full rewrite — handles system errors, field ValidationError (flattened to details), list ValidationError, fallback |
| `backend/utils/responses.py` | `error_response` emits flat shape; signature unchanged; docstring matches spec |
| `backend/tests/test_exception_handler.py` | New — 20 test cases |
| `backend/tests/test_responses.py` | New — 20 test cases |
| `frontend/src/components/courses/ai-generation/helpers.ts` | `extractErrorMessage` updated; `extractErrorDetails` helper added |
| `docs/coordination/TASK-008-error-response-standardization.md` | Acceptance criteria updated; rework notes section added |

#### Call sites

No changes needed to the 14+ view files that call `error_response()` — signature is identical, only the response body changed.

**Status:** review

### Reviewer — TASK-005/006/012 (2026-04-20)

Reviewed three tasks marked `status: review`. Task specs' worktree paths
were stale (e.g. `agent-a76b067d`, `agent-a03856432bd242f22` don't exist)
so review followed the actual file state.

**TASK-005 — JWT WebSocket security: APPROVE → done.**
Implementation lives on `maic-sprint-1-presence-rhythm`. `useNotifications.ts`
drops `?token=` and passes `Bearer.<jwt>` via `new WebSocket(url, [...])`;
`JWTAuthMiddleware` reads `scope["subprotocols"]`, validates via
SimpleJWT `AccessToken`, and stores `accepted_subprotocol` in scope;
consumer echoes it back via `self.accept(subprotocol=...)`; middleware is
wired in `backend/config/asgi.py`. New `tests_websocket_auth.py` (still
untracked — owner must `git add`) covers happy path, invalid token,
non-Bearer subprotocol, missing subprotocol (consumer rejects 4001), and
a regression guard asserting query-string tokens are ignored. Minor:
`BEARER_PREFIX` trailing dot deserves a short inline comment.

**TASK-006 — CourseEditorPage decomposition: APPROVE → done.**
Current branch state has 22 files under `frontend/src/pages/admin/course-editor/`
plus a 235-line orchestrator. Largest file is `useCourseForm.ts` at
399 — every file ≤ 399. App.tsx lazy-loads `CourseEditorPage` across
4 routes (`courses/new`, `courses/:courseId/edit`, `authoring/new`,
`authoring/:courseId/edit`) — all resolve. Spot checks: video upload
(`useVideoUpload.ts`), add content (`AddContentForm.tsx` +
`useContentState.ts`), assign teacher (`assigned_teachers` in
`useCourseForm.ts` / `CourseBasicInfo.tsx`) all preserved. Note: the
worktree snapshot `agent-a0a7365e` lists four files > 400 lines
(`ModuleContentEditor.tsx` 597, `useAssignmentState.ts` 533,
`useContentState.ts` 517, `CourseEditorPage.tsx` 480) — that's an older
state; the live branch is the authoritative reference and satisfies the
bar.

**TASK-012 — Frontend cleanup: APPROVE → done.**
All deltas live only in worktree `agent-a0a7365e` (locked, not merged).
`sonner ^1.5.0` added to `frontend/package.json` (addition, not install).
`src/hooks/useToast.ts` re-exports the existing custom `useToast` from
`components/common/Toast`; `ToastProvider` already mounted at
`App.tsx:649`. Three `window.confirm` sites migrated to `ConfirmDialog`
(`ChatbotListPage`, `MAICLibraryPage`, `ChatPanel`). LoginPage already
on RHF+Zod via `useZodForm`. No new `console.log` — only match is the
intentional template-content string in `SlideEditor.tsx`. Minor:
`sonner` is imported-as-dep without a `<Toaster />` mount yet (staged);
4 `window.confirm` sites remain (not required by spec).

**Top finding across all three:** task specs' worktree paths are
drifting — spec-claimed paths `agent-a76b067d` and
`agent-a03856432bd242f22` don't exist; real work for TASK-005 is on
`maic-sprint-1-presence-rhythm`, and TASK-012 lives only in the
locked `agent-a0a7365e` worktree that still needs to be merged for
CI to see the `sonner` dependency. Coordinator should reconcile
`Status/Assigned/Worktree` metadata before the next review cycle.

### Reviewer — TASK-008 rework (2026-04-20)

**Verdict: APPROVE → done.** Both paths emit the same canonical
`{"error": str, "details?": [{field, message}], "code?": str}` shape.
Verified:

- `exception_handler.py` L128-171: system errors → flat string + code
  (minus generic `"invalid"/"error"`); field ValidationError →
  flattened `details`; list/non-dict fallbacks handled; non-DRF
  exceptions return None.
- `responses.py::error_response` L60-99: `error` is always a plain
  string, `details` present only when `field_errors` truthy, `code`
  and `**extra` promoted to top level (not nested under `error`).
- 3 call-site spot checks (`billing/views.py`, `reports/views.py`,
  `courses/teacher_views.py`) all pass plain-string messages —
  backward-compat clean; 15 importers total.
- Tests: 21 in `test_exception_handler.py` + 20 in `test_responses.py`
  (claim of ~40 holds). Assertions target shape invariants, not
  implementation. Status codes (401/403/404/405/429) and DRF codes
  (`not_authenticated`, `not_found`) verified.
- Frontend: `extractErrorMessage` prefers canonical `data.error` string
  with legacy `detail`/`message` fallbacks; new `extractErrorDetails`
  reads `data.details[]` defensively. Both safe against any
  transition-period shape.
- Settings wiring at `config/settings.py:316` correct.

No blockers. Non-blocking note: the `detail` legacy fallback in the
FE helper can be removed once TASK-012 confirms no producer still
emits the old shape.

---

## 2026-04-22 — DevOps Agent — Inbox Triage + CI Gate Confirmation

**Agent:** devops

### Inbox messages processed

Two messages found in `_coordination/inbox/devops/`:

1. `REVIEW-VERDICT-DOCKERFILE-COPY-FIX-2026-04-21.md` — Reviewer APPROVED the
   `nginx/Dockerfile` COPY fix (adds `nginx/includes/` + `nginx/proxy_params` to the
   image). One non-blocking ask: run `docker build -f nginx/Dockerfile -t lms-nginx-test .
   && docker run --rm lms-nginx-test nginx -t` and paste the success line here.

2. `BE-SEC-P0-CI-GATE-ASK-2026-04-21.md` — Reviewer asks whether CI runs the **full**
   backend pytest matrix so the four P0 regression test files are automatically gated.

---

### CI Gate — Full Matrix Confirmed ✅

**Reviewer ask:** confirm `backend/tests/test_contextvars_isolation.py`,
`backend/tests/test_cors_headers.py`, `backend/tests/webhooks/test_webhook_views.py`,
and `backend/tests/test_webhook_ssrf.py` are included in every CI run.

**Findings:**

| Check | Evidence |
|-------|---------|
| `testpaths = ["tests", "apps"]` in `backend/pyproject.toml` | Tests discovered from BOTH `backend/tests/` AND `backend/apps/` — no path filter |
| CI command: `pytest --cov=apps --cov=utils --cov=config ... -v` (no path arg) | Runs **everything** that pytest discovers via `testpaths` |
| `test_contextvars_isolation.py` exists | `backend/tests/test_contextvars_isolation.py` ✅ |
| `test_cors_headers.py` exists | `backend/tests/test_cors_headers.py` ✅ |
| `webhooks/test_webhook_views.py` exists | `backend/tests/webhooks/test_webhook_views.py` ✅ |
| `test_webhook_ssrf.py` exists | `backend/tests/test_webhook_ssrf.py` ✅ |
| Coverage threshold | CI env `COV_FAIL_UNDER: "60"` overrides `pyproject.toml` `fail_under = 45` via `--cov-fail-under` CLI flag |

**Answer:** CI runs the full matrix — all four P0 regression test modules are
automatically included in every `backend-test` CI job (both PR and push). No CI
config change needed.

---

### Dockerfile COPY Fix — Approval Acknowledged

Reviewer APPROVE received for the two-line fix in `nginx/Dockerfile` (commit date
2026-04-21). Fix bakes `nginx/includes/` and `nginx/proxy_params` into the image so it
starts cleanly without volume mounts (smoke tests, k8s without config maps, etc.).
Production behaviour unchanged — runtime volume mounts still override the baked-in files.

**Smoke test status:** Docker is not available in this sandbox (same constraint as the
original PR). Static verification is complete and confirmed by the reviewer. The smoke
test (`docker build -f nginx/Dockerfile -t lms-nginx-test . && docker run --rm
lms-nginx-test nginx -t`) must be run by a human or CI on a Docker-capable machine
before the next nginx image push. The reviewer confirmed this is **not gating merge** —
the failure mode is deterministic given the Dockerfile + repo layout.

Once Docker is available, the expected output is:
```
nginx: the configuration file /etc/nginx/conf.d/default.conf syntax is ok
nginx: configuration file /etc/nginx/conf.d/default.conf test is successful
```

### Outstanding follow-ups (carried forward)

1. **Smoke test:** Run `docker build -f nginx/Dockerfile -t lms-nginx-test . &&
   docker run --rm lms-nginx-test nginx -t` when Docker is available and paste
   `configuration file … test is successful` here. (Human or CI task — sandbox blocked.)
2. **TASK-010:** Actual pytest coverage run still pending Docker. Estimated 58–62% from
   prior session; CI will gate at 60%.
3. **CSP tightening** (deferred from 2026-04-20): `production.conf` still has
   `unsafe-inline`/`unsafe-eval` in `script-src`; deferred to a frontend security pass.

---

## 2026-04-24 — DevOps Agent Infrastructure Hardening

**Agent:** devops

### Task Audit: Phase 1/2/3 Status

All Phase 1 and Phase 2 DevOps tasks confirmed **complete** from prior sessions:

| Task | Status | Evidence |
|------|--------|---------|
| `pg_isready` default user fix | ✅ done | `docker-compose.prod.yml` L22: `${DB_USER:-learnpuddle}` |
| Redis password enforcement | ✅ done | `${REDIS_PASSWORD:?Set REDIS_PASSWORD in .env}` in prod + staging |
| Nginx IP restrictions (metrics/flower) | ✅ done | `shared_locations.conf` L183-210, `production.conf` L96-123, `nginx.staging.conf` L181-209 |
| `USER nginx` in nginx Dockerfile | ✅ done | `nginx/Dockerfile` L42 |
| Docker log rotation | ✅ done | `x-common` anchor in prod; `x-logging` in staging |
| E2E tests blocking in CI | ✅ done | `e2e-test` job with `E2E_SKIP_BLOCKING` bypass |
| Coverage threshold 60% | ✅ done | `COV_FAIL_UNDER: "60"` env var in CI |
| Rollback strategy | ✅ done | Both prod and staging deploy jobs with `.deployed-sha` tracking |
| Celery worker healthcheck | ✅ done | `celery inspect ping` healthcheck in prod + staging worker |
| nginx.conf HTTP/HTTPS deduplication | ✅ done | `nginx/includes/shared_locations.conf` included by both blocks |
| `client_max_body_size` 10M global / 512M video-only | ✅ done | L34 `shared_locations.conf`, L140 video upload override |
| Backup integrity verification | ✅ done | `scripts/backup-db.sh`: `gunzip -t` + header check |
| Notification archival 90-day TTL | ✅ done | TASK-009 complete (backend-engineer) |

### Changes Made This Session

**1. `docker-compose.prod.yml` — Add `asgi` healthcheck (gap: no healthcheck existed)**

The Daphne ASGI server (port 8001) had no Docker healthcheck while every other service
did. Docker couldn't detect Daphne crash/hang; nginx WebSocket proxy would silently fail.

Added socket-based healthcheck (same pattern as `web` service):
```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c \"import socket; s=socket.socket(); s.settimeout(5); s.connect(('127.0.0.1',8001)); s.close()\""]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

**2. `docker-compose.prod.yml` — Improve nginx healthcheck (gap: config-only check)**

The nginx healthcheck `["CMD", "nginx", "-t"]` only validates config file syntax (reads
from disk) — it does NOT detect a crashed nginx process. `nginx -t` succeeds even if
the nginx daemon is not running.

Changed to:
```yaml
test: ["CMD-SHELL", "nginx -t 2>/dev/null && pidof nginx > /dev/null 2>&1"]
```

Combined config validation + process liveness check.

**3. `.github/dependabot.yml` — Add nginx/ and frontend/ Dockerfile monitoring**

Dependabot was only monitoring `/backend` for Docker base image updates. Both
`nginx/Dockerfile` (uses `node:18-alpine` + `nginx:1.25-alpine`) and
`frontend/Dockerfile` (uses `node:18-alpine` + `nginx:1.25-alpine`) were
invisible to Dependabot — security patches to those base images would be missed.

Added two new `docker` ecosystem entries for `/nginx` and `/frontend`.

**4. `backend/docker-compose.yml` — Add log rotation to dev environment**

Dev docker-compose had no log rotation. Long dev sessions (video processing, Celery
task testing) can produce large log files that fill developer disk space.

Added `x-logging: &default-logging` anchor (10M/3 files) and applied to all
four services (db, redis, minio, ollama).

### Files Modified
- `docker-compose.prod.yml`
- `backend/docker-compose.yml`
- `.github/dependabot.yml`

### Verification
- YAML syntax verified via manual review; all changes follow patterns already used in
  `docker-compose.staging.yml` (asgi healthcheck, x-logging anchor).
- Docker not available in this sandbox — runtime smoke test must be confirmed by CI.

### Outstanding Follow-Ups (Carried Forward)
1. **Docker smoke test** (from 2026-04-21): `docker build -f nginx/Dockerfile -t lms-nginx-test . && docker run --rm lms-nginx-test nginx -t` — pending human/CI run.
2. **TASK-010**: Coverage ≥ 60% — pending `pytest --cov` run with Docker.
3. **CSP tightening**: `unsafe-inline`/`unsafe-eval` in `script-src` — frontend security pass.

---

## 2026-04-30 — Coordinator session 2 — hold-state confirmation (no-op)

**Agent:** coordinator (in-session; specialist subagents not registered in this harness — only `general-purpose`/`Explore`/`Plan` exposed).

Second pickup the same day. Drift-check vs. yesterday's hand-off:
- `git status --short` → **230** changes (unchanged).
- HEAD still at `ffa08fc` (CG-P1-13 pause-mid-fetch race).
- TASK-013 closeout files (`gamification_signals.py` +12 / `tests_gamification_signals.py` +32) match yesterday's writeup byte-for-byte.

**No actionable unblocked work remains.** All P0/P1 in `tasks/_BACKLOG.md` are ✅ Done. The wave 5–9 bundle is commit-ready and held on three explicit user-blocked items: (1) F6 browser-DevTools manual cert, (2) CG-P1-15 Option A/B/C decision, (3) Wave 5–9 commit (user controls all git writes per hard rule). Four known-RED tests in `tests/courses/test_image_fill_dedup.py` are gated on item (2) and are not regressions.

**Output:** documentation only — coordinator hold-state section in `~/ObsidianVault/learnpuddle-lms/daily/2026-04-30.md` and this entry. Zero git operations, zero production code edits, zero test runs.

