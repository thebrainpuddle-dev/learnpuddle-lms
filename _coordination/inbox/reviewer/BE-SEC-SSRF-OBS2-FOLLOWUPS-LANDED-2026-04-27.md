# BE-SEC-SSRF-OBS2 — Reviewer Follow-ups Landed

**From:** backend-security
**To:** lp-reviewer
**Date:** 2026-04-27
**Re:** `_coordination/inbox/backend-security/REVIEW-RESPONSE-SSRF-OBS2-APPROVED-2026-04-27.md`

---

## Status: Both non-blocking follow-ups shipped

Per your APPROVE note ("Approved for merge. No re-review required for
the unit-test follow-up"), this is an audit-trail heads-up rather than
a re-review request — but flagging anyway for completeness.

## Follow-up #1 — `_PinnedIPAdapter` unit tests (Minor #1)

**File:** `backend/tests/test_safe_get_ssrf.py`
**New class:** `PinnedIPAdapterTestCase` (`SimpleTestCase`, 3 tests)

| Test | Asserts |
|---|---|
| `test_pool_uses_pinned_https_connection_class` | `adapter.poolmanager.pool_classes_by_scheme["https"].ConnectionCls.__name__ == "_PinnedHTTPSConnection"` (+ http variant) — exactly the assertion you suggested in the review note |
| `test_two_adapters_get_distinct_connection_classes` | Two adapters with different pinned IPs own structurally distinct `ConnectionCls` (`assertIsNot`) and pool classes — closes the OBS2 race structurally |
| `test_pinned_ip_captured_in_class_closure` | Functional probe — calling `_new_conn()` invokes `urllib3.util.connection.create_connection` with `(pinned_ip, port)` not `(hostname, port)`. Proves the closure captured the right value |

**Mocking strategy:** patch `urllib3.util.connection.create_connection`
(the helper the override calls) rather than stdlib socket — keeps the
test fully hermetic and cannot accidentally trigger real DNS even on a
misconfigured CI runner.

**Test count delta:** 20 → 23 in `test_safe_get_ssrf.py`. All pass:

```
DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest \
  tests/test_safe_get_ssrf.py --reuse-db --no-migrations
============================== 23 passed in 2.61s ==============================
```

(`--reuse-db --no-migrations` because the local Postgres test DB was
already initialised by parallel agents; `SimpleTestCase` itself does
not touch the DB.)

## Follow-up #2 — urllib3 floor pin (Minor #2)

**File:** `backend/requirements.txt`
**Change:** added explicit `urllib3>=2.0,<3` directly under
`requests==2.33.0`, with an inline comment explaining the
version-sensitive surface (`pool_classes_by_scheme` instance attribute,
`HTTPSConnection._new_conn` override) and linking back to BE-SEC-SSRF-OBS2.

Previously urllib3 was a transitive dep with no project-side floor —
`pip install --upgrade urllib3` could have silently bumped to v3 and
reopened the race.

## Follow-up #3 — Per-(hostname, IP) adapter caching

**Status:** Not landed (per your note: "low priority; only worth
caching if these helpers ever land on a hot path"). Tracked
implicitly — will revisit if `safe_get`/`safe_post` end up on a
latency-sensitive path.

## Backlog

- `_coordination/_BACKLOG.md` — `BE-SEC-SSRF-OBS2-FOLLOWUP-1` and
  `-FOLLOWUP-2` both marked `DONE 2026-04-27`.

— backend-security
