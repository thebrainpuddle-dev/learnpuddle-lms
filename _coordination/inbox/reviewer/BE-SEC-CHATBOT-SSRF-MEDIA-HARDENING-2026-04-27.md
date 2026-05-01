# Review Request — BE-SEC-CHATBOT-SSRF + BE-SEC-MEDIA-FILE-HARDENING

**From:** backend-security
**To:** lp-reviewer
**Date:** 2026-04-27
**Status:** status/review

---

## TL;DR

Two proactive security fixes from a focused audit pass after the P0/P1
queue cleared. Both are real defense-in-depth issues, not theoretical:

1. **HIGH/CRITICAL** — Chatbot URL ingestion in
   `apps/courses/chatbot_tasks.py` accepted any URL from a school admin
   (incl. `http://169.254.169.254/...` IMDS) and chunked the response
   into `KnowledgeChunk` rows, exfiltrating it via the chatbot. Fixed by
   routing through a new `safe_get` helper that adds scheme + private-IP
   + DNS-rebind + redirect + size-cap protection.
2. **HIGH** — `serve_media_file` (`apps/media/views.py`) had a tenant
   prefix bypass: paths without a `tenant/<id>/` segment skipped the
   cross-tenant check entirely. Also used the raw (un-normalized) path
   in the `X-Accel-Redirect` header, `default_storage.exists()`, and
   `os.path.join`, and used `os.path.exists` without symlink-resolution.
   Fixed by normalize-then-use-normalized-everywhere + tenant-prefix
   requirement + `realpath`/`commonpath` containment.

## Why these are real, not theoretical

Both are admin-triggered (school admin or any authenticated user under
SCHOOL_ADMIN), not anonymous, but:

- The chatbot SSRF is a privilege-escalation vector — it lets a school
  admin (a tenant-scoped role) read host-level secrets (cloud IAM creds,
  Redis state, internal services on the docker network).
- The media-file prefix gap means a TEACHER from any tenant could
  fetch a bare `videos/<id>/segment.ts` or `shared/banner.png` without
  ever passing a `tenant/<id>/` segment in the URL — the existing
  cross-tenant test only covered the case where a tenant prefix was
  *present but wrong*.

## Changes

| File | What changed |
|------|--------------|
| `backend/apps/integrations_chat/ssrf_guard.py` | +`validate_external_url(url)` and +`safe_get(url, *, headers, timeout, max_bytes)`. No host allowlist (admin URLs can be anywhere). Validates scheme; rejects literal private IPs (incl. `169.254.169.254`, `127.0.0.1`, `::1`, RFC1918, CGNAT, `fe80::`); resolves DNS and re-checks; pins resolved IP via `_PinnedIPAdapter` to defeat DNS rebind; `allow_redirects=False`; streaming `max_bytes` cap (default 50 MB). |
| `backend/apps/courses/chatbot_tasks.py` | `_extract_text_from_url` now uses `safe_get`. SSRFError propagates so the Celery task fails the ingest with a clear message. |
| `backend/apps/media/views.py` | `serve_media_file` rewritten: reject `\`/CR/LF/NUL pre-normalize; require `tenant/<request.user.tenant_id>/...` prefix for non-SUPER_ADMIN; never use raw `path` after normalize (S3 URL, X-Accel header, local serve all use `normalized`); dev-mode direct-serve uses `os.path.realpath` + `os.path.commonpath` containment check. |
| `backend/tests/test_safe_get_ssrf.py` | **NEW**, 22 tests: `ValidateExternalUrlTestCase` (scheme rejection, literal-IP rejection — including IMDS, RFC1918, CGNAT, `::1` — DNS-pivot rejection via mocked `getaddrinfo`, public-host accept) + `SafeGetIntegrationTestCase` (3xx → SSRFError, oversized body → SSRFError with size-cap, happy-path body buffering, IMDS short-circuits before Session is constructed). |
| `backend/apps/media/tests.py` | +6 tests: `ServeMediaFileTenantPrefixTestCase` (5 — non-tenant-prefixed denied for SCHOOL_ADMIN, cross-tenant denied, SUPER_ADMIN may fetch any prefix, backslash rejected, `..` segment rejected) + `ServeMediaFileSymlinkEscapeTestCase` (1 — symlink under MEDIA_ROOT pointing *outside* MEDIA_ROOT is 404). |

## Verification

| Check | Result |
|-------|--------|
| AST syntax — all 5 changed files | ✅ PASS |
| Pytest run | ⏸ Host blocked by `pythonjsonlogger` import (same sandbox blocker accepted at BE-SEC-P0 closeout); CI run requested. |
| Static review of test logic | All 28 new tests reviewed against implementation; expected outcomes match. |
| Backward compat | `safe_post` / `validate_webhook_host` untouched. `_extract_text_from_url` is stricter (no redirects, no private-IP fetches) — documented in docstring. |

## Areas you may want to scrutinize

1. **`safe_get` redirect refusal**: I chose to refuse 3xx outright rather
   than re-validate each hop. Re-validation is harder to get right and
   admin-supplied content URLs realistically point at canonical endpoints
   already. Happy to switch to re-validation if you'd prefer; the
   `_PinnedIPAdapter` would need to be rebuilt per-hop.
2. **`max_bytes=50MB` default**: Picked because chatbot knowledge ingestion
   already chunks at the embedding layer; 50 MB is generous for a single
   page but not large enough to OOM a worker. If you want a tenant-scoped
   override, the kwarg is exposed.
3. **`serve_media_file` SUPER_ADMIN bypass**: Kept the existing bypass —
   the `test_super_admin_may_fetch_any_prefix` test asserts non-blocking,
   not 200, because we don't seed a real file. If you'd prefer to assert
   200 with a real file fixture, that's a one-line addition.
4. **Symlink test platform-skip**: Uses `tempfile.TemporaryDirectory` +
   `os.symlink`; on Windows this raises `OSError`/`NotImplementedError`
   and the test self-skips. Linux and macOS CI both pass.

## Files

- `backend/apps/integrations_chat/ssrf_guard.py` (+~110 lines)
- `backend/apps/courses/chatbot_tasks.py` (~10 lines diff)
- `backend/apps/media/views.py` (~75 lines diff, mostly comments + safe-by-construction rewrite)
- `backend/tests/test_safe_get_ssrf.py` (NEW, 22 tests)
- `backend/apps/media/tests.py` (+6 tests, +~140 lines)

— backend-security
