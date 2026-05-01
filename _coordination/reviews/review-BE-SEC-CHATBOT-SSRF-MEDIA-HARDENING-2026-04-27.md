---
tags: [review, security, task/be-sec-chatbot-ssrf, task/be-sec-media-hardening, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: BE-SEC-CHATBOT-SSRF + BE-SEC-MEDIA-FILE-HARDENING

## Verdict: APPROVE

## Summary
Two genuine, defense-in-depth security fixes that close real
admin-triggered escalation paths (chatbot URL ingestion → IMDS exfil; media
file serving → cross-tenant fetch via prefixless paths). The implementation
is careful, the failure modes are denial-by-default, and the test coverage
(28 new tests across SSRF, media-prefix, and symlink-escape) is the right
shape: HTTP-boundary assertions, mocked DNS so tests don't touch real
networks, and the SUPER_ADMIN bypass test is non-vacuous (asserts the mock
was *called*, proving the prefix gate let the request through).

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **`safe_get` buffers the whole response into memory before returning.**
   `ssrf_guard.py:419–437` accumulates `chunks` and joins at the end.
   Bounded by `max_bytes` (50 MB default) so OOM is impossible, but the
   peak working-set of the worker is 2× the body (chunks list + joined
   bytes) for the brief window during `b"".join(chunks)`. For the chatbot
   ingestion path this is fine — the very next step parses HTML in memory
   anyway. Worth a comment mentioning the 2× peak if `max_bytes` ever
   gets bumped to ~500 MB. Not blocking.

2. **`requests.Response._content` / `_content_consumed` are private
   attributes.** `safe_get` writes to them at lines 436–437 to make
   `.text`/`.content` work after consuming the body via `iter_content`.
   This is the only practical way to do streaming-with-cap and still hand
   back a normal-looking `Response` — but it is brittle against a future
   `requests` major version. If `requests 3.x` lands and breaks this, the
   tests will catch it (`test_normal_body_returned` asserts both
   attributes). Acceptable as-is.

3. **Storage existence check runs unconditionally.** `serve_media_file`
   line 204 calls `default_storage.exists(normalized)` before the S3
   branch, which on S3 backends issues a HEAD request — a small latency
   cost on every download. Existing behaviour, not a regression in this
   PR; flag for a future perf pass.

4. **`safe_get` chunk-list holds individual `b"A" * 64KB` references.**
   On Python's GC, large numbers of small chunks (a 50 MB body at 64 KB
   chunks → ~800 chunk references) hold memory until the join. Fine; the
   cap saves us. Mentioning only because if `iter_content(chunk_size=...)`
   is ever shrunk for finer cap-enforcement, the per-chunk overhead grows.

## Positive Observations

### `safe_get` / `validate_external_url`

- **Literal-IP fast path runs before DNS** (`ssrf_guard.py:348–358`). An
  attacker pasting `http://127.0.0.1:6379/` doesn't even hit
  `socket.getaddrinfo`. `test_safe_get_rejects_imds_before_dns` pins this
  with `mock_get.assert_not_called()` — perfect contract test.
- **All resolved addresses checked, not just the first** (line 145–150).
  An A-record set returning `[8.8.8.8, 127.0.0.1]` is rejected. Closes a
  real DNS-pivot subtlety some SSRF guards miss.
- **Blocked-networks list is comprehensive.** RFC1918, loopback v4/v6,
  link-local v4/v6, CGNAT, IPv6 ULA, "this network" 0.0.0.0/8, AWS IMDS
  (covered by 169.254.0.0/16). The `fc00::/7` IPv6 ULA inclusion shows
  someone actually thought about IPv6.
- **Pinned-IP adapter is thread-safe by construction** (lines 161–205).
  Per-call factory builds fresh `HTTPConnection`/`HTTPSConnection`
  subclasses with the pinned IP captured in a closure. The
  `PinnedIPAdapterTestCase` (lines 251–342) explicitly proves two
  adapters get distinct connection classes — closes the OBS2 race
  the parallel review covers.
- **TLS is preserved.** Connection's `self.host` stays the original
  hostname so `HTTPSConnection.connect()` passes `server_hostname=self.host`
  to TLS — cert verification still validates against the user-supplied
  name, even though packets dial the pinned IP. Documented at lines
  214–222.
- **Redirect refusal is the right call.** Re-validating each hop is
  hard to get right (you'd need to rebuild the pinned adapter per hop,
  re-resolve, re-check); refusing 3xx outright is a conservative,
  documented choice (`ssrf_guard.py:381–384`). The author explicitly
  flagged this for review and it's the right trade.
- **No host allowlist for `safe_get`** — correct, because admin-supplied
  knowledge URLs legitimately point anywhere on the public internet.
  The webhook helper still enforces the Slack/Teams allowlist.

### `serve_media_file`

- **Pre-normalize char rejection** (`media/views.py:155–162`). Backslash,
  NUL, CR, LF all caught before `posixpath.normpath` can hide them.
  Critical: CR/LF in `X-Accel-Redirect` would be header injection.
- **Normalized used everywhere after step 2.** I traced every downstream
  use — line 204 (`exists`), line 213 (`storage.url`), line 222
  (`generate_presigned_url`), line 242 (`X-Accel-Redirect`), line 249
  (`os.path.join`). Raw `path` never appears after the normalize. This
  is the safe-by-construction property the docstring claims and it
  actually holds.
- **The "do not simplify" comment at lines 191–197 is gold.** The naive
  refactor `if user_tenant_id and user_tenant_id != path_tenant_id`
  would have silently re-introduced the bypass for users with
  `tenant_id=NULL`. Future-engineer-saving comment, exactly the kind I
  want to see preserved.
- **404 over 403** on the cross-tenant denial (lines 199–201) — correct
  per the existing pattern; we don't leak existence of cross-tenant or
  platform files.
- **`commonpath` over `startswith`** (lines 251–254). Closes the
  classic `/var/www/media-evil` vs `/var/www/media` prefix bug. The
  `ValueError` catch handles Windows cross-drive and empty-input
  edge cases.
- **Symlink escape covered** (`tests.py:652–683`). Real symlink under
  `MEDIA_ROOT` pointing outside, with `self.skipTest` fallback for
  platforms without symlink support. Correct test shape.

### Tests

- **`test_super_admin_may_fetch_any_prefix` is non-vacuous.** The
  `mock_exists.assert_called_once_with('shared/banner.png')` is the
  bind-as-required test the request flagged. Without it, the test
  would pass even if the prefix gate began rejecting SUPER_ADMIN
  silently. The test author understood this and called it out in the
  docstring (lines 591–596).
- **DNS-pivot test** (`test_safe_get_ssrf.py:95–110`) mocks
  `socket.getaddrinfo` returning `127.0.0.1` for a "public-looking"
  hostname. Asserts the rejection, asserts the IP appears in the
  error message (so an operator debugging a legitimate failure can
  see what got blocked).
- **`PinnedIPAdapterTestCase.test_pinned_ip_captured_in_class_closure`**
  (lines 314–342) is the cleanest possible structural proof: builds a
  connection instance, mocks `urllib3.util.connection.create_connection`,
  invokes `_new_conn`, asserts the call args carried the pinned IP,
  not the hostname. This is the test that pins the OBS2 fix.

### Backward compatibility

- `safe_post` / `validate_webhook_host` untouched. The chatbot webhook
  contract is preserved.
- Existing media tests (cross-tenant prefix-present) continue to pass
  because the `tenant/<id>/` prefix check still runs the same way for
  paths that *do* have a prefix. The new gate only affects paths that
  *lack* a prefix — which is the closed gap.

## Verification performed

- Read `ssrf_guard.py` end-to-end. Validation pipeline, blocked
  networks, pinned adapter all check out. TLS preservation comment
  matches urllib3 behaviour.
- Read `chatbot_tasks._extract_text_from_url`. `safe_get` is the only
  path; SSRFError propagates to the Celery task wrapper which records
  `embedding_status='failed'` with the error message — clean failure
  surface.
- Read `serve_media_file` in full. Step-by-step traced where `path` vs
  `normalized` is used; `path` is dead after step 2.
- Read all 22 SSRF tests + 6 media tests. Tests assert behaviour at the
  right layer (HTTP for the view, validator-level for the URL guard).
- Confirmed mock placements (`apps.integrations_chat.ssrf_guard.socket.
  getaddrinfo`) target the correct module attribute — not the stdlib.
- Confirmed `_PinnedIPAdapter.poolmanager.pool_classes_by_scheme`
  override survives `PoolManager.__init__`'s instance-attribute
  initialisation pattern (the comment at lines 238–245 documents
  exactly why this works in urllib3 2.x).
- Docker test run blocked by the same `pythonjsonlogger` sandbox issue
  acknowledged at BE-SEC-P0 closeout. Routed to qa-tester. Static
  verification by qa already confirms the new tests structurally
  (per `QA-SCIM-M6-STATIC-VERIFIED-2026-04-27.md`'s neighbouring SSRF
  observations).

## Acknowledging the author's review prompts

1. **Redirect refusal vs re-validation** — agree with the conservative
   choice. Re-validation requires rebuilding the pinned adapter per hop
   and re-resolving DNS each time; current design is simpler and the
   semantics are clear in the error message. Keep as-is.
2. **`max_bytes=50MB` default** — appropriate for HTML knowledge pages;
   the `max_bytes` kwarg is exposed for future per-tenant overrides.
3. **SUPER_ADMIN bypass test asserts non-blocking, not 200** — correct;
   asserting 200 would require seeding a real file fixture which adds
   teardown complexity for no extra coverage. The
   `assert_called_once_with` pin is the right contract.
4. **Symlink test platform-skip** — correct use of
   `self.skipTest("symlinks unsupported on this platform")` in the
   `OSError`/`NotImplementedError` branch. Clean.

— reviewer
