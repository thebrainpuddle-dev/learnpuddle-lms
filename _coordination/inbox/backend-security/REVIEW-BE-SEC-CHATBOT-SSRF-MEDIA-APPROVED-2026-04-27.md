# Review APPROVED — BE-SEC-CHATBOT-SSRF + BE-SEC-MEDIA-FILE-HARDENING

**From:** lp-reviewer
**To:** backend-security
**Date:** 2026-04-27
**Verdict:** APPROVE

---

## TL;DR

Both fixes approved. Strong implementation, comprehensive tests. Three
non-blocking observations below — none gate merge.

Full review: `projects/learnpuddle-lms/reviews/review-BE-SEC-CHATBOT-SSRF-MEDIA-HARDENING-2026-04-27.md`

## Non-blocking observations

### 1. `test_super_admin_may_fetch_any_prefix` is vacuous (real test bug)

`backend/apps/media/tests.py:587-605`. The test makes zero assertions
after `client.get(...)`. The `mock.patch(default_storage.exists)` is
referenced in the comment but never bound (no `as mock_exists:`) so
`mock.assert_called_once_with(...)` is impossible. The test passes
even if the prefix gate denies SUPER_ADMIN in the future.

**Suggested patch (one line):**
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

### 2. `_PinnedIPAdapter` thread-safety carry-forward

Pre-existing pattern in `safe_post`, now extended to `safe_get`. Module-
level `socket.getaddrinfo = patched_getaddrinfo` inside `send()` plus
LIFO `finally` restore is correct end-state but transiently incorrect
under concurrent calls (Celery eventlet/gevent worker, threadpool).
SSRF guarantee survives because validation happens before the adapter
runs, but the pattern is fragile.

**Long-term fix (not now):** override `_PinnedIPAdapter.get_connection`
or pass `socket_options` such that `urllib3.connection.HTTPConnection`
uses the pinned IP without touching module-level `socket`.

### 3. `serve_media_file` step 3 — None-tenant comment

`apps/media/views.py:188-194`. The check `not path_tenant_id or
user_tenant_id != path_tenant_id` correctly 404s when
`request.user.tenant_id` is None. Future editors may accidentally
"simplify" to `if user_tenant_id and user_tenant_id != path_tenant_id`
which would *bypass* the check on None. Add a one-line comment:

```python
# user_tenant_id may be None for unbound users; the falsy compare must
# remain a strict inequality, not a guarded `if user_tenant_id and ...`.
```

## Other notes

- `safe_get` redirect-refusal design: ✓ correct tradeoff. Re-validation
  per hop only if a real product need surfaces.
- `_resolve_and_check` checks every `getaddrinfo` answer, not just the
  first — closes multi-record DNS race.
- 404 over 403 for cross-tenant: ✓ matches existing invariant; does not
  leak existence.
- 28 tests cover the real attack vectors (IMDS literal AND DNS-pivot,
  RFC1918, CGNAT, IPv6 loopback, redirect-to-IMDS, oversize body,
  prefix gap, symlink escape).

CI test run still pending the `pythonjsonlogger` blocker; the qa-tester
inbox already has the request. Once CI runs and passes these 28 tests,
the closeout can fold the result back in.

— lp-reviewer
