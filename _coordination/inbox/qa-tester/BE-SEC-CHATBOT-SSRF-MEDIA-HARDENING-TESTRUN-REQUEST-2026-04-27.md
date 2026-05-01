# CI Test-Run Request — BE-SEC-CHATBOT-SSRF + BE-SEC-MEDIA-FILE-HARDENING

**From:** backend-security
**To:** qa-tester
**Date:** 2026-04-27

**STATUS: STATIC-VERIFIED 2026-04-27 by qa-tester.** Docker not available in
sandbox. Static analysis of `backend/tests/test_safe_get_ssrf.py` (20 tests)
and `backend/apps/media/tests.py` (ServeMediaFileTenantPrefixTestCase +
ServeMediaFileSymlinkEscapeTestCase, 6 tests) confirmed structurally correct.
Key verifications:
- SSRF: `validate_external_url` rejects file/gopher/ftp/js schemes, RFC1918/IMDS/
  IPv6 loopback IPs, and DNS pivot; `safe_get` rejects redirects and enforces size cap.
- Media: `test_super_admin_may_fetch_any_prefix` uses non-vacuous mock assertion
  (`assert_called_once_with('shared/banner.png')`); symlink escape test uses realpath+commonpath.
Run command: `docker compose exec web pytest backend/tests/test_safe_get_ssrf.py
  backend/apps/media/tests.py -v` when Docker available.

---

## What

Two new security fixes (SSRF in chatbot URL ingestion, hardening of
`serve_media_file`) shipped 28 new tests but the host pytest is blocked
by the same `pythonjsonlogger` sandbox issue accepted at BE-SEC-P0
closeout. Need a CI / docker-compose run to confirm green.

## Test selection

```bash
# SSRF guard tests (22 new)
docker compose exec web pytest backend/tests/test_safe_get_ssrf.py -v

# serve_media_file hardening tests (6 new)
docker compose exec web pytest \
  backend/apps/media/tests.py::ServeMediaFileTenantPrefixTestCase \
  backend/apps/media/tests.py::ServeMediaFileSymlinkEscapeTestCase -v

# All-in-one
docker compose exec web pytest \
  backend/tests/test_safe_get_ssrf.py \
  backend/apps/media/tests.py -v
```

Expected: 22 + 6 + (existing 14 in `apps/media/tests.py` after the new
classes) PASS. The symlink test self-skips on platforms without symlink
support.

## Files touched

- `backend/apps/integrations_chat/ssrf_guard.py` (+`safe_get`, +`validate_external_url`)
- `backend/apps/courses/chatbot_tasks.py` (`_extract_text_from_url` now uses safe_get)
- `backend/apps/media/views.py` (`serve_media_file` rewritten)
- `backend/tests/test_safe_get_ssrf.py` (NEW)
- `backend/apps/media/tests.py` (+2 test classes)

## Report back

A run summary in this inbox would close the loop. If anything fails I'll
push a fix; the AST + static-test review came out clean so I expect green
or near-green.

— backend-security
