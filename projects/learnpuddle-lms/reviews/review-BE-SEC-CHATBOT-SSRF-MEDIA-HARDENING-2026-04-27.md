---
tags: [review, task/BE-SEC-CHATBOT-SSRF, task/BE-SEC-MEDIA-FILE-HARDENING, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: BE-SEC-CHATBOT-SSRF + BE-SEC-MEDIA-FILE-HARDENING

## Verdict: APPROVE

## Summary

Two well-scoped defense-in-depth fixes from a proactive audit. The chatbot
URL-ingestion SSRF is a genuine privilege-escalation vector (school admin →
host-level secrets via IMDS/Redis/etc.) and the media-prefix gap is a real
cross-tenant exposure for any path lacking a `tenant/<id>/` segment. Both
fixes are implemented correctly, with a thoughtful guard library
(`safe_get`/`validate_external_url`) that complements the existing
`safe_post`/`validate_webhook_host` shape. 28 new tests, all assert
real behaviour. Approving with a handful of non-blocking observations
posted to backend-security inbox.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### 1. `test_super_admin_may_fetch_any_prefix` is effectively a no-op

`backend/apps/media/tests.py:587-605`. The test calls `client.get(...)`
inside a `mock.patch(default_storage.exists)` block and then makes **zero
assertions**. The comment explains the intent ("the mock would not have
been called if the request was rejected before that step"), but the
test never actually checks `mock_exists.called` or the response status
code, so it passes vacuously even if the prefix gate denies SUPER_ADMIN
in the future. Backend-security flagged this in "Areas you may want to
scrutinize #3" — confirming it should be tightened.

**Suggested fix** (one line):
```python
mock_exists.assert_called_once_with('shared/banner.png')
self.assertEqual(response.status_code, 404)  # file doesn't exist
```
Or capture the mock reference: `with mock.patch(...) as mock_exists:`.

Non-blocking — the prefix gate is correct in production code; the
regression risk is small. But the test as written gives false confidence.

### 2. `_PinnedIPAdapter` monkey-patches module-level `socket.getaddrinfo`

`backend/apps/integrations_chat/ssrf_guard.py:177-195`. Pre-existing
pattern (used by `safe_post` already) but worth re-flagging now that
`safe_get` extends the surface to admin-supplied URLs called from Celery
workers. With concurrent `safe_get`/`safe_post` calls in the same
process (e.g. eventlet/gevent worker, threadpool), the inner
`original_getaddrinfo` capture for thread B will see thread A's patched
version. The `finally` blocks restore in LIFO order so the true original
is restored once the outermost call completes, but during the overlap
window thread B's "fallback to original" path actually pins through
A's hostname. End-state is correct; the transient is benign for the
SSRF guarantee (B's hostname has already been validated and the IP
verified before send) but the pattern is fragile. Worth a TODO to
move to `urllib3.connection.HTTPConnection.set_socket_options` or a
custom `connect()` override on the adapter long-term.

Non-blocking — same risk profile as `safe_post`, which has been in
production. Filing as defense-in-depth carry-forward.

### 3. `safe_get` redirect refusal vs. re-validation

Author flagged this as a design choice (#1 in the request). I agree
with the chosen tradeoff: re-validating each hop is hard to get right
and admin-supplied content URLs realistically point at canonical
endpoints. The `Location` header contents are surfaced in the
`SSRFError` for the operator (good). If a future requirement surfaces
("we need to follow one redirect for X"), `safe_get` can grow a
`max_redirects=N` kwarg with per-hop `validate_external_url` then.

### 4. `serve_media_file` — `request.user.tenant_id` falsy short-circuit

`apps/media/views.py:188-194`. If `request.user.tenant_id` is None
(possible for SUPER_ADMIN with no tenant binding, or stale/inactive
user), `user_tenant_id = None` and the check `not path_tenant_id or
user_tenant_id != path_tenant_id` correctly 404s. Good. Worth a
one-line comment so future editors don't accidentally `if user_tenant_id`
which would *bypass* the check on None. (Style nit only.)

## Positive Observations

- **`validate_external_url` correctly handles literal-IP inputs** (lines
  287-298): bypasses DNS for `http://127.0.0.1:6379/` and friends rather
  than relying on `getaddrinfo` to "resolve" a literal. Closes the
  trivial bypass.
- **Streaming size cap is enforced via `iter_content`** with proper
  `response.close()` in `finally`, then `_content` re-attached so callers
  can use `.text`/`.content` transparently. Idiomatic.
- **`_resolve_and_check` validates *every* address in the `getaddrinfo`
  result** (line 142-147), not just the first — defends against
  multi-record DNS that mixes public and private answers.
- **`serve_media_file` step ordering is sound**: pre-normalize char
  rejection → normalize → traversal check → tenant prefix → existence
  → realpath/commonpath. Each step is independently necessary.
- **`commonpath` over `startswith`** for the symlink containment check
  (line 247) — correctly avoids the `media-evil` vs `media` prefix
  collision that would have been a subtle bug.
- **404 over 403** for cross-tenant paths (line 192-194) — does not
  leak the existence of files in other tenants. Matches the existing
  invariant in this view.
- **Tests cover the real attack vectors**: IMDS literal AND IMDS-via-DNS
  pivot, RFC1918 ranges, CGNAT, IPv6 loopback, redirect-to-IMDS,
  oversize body, path-prefix gap, symlink escape. The `safe_get` IMDS
  short-circuit test (`test_safe_get_rejects_imds_before_dns`) is
  particularly nice — proves the validation happens before any Session
  is constructed.
- **Backwards-compat preserved**: `safe_post` and `validate_webhook_host`
  unchanged; `_extract_text_from_url` is strictly stricter (no silent
  expansion of capability).

## Verification Notes

- Read all 5 changed files and 2 new test classes. AST/syntax clean.
- Cross-checked test expectations against production code: error
  messages (`SSRF_REDIRECT_BLOCKED`, `SSRF_SIZE_CAP_EXCEEDED`,
  `SSRF_BLOCKED`) match the strings asserted by tests.
- Pytest run deferred — same `pythonjsonlogger` host blocker accepted at
  BE-SEC-P0 closeout. CI run requested in qa-tester inbox by author.
- No test for `pythonjsonlogger`-blocked CI gate run yet; once CI runs
  these 28 tests, fold the result back into the closeout.

## Recommendations (non-blocking, posted to backend-security inbox)

1. Tighten `test_super_admin_may_fetch_any_prefix` with an actual
   assertion.
2. Add a `# tenant_id may be None — falsy comparison is intentional`
   comment in `serve_media_file` step 3.
3. Track `_PinnedIPAdapter` thread-safety as a defense-in-depth backlog
   item.

— lp-reviewer
