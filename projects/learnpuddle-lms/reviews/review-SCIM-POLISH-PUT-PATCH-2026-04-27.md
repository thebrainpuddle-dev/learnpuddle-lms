---
tags: [review, task/SCIM-POLISH-PUT-PATCH, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: SCIM PUT replace semantics + PATCH conditional save

## Verdict: APPROVE

## Summary

Two minimal, well-targeted polish edits in `backend/apps/users/scim_views.py`
that close the two non-blocking observations I left on TASK-023 M2 and the
SCIM M3-M4 review:

1. **PUT** now uses `"key in dict"` semantics for `givenName`/`familyName`
   instead of the silently-overwriting `or user.first_name` fallback —
   absent key retains the stored value; present key (even null/empty)
   replaces it. Matches Okta/Azure AD shape; documented inline against
   RFC 7644 §3.5.1.
2. **PATCH** now tracks `_user_changed` and only calls `user.save()` when
   at least one recognised `replace` op fired. Eliminates the wasted
   UPDATE when every op in the batch is an unrecognised type (e.g. an
   IdP sends `add`/`remove` ops we don't yet implement).

Both changes are surgical (~10 LOC net) and stay inside the call path
exercised by the existing `tests_scim.py` suite. The pre-existing
`test_patch_unknown_op_type_logs_debug_and_returns_200` continues to
pass because it only asserts on `first_name`/`is_active` (unchanged) —
not on `updated_at`, which now legitimately stays the same.

## Files reviewed

| File | Change |
|------|--------|
| `backend/apps/users/scim_views.py:402-427` | PUT: `if "givenName" in name_obj` / `if "familyName" in name_obj` guards replace the `or user.first_name`/`or user.last_name` fallback |
| `backend/apps/users/scim_views.py:443-483` | PATCH: `_user_changed = False`, set `True` inside the `replace` branch, conditional `user.save()` |

(Other edits in the working-tree diff — throttle wiring, `sortBy`
allowlist, `_coerce_scim_str` — belong to separately-approved review
notes and are not in scope here. Confirmed against the in-tree diff
attribution.)

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### 1. PATCH skips `user.save()` even if `_apply_scim_replace_*` no-ops

`_user_changed = True` is set unconditionally whenever the `replace`
branch is taken, regardless of whether the helper actually mutated any
field. Concretely: a `replace` op against an unrecognised path
(e.g. `path == "displayName"`) calls `_apply_scim_replace_path` →
falls through every elif → returns without mutation. We still mark
`_user_changed = True` and call `save()`. End result is one wasted
UPDATE per "all-replaces-but-all-unrecognised-paths" batch.

That's strictly better than today (we still skip the all-unknown-ops
case), and the tighter version (helpers return `bool` and the caller
ORs them) was correctly deferred at the SCIM-NULL-COERCION review.
Carry-forward only.

### 2. PUT comment is honest about being lenient vs. RFC

The inline comment names this as "slightly more lenient than strict
RFC but matches Okta/Azure AD behaviour and avoids silently blanking
names on partial PUT bodies." That's the right framing — strict RFC
PUT would 400 on a partial body. The lenient interpretation is the
de-facto IdP shape. Worth noting to qa-tester so they don't write a
"strict-RFC PUT" regression test that would fight this. Will mention
in the cross-post.

### 3. No tests landed in this PR

Author requested regression coverage from qa-tester via
`_coordination/inbox/qa-tester/SCIM-POLISH-REGRESSION-TESTS-2026-04-27.md`
(per the request body). Acceptable given the helper-style of the change
(small, easily-traced) and the existing `tests_scim.py` coverage that
still exercises both verbs. **Will block on receipt of qa-tester's
regression tests if they don't land within 48h** — these two behavioural
shifts are the kind of thing IdP integration tests need to pin.

Specifically, we need at least:

- `test_put_omitting_givenName_retains_existing_first_name`
- `test_put_with_explicit_null_givenName_clears_first_name`
- `test_patch_all_unrecognised_ops_does_not_call_save` (mock
  `User.save` and assert call_count == 0).

## Positive Observations

- **PUT semantics now match the obvious mental model.** "If the IdP
  didn't send the field, don't change it" is what every IdP integrator
  expects. The previous `or user.first_name` form silently no-op'd on
  empty string and would persist a literal None-stringified value if
  someone passed null. Both classes of bug are gone.
- **Both helpers handle null safely.** `str(name_obj.get("givenName")
  or "").strip()` reuses the same `or ""` guard as the now-canonical
  `_coerce_scim_str` helper. No more "None"-string regressions.
- **`_user_changed` flag is named what it is.** Not `dirty`, not
  `should_save` — the variable says exactly what it means. Future
  contributors won't have to re-derive its purpose.
- **Comment block above `_user_changed` calls out the motivating
  scenario.** Names the IdP-sends-`add` case explicitly. Future
  readers don't have to spelunk git blame to understand why the flag
  exists.
- **Unrecognised op types still hit the DEBUG log.** `_user_changed`
  doesn't suppress the visibility — operators can still see "Azure AD
  sent this op type we don't handle" in DEBUG logs.
- **YAGNI respected on path-less `add`/`remove`.** Author correctly
  deferred to a future ticket (Azure AD uses `replace` exclusively,
  per the M3-M4 verdict). No premature support landed.
- **`run_tests.sh` deletion deferred honestly.** Author flagged the
  sandbox `rm` blocker rather than working around it. Good signal
  hygiene.

## Verification performed by reviewer

- Read PUT handler (lines 402-440) and PATCH handler (lines 443-498)
  in full. Logic traces cleanly: PUT `if "key" in dict` guards never
  trigger on absent keys; PATCH `_user_changed` defaults False and
  flips True only in the `replace` branch.
- Cross-checked the existing `test_patch_unknown_op_type_logs_debug_and_returns_200`
  assertions — only checks `first_name`/`is_active`. Both are
  untouched on unknown-op batches in either old or new code. Passes
  unchanged. ✓
- Existing `_apply_scim_replace_dict` path (path-less replace from
  Azure AD) flows through the same `_user_changed = True` flip. PATCH
  semantics for the `{"op":"replace","value":{...}}` shape are
  preserved.
- Other diff hunks in `scim_views.py` (throttle calls, `sortBy`
  allowlist, `_coerce_scim_str`) belong to other already-reviewed
  changes. Confirmed via grep and the SCIM-NULL-COERCION review note —
  none affect the PUT/PATCH polish under review here.
- Static review only — same Docker/`pythonjsonlogger` blocker.

## Action for author

1. Mark `status/done` once qa-tester confirms or files the regression
   tests.
2. (Carry-forward) If `_user_changed` precision becomes a real concern,
   thread bool returns through `_apply_scim_replace_path` and
   `_apply_scim_replace_dict` — same shape proposed and deferred at
   SCIM-NULL-COERCION.
3. Delete `run_tests.sh` next time a `rm` is possible.

— lp-reviewer
