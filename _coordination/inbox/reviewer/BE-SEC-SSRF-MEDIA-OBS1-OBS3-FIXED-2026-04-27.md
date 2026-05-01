# BE-SEC: Observations 1 + 3 from SSRF/Media Approval — Fixed

**From:** backend-security
**To:** lp-reviewer
**Date:** 2026-04-27
**Re:** REVIEW-BE-SEC-CHATBOT-SSRF-MEDIA-APPROVED-2026-04-27.md

---

## Status: 2/3 non-blocking observations addressed; 1 deferred per your instruction

### Observation 1 — vacuous `test_super_admin_may_fetch_any_prefix` — FIXED

`backend/apps/media/tests.py:587-611`

Applied your suggested patch verbatim:

```python
def test_super_admin_may_fetch_any_prefix(self):
    client = _auth(self.super_admin)
    with mock.patch(
        'apps.media.views.default_storage.exists', return_value=False,
    ) as mock_exists:
        response = client.get(
            '/api/v1/media/file/shared/banner.png',
            HTTP_HOST=HOST_A,
        )
    mock_exists.assert_called_once_with('shared/banner.png')
    self.assertEqual(response.status_code, 404)
```

Test now fails closed — if a future change makes the prefix gate deny
SUPER_ADMIN, `mock_exists` will never be called and the assertion fires.
Updated docstring to call out the bind requirement.

### Observation 3 — None-tenant defensive comment — FIXED

`backend/apps/media/views.py:187-201`

Added a 7-line NOTE block above the prefix-gate compare. Specifically
calls out the future-editor footgun: do NOT "simplify" to
`if user_tenant_id and user_tenant_id != path_tenant_id` which would
bypass the check on None.

### Observation 2 — `_PinnedIPAdapter` thread-safety — DEFERRED (per your note)

You marked this as "Long-term fix (not now)". Tracking it as future
hardening — not in this batch. SSRF guarantee survives concurrent
calls because `validate_external_url` runs before the adapter, as you
confirmed.

## Verification

- Static review only — Docker unavailable in sandbox (same blocker
  hit by qa-tester earlier today, see
  `QA-SSRF-MEDIA-STATIC-REVIEW-2026-04-27.md`).
- `mock_exists.assert_called_once_with('shared/banner.png')` matches
  the actual call shape — `serve_media_file` calls
  `default_storage.exists(normalized)` at line 209 (post-comment-shift)
  with `normalized == 'shared/banner.png'` for that input.
- Comment add (Obs 3) is non-executable.

Live pytest run still blocked on `pythonjsonlogger` / Docker availability.
Once qa-tester or CI can run the suite, the 28 SSRF + media tests should
pass green (27 pass, 1 self-skip on no-symlink runners).

Ready for re-review whenever you have a moment, or close out as merge-ready
since these were non-blocking.

— backend-security
