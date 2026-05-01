---
tags: [review, task/qa-test-coverage-pass, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-19
---

# Review: QA coverage pass — quiz_helpers, MAIC director-turn, Stripe webhook, tenant-me cleanup

## Verdict: APPROVE (with minor cleanup nits)

Scope: tests-only PR from qa-tester. No production code touched. Inbox ticket
marked "FYI / optional review"; I still walked the diffs since three of the
four files target security- and billing-sensitive code paths.

## Summary

Strong defensive coverage pass. All four test files land meaningful regression
guards on recently-shipped code (TASK-013 quiz helpers, BE-SEC-002 MAIC
director-turn role boundaries, OBS-4 Stripe exception granularity,
BE-SEC-001 `@tenant_required` stale-comment cleanup). Behaviour assertions
match production implementations I cross-read (`apps/progress/quiz_helpers.py`,
`apps/billing/webhook_views.py`). Zero risk to prod; approve for merge once
a live `pytest` run in Docker confirms green — the author flagged this is still
pending because Docker is unavailable in the QA sandbox.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### M1 — `test_quiz_helpers.py::test_tenant_isolation_separate_teachers` is mis-named

`backend/tests/progress/test_quiz_helpers.py:608-627`

The test takes `tenant_b` as a fixture parameter but never uses it. `teacher_b`
is created in `teacher_user.tenant` (line 618: `tenant=teacher_user.tenant`).
The test actually verifies "two teachers in the **same** tenant each get their
own attempt_number sequence" — which is legitimate behaviour to pin — but the
name and the unused `tenant_b` fixture parameter imply cross-tenant isolation
that the test does not exercise.

Two clean options:
1. Rename to `test_attempt_number_is_per_teacher` and drop the `tenant_b`
   parameter, OR
2. Actually exercise cross-tenant: create `teacher_b` in `tenant_b`, also
   create a `Course`/`Assignment`/`Quiz` in `tenant_b`, and assert each
   teacher's `start_quiz_attempt` only sees their own tenant's quiz rows.

Option 1 is the low-effort fix since the current assertion body doesn't need
cross-tenant data.

### M2 — Unused imports in `test_quiz_helpers.py`

```python
from unittest import mock                 # line 22 — never referenced
from apps.tenants.models import Tenant    # line 42 — never referenced
from apps.users.models import User        # line 43 — shadowed by the local
                                          # `from apps.users.models import User`
                                          # inside test_tenant_isolation_…
```

Drop them. The local re-import at line 612 can also be promoted to the top.

### M3 — QA author could not run the tests

The handoff memo explicitly states Docker is unavailable in the agent sandbox,
so these tests were written but never executed. That is not a blocker for
test-only additions (they can't break prod), but before `status/done` flips we
need one green run of:

```bash
docker compose exec web pytest \
  tests/progress/test_quiz_helpers.py \
  tests/courses/test_maic_permissions.py \
  tests/billing/test_stripe_webhook.py \
  tests/tenants/test_tenant_views.py -v
```

Any red test at runtime → `status/in-progress` and we reopen.

## Positive Observations

1. **`test_quiz_helpers.py`** — Cleanly layered: pure-function tests first
   (`validate_answers_payload`, `serialize_attempt`, `_is_expired`) using
   lightweight stub objects, DB-backed tests second. Stubs for `_is_expired`
   are a nice touch — avoids unnecessary DB fixtures for a pure time check.
   Coverage of M1 (stale-close) and M2 (`select_for_update` race) from the
   TASK-013 review is explicit and well-commented.

2. **`test_maic_permissions.py` extensions** — The 403-for-teacher-on-student-
   endpoint assertion is the exact regression guard we wanted from BE-SEC-002:
   it prevents a future decorator swap from silently weakening role isolation.
   LLM calls are mocked via `mock.patch("apps.courses.maic_views.director_next_turn", …)`
   at the import site — correct patching target; would not accidentally hit
   the real provider if `OPENROUTER_API_KEY` were set in the test env.

3. **`test_stripe_webhook.py`** — Nails the OBS-4 delta:
   - `SignatureVerificationError` → 401 (line 133)
   - `Exception` → 500 (line 161)
   - `ValueError` → 400 (unchanged)
   Plus the handler-crash case (line 239) documents the "log-and-return-200"
   behaviour that prevents pointless Stripe retries for application bugs. The
   autouse `bypass_stripe_throttle` fixture (line 56) is the right call —
   keeps exception-handling assertions deterministic.

4. **`test_tenant_views.py` stale-comment cleanup** — Docstring now
   accurately describes the `@tenant_required` regression guard instead of
   the misleading "intentionally failing" marker. Zero logic change. 

5. **Mock targeting is correct throughout.** The Stripe webhook test patches
   `apps.billing.webhook_handlers.handle_checkout_session_completed` — this is
   the module attribute `getattr(webhook_handlers, handler_name, None)` resolves
   against in `webhook_views.py:76`, so the mock is actually seen. I verified
   that path.

## Action Items

1. **qa-tester (non-blocking):** address M1 and M2 in a follow-up tidy-up
   commit. If you'd rather leave them, fine — they do not affect correctness.
2. **Blocking for `status/done` flip:** one green local/CI pytest run per the
   command in M3.

## Notifications

- qa-tester inbox: APPROVE + nits.
- shared-log: appended.

— lp-reviewer
