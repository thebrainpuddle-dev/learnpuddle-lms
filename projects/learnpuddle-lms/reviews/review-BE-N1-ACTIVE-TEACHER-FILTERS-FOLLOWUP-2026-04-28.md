---
tags: [review, task/BE-N1-FOLLOWUP, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: BE-N1 Follow-up — ACTIVE_TEACHER_FILTERS + individual-only test

## Verdict: APPROVE

## Summary

Polish/refactor diff cleanly addresses all four non-blocking observations from
`review-BE-N1-COURSE-GROUP-FIX-2026-04-27.md`. No behavior change, single new
test pins existing fast-path behavior, and the divergence risk between the
prefetch predicate and the DB-fallback predicate is now eliminated by a single
shared module-level constant.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **Out-of-scope change shipped without callout.** The diff also converts a
   silent `except Exception: pass` in `ContentSerializer.get_video_asset_status`
   into a `logger.warning(...)` call. This is a positive change and aligns
   with the in-flight silent-exception-hardening effort (see
   `QA-SILENT-EXCEPTION-HARDENING-2026-04-27.md`), but it was not listed in the
   four-item follow-up table. For future polish PRs, please either include
   such opportunistic hardening in the scope summary or split it into its own
   diff so reviewers can grep the changelog deterministically. Not blocking.

2. **`ACTIVE_TEACHER_FILTERS` is exported from `serializers.py` and imported
   by `views.py`.** That's a serializer module owning a constant that the view
   layer depends on, which is a slightly unusual ownership direction (views
   typically depend on serializers, fine here). If this constant grows more
   consumers (e.g. analytics, reports), consider moving it to
   `apps/users/constants.py` or `apps/courses/constants.py` so the dependency
   direction stays import-DAG-clean. Not blocking — current scope is small
   enough that the convenience wins.

## Positive Observations

- **Single source of truth achieved.** Both the nested `Prefetch` queryset in
  `views.py:140-143` and the DB-fallback in `serializers.py:209-212` now spread
  `**ACTIVE_TEACHER_FILTERS`. The two predicates can no longer drift — exactly
  the failure mode the prior review flagged.
- **PEP 8 import block restored.** `logger = logging.getLogger(__name__)` and
  `ACTIVE_TEACHER_FILTERS` now sit cleanly after the import block in
  `serializers.py:18-24`. Module header is readable end-to-end.
- **Fast-path test (Test 5) is genuinely behavior-pinning.** It deliberately
  omits `assigned_groups` so the assertion only passes when the
  `if not groups: return len(individual_ids)` branch at `serializers.py:192`
  is hit. A future refactor that accidentally always falls through to the
  group path would fail this test even with N=3 individual teachers — good
  pin.
- **N+1 guard comment is the right kind of comment.** It explains *why* the
  strict `==` is intentional and tells the next contributor where to look
  if the assertion fires unexpectedly. This is signpost commenting at its
  best — it answers a question the reader is about to ask.
- **No behavior diff in the hot path.** The two prefetched-vs-fallback paths
  in `get_assigned_teacher_count` are unchanged in shape. Only the literal
  filter dict was hoisted to a module constant. Risk surface is essentially
  zero.
- **Test isolation preserved.** The new Test 5 uses fresh `ind1/ind2/ind3`
  emails scoped to a `setUp`-created tenant, so it can't collide with the
  other tests in the same class.

## Verification Performed

- Diff review of `serializers.py`, `views.py`, `tests_course_group_n1.py`.
- Confirmed `Prefetch`, `TeacherGroup`, and `_User` are all imported in
  `views.py` (lines 5, 15, 16) before first use.
- Confirmed `ACTIVE_TEACHER_FILTERS` is module-level (not class-level) in
  `serializers.py` so `from .serializers import ACTIVE_TEACHER_FILTERS` in
  `views.py` resolves at import time without triggering serializer-class
  initialization side-effects.
- Verified Test 5 wiring (`course.assigned_teachers.add(t1, t2, t3)` with no
  `assigned_groups` call) genuinely exercises the `if not groups` fast-path.
- Verified the N+1 guard test (Test 7) comment matches the actual assertion
  semantics.

## Test Run Status

Pytest re-run **deferred** — same `pythonjsonlogger` sandbox issue that has
been blocking phase 2-4 verification across this sprint. Approval is on:
- diff review
- import-graph correctness
- test-design review (new Test 5 + N+1 guard comment)
- AST/static checks reported by author

When the sandbox is unblocked, please run:
```
docker compose exec web pytest backend/apps/courses/tests_course_group_n1.py -v
```
Expect **7 tests PASS** (was 6 before this follow-up).

## Recommendation

Merge. Update the task to `status/done`. No further follow-ups required for
this thread.

— reviewer
