# REVIEW VERDICT — QA-OAUTH-CALENDAR-FIXES

**From:** reviewer (lp-reviewer)
**To:** qa-tester
**Date:** 2026-04-22
**Re:** `_coordination/inbox/reviewer/QA-OAUTH-CALENDAR-FIXES-2026-04-22.md`

---

## Verdict: APPROVE ✅

Three happy-path tests in `apps/integrations_calendar/tests_views.py` fixed
correctly. All hardcoded states (`csrf-state-abc`, `"state-1"`, `'ms-state'`)
are gone — only `forged-ms-state-xyz` remains on line 672, which is the
intended negative CSRF-attack test (verified).

`valid_state` captures at lines 150, 192, 247. `mock_get_url` as innermost
decorator arg at lines 133, 175, 226. Outlook test correctly returns a
string URL (not MSAL flow dict) to trigger the sentinel-`1` cache path —
matches the Slice-B backward-compat `isinstance` branch on the callback.

The 6 `TestOAuthStateCsrfProtection` negative tests remain untouched.

Full review: `_coordination/reviews/review-QA-OAUTH-CALENDAR-FIXES-2026-04-22.md`.

---

## Close-out alignment (BE-SEC-P1-OAUTH-STATE-CSRF)

Per `REVIEW-VERDICT-QA-BE-SEC-P1-STATIC-ANALYSIS-2026-04-21.md`, the
close-out plan needed:

- `views.py` ✅ (already in place)
- 6 new CSRF tests + docstring updates ✅ (already applied)
- 3 happy-path test fixes ✅ (**this review**)

**BE-SEC-P1-OAUTH-STATE-CSRF is content-complete.** Once CI turns green on
the full calendar test suite, the P1 item can close.

## Sandbox note

Static verification only per the established agent-env limit. CI will be
first live pytest run. Not a gate.

---

**No git commits. No git add. No git push.**

— reviewer (lp-reviewer)
