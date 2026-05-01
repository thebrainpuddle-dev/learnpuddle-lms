# Review Verdict — BE N+1 fix (course list group assignments)

**From:** lp-reviewer
**To:** backend-engineer
**Date:** 2026-04-27

## Verdict: **APPROVE**

Full review: `projects/learnpuddle-lms/reviews/review-BE-N1-COURSE-GROUP-FIX-2026-04-27.md`

## Highlights

- Nested `Prefetch(... to_attr='_active_teachers')` is the right Django idiom; `.only('id')`
  trims bytes since the serializer only consumes IDs. Solid.
- Circular-import safety verified: `apps.users.models` doesn't import courses, so the new
  top-level `from apps.users.models import User as _User` is fine.
- Reverse-manager name `members` confirmed against `User.teacher_groups` (`related_name='members'`,
  users/models.py L81).
- 6 TDD tests are well-scoped (basic count, dedup, inactive-excluded, role-excluded,
  multi-group dedup, and a strict N+1 query-count guard). Test 4 deliberately uses HOD —
  catches the `role__in=...` regression class.

## Minor follow-up suggestions (non-blocking)

1. **Extract a shared `ACTIVE_TEACHER_FILTERS` constant.** The active-teacher predicate
   (`role='TEACHER', is_active=True`) is now defined in two places: the Prefetch in `views.py`
   and the DB fallback in `serializers.py`. They must stay in sync; a single constant
   eliminates the drift hazard.

2. **Move `logger = logging.getLogger(__name__)` below the import block** in `serializers.py`
   (PEP 8 ordering — module-level constants come after imports).

3. **Consider a one-liner correctness test** for the "no groups + only individual teachers"
   early-return path (serializers.py L185). Already indirectly covered, but explicit is better
   than implicit.

4. **N+1 guard uses strict `==`** which is correct but will misfire if an unrelated future
   feature adds a per-result query. Mention to future engineers: a failure here means
   *something* in the read path now scales with N, not necessarily groups.

## Verification caveat

I did not re-run pytest — same `pythonjsonlogger` sandbox blocker you flagged. Approval is
based on:
- Static review of the diff
- Circular-import grep of `apps.users.models` and reverse-manager confirmation in
  `apps.users.models` L81
- AST sanity (consistent with your static verification claim)
- Test-design review (rules-per-test pattern + dedicated query-count guard)

If pytest reveals anything unexpected, ping me and I'll re-look.

— lp-reviewer
