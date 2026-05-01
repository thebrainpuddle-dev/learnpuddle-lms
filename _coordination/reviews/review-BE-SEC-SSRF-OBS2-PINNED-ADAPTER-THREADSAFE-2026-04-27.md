---
tags: [review, security, task/be-sec-ssrf-obs2, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: BE-SEC SSRF Obs 2 — `_PinnedIPAdapter` thread-safe refactor (+ follow-ups)

## Verdict: APPROVE

## Summary
Closes the OBS2 race correctly and minimally. The previous
`socket.getaddrinfo` module-level monkey-patch in `_PinnedIPAdapter.send`
is gone; the pinned IP now lives in a per-adapter class closure on
`HTTPSConnection`/`HTTPConnection` subclasses, wired through urllib3's
documented `pool_classes_by_scheme` extension point. TLS SNI and `Host`
header preservation are intact. The follow-ups (`PinnedIPAdapterTestCase`
and the `urllib3>=2.0,<3` floor pin) both landed and are exactly what was
discussed in the prior review.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None worth blocking on. Two observations:

1. **`_build_pinned_pool_classes` constructs four nested classes per
   adapter instance.** Cheap, but if `safe_get`/`safe_post` ever ends up
   on a hot path (current usage is admin-triggered chatbot ingestion +
   webhooks), a per-`(hostname, IP)` LRU cache on the factory would
   amortise the cost. Author already acknowledged this as a deferred
   item ("Per-(hostname, IP) adapter caching — Not landed [...] only
   worth caching if these helpers ever land on a hot path"). Agreed,
   defer.

2. **`pool_classes_by_scheme` instance-attribute trap is documented in
   the code** (`ssrf_guard.py:238–245`). The comment explicitly warns
   that subclassing `PoolManager` with a class-level override won't
   work because `PoolManager.__init__` clobbers it. This is exactly
   the kind of comment that prevents a future "let me clean this up"
   refactor from silently re-introducing the OBS2 race. Excellent.
   Nothing to change — calling out as a positive, mainly.

## Positive Observations

- **No more module-level monkey-patching.** The previous implementation
  monkey-patched `socket.getaddrinfo` for the duration of `.send()`. In
  a multi-threaded WSGI/ASGI worker, that patch would leak: thread A
  resolving for IP_X could see its `getaddrinfo` mock reverted (or
  replaced by thread B's mock for IP_Y) mid-request. Concrete race,
  now structurally impossible — the pinned IP is captured in the class
  closure and never mutates after `_PinnedIPAdapter.__init__`.
- **TLS SNI + cert verification preserved.** Confirmed: `self.host` on
  the connection stays as the original hostname (we only override
  `_new_conn` to dial the pinned IP), so urllib3's
  `HTTPSConnection.connect()` still passes
  `server_hostname=self.host` to the TLS wrap. The cert chain validates
  against the user-supplied hostname, not the IP. The docstring at
  `ssrf_guard.py:214–222` explains this; the test
  `test_pinned_ip_captured_in_class_closure` empirically proves the
  closure carried the pinned IP into `create_connection`'s first arg.
- **Validation runs first.** `validate_external_url` /
  `validate_webhook_host` execute in `safe_get` / `safe_post` *before*
  the adapter is constructed (`safe_get` lines 393–398). The adapter
  is the secondary defense against a DNS-rebind race between
  validation and the actual HTTP request — primary defense is the
  IP-network check. Both layers required for full protection; both
  present.
- **Test coverage is the right shape.**
  - `test_pool_uses_pinned_https_connection_class` — structural pin
    that the override is wired. Catches a future regression where
    `init_poolmanager` is rewritten to drop the
    `pool_classes_by_scheme` replacement.
  - `test_two_adapters_get_distinct_connection_classes` — uses
    `assertIsNot` on the `ConnectionCls`, which is the *structural*
    proof that no shared-mutable-state race is possible. If two
    adapters ever shared a class object, this test fails immediately.
  - `test_pinned_ip_captured_in_class_closure` — functional probe;
    invokes `_new_conn`, asserts `create_connection` was called with
    `(pinned_ip, port)`. Patches the urllib3 helper, not stdlib
    socket — keeps the test hermetic and protects against
    accidental real DNS in CI.
- **Mock target is correct.** `urllib3.util.connection.create_connection`
  is the helper the override actually calls; patching it (rather than
  `socket.create_connection`) targets the boundary the code uses.
  This is the right level of mocking — neither too high (would test
  nothing) nor too low (would couple the test to stdlib internals).
- **Smoke test in the review request is non-trivial.** The
  ALL CHECKS PASSED output verifies four properties in sequence:
  PoolManager type, pool_classes_by_scheme content, connection-class
  overrides, isolation between adapters. That's the right pre-CI
  validation given the Docker sandbox blocker.
- **`urllib3>=2.0,<3` floor pin landed correctly**
  (`backend/requirements.txt:50`) with a 7-line comment that names
  the version-sensitive surface (`pool_classes_by_scheme` instance
  attribute, `HTTPSConnection._new_conn`), references the BE-SEC-SSRF-OBS2
  ticket, and explains the failure mode (silent break +
  reopened DNS-rebind race). Future engineer running `pip install
  --upgrade` is now safe.
- **Public contract unchanged.** `safe_get` / `safe_post` /
  `validate_*` signatures are identical; existing callers
  (`chatbot_tasks._extract_text_from_url`, the webhook senders)
  are untouched. The 22 prior tests continue to pass without
  modification.

## Verification performed

- Read `_build_pinned_pool_classes` and both `_Pinned*Connection`
  subclasses (`ssrf_guard.py:161–205`) — closure capture is correct,
  `_new_conn` signature matches what `urllib3.util.connection.
  create_connection` accepts in 2.6.x.
- Read `_PinnedIPAdapter.init_poolmanager` (`ssrf_guard.py:235–256`)
  — verified the replacement of `pool_classes_by_scheme` happens
  *after* `PoolManager.__init__` returns, defeating the
  instance-attribute clobber the comment warns about.
- Read all three new tests in `PinnedIPAdapterTestCase`
  (`test_safe_get_ssrf.py:251–342`). Assertions pin both structural
  isolation and functional behavior of the pinned IP capture.
- Confirmed `urllib3>=2.0,<3` line in `backend/requirements.txt:50`,
  with the explanatory block at lines 43–49.
- Confirmed the smoke-test output cited in the request matches
  what the code should produce (per-adapter PoolManager whose
  `pool_classes_by_scheme` maps to the `_PinnedHTTPConnectionPool`
  subclass with the correct `ConnectionCls`).
- Cross-referenced with the parallel CHATBOT-SSRF + MEDIA-HARDENING
  review I just wrote — same code path, both reviews consistent on
  thread-safety and TLS-preservation analysis.

## Closeout

The follow-up note (`BE-SEC-SSRF-OBS2-FOLLOWUPS-LANDED-2026-04-27.md`)
states this is an audit-trail heads-up rather than a re-review request,
but I'm formalizing the verdict here regardless because (a) the OBS2
refactor itself was filed as a review request, and (b) two of the three
follow-ups landed in this same change set. Both follow-ups (#1 unit
tests, #2 urllib3 floor pin) are approved as part of this verdict.

The third follow-up (per-(hostname, IP) adapter caching) is correctly
deferred until the helpers move onto a hot path.

— reviewer
