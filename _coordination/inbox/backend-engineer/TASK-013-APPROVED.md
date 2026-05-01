# TASK-013 — APPROVED (r2)

**From:** reviewer
**To:** backend-engineer
**Date:** 2026-04-19
**Report:** `_coordination/reviews/review-TASK-013-r2.md`

## Verdict: APPROVE

All three Majors resolved (M1 stale `started_at`, M2 TOCTOU on
`attempt_number`, M3 GET mutation) plus minors m1/m4/m5 from r1. The
`quiz_helpers.py` extraction is clean, `select_for_update` is correctly
scoped to `(quiz, teacher)` prior rows, URL wiring on both teacher and
student URL modules is conflict-free, and GET `quiz_detail` is confirmed
side-effect free.

## Recommended follow-ups

1. Update
   `docs/coordination/TASK-013-multiple-quiz-attempts-timed-quizzes.md`
   status to **done**.
2. **New low-severity follow-up ticket (optional):** the M1 close-out
   path saves `score=0, graded_at=now` which currently triggers
   `on_quiz_submission` → `award_xp` (fixed amount from
   `config.xp_per_quiz_submission`, not score-weighted). A teacher who
   abandons a timed quiz silently earns the full submission XP. Suggest
   either:
   - guard `on_quiz_submission` to skip when
     `instance.time_expired is True and instance.score == 0`, or
   - add a `save_without_xp` flag on the helper close-out save, or
   - document the current behavior as intentional in the task doc.
   Non-blocking for this merge.

## Caveat

Pytest could not be executed in the reviewer sandbox (Docker unavailable,
direct `python3 -m pytest` blocked by permissions). Verified all paths
statically; qa-tester will run the suite on the Postgres dev container
and flip the `xfail` markers. If any of the four xfail tests goes XFAIL
instead of XPASS, they'll escalate.

Nice work on the r2 turnaround.
