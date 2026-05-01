---
tags: [review, task/BE-SEC-SSRF-MEDIA-OBS1, task/BE-SEC-SSRF-MEDIA-OBS3, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: BE-SEC SSRF/Media Obs 1 + Obs 3 — followup fixes

## Verdict: APPROVE

## Summary

Two minor non-blocking observations from
`review-BE-SEC-CHATBOT-SSRF-MEDIA-HARDENING-2026-04-27.md` are resolved.
Obs 1 (`test_super_admin_may_fetch_any_prefix` was vacuous) is now a
real regression test; Obs 3 (None-tenant defensive comment) is a
7-line NOTE block that explicitly forbids the obvious "simplification"
that would re-open the bug. Obs 2 (thread-safe `_PinnedIPAdapter`)
landed separately in `BE-SEC-SSRF-OBS2-…-2026-04-27` and is approved
in its own review note.

## Files reviewed

| File | Change |
|------|--------|
| `backend/apps/media/tests.py` | `test_super_admin_may_fetch_any_prefix` rewritten with `mock.patch(...) as mock_exists` bind + `mock_exists.assert_called_once_with('shared/banner.png')` + `assertEqual(response.status_code, 404)` |
| `backend/apps/media/views.py` | Lines 191–198: 7-line NOTE explaining why the falsy compare must NOT be "simplified" |

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

None worth opening — both fixes match the suggested patches verbatim.

## Positive Observations

- **Test now fails closed.** `mock_exists.assert_called_once_with(...)`
  forces a failure if a future change makes the prefix gate deny
  SUPER_ADMIN: the existence check would never be reached, the mock
  would never be called, and the assert fires. Exactly the regression
  shape the original review flagged.
- **`assert_called_once_with` over `assert_called`.** Catches both
  "never called" (gate denied) and "called too many times" (some weird
  retry/loop) regressions. Strictly more precise than what was
  suggested.
- **Inline test docstring explains the bind requirement.** "The bind
  ``as mock_exists`` is required so we can assert the call — without it
  the test passes vacuously even if the prefix gate begins denying
  SUPER_ADMIN." Future readers who see `as mock_exists` and try to
  "clean it up" will see the warning.
- **NOTE block in `views.py` calls out the exact footgun.** The
  `if user_tenant_id and user_tenant_id != path_tenant_id` "improvement"
  is named explicitly and explained — that's the version a code-quality
  pass would otherwise propose. Pre-emptively documenting the trap
  beats fixing the regression later.
- **Comment language is precise.** "Both ``not path_tenant_id`` and
  ``None != '...'`` are intentionally truthy denial paths" — names both
  branches that depend on the strict-inequality form. No room for
  partial-fix.
- **Static-only verification reasoning.** Author re-confirmed the
  asserted call shape against the production call site
  (`default_storage.exists(normalized)` with `normalized ==
  'shared/banner.png'` for the test input). I read the same
  call site (line 204) — matches.

## Verification performed by reviewer

- Diffed `backend/apps/media/tests.py` and `backend/apps/media/views.py`
  against `HEAD`. Both edits are exactly the form proposed in the prior
  review.
- Read `serve_media_file` lines 176–205 to confirm the comment lives
  immediately above the compare it describes (line 198) — yes,
  positioned correctly so a future editor reading the inequality first
  sees the warning before considering a refactor.
- Confirmed `default_storage.exists(normalized)` at line 204 takes the
  normalized path, matching the test's `assert_called_once_with`
  argument. No spurious-failure risk if the normalize step ever changes
  shape (the test would fail meaningfully).
- Static review only — same Docker/`pythonjsonlogger` blocker; CI run
  pending.

## Action for author

None blocking. Mark the task `status/done`. Obs 2 already has its own
APPROVE note. The 28-test SSRF + media batch is fully approved as of
this review.

— lp-reviewer
