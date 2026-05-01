---
tags: [review, task/BE-SEC-SSRF-OBS2, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: BE-SEC-SSRF-OBS2 — `_PinnedIPAdapter` thread-safe refactor

## Verdict: APPROVE

## Summary

Closes the `_PinnedIPAdapter` thread-safety concern flagged in
`review-BE-SEC-CHATBOT-SSRF-MEDIA-HARDENING-2026-04-27.md` (Minor #2,
Recommendation #3). The module-level `socket.getaddrinfo` monkey-patch in
`send()` is replaced with per-instance `HTTPConnection`/`HTTPSConnection`
subclasses whose `_new_conn` dials the pinned IP directly, wired through
a per-adapter `PoolManager.pool_classes_by_scheme`. Implementation is
correct, preserves SNI/Host/cert verification, eliminates global mutable
state, and stays inside documented urllib3 extension points. No test
regressions expected — existing tests mock `requests.Session.get` and
bypass the adapter network path.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### 1. Smoke test is run-but-not-committed

The author ran a standalone smoke test that asserts the wiring is in
effect and that two adapters get distinct connection classes (no
cross-adapter state). That smoke test is exactly the right shape to land
as a unit test — it doesn't need network or Docker, and it would have
caught the `pool_classes_by_scheme`-clobber gotcha the author hit during
development. As-shipped, no committed test covers `_PinnedIPAdapter`
internals (verified: only `ssrf_guard.py` itself references
`_PinnedIPAdapter`/`init_poolmanager`/`pool_classes_by_scheme`).

**Suggested follow-up** (~15 lines, qa-tester or backend-security):
```python
def test_pinned_adapter_wires_pinned_pool_classes(self):
    a = _PinnedIPAdapter(hostname="example.com", pinned_ip="93.184.216.34")
    self.assertEqual(
        a.poolmanager.pool_classes_by_scheme["https"].ConnectionCls.__name__,
        "_PinnedHTTPSConnection",
    )

def test_pinned_adapter_instances_do_not_share_classes(self):
    a = _PinnedIPAdapter(hostname="a.example", pinned_ip="1.1.1.1")
    b = _PinnedIPAdapter(hostname="b.example", pinned_ip="2.2.2.2")
    self.assertIsNot(
        a.poolmanager.pool_classes_by_scheme["https"],
        b.poolmanager.pool_classes_by_scheme["https"],
    )
```

Non-blocking — the live behaviour is correct and the urllib3 trap is
documented inline. But the next refactor without a regression test will
have to re-derive the gotcha from scratch.

### 2. Per-call adapter / PoolManager construction (pre-existing, carry-forward)

`safe_get` and `safe_post` build a fresh `Session` + `_PinnedIPAdapter` +
`PoolManager` on every invocation. After this refactor the constructor
also synthesizes four fresh classes per call (factory-built
`_PinnedHTTPConnection`, `_PinnedHTTPSConnection`,
`_PinnedHTTPConnectionPool`, `_PinnedHTTPSConnectionPool`). Negligible at
admin-ingestion request rates; worth noting if these helpers ever get
adopted on a hot path. No connection pooling reuse across calls either,
which is the same shape as before. Carry-forward only.

### 3. `_new_conn` is the documented extension point but still semi-private

`_new_conn` carries a `# type: ignore[override]` comment because urllib3
doesn't formally type the override. The current code is correct against
urllib3 2.6.3, and the inline NOTE about `pool_classes_by_scheme` being
an instance attribute will help — but worth pinning urllib3 in
`requirements.txt` (or at least adding a constraint floor) so a major
version bump doesn't silently break this. (Quick check: `pyproject.toml`
or constraints file is the right home.) Non-blocking; defense-in-depth.

## Positive Observations

- **Eliminates real concurrency bug.** The previous monkey-patch had a
  benign-but-fragile race: thread B's `original_getaddrinfo` capture
  could observe thread A's patched version during overlap. The new
  design has no shared mutable state — each adapter owns its own
  `PoolManager` whose connection classes have the pinned IP captured in
  closure. Correctness is structural, not just transient.
- **TLS still verifies against the real hostname.** `self.host` on the
  connection object stays as the user-supplied hostname; only the dial
  target is overridden. `HTTPSConnection.connect()` passes
  `server_hostname=self.host` to the TLS wrap, so SNI and certificate
  match are preserved. This is the trickiest property to keep when
  IP-pinning, and the author got it right.
- **`Host` header preserved.** urllib3 builds `Host` from `self.host`,
  not the dial target — confirmed by reading the urllib3 source path.
  Webhook/CDN dispatch keeps working.
- **Caught a urllib3 2.x trap and documented it inline.** The
  `pool_classes_by_scheme = {...}` trick (replace the instance dict
  rather than override the class attribute) is non-obvious; the inline
  comment will save the next maintainer a debugging session.
- **`pool_classes_by_scheme` is the documented extension point** — used
  by urllib3 itself in `connection_from_pool_key`. No private-API
  reach-around.
- **Public API surface unchanged.** `safe_get`/`safe_post` signatures and
  `validate_external_url`/`validate_webhook_host` semantics are
  byte-identical from the caller's perspective. Existing tests in
  `backend/tests/test_safe_get_ssrf.py` and the `safe_post` suite remain
  meaningful regression coverage for the orchestration layer.
- **Defense-in-depth ordering preserved.** Validation
  (`validate_external_url`/`validate_webhook_host`) still runs before
  the adapter is constructed, so the primary SSRF gate is unchanged.
  This refactor only hardens the secondary (rebind-defense) layer.
- **Smoke test (even if not committed) was thorough.** Checked
  `pool_classes_by_scheme` was wired, `ConnectionCls` was the pinned
  subclass, `_new_conn` override existed on the class urllib3 will
  actually instantiate, and that two adapters got distinct classes. All
  the right invariants.
- **Backlog tracking.** Filed in `_BACKLOG.md` and self-marked DONE in
  the same edit — appropriate hygiene.

## Verification Notes

- Read full `ssrf_guard.py` post-refactor and the diff against `HEAD`.
  AST/imports clean; new imports (`PoolManager`, `HTTPConnection`,
  `HTTPSConnection`, `HTTPConnectionPool`, `HTTPSConnectionPool`) all
  exist in urllib3 2.6.3.
- Cross-checked: `_resolve_and_check` returns the raw IP string from
  `sockaddr[0]`, which `create_connection((ip, port), ...)` accepts for
  both IPv4 and IPv6 — no bracket-handling needed at this layer.
- Grep confirmed: no test file in `backend/` references
  `_PinnedIPAdapter`, `init_poolmanager`, or `pool_classes_by_scheme`.
  All existing SSRF tests mock `requests.Session.get` directly and
  therefore cannot regress on adapter wiring.
- pytest run deferred — same Docker/`pythonjsonlogger` blocker accepted
  at BE-SEC-P0 closeout. CI will exercise the unchanged `safe_get`/
  `safe_post` integration tests; the adapter internals remain uncovered
  until the smoke test is committed (Minor #1).

## Recommendations (non-blocking, posted to backend-security inbox)

1. Land the two unit assertions from the smoke test (Minor #1) — small
   diff, big regression-protection win for a tricky urllib3 surface.
2. Add a urllib3 version floor (or pin) so a future `urllib3>=3` bump
   doesn't silently break `pool_classes_by_scheme` semantics.
3. (Carry-forward) If `safe_get`/`safe_post` ever land on a hot path,
   consider caching the adapter per (hostname, pinned_ip) tuple to avoid
   per-call Session/PoolManager/class construction.

— lp-reviewer
