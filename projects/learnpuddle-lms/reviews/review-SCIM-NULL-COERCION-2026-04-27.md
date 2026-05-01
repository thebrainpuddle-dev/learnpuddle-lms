---
tags: [review, task/SCIM-NULL-COERCION, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: SCIM null-coercion consistency (`_coerce_scim_str`)

## Verdict: APPROVE

## Summary

Single-helper, single-call-site fix that replaces the silently-broken
`str(value).strip()` pattern (which persisted the literal string `"None"`
when an IdP sent JSON `null` to clear an attribute) with a tiny
`_coerce_scim_str(value)` helper that maps null/falsy values to `""`.
The helper is applied uniformly across four string branches in
`_apply_scim_replace_path` and four corresponding branches in
`_apply_scim_replace_dict`. PUT was already correct — this brings PATCH
to parity. Two well-shaped regression tests pin both branches.

## Files reviewed

| File | Change |
|------|--------|
| `backend/apps/users/scim_views.py` | New `_coerce_scim_str(value) -> str` (line 291); applied to `name.givenName`, `name.familyName`, `externalId`, `<_EXT_USER>:department` in both PATCH helpers |
| `backend/apps/users/tests_scim.py` | +2 tests: `test_patch_null_given_name_via_pathless_replace_stores_empty_string`, `test_patch_null_given_name_via_pathed_replace_stores_empty_string` |

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### 1. `_coerce_scim_str(0)` returns `""` (not `"0"`)

`return str(value or "").strip()` — the `or` evaluates `0`, `0.0`, `False`,
empty containers as falsy and they all collapse to `""`. For the SCIM
string attributes covered here (`first_name`, `last_name`, `employee_id`,
`department`) the spec only carries `str | null`, so this is operationally
fine. The PUT handler uses the same idiom (`str(v or "").strip()`) so we
are consistent across SCIM verbs. Worth a one-line docstring note (the
docstring already calls this out as an "edge case" — good) but not
worth blocking.

### 2. `bool(value)`-style coercion for `active` was deferred

The author noted in the request that `_user_changed` precision (returning
a bool from each helper to avoid a wasted UPDATE on a no-op PATCH) was
deferred. That's the right call — separate concern, low ROI, and the
SCIM POLISH series already pinned the all-unknown-ops branch with
`test_patch_unknown_ops_only_does_not_write_to_db`.

### 3. The two new tests both assert `first_name == ""`

That's the correct primary invariant (regression: was `"None"`).
A nice-to-have follow-up would be a parallel test for
`name.familyName: null` and one for `externalId: null` /
`department: null`, since the helper covers four code branches but the
test suite only exercises one. The risk of branch drift is low (the
helper is a pure function applied identically) but coverage is the
formal proof. Non-blocking; backlog if it ever flakes.

## Positive Observations

- **Helper is the right size.** Three lines, one responsibility, one
  docstring. Will not develop bit-rot.
- **Both PATCH dispatch branches updated symmetrically.** Pathed and
  path-less replaces now share identical null handling — eliminates
  the "fix the same bug in two places" risk that got us here.
- **Tests pin both dispatch paths separately.** Path-less
  (`_apply_scim_replace_dict`) and pathed (`_apply_scim_replace_path`)
  are exercised by independent tests with distinct payload shapes.
  If a future refactor breaks one branch, the other test still catches
  the regression.
- **Test failure messages are useful.** Both tests include an
  `assertEqual` message that explains the regression (`"_coerce_scim_str
  must return '' not 'None'"`). When this fails in CI six months from
  now, the operator will know exactly what broke.
- **Pre-existing fixtures reused.** Tests use the same `_setup()` /
  `_scim_headers()` helpers as the rest of `TestSCIMPatchUser` — no
  test infrastructure churn.
- **PUT untouched.** PUT was already correct (`str(v or "").strip()`);
  the author correctly noted this and didn't refactor it gratuitously.
  YAGNI respected.

## Verification performed by reviewer

- Read `_coerce_scim_str` (line 291), all 4 call sites in
  `_apply_scim_replace_path` (lines 329, 331, 333, 335), and all 4
  call sites in `_apply_scim_replace_dict` (lines 359, 361, 364, 368).
  Each branch passes the SCIM input directly without intermediate
  coercion. Logic traces cleanly.
- Confirmed both new tests live under `TestSCIMPatchUser` alongside the
  M3/M4 path-less tests; no test class duplication.
- Confirmed `str(None or "").strip() == ""` and `str("Alice" or
  "").strip() == "Alice"` — helper semantics match the documented
  contract.
- Cross-checked PUT handler (lines 414–427) — already uses the same
  pattern inline, so PATCH now matches PUT behaviour for null inputs.
- AST/static-only verification accepted per BE-SEC-P0 closeout
  sandbox-blocker norm. QA tester filed a separate static-review report
  confirming both new tests are structurally correct
  (`QA-SCIM-NULL-COERCION-STATIC-REVIEW-2026-04-27.md`).

## Action for author

None blocking. Mark task `status/done`. Backlog candidates if useful
later:

1. Parallel null-coercion tests for `familyName`, `externalId`,
   `department` (3 more one-screen tests).
2. `_user_changed` precision (helper returns bool) — already
   intentionally deferred by author, agreed.

— reviewer
