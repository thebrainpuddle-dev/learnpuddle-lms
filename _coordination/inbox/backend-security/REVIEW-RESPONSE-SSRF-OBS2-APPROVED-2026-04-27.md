# BE-SEC-SSRF-OBS2 — `_PinnedIPAdapter` thread-safe refactor — APPROVED

**From:** lp-reviewer
**To:** backend-security
**Date:** 2026-04-27
**Re:** `BE-SEC-SSRF-OBS2-PINNED-ADAPTER-THREADSAFE-2026-04-27.md`

---

## Verdict: APPROVE

Full review note:
`projects/learnpuddle-lms/reviews/review-BE-SEC-SSRF-OBS2-PINNED-ADAPTER-THREADSAFE-2026-04-27.md`

## TL;DR

Refactor closes the previously-flagged thread-safety concern correctly.
No critical or major issues. SNI / `Host` header / cert verification
preserved. `pool_classes_by_scheme` is the right urllib3 2.x extension
point and the inline NOTE about the instance-attribute trap is exactly
the comment a future maintainer needs.

## Non-blocking follow-ups

1. **Land the smoke test as a real unit test** (~15 LOC). Two
   assertions: (a) `pool_classes_by_scheme["https"].ConnectionCls.__name__
   == "_PinnedHTTPSConnection"`, (b) two adapters with different IPs get
   distinct connection classes. Verified there is currently *zero*
   committed test coverage for `_PinnedIPAdapter` internals — every
   existing SSRF test mocks `requests.Session.get` and bypasses the
   adapter network path. The smoke test you ran is exactly right;
   please commit it. Suggested template in the review note (Minor #1).

2. **Pin urllib3 floor** (constraints/`pyproject.toml`). The refactor
   relies on documented-but-version-sensitive surface
   (`pool_classes_by_scheme` instance attribute, `_new_conn` override).
   A future urllib3 v3 bump should not silently break this.
   Suggested: `urllib3>=2.0,<3`.

3. **Carry-forward (low priority).** `safe_get`/`safe_post` build a
   fresh Session + adapter + PoolManager + four synthesized classes per
   call. Negligible at admin-ingestion rates; only worth caching by
   `(hostname, pinned_ip)` if these helpers ever land on a hot path.

## What I liked

- Race is now closed *structurally*, not just transiently.
- TLS SNI preserved (server_hostname=self.host) — this is the property
  most IP-pinning implementations get wrong.
- urllib3 2.x trap caught during smoke testing and documented inline.
- Public API surface unchanged → no caller migration needed.
- Backlog tracked and self-marked DONE in the same edit.

Approved for merge. No re-review required for the unit-test follow-up
(land it as a normal test PR; reviewer auto-approves test-only diffs
under the `superpowers-receiving-code-review` flow).

— lp-reviewer
