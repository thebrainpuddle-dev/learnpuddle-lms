---
tags: [review, task/BE-SEC-SSRF-MEDIA, verdict/approve, reviewer/lp-reviewer, closeout]
created: 2026-04-27
---

# Review: BE-SEC SSRF/Media — Observations 1 + 3 Closeout

## Verdict: APPROVE — merge-ready

Closeout for non-blocking observations from
`REVIEW-BE-SEC-CHATBOT-SSRF-MEDIA-APPROVED-2026-04-27.md`.

## Summary

Both fixable observations applied verbatim. Observation 2 (`_PinnedIPAdapter`
thread-safety) explicitly deferred per my prior note — tracked as future
hardening, not in this batch. The patch landed exactly as requested; nothing
else moved.

## Verification

### Observation 1 — `test_super_admin_may_fetch_any_prefix` no longer vacuous

`backend/apps/media/tests.py:587-610`

Confirmed:

- `mock.patch(...)` is bound `as mock_exists` (line 600). ✅
- `mock_exists.assert_called_once_with('shared/banner.png')` is present
  at line 608 and matches the actual call shape — `serve_media_file` calls
  `default_storage.exists(normalized)` at views.py:204 with
  `normalized == 'shared/banner.png'` for input
  `/api/v1/media/file/shared/banner.png`. ✅
- Explicit `self.assertEqual(response.status_code, 404)` at line 610 nails
  down the step-4 outcome. ✅
- Docstring updated to call out *why* the bind is required ("without it
  the test passes vacuously even if the prefix gate begins denying
  SUPER_ADMIN"). Future-editor footgun documented. ✅

The test now fails closed. If a future change makes the prefix gate
deny SUPER_ADMIN, the request 404s before reaching `default_storage.exists`,
so `mock_exists.assert_called_once_with(...)` fires.

### Observation 3 — None-tenant defensive comment

`backend/apps/media/views.py:187-201`

Confirmed:

- 7-line NOTE block above the prefix-gate compare. ✅
- Explicitly names the simplification footgun:
  `if user_tenant_id and user_tenant_id != path_tenant_id` would bypass
  on None. ✅
- States the invariant: both `not path_tenant_id` and `None != "..."` are
  intentionally truthy denial paths. ✅
- Pure comment add — no logic change, no test impact. ✅

### Observation 2 — `_PinnedIPAdapter` thread-safety

Deferred as agreed. SSRF guarantee survives concurrent calls because
`validate_external_url` runs *before* `_PinnedIPAdapter`'s
`socket.getaddrinfo` patch is applied — the IP is already validated by the
time the adapter touches the socket module. The pattern is fragile but
the security property holds. Long-term fix (override `get_connection` or
pass `socket_options`) tracked separately.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

None.

## Positive Observations

- `mock.patch` bind change is the most defensible form: both *call shape*
  and *status code* asserted, with a docstring that tells the next
  engineer why both matter. This is the right pattern for any
  side-effect-only assertion in this codebase — worth replicating.
- The NOTE block in `serve_media_file` step 3 is exemplary defensive-comment
  craft: it names the *exact* wrong-fix a hurried reviewer might suggest
  ("simplify to `if user_tenant_id and ...`"), explains *why* it's wrong
  ("would bypass the check on None"), and states the invariant. This is
  what comments are for.
- Verification discipline: backend-security correctly noted Docker
  unavailability and stated explicitly that the verification is static.
  No false claim of "tests pass". Matches the
  `superpowers-verification-before-completion` posture.

## Outstanding (not in this batch)

- `_PinnedIPAdapter` get_connection / socket_options refactor — file an
  issue, not blocking.
- Live pytest run of the 28 SSRF + media tests — blocked on
  `pythonjsonlogger` / Docker availability in the agent sandbox. CI will
  exercise on next push. Static analysis confirms structure is sound; QA
  static review (qa-tester, 2026-04-27) reached the same conclusion.

## Status

- Review request → **closed, approved**.
- BE-SEC SSRF/Media hardening batch → **merge-ready**.
- Observation 2 → tracked as future hardening (not blocking).

— lp-reviewer
