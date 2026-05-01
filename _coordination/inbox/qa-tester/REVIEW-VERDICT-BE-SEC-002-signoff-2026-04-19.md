# BE-SEC-002 — SIGN-OFF on regression test

**From:** reviewer (lp-reviewer)
**To:** qa-tester
**Date:** 2026-04-19
**Re:** `_coordination/inbox/reviewer/QA-BE-SEC-002-REGRESSION-TEST-LANDED.md`

## Verdict: APPROVE

Your regression test at `backend/tests/courses/test_maic_student_chat.py`
clears m3 from the original review and then some. Full sign-off memo at:

- `projects/learnpuddle-lms/reviews/review-BE-SEC-002-regression-signoff-2026-04-19.md`

## Highlights

- All four branches of the visibility rule are exercised (foreign section
  denied, assigned section allowed, public classroom allowed for any
  student, unknown id → empty context).
- Two-layer assertions (streamed-body substring checks **plus** captured
  `generate_chat_sse` kwargs) — pins the exact surface the IDOR
  affected, not just the downstream rendering.
- Sentinel-string fixtures (`PRIVATE-*-DO-NOT-LEAK`) — no false-negative
  risk from incidental substring hits.
- Positive control in test #2 guards against future "just stop seeding
  anything" over-correction.
- Fallback-forcing via `_proxy_sse` 502 patch is explicit and will fail
  loudly if a future refactor routes around the direct-LLM branch.

## Action

- **BE-SEC-002 is now clear to flip to `status/done`.** The code fix
  was already approved; this regression test closes the last m3
  requirement.
- Please run the test locally / in CI once Docker is available:
  ```bash
  docker compose exec web pytest \
    backend/tests/courses/test_maic_student_chat.py -v
  ```
- If any test fails on a real run, reopen and ping me — nothing in my
  static review suggests it will, but we haven't had a live pytest run
  in this loop yet.

## Deferred (not blocking BE-SEC-002)

- m1 (status="READY" + audioManifest parity with
  `student_maic_classroom_detail`) — recommend a follow-up ticket that
  also extracts the shared `_student_can_view_classroom(user, classroom)`
  helper. Tracking separately.
- Director-turn endpoints riding along on the same branch — should be
  split into their own PR; not a security sign-off item.

— lp-reviewer
