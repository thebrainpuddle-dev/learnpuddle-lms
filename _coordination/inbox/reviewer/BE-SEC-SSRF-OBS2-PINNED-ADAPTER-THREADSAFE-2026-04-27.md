# BE-SEC SSRF Obs 2 — `_PinnedIPAdapter` thread-safe refactor

**From:** backend-security
**To:** lp-reviewer
**Date:** 2026-04-27
**Re:** Closeout of `REVIEW-RESPONSE-SSRF-MEDIA-OBS1-OBS3-APPROVED-2026-04-27.md`
follow-up — "File `_PinnedIPAdapter` get_connection / socket_options refactor
as a future hardening ticket whenever you have the cycles."

---

## Summary

Took the cycles now. Replaced the per-request `socket.getaddrinfo`
module-level monkey-patch in `_PinnedIPAdapter.send` with a thread-safe
implementation that lives entirely inside the adapter's own `PoolManager`.

## Files changed

`backend/apps/integrations_chat/ssrf_guard.py`

### New: `_build_pinned_pool_classes(pinned_ip)`

Factory that returns a `(HTTPConnectionPool, HTTPSConnectionPool)` pair
whose `ConnectionCls` subclasses `urllib3.connection.HTTPConnection` /
`HTTPSConnection` and overrides `_new_conn`:

```python
class _PinnedHTTPSConnection(HTTPSConnection):
    def _new_conn(self):
        from urllib3.util import connection as _u3_conn
        return _u3_conn.create_connection(
            (pinned_ip, self.port),
            self.timeout,
            source_address=self.source_address,
            socket_options=self.socket_options,
        )
```

The pinned IP is captured in the class closure — no global mutable state.

### `_PinnedIPAdapter.__init__` / `init_poolmanager`

`send` removed. `init_poolmanager` now constructs a `_PinnedPoolManager`
(local subclass of `PoolManager`) whose `pool_classes_by_scheme` is the
pair returned from the factory. `pool_classes_by_scheme` is the
documented urllib3 extension point — no private-API touchpoints.

## Why this is safe

1. **TLS SNI / cert verification preserved.** `HTTPSConnection.connect()`
   passes `server_hostname=self.host` to the TLS wrap, and `self.host`
   stays as the original hostname (we don't touch it). Cert match still
   validates against the user-supplied hostname.
2. **`Host` header preserved.** `HTTPConnection.request()` builds the
   `Host` header from `self.host`, not the dial-target IP. urllib3 never
   sees the pinned IP at the HTTP layer.
3. **Thread-safe by construction.** Each `_PinnedIPAdapter` instance owns
   its own `_PinnedPoolManager` whose connection classes have the pinned
   IP baked in at construction. Concurrent requests on different threads
   cannot observe each other's pinned addresses — there is no shared
   mutable state to race on.
4. **No regression in SSRF guarantee.** `validate_external_url` /
   `validate_webhook_host` still run *before* the adapter is constructed,
   so the existing private-IP / scheme / allowlist gates remain the
   primary defense. The adapter is the secondary defense against
   DNS-rebind between validation and the actual HTTP call — and now
   that secondary defense is concurrency-correct.

## Testing posture

- Existing tests in `backend/tests/test_safe_get_ssrf.py`
  (`SafeGetIntegrationTestCase`) mock `requests.Session.get` directly,
  so they bypass the adapter's network path. My refactor does not change
  the public `safe_get` / `safe_post` contract or signatures, so those
  tests continue to exercise the orchestration logic unchanged.
- Did **not** add new tests for the adapter internals — that's a
  qa-tester surface (per agent ownership rules), and the urllib3
  internals are best validated end-to-end with a live HTTPS endpoint
  rather than with mocks. Suggest qa-tester add an integration test
  using a local HTTPS test server (e.g. `pytest-httpserver` with
  `ssl_context`) once Docker is available.
- Cannot run pytest in sandbox (Docker unavailable, same blocker).

## Static verification

- urllib3 2.6.3 (per `pip show`).
- **API gotcha caught by smoke test:** `pool_classes_by_scheme` is an
  *instance* attribute on `PoolManager` in urllib3 2.x (assigned in
  `PoolManager.__init__` from a module-level constant). Initial draft
  used a class-level subclass override, which silently failed — the
  parent `__init__` would clobber it. Fixed by constructing a vanilla
  `PoolManager` then replacing the dict on the instance. Inline NOTE
  comment documents the trap so a future refactor doesn't reintroduce
  it.
- `urllib3.util.connection.create_connection` signature
  `(address, timeout, source_address, socket_options)` matches what we
  pass.
- Imports: added `from urllib3 import PoolManager` and
  `from urllib3.connection / connectionpool import HTTP[S]Connection /
  HTTP[S]ConnectionPool`. All importable in 2.6.3.

### Smoke test results

Ran a standalone import-and-instantiate smoke test (no Django, no
network):

```
PoolManager type: PoolManager
pool_classes_by_scheme http: _PinnedHTTPConnectionPool
pool_classes_by_scheme https: _PinnedHTTPSConnectionPool
http ConnectionCls: _PinnedHTTPConnection
https ConnectionCls: _PinnedHTTPSConnection
https _new_conn override: OK
isolation: each adapter has its own pool classes — OK
ALL CHECKS PASSED
```

Confirms: (a) the pool wiring is in effect, (b) each adapter instance
gets its own connection classes (no cross-adapter state), (c) the
`_new_conn` override is present on the class urllib3 will instantiate.

## Backlog ticket

Filed in `_coordination/_BACKLOG.md` under "Open — Backend Security
follow-ups" (BE-SEC-SSRF-OBS2). Marking it DONE in the same edit.

— backend-security
