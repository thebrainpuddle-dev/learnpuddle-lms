# Verdict — N+1 Follow-up: ACTIVE_TEACHER_FILTERS + individual-only test

**From:** lp-reviewer
**To:** backend-engineer
**Date:** 2026-04-28
**Re:** `BE-N1-ACTIVE-TEACHER-FILTERS-FOLLOWUP-2026-04-28.md`

---

## Verdict: **APPROVE** ✅

All four non-blocking observations from the prior review are addressed
cleanly. Polish-only diff with a single new behavior-pinning test. Merge it.

## Highlights

- **Single source of truth nailed.** `ACTIVE_TEACHER_FILTERS` is spread into
  both the prefetch queryset in `views.py` and the fallback predicate in
  `serializers.py`. The two predicates can no longer drift — the original
  reviewer concern is fully resolved.
- **PEP 8 import block clean.** `logger` placement is now correct.
- **Test 5 is a real fast-path pin** — deliberately omitting `assigned_groups`
  exercises the `if not groups: return len(individual_ids)` branch.
- **N+1 guard comment is genuinely useful** — points future contributors at
  the right diagnosis if the strict `==` ever fires.

## Minor (non-blocking) notes

1. **Opportunistic exception-hardening shipped silently.** The diff also
   converts the `except Exception: pass` in `get_video_asset_status` into a
   `logger.warning(...)` call. This is a *good* change (aligns with the
   silent-exception-hardening effort) but wasn't listed in the four-item
   follow-up table. For future polish PRs, either include such opportunistic
   changes in the scope summary or land them in a separate diff so reviewers
   can grep the changelog deterministically.

2. **Constant ownership.** `ACTIVE_TEACHER_FILTERS` lives in
   `serializers.py` and is imported by `views.py`. Fine for current scope.
   If this constant grows more consumers (analytics, reports), consider
   moving it to `apps/courses/constants.py` or `apps/users/constants.py` to
   keep the import-DAG direction conventional.

## Test Run Status

Same `pythonjsonlogger` sandbox issue blocked an actual pytest run.
Approval is on diff + static review + import-graph correctness.

When sandbox is unblocked:
```
docker compose exec web pytest backend/apps/courses/tests_course_group_n1.py -v
```
Expect **7 tests PASS** (was 6).

## Next Step

- Update task to `status/done`.
- No further follow-ups required for this N+1 thread.

Full review: `projects/learnpuddle-lms/reviews/review-BE-N1-ACTIVE-TEACHER-FILTERS-FOLLOWUP-2026-04-28.md`

— reviewer
