# FYI — P1 finding handed to backend-engineer: OAuth state CSRF

**From**: backend-security
**To**: reviewer
**Date**: 2026-04-20

Heads up: during today's ongoing P1/P2 audit I found an OAuth CSRF gap in
the calendar connect flow. Full write-up at
`_coordination/inbox/backend-engineer/BE-SEC-P1-OAUTH-STATE-CSRF.md`.

## Why this note

- I did **not** write the fix — calendar views are outside my hard
  file-ownership list (`tenant_middleware.py`, `tenant_manager.py`,
  `users/serializers.py`, `nginx/`, `docker-compose.prod.yml`).
- I did **not** commit anything (per backend-security no-git-write rule).
- The handoff to backend-engineer includes a TDD test plan and a minimal
  fix shape (server-side state cache + single-use consumption + full
  MSAL flow-dict persistence for Outlook).

## Severity call

P1 (High). Requirements for exploitation:
1. Attacker has an account at Google / Microsoft (trivial).
2. Attacker can get a victim-admin's browser to hit
   `/api/v1/calendar/{provider}/callback/?code=X&state=Y` while
   authenticated (e.g. malicious email link, XSS on any *.learnpuddle.com
   subdomain, or an IDN phishing lookalike).

Post-exploitation the attacker receives a live feed of the victim tenant's
course schedule via their own calendar and keeps a working refresh token.

## No action required from you yet

Just a heads-up so you're not surprised when backend-engineer opens a
review request under the `BE-SEC-P1-OAUTH-STATE-CSRF` tag. I'll watch my
inbox for their ack.

## Other audit findings today

None. I scanned:

- `backend/apps/integrations_chat/` — SSRF guard is correct (allowlist +
  RFC1918 rejection + DNS pin via transport adapter). Views are
  `@admin_only @tenant_required` consistently. Nothing to escalate.
- `backend/apps/courses/scorm_views.py` — explicitly hardened (`defusedxml`
  for XXE, `_safe_join` + `_safe_extract_zip` for zip-slip and decompression
  bombs, per-user-per-package rate limit on commits, tenant isolation via
  `TenantManager`). Looks correct.
- `backend/apps/reports_builder/query_engine.py` — header comment
  declares "No dynamic eval, no .extra(), no raw SQL"; whitelisted sources,
  whitelisted fields, whitelisted operators, ROW_CAP fail-closed. Clean.

— backend-security
