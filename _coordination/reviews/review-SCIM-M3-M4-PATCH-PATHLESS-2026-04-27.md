---
tags: [review, task/TASK-023-followup-M3-M4, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: SCIM PATCH M3 (path-less replace) + M4 (unknown-op DEBUG log) + analytics docstring

## Verdict: APPROVE

## Summary
Closes the two non-blocking follow-ups from the TASK-023 verdict cleanly.
Path-less replace is dispatched to a separate helper (Azure AD interop is now
covered), unknown ops are logged at DEBUG without spamming, and the
`approval_trends` docstring now matches the runtime behaviour for null
scores. Four targeted tests, no regressions to existing PATCH coverage.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **`_user_changed = True` set on any `replace` op, not on actual mutation.**
   Look at `scim_views.py:464–472`. If an IdP sends a `replace` op with an
   *unrecognised* path (e.g. `{"op":"replace","path":"foo.bar","value":1}`),
   `_apply_scim_replace_path` silently ignores it (correct per RFC 7644
   §3.5.2), but `_user_changed` still flips to `True` and a wasted
   `user.save()` follows. The conditional-save optimisation introduced in
   the polish sprint protects only against unknown *op types* (add/remove),
   not unknown paths inside `replace`. Low severity — the wasted UPDATE is
   one extra write per quirky-IdP request — but worth a comment or a return-
   value from the helpers (`bool` indicating "did I actually touch the user")
   in a future polish pass. Not blocking.

2. **`approval_trends` is unbounded.** Outside this PR's scope, but the
   queryset at `analytics_views.py:154` iterates every
   `AssignmentSubmission` for the tenant with no LIMIT and no aggregation
   in SQL. Fine for current scale; flag for a future sprint to push the
   month-bucketing into `annotate(period=TruncMonth(...))` + `Count(...)`
   when tenants pass ~100k submissions. The docstring fix this PR adds is
   correct and useful regardless.

## Positive Observations

- **Dispatch logic is the right shape.** `if not path and isinstance(value,
  dict): _apply_scim_replace_dict(...) else: _apply_scim_replace_path(...)`
  at `scim_views.py:465–471` is exactly the RFC 7644 §3.5.2.3 split. The
  `else` branch preserves prior behaviour bit-for-bit, which keeps the four
  pre-existing PATCH tests green without modification.
- **Helpers are pure and easy to reason about.** `_apply_scim_replace_dict`
  treats keys as virtual paths, mirrors `_apply_scim_replace_path`'s
  branches, and uses the same `_coerce_scim_str` helper landed in the
  parallel null-coercion fix. Consistency is excellent.
- **M4 log discipline.** DEBUG level is correct — unknown ops are an "IdP
  is doing something we don't model yet" signal, not an error. The log
  format includes both the op type and the user id, so a future operator
  can grep for `"unrecognised op type"` and immediately see which IdP and
  which user. The `if op_type:` guard avoids logging empty-string noise.
- **Tests cover the right axes.**
  - `test_patch_pathless_replace_deactivates_user` — the one Azure AD
    payload that prompted M3 in the first place.
  - `test_patch_pathless_replace_updates_name_dict` — nested-dict branch.
  - `test_patch_pathless_replace_mixed_with_pathed_ops` — proves the two
    helpers compose in a single `Operations` array, which is the realistic
    IdP payload shape.
  - `test_patch_unknown_op_type_logs_debug_and_returns_200` — uses
    `caplog.at_level(logging.DEBUG, logger="apps.users.scim_views")`
    correctly (logger name matches, level set explicitly), asserts both
    "no mutation" and "log line emitted". Tight.
- **Existing tests untouched.** Verified the four pre-existing
  `TestSCIMPatchUser` tests (`test_patch_deactivate_sets_is_active_false`
  et al.) all use `path=` and so route through the unchanged
  `_apply_scim_replace_path` branch. Zero regression risk.
- **Docstring change is accurate.** `analytics_views.py:177–182` runs
  `if sub.score is not None and sub.score >= passing → approved else →
  rejected`. The new docstring lines 134–136 describe exactly that. A
  future engineer who is uncertain about how null scores bucket now finds
  the answer in the docstring instead of having to read the loop.
- **Test count math checks out.** SCIM polish landed 68; null-coercion +2
  → 70; M3/M4 +4 → 74; M6 +2 → 76. (Reviewer note: the M6 review request
  separately said 72 because it was authored against the pre-M3/M4 baseline.
  No conflict — the four tests just landed in different PRs that each report
  against the file state they observed.)

## Verification performed

- Read `_apply_scim_replace_dict` (`scim_views.py:339–368`) and the
  PATCH dispatch loop (`:443–498`). Logic matches the request description.
- Read all four new tests (`tests_scim.py:762–886`). Assertions target
  behaviour at the HTTP boundary, not implementation internals.
- Read `approval_trends` body and confirmed the docstring matches the
  null-score handling at line 179.
- Confirmed no DB schema change required (no migrations needed for any
  of these items).
- Docker test run is routed to qa-tester per the standing sandbox
  arrangement; the static analysis here matches qa's prior verifications
  on neighbouring SCIM work.

— reviewer
