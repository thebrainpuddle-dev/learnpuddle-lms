---
tags: [review, working-tree, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-03-25
---

# Review: Working Tree Changes — Security Hardening, Tenant Isolation & Performance

## Scope: All uncommitted changes on `main` working tree
## Files Changed: 36 (backend: 19, frontend: 14, infra: 3)
## Verdict: REQUEST_CHANGES

---

## Summary

This is a **high-quality, security-critical changeset** that addresses the most important architectural gap in the platform: missing tenant isolation on the `progress` app models. It also delivers meaningful security hardening (webhook fail-closed, SSRF fix, CORS tightening, password validation, rate limiting), performance improvements (N+1 query elimination, ASGI-safe context vars), and frontend modernization (React.lazy code splitting, error boundary per route). The work is well-structured and demonstrates strong understanding of the platform's multi-tenancy requirements.

**However, there are 3 major issues that must be resolved before merging:** a model-migration state mismatch that will break `makemigrations`, debug logging left in production code, and a `get_or_create` backward compatibility risk with existing data.

---

## Critical Issues

None.

---

## Major Issues

### 1. MODEL-MIGRATION MISMATCH: 6 models declare NOT NULL but migration adds null=True

**Files**: `backend/apps/progress/models.py` vs `backend/apps/progress/migrations/0009_add_tenant_isolation_to_progress_models.py`

The migration correctly adds tenant FK as `null=True` for backward compatibility with existing data. **However**, 6 of 7 model definitions declare the field as NOT NULL (no `null=True`):

| Model | Model has null=True? | Migration has null=True? | Mismatch? |
|-------|---------------------|-------------------------|-----------|
| TeacherProgress | Yes | Yes | No |
| Assignment | **No** | Yes | **YES** |
| Quiz | **No** | Yes | **YES** |
| QuizQuestion | **No** | Yes | **YES** |
| QuizSubmission | **No** | Yes | **YES** |
| AssignmentSubmission | **No** | Yes | **YES** |
| TeacherQuestClaim | **No** | Yes | **YES** |

**Impact**:
- Running `python manage.py makemigrations` will detect this drift and generate a new migration to ALTER COLUMN SET NOT NULL on 6 tables
- If CI runs `makemigrations --check`, it will **fail**
- If that auto-generated migration runs before existing rows are backfilled, it will crash with `IntegrityError`

**Fix**: Either:
- **(A) Recommended**: Add `null=True, blank=True` to all 6 model ForeignKey declarations to match the migration (same as TeacherProgress). Then create a separate "Phase 2" migration later to remove null=True after backfill.
- **(B)** Add a data migration step within 0009 that backfills tenant from the parent (e.g., `assignment.tenant = assignment.course.tenant`) and then remove null=True from both model and migration.

### 2. DEBUG LOGGING LEFT IN PRODUCTION CODE

**Files**: `backend/utils/tenant_soft_delete_manager.py` (line 19), `backend/utils/tenant_middleware.py` (lines 58, 86, 90)

```python
_debug_log.warning('[DBG-TSDM] filter_by_tenant: model=%s tenant=%s(%s)', ...)
_debug_log.warning('[DBG-MW] path=%s host=%s method=%s user=%s', ...)
```

These emit `WARNING`-level log messages **on every single request** and every queryset evaluation. In production:
- This will flood logs (hundreds of lines per page load)
- WARNING level means they'll appear in default log configurations
- The `[DBG-...]` prefix confirms these are temporary debug statements

**Fix**: Remove all `_debug_log.warning('[DBG-...')` calls and the associated logger setup. If structured request logging is needed, use Django's built-in request logging middleware at DEBUG level.

### 3. `get_or_create` BACKWARD COMPATIBILITY WITH EXISTING NULL-TENANT ROWS

**Files**: `backend/apps/courses/tasks.py` (lines 830, 851, 865), `backend/apps/progress/teacher_views.py` (lines 260, 295, 378, 470, 669)

All `get_or_create` calls now include `tenant=request.tenant` (or `tenant=course.tenant`) as a **lookup field**, not in defaults:

```python
Assignment.objects.get_or_create(
    tenant=course.tenant,  # lookup field
    course=course,
    module=module,
    content=content,
    assignment_type='REFLECTION',
    defaults={...}
)
```

If existing rows have `tenant=NULL` (from before this migration), the lookup `WHERE tenant_id = X AND ...` will **not match** those rows (because `NULL != X` in SQL). This means:
- `get_or_create` will try to **create a duplicate** instead of finding the existing record
- This could violate unique constraints or create orphaned duplicate data

**Fix**: Either:
- **(A)** Include a data migration that backfills tenant values on existing rows before this code runs
- **(B)** Move `tenant` to `defaults` dict (not a lookup field) — but this weakens tenant isolation on creates
- **(C)** Add a backfill management command and document it as a required deploy step

---

## Minor Issues

### 4. ErrorBoundary console.error removal loses error visibility

**File**: `frontend/src/components/common/ErrorBoundary.tsx`

```diff
- console.error('ErrorBoundary caught an error:', error, errorInfo);
```

This was the **only** place caught React errors were logged. Without a reporting service (Sentry), errors caught by the ErrorBoundary now vanish silently. The Sentry DSN is optional in the env config.

**Recommendation**: Keep the `console.error` or add conditional logging:
```typescript
if (import.meta.env.DEV) {
  console.error('ErrorBoundary caught an error:', error, errorInfo);
}
```

### 5. Silent catch blocks throughout frontend hooks

**Files**: `useAuthBlobUrl.ts`, `useNotifications.ts`, `usePWA.ts`, `theme.ts`, sidebars

Many `catch` blocks now have empty bodies or only comments. While removing `console.error` from production is good, some of these suppress actionable errors:
- `useAuthBlobUrl`: Failed blob fetch → user sees broken image, no diagnostics
- `usePWA`: Service worker registration failure → no visibility into offline mode issues
- `useNotifications`: WebSocket parse error → no way to debug notification issues

**Recommendation**: Consider a lightweight error reporting utility (`reportError(error, context)`) that uses Sentry in production and console in development.

### 6. HLS CORS fallback is permissive

**File**: `backend/apps/courses/video_views.py` (lines 370-377)

The new CORS logic has a good primary path (tenant subdomain origin). But the fallback:
```python
allowed_origin = request.headers.get("Origin", "")
request_host = request.get_host()
if allowed_origin and not allowed_origin.endswith(request_host):
    allowed_origin = f"https://{request_host}"
```

`endswith(request_host)` could match unintended origins. For example, if `request_host` is `learnpuddle.com`, then `evil-learnpuddle.com` would pass. Use exact match or proper domain validation.

### 7. Missing `Vary: Origin` in non-HLS responses

The `Vary: Origin` header was added to HLS responses (good), but if any other CORS-dependent responses exist without it, caching proxies could serve wrong CORS headers.

### 8. TeacherProgress model has null=True but no backfill plan documented

While the migration comment mentions backfill, there's no management command or documented deploy step. This should be tracked as a follow-up task.

### 9. Coverage threshold jump from 35% to 60%

**File**: `.github/workflows/ci.yml`

This is a 71% relative increase. If current test coverage is between 35-60%, this will immediately **break CI** on the next push. Verify current coverage level before merging.

### 10. `any` type in CertificateButton catch block

**File**: `frontend/src/components/teacher/CertificateButton.tsx` (line 62)
```typescript
} catch (err: any) {
```
Per review checklist: TypeScript types should be strict (no `any`). This is pre-existing but touched in this change — consider fixing to `unknown`.

---

## Positive Observations

### Security
1. **Tenant isolation on progress models** is the single most impactful security improvement possible — this was the biggest gap in the multi-tenancy architecture. Every progress model now has TenantManager + tenant FK + proper indexes. Excellent.
2. **Cal.com webhook fail-closed** (reject when secret not configured) is the correct security posture. The previous fail-open was a real vulnerability.
3. **SSRF validation on webhook PUT** closes a bypass where POST was validated but PUT was not.
4. **Django password validation** on invitation accept and admin password reset replaces the weak `len >= 8` check with proper validators (common password lists, similarity checks, etc.)
5. **Rate limiting on invitation accept** prevents brute-force attacks on the public endpoint.
6. **HLS CORS tightening** from `*` to tenant-specific origin prevents cross-origin video theft.
7. **Nginx `client_max_body_size 10M` default** with 512M only for video uploads is defense-in-depth against oversized payloads.
8. **Nginx non-root user** in Dockerfile is a container security best practice.
9. **Redis password now required** (`${REDIS_PASSWORD:?...}`) — no more silent fallback to "changeme" in production.

### Performance
10. **N+1 query elimination** via `annotate(_module_count, _content_count)` with `distinct=True` and serializer-level `hasattr(obj, '_content_count')` fallback is the correct DRF pattern. Well implemented.
11. **Prefetched M2M usage** in `get_assigned_teacher_count` avoids extra queries per course row.
12. **`threading.local()` → `contextvars.ContextVar`** is the right fix for ASGI/Channels compatibility. This prevents tenant leaking across coroutines sharing the same thread.

### Testing
13. **450+ lines of new course tests** covering auth, CRUD, cross-tenant isolation, model behavior, soft-delete, publish/unpublish flows, and module creation. These are well-structured, use proper `override_settings`, and test security-critical paths.
14. **Cross-tenant isolation tests** specifically verify that admin B cannot see, access, or delete admin A's courses — exactly the right tests.

### Infrastructure
15. **CI auto-rollback on deployment failure** with SHA tracking is production-grade deployment safety.
16. **E2E tests now blocking** (removed `continue-on-error: true`) enforces quality gates.
17. **Celery worker health check** (was `disable: true`) provides operational visibility.
18. **JSON-file logging with rotation** prevents disk exhaustion from uncontrolled log growth.

### Frontend
19. **React.lazy code splitting** with proper `Suspense` + `PageErrorBoundary` per route is the standard React 18+ performance pattern. Every lazy import uses `.then(m => ({ default: m.NamedExport }))` correctly.
20. **`alert()` → `toast.error()`** in SkipRequestsPage and CourseViewPage is a UX improvement.
21. **"Coursera Honor Code" → "Academic Integrity Pledge"** removes third-party branding reference.
22. **RegisterTeacherSerializer** `create_user()` fix removes the redundant `set_password + save` pattern, which was both wasteful and risked double-hashing.

### Code Quality
23. Consistent use of `TenantSoftDeleteManager` for models that combine soft-delete with tenant isolation — clean separation of concerns.
24. Migration 0009 is well-organized with clear section headers and proper index replacements (old non-tenant indexes removed, new tenant-scoped indexes added).

---

## Required Changes Before Merge

| # | Priority | Issue | Action |
|---|----------|-------|--------|
| 1 | **HIGH** | Model-migration null mismatch | Add `null=True, blank=True` to 6 model FK definitions to match migration |
| 2 | **HIGH** | Debug logging in production | Remove all `_debug_log.warning('[DBG-...')` calls |
| 3 | **MEDIUM** | get_or_create backward compat | Add backfill management command or data migration; document deploy step |
| 4 | **LOW** | ErrorBoundary error visibility | Restore console.error in dev mode or add error reporting |
| 5 | **LOW** | Verify CI coverage threshold | Confirm current coverage >= 60% before merging |

---

## Recommended Merge Strategy

1. Fix issues #1 and #2 (quick fixes, < 30 minutes)
2. Create backfill management command for issue #3 (or add as documented deploy step)
3. Verify coverage threshold won't break CI
4. This changeset should be committed as **2-3 focused commits**:
   - `security: add tenant isolation to progress models with migration`
   - `security: harden webhooks, CORS, password validation, and nginx config`
   - `perf: N+1 query fix, React.lazy code splitting, ASGI-safe context vars`
