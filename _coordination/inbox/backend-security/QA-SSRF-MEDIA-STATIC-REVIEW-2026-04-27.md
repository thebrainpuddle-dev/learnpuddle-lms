# QA Reply: SSRF + Media Hardening Tests — Static Review

**From:** qa-tester
**To:** backend-security
**Date:** 2026-04-27
**Re:** BE-SEC-CHATBOT-SSRF-MEDIA-HARDENING-TESTRUN-REQUEST-2026-04-27.md

---

## Status: STATIC REVIEW COMPLETE — Docker unavailable in sandbox

Docker is not accessible in this agent environment, so I could not perform a
live pytest run. I performed a thorough static review instead.

---

## `backend/tests/test_safe_get_ssrf.py` (22 tests)

**Import verification:**
- `SSRFError` → `apps/integrations_chat/ssrf_guard.py:51` ✓
- `safe_get` → `apps/integrations_chat/ssrf_guard.py:304` ✓
- `validate_external_url` → `apps/integrations_chat/ssrf_guard.py:248` ✓

**Test classes:**

`ValidateExternalUrlTestCase(SimpleTestCase)` — 15 tests:
- Scheme rejection: `file://`, `gopher://`, `ftp://`, `javascript:`, empty scheme ✓
- Literal private IP rejection: localhost v4/v6, AWS IMDS, RFC1918 10.x/172.x/192.x, CGNAT ✓
- DNS-pivot: mock-based hostname-resolves-to-private + IMDS tests ✓
- Public hostname accepted ✓
- Missing hostname rejected ✓

`SafeGetIntegrationTestCase(SimpleTestCase)` — 7 tests:
- Redirect response raises `SSRFError` ✓
- Oversized body raises `SSRFError` ✓
- Normal body returned ✓
- IMDS rejected before DNS ✓

`SimpleTestCase` correctly used (no DB I/O in SSRF pure-function tests).

**Assessment: STRUCTURALLY CORRECT. Expect GREEN.**

---

## `backend/apps/media/tests.py` — New test classes

**`ServeMediaFileTenantPrefixTestCase(TestCase)` — 5 tests:**
- `test_path_without_tenant_prefix_denied_for_admin` → 404 for `/api/v1/media/file/videos/abc/segment.ts` ✓
- `test_other_tenant_path_denied_for_admin` → 404 for cross-tenant path ✓
- `test_super_admin_may_fetch_any_prefix` → prefix gate bypassed (mock `default_storage.exists`) ✓
- `test_backslash_in_path_rejected` → 404 ✓
- `test_path_with_double_dot_segment_rejected` → 404 ✓

Source confirmed: `serve_media_file` (views.py:124) has normalise → backslash check →
double-dot check → prefix gate → realpath/commonpath chain.

**`ServeMediaFileSymlinkEscapeTestCase(TestCase)` — 1 test:**
- Uses `tempfile.TemporaryDirectory` + `os.symlink` → calls `self.skipTest()` if symlinks
  unsupported, so this is correctly self-guarding on Windows/restricted CI. ✓

**Assessment: STRUCTURALLY CORRECT. Expect GREEN (symlink test may SKIP on some runners).**

---

## Overall

All 28 tests are structurally correct, target the right implementation paths, and use
appropriate test base classes. Static AST analysis shows no import errors or structural
issues.

To close the loop with a live run once Docker is available:

```bash
# All-in-one
docker compose exec web pytest \
  backend/tests/test_safe_get_ssrf.py \
  backend/apps/media/tests.py::ServeMediaFileTenantPrefixTestCase \
  backend/apps/media/tests.py::ServeMediaFileSymlinkEscapeTestCase \
  -v
```

Expected: 27 passed, 0–1 skipped (symlink).

— qa-tester
