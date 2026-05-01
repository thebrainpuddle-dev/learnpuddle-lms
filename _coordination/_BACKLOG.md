# Open — Backend Security follow-ups

## Hardening (🟡)

- ~~**BE-SEC-SSRF-OBS2** — `backend/apps/integrations_chat/ssrf_guard.py` `_PinnedIPAdapter.send` (lines ~177-195) — Replace the per-request `socket.getaddrinfo` module-level monkey-patch with a thread-safe primitive: subclass `urllib3.connection.HTTPSConnection` overriding `_new_conn` to `socket.create_connection((self._pinned_ip, self.port), ...)` and wire it through `init_poolmanager` so each `_PinnedIPAdapter` instance only mutates its own pool's connection class. Preserves SNI/Host (the connection's `self.host` already carries the original hostname). Reviewer note from `REVIEW-RESPONSE-SSRF-MEDIA-OBS1-OBS3-APPROVED-2026-04-27.md`: "Not blocking; SSRF guarantee holds via `validate_external_url` running first." Concurrency hazard: under simultaneous pinned requests on different threads, the in-flight monkey-patch can leak so one thread's `getaddrinfo` returns another's pinned IP. Owner: backend-security.~~ DONE 2026-04-27 — implemented via `_build_pinned_pool_classes(pinned_ip)` factory + per-adapter `_PinnedPoolManager` (`pool_classes_by_scheme`). No global mutable state; `self.host` preserved for SNI/Host. Pending review.

- ~~**BE-SEC-SSRF-OBS2-FOLLOWUP-1** — Land smoke unit tests for `_PinnedIPAdapter` internals (no committed coverage today; existing SSRF tests mock `requests.Session.get` and bypass the adapter network path). Reviewer ask in `REVIEW-RESPONSE-SSRF-OBS2-APPROVED-2026-04-27.md` (Minor #1). Owner: backend-security.~~ DONE 2026-04-27 — added `PinnedIPAdapterTestCase` (3 tests) to `backend/tests/test_safe_get_ssrf.py`: (a) `pool_classes_by_scheme["https"].ConnectionCls` is the pinned subclass, (b) two adapters with different pinned IPs own structurally distinct connection classes, (c) `_new_conn` actually dials the pinned IP not the hostname (closure capture proof). All 23 tests in the file pass under `--reuse-db --no-migrations`.

- ~~**BE-SEC-SSRF-OBS2-FOLLOWUP-2** — Pin urllib3 floor in `backend/requirements.txt` (`urllib3>=2.0,<3`) so a future v3 bump cannot silently break `pool_classes_by_scheme` / `_new_conn` override surface. Reviewer ask in `REVIEW-RESPONSE-SSRF-OBS2-APPROVED-2026-04-27.md` (Minor #2). Owner: backend-security.~~ DONE 2026-04-27 — added explicit `urllib3>=2.0,<3` line under `requests==2.33.0` with a comment explaining the version-sensitive surface and linking to BE-SEC-SSRF-OBS2.

---

# Sprint 2 Batch 4 — Review Round 1 Backlog

## Should-Fix (🟡)

- ~~**F6** — `backend/tests/courses/test_logging_phases.py:19` — Remove module-level `pytestmark = pytest.mark.django_db`; scope `@pytest.mark.django_db` only to `test_json_retry_warn_carries_phase_field` which uses the `ai_config` → `tenant` DB fixture. The 3 pure-Python tests (`test_maic_phase_enum_values`, `test_log_extra_schema`, `test_log_extra_classroom_id_defaults_to_empty_string`) and `test_enforce_budgets_warn_carries_phase_field` run without Postgres.~~ DONE 2026-04-24

- ~~**F9** — Add `.github/workflows/e2e.yml` — standalone CI workflow that spins up Postgres + Redis, seeds demo tenant, starts Django + Vite, and runs the Playwright e2e suite on pull_request + workflow_dispatch.~~ DONE 2026-04-24

## Forward-Looking (🟢)

- ~~**F8** — Add TODO comment in `playwright.config.cjs` near `workers: 1` noting that parallelism depends on F9 CI stability and whether tests share classroom state.~~ DONE 2026-04-24

## Doc Nit (🟢)

- ~~**F10** — Document password dependency: add docstring note to `create_demo_tenant.py` that `Teacher@123` is wired into e2e suite; add source-of-truth comment in `maic-full-playback.spec.js`.~~ DONE 2026-04-24

---

# Sprint 2 Batch 2 — Review Round 1 Backlog

## Must-Fix (🔴)

_(none from this batch)_

## Should-Fix (🟡)

- ~~**F4** — Add unit tests for SW image cache logic at `frontend/public/service-worker.js`. Covers `isImageRequest()`, LRU eviction at 50 entries, `imageStaleWhileRevalidate()` flows, Authorization-skip. node:vm sandbox approach. ≥10 tests.~~ DONE 2026-04-24

## Mobile UX Nit (🟢)

- ~~**F5** — `OfflineIndicator.tsx:53` — `fixed bottom-4` overlaps iOS keyboard. Use `visualViewport` API to compute safe bottom when keyboard open; fall back to `bottom-4`. Add 2 tests.~~ DONE 2026-04-24

## Doc Nit (🟢)

- ~~**F6** — `service-worker.js:97-100` — Add comment explaining Authorization-skip order vs image-request branch. Note `<img>` tags are unaffected.~~ DONE 2026-04-24
