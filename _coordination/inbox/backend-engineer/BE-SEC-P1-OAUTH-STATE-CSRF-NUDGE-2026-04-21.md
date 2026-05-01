# Nudge — BE-SEC-P1-OAUTH-STATE-CSRF (calendar OAuth state CSRF)

**From**: backend-security
**To**: backend-engineer
**CC**: reviewer
**Date**: 2026-04-21
**Re**: `_coordination/inbox/backend-engineer/BE-SEC-P1-OAUTH-STATE-CSRF.md`
       (handed off 2026-04-20)

## Status check

Two days elapsed since the OAuth state CSRF advisory landed in your
inbox. No ack in `_coordination/inbox/backend-security/`, no entry in
`shared-log.md`, and a fresh re-check of the working tree today shows
the gap is still present:

- `backend/apps/integrations_calendar/views.py` — `grep -n
  'oauth_state\|OAUTH_STATE_MISMATCH'` returns only the unrelated iCal
  cache calls (lines 309 / 324). No server-side state storage, no
  callback validation, no single-use consumption.
- `connect_calendar` still generates `state = secrets.token_urlsafe(32)`
  and echoes it to the response body without persisting it.
- `calendar_callback` still forwards `state` into `exchange_code` without
  a same-user / same-flow check, so both Google (via
  `flow.fetch_token(code=code)` short-circuit) and Outlook (via the
  `{"state": state}` stub dict) remain exploitable.
- `tests_views.py::test_callback_with_bad_state_rejected_by_provider`
  is still the only callback-state test, and it exercises the mock, not
  the real validation path.

## Why this matters

Severity remains **P1 (account-takeover-adjacent)**. Exploit pattern is
unchanged:

1. Attacker creates their own Google / Outlook account.
2. Attacker initiates a calendar connect from their own account and
   grabs the callback URL pattern.
3. Attacker gets a victim-admin (already authenticated to
   `{tenant}.learnpuddle.com`) to hit
   `GET /api/v1/calendar/{provider}/callback/?code=<attacker_code>&state=<anything>`
   — e.g. via a phishing email, XSS on any tenant subdomain, or a CSRF
   form auto-submit.
4. LearnPuddle's `get_or_create(user=victim, provider=provider)` binds
   the **attacker's** OAuth tokens into the **victim's**
   `CalendarConnection` row.
5. Every `sync_calendar_connection` run thereafter pushes the victim
   tenant's course deadlines / events to the attacker's calendar. The
   attacker's refresh token survives password rotation.

## What I need from you

Please either:

a) **Ack + ETA** in `_coordination/inbox/backend-security/` — if
   you've picked this up, I'll log that and stand down the nudge.

b) **Reassign back** if calendar integrations is outside your queue
   too. I flagged this to you because my hard file-ownership
   (`tenant_middleware.py`, `tenant_manager.py`,
   `users/serializers.py`, `nginx/nginx.conf`,
   `docker-compose.prod.yml`) does not include
   `apps/integrations_calendar/`, and the fix needs Outlook MSAL
   expertise (you've touched that area before per the file history).
   If you want me to take it anyway under a one-off exception, say so
   and I'll move.

c) **Flag as lower-severity / deferred** with a justification so
   reviewer can decide whether to re-prioritize. I don't see a way to
   downgrade it on the evidence — it's textbook RFC 6749 §10.12 —
   but if there's mitigating context I'm missing (e.g. network
   egress restrictions on staging that make exploitation harder),
   please share.

Advisory with the TDD test plan + minimal fix shape is unchanged at
`_coordination/inbox/backend-engineer/BE-SEC-P1-OAUTH-STATE-CSRF.md`.
No new audit-surface changes today worth escalating — see today's
entry in `shared-log.md`.

— backend-security
