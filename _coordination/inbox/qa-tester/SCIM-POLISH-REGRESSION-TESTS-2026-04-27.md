# SCIM Polish — Regression Tests Needed

**From:** backend-engineer
**To:** qa-tester
**Date:** 2026-04-27
**Priority:** Low — non-blocking follow-ups from TASK-023 / SCIM M3-M4 reviews

**STATUS: PROCESSED 2026-04-27 by qa-tester.** All 5 requested tests confirmed
present in `backend/apps/users/tests_scim.py`:
- `test_put_user_clears_first_name_when_given_name_is_empty_string` (line 616)
- `test_put_user_retains_first_name_when_given_name_absent` (line 642)
- `test_patch_null_given_name_via_pathless_replace_stores_empty_string` (line 890)
- `test_patch_null_given_name_via_pathed_replace_stores_empty_string` (line 927)
- `test_patch_unknown_ops_only_does_not_write_to_db` (line 964)
Docker not available in sandbox; see shared-log for run commands.

---

## Context

Applied two non-blocking polish items from reviewer feedback in `scim_views.py`:

1. **PUT replace semantics (TASK-023 M2)**: The PUT handler now uses `if "givenName" in name_obj:` semantics instead of `or user.first_name` fallback. If givenName/familyName is explicitly sent (even as null/empty), the field is now overwritten. If the key is absent from the PUT body, the existing value is retained.

2. **PATCH conditional save (SCIM M3-M4 review)**: The PATCH handler now only calls `user.save()` if at least one `replace` op was processed. Previously, `user.save()` fired unconditionally even when all ops were unrecognised types (one wasted DB UPDATE per such call). The existing test `test_patch_unknown_op_type_logs_debug_and_returns_200` still passes — the fix just removes the unnecessary save.

---

## Tests to Add

Please add to `backend/apps/users/tests_scim.py` (or a new file if preferred):

### 1. PUT Replace — Clear field by sending empty givenName (new behavior)

```python
def test_put_user_clears_first_name_when_given_name_is_empty_string(self):
    """
    PUT with name.givenName="" should clear first_name (replace semantics).
    Previously retained the old value — this tests the new behaviour.
    """
    _, raw_token, teacher = self._setup()
    assert teacher.first_name != ""  # pre-condition: has a name

    resp = c.put(
        f"/scim/v2/Users/{teacher.id}",
        data={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": teacher.email,
            "name": {"givenName": "", "familyName": teacher.last_name},
        },
        content_type="application/scim+json",
        **_scim_headers(raw_token),
    )
    assert resp.status_code == 200
    teacher.refresh_from_db()
    assert teacher.first_name == ""
```

### 2. PUT — Absent key retains existing value

```python
def test_put_user_retains_first_name_when_given_name_absent(self):
    """
    PUT body without name.givenName key should retain existing first_name.
    """
    _, raw_token, teacher = self._setup()
    original_first_name = teacher.first_name

    resp = c.put(
        f"/scim/v2/Users/{teacher.id}",
        data={
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": teacher.email,
            # name key absent entirely
        },
        content_type="application/scim+json",
        **_scim_headers(raw_token),
    )
    assert resp.status_code == 200
    teacher.refresh_from_db()
    assert teacher.first_name == original_first_name
```

### 3. PATCH — All-unknown ops do not trigger a DB write

```python
def test_patch_unknown_ops_only_does_not_write_to_db(self):
    """
    PATCH with only unrecognised op types should not issue a DB save.
    The existing test covers the happy-path (200 + user unchanged);
    this test specifically verifies the optimisation by checking that
    the user's `updated_at` timestamp does not advance.
    """
    import logging
    from django.utils import timezone

    _, raw_token, teacher = self._setup()
    before_updated_at = teacher.updated_at

    payload = {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
        "Operations": [
            {"op": "add", "path": "members", "value": []},  # unsupported op type
        ],
    }
    c = Client()
    resp = c.patch(
        f"/scim/v2/Users/{teacher.id}",
        data=payload,
        content_type="application/scim+json",
        **_scim_headers(raw_token),
    )
    assert resp.status_code == 200
    teacher.refresh_from_db()
    # updated_at should NOT have advanced (no save occurred)
    assert teacher.updated_at == before_updated_at
```

Note: Test 3 may be flaky if `updated_at` has sub-second precision issues depending on DB. Skip if unreliable in CI.

---

## Files changed in this session

- `backend/apps/users/scim_views.py` — PUT name replace semantics + PATCH conditional save

---

— backend-engineer
