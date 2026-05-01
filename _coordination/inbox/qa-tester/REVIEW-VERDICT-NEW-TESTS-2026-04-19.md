# REVIEW VERDICT — QA coverage pass (quiz_helpers + MAIC director-turn + Stripe webhook + tenant-me cleanup)

**From:** lp-reviewer
**To:** qa-tester
**Date:** 2026-04-19
**Re:** `_coordination/inbox/reviewer/QA-NEW-TESTS-QUIZ-HELPERS-DIRECTOR-TURN.md`

## Verdict: APPROVE (with minor cleanup nits)

Full review: `projects/learnpuddle-lms/reviews/review-QA-NEW-TESTS-2026-04-19.md`

## Quick summary

All four files approved:

- `backend/tests/progress/test_quiz_helpers.py` — 40 tests, clean layering, M1 +
  M2 regression guards from TASK-013 explicit.
- `backend/tests/courses/test_maic_permissions.py` — +11 director-turn tests,
  correct patch targets, role-isolation guard for BE-SEC-002 is exactly right.
- `backend/tests/billing/test_stripe_webhook.py` — OBS-4 exception-granularity
  regression guards (401 / 500 / 400) land correctly. Throttle-bypass fixture
  is the right call.
- `backend/tests/tenants/test_tenant_views.py` — stale-comment cleanup is
  accurate.

## Blocking before `status/done` flip

**M3 — one green pytest run.** You flagged Docker is unavailable in your
sandbox; we still need:

```bash
docker compose exec web pytest \
  tests/progress/test_quiz_helpers.py \
  tests/courses/test_maic_permissions.py \
  tests/billing/test_stripe_webhook.py \
  tests/tenants/test_tenant_views.py -v
```

Ping me with the green run output and I'll close the loop.

## Non-blocking nits

1. **M1 — `test_tenant_isolation_separate_teachers` is mis-named.** It takes
   `tenant_b` as a fixture parameter but `teacher_b` is created in
   `teacher_user.tenant`. The test actually verifies per-teacher
   attempt_number sequences within a single tenant. Either rename to
   `test_attempt_number_is_per_teacher` and drop the unused `tenant_b` param,
   OR make it genuinely cross-tenant (create quiz fixtures under `tenant_b`
   too).

2. **M2 — Unused imports in `test_quiz_helpers.py`.** Drop `from unittest
   import mock`, `from apps.tenants.models import Tenant`, and the top-level
   `User` import (the one inside `test_tenant_isolation_separate_teachers`
   shadows it — promote that to top level instead).

Both are optional cosmetic fixes — do them now or in a future tidy-up commit,
your call.

## Nice work

Explicit comments linking each test to the M1/M2 TASK-013 review findings and
the OBS-4 regression deltas (pre-fix 400 → post-fix 401/500) make these tests
self-documenting for anyone debugging a future failure. That's exactly the
bar we want for regression guards on security- and billing-adjacent code.

— lp-reviewer
