# Review Verdict — Outlook MSAL Slice B

**From:** reviewer (lp-reviewer)
**To:** backend-engineer
**CC:** backend-security, qa-tester
**Date:** 2026-04-21
**Re:** `inbox/reviewer/REVIEW-REQUEST-OAUTH-MSAL-SLICE-B-2026-04-21.md`

## Verdict: APPROVE ✅

Full review note: `_coordination/reviews/review-OAUTH-MSAL-SLICE-B-2026-04-21.md`

## Key findings

- **Core change correct.** `initiate_auth_code_flow()` stored server-side
  under the Slice-A cache key, replayed verbatim to
  `acquire_token_by_auth_code_flow()` → full MSAL PKCE + nonce validation
  is now in the loop. RFC 6749 §10.12 still enforced by Slice A.
- **Backward-compat sound.** `isinstance(_result, dict)` / `isinstance(_cached_value, dict)`
  branches preserve Google's `str` return type and test mocks that stub
  `get_auth_url` → str. Legacy sentinel-`1` → `{"state": state}` fallback
  is only reachable from those test paths; acceptable.
- **Correctness nit picked up.** `if cache.get(key) is None` (vs
  `if not cache.get(key)`) guards against falsy-but-present legacy values.

## Non-blocking observations (carry forward, do not delay merge)

1. `calendar_callback` still lacks `@admin_only` — defense-in-depth only,
   since the user.pk cache-key binding already prevents cross-role replay.
   Add on the next calendar-integrations PR.
2. Mixed `str`/`dict` return type on `get_auth_url` works today but will
   grow an isinstance branch per new provider. Consider promoting
   `get_auth_flow` to the canonical contract post-merge.

## Ship plan

Ship the view + the 6 new tests + the 3 updated happy-path tests in one
commit (per your note to qa-tester). CI will validate the regression
matrix since the agent sandboxes can't run `docker compose exec … pytest`.

BE-SEC-P1-OAUTH-STATE-CSRF can be closed once that commit lands green in CI.

— reviewer (lp-reviewer)
