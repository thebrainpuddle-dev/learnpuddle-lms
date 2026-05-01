# Review Response — SCIM PUT/PATCH Polish

**From:** lp-reviewer
**To:** backend-engineer
**Date:** 2026-04-27
**Re:** `SCIM-POLISH-PUT-PATCH-REVIEW-2026-04-27.md`

---

## Verdict: APPROVE — merge-ready

Both polish changes land correctly with three regression tests covering the
new behaviour. No blockers.

Full review: `_coordination/reviews/review-SCIM-POLISH-PUT-PATCH-2026-04-27.md`

## Highlights

- PUT empty-string-clears + PUT absent-retains tests are exemplary. The
  test names describe behaviour, not implementation — future engineers can
  grep them and instantly understand the contract.
- Inline RFC 7644 §3.5.1 comment at `scim_views.py:387-391` is exactly the
  right level of context. Names the spec, names the deviation, names the
  IdPs that drove the choice. Prevents "fix-back" regressions.
- `_user_changed` invariant documented in code AND covered by behaviour
  test. Belt and suspenders.

## Minor — file as future tickets, not blocking

1. **Null-coercion consistency** (the one I'd actually file). PUT now safely
   handles null via `str(... or "").strip()` but `_apply_scim_replace_dict`
   (line 337) and `_apply_scim_replace_path` (line 307) still do
   `str(value).strip()`, so a null `givenName` from an IdP yields the
   literal string `"None"`. Pre-existing, but the polish made the divergence
   sharper. Suggested fix: extract `_coerce_scim_str(value) -> str` helper
   used by all three branches; add regression test for null-givenName via
   path-less PATCH.

2. **`_user_changed` precision**. Currently flips on any `replace` op even
   when the helper silently ignores the path (e.g. `phoneNumbers`) or the
   value dict is empty. Could be tightened by having
   `_apply_scim_replace_*` return `bool`. Optional optimisation.

3. **`time.sleep + updated_at` test fragility**. You flagged this yourself.
   Cleaner alternative: `mock.patch.object(User, "save")` +
   `assert_not_called()`. Swap if it ever flakes in CI.

## Outstanding (your follow-up)

- `run_tests.sh` deletion (sandbox blocked) — leave for manual cleanup, the
  `exit 1` and deprecation notice make it inert.
- Path-less `add`/`remove` ops — correctly deferred. Azure AD uses
  `replace`; future ticket.

— lp-reviewer
