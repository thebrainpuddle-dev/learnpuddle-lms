---
tags: [review, task/SCIM-POLISH, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: SCIM User PUT/PATCH Polish

## Verdict: APPROVE

Both polish changes land correctly with regression tests that verify the new
behaviour (not the implementation). One minor consistency observation worth
filing as a future ticket — non-blocking.

## Summary

Two surgical changes to `backend/apps/users/scim_views.py`:

1. **PUT replace semantics** — switched from `or fallback` to `"key in dict"`.
   Now mirrors RFC 7644 §3.5.1 behaviour: present (even null/empty) overwrites,
   absent retains. Lenient on null vs strict spec, but matches Okta/Azure AD.
2. **PATCH conditional save** — `_user_changed` flag gates `user.save()`.
   All-unknown-op batches now skip the wasted UPDATE.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### Inconsistent null-handling between PUT and PATCH path-less replace

**Pre-existing, not introduced by this PR — but the polish made the divergence
more visible. File a follow-up; do not block this merge.**

The PUT branch now safely coerces null:

```python
# scim_views.py:393 (PUT)
user.first_name = str(name_obj.get("givenName") or "").strip()
```

But `_apply_scim_replace_dict` (PATCH path-less) and
`_apply_scim_replace_path` (PATCH pathed) don't:

```python
# scim_views.py:337 (_apply_scim_replace_dict)
user.first_name = str(name_obj["givenName"]).strip()

# scim_views.py:307 (_apply_scim_replace_path)
user.first_name = str(value).strip()
```

If an IdP sends `{"op":"replace","path":"name.givenName","value":null}` or
`{"op":"replace","value":{"name":{"givenName":null}}}`, the user's
`first_name` becomes the literal string `"None"`. Azure AD doesn't typically
send null for these fields, but I'd rather not bet a tenant's user table on
that.

**Suggested fix (future ticket)**: extract a `_coerce_scim_str(value)` helper
and use it consistently across all three branches:

```python
def _coerce_scim_str(value) -> str:
    return str(value or "").strip()
```

Then PUT, `_apply_scim_replace_path`, and `_apply_scim_replace_dict` all share
the same null-handling. Add a regression test:
`test_patch_pathless_replace_with_null_givenName_yields_empty_string`.

Tracking only — not blocking this batch.

### `_user_changed = True` fires for `replace` ops with unrecognised paths

When a `replace` op carries a path that `_apply_scim_replace_path` silently
ignores (e.g. `phoneNumbers`), the helper does nothing but `_user_changed` is
still set, triggering a wasted save. Same for `_apply_scim_replace_dict`
called with an empty value dict.

The targeted optimisation (all-`add`-ops batch) works as advertised and the
new test proves it; this is a residual gap, not a regression. Could be closed
by having both helpers return a `bool` indicating whether they mutated the
user object — minor refactor, not in scope here.

### `test_patch_unknown_ops_only_does_not_write_to_db` uses sleep+timestamp

`time.sleep(0.05)` plus `updated_at` comparison is correct but slightly
fragile and adds 50ms to the test suite. The author flagged this themselves.

A cleaner alternative is mock-based:

```python
with mock.patch.object(User, "save") as mock_save:
    resp = c.patch(...)
mock_save.assert_not_called()
```

This is faster, deterministic, and tests the exact invariant. Not blocking
— if it stays green in CI, leave it; if it ever flakes, swap to the mock
form.

## Positive Observations

- **Test naming is excellent.** Names like
  `test_put_user_clears_first_name_when_given_name_is_empty_string` and
  `test_put_user_retains_first_name_when_given_name_absent` describe the
  *behaviour* under test, not the implementation. New engineers can grep
  these names and instantly understand the contract.
- **Inline comment quoting RFC 7644 §3.5.1** at scim_views.py:387-391 is
  exactly the right level of context — names the spec, names the deviation
  (lenient on null vs strict), names the IdPs that drove the choice. This
  prevents the next engineer from "fixing" it back into a regression.
- **The PATCH conditional-save invariant** is documented in code (lines
  431-435) AND covered by a behaviour test. Both belt and suspenders — good.
- **`run_tests.sh` deletion sandbox limit** was correctly disclosed rather
  than worked around. The file has `exit 1` and a deprecation notice; safe
  to leave for manual cleanup.
- **Path-less add/remove** correctly deferred — Azure AD uses `replace`,
  scope creep avoided. Good YAGNI discipline.

## Outstanding (not in this batch)

- File a future ticket: "SCIM null-value coercion consistency across PUT and
  PATCH" — extract `_coerce_scim_str` helper, add regression test for
  null-givenName.
- Optional: have `_apply_scim_replace_*` helpers return a `bool` so
  `_user_changed` only flips on actual mutation. Minor optimisation.
- Optional: swap `time.sleep + updated_at` test to `mock.patch(User.save)`
  if CI flakes.

## Status

- Review request → **closed, approved**.
- SCIM polish → **merge-ready**.
- Three minor follow-ups noted above, none blocking.

— lp-reviewer
