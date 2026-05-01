---
tags: [review, task/BE-N1-course-group, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-27
---

# Review: BE-N1 — CourseListSerializer N+1 fix for group assignments

## Verdict: APPROVE

## Summary
Eliminates the last N+1 in `GET /api/v1/courses/`: the per-course `User.objects.filter(...).count()`
that the serializer's `get_assigned_teacher_count` issued for courses with `assigned_groups`. Fix
uses Django's nested `Prefetch(... to_attr='_active_teachers')` to load active teacher IDs in
bulk; serializer prefers the prefetched lists and falls back to the existing DB query when used
outside the list-view queryset. 6 TDD tests cover correctness (5) and the N+1 contract (1). I'd
ship this.

## Verification

| Check | Result |
|---|---|
| Engineer test count claim | 6/6 (per request) |
| Reviewer static review of diff | views.py (top-level User import, nested Prefetch with `.only('id')`, single quoted-string `members` reverse manager), serializers.py (prefetch-aware path + DB fallback preserved) — all clean |
| Circular-import safety check | `apps.users.models` does not import from `apps.courses` (verified via grep). `User.teacher_groups` uses the string ref `'courses.TeacherGroup'`, so the new top-level `from apps.users.models import User as _User` in `apps.courses.views` is safe |
| Reverse-manager name | `User.teacher_groups` declares `related_name='members'` (users/models.py L81). Prefetch path `'members'` and `to_attr='_active_teachers'` both line up |
| Reviewer pytest re-run | **Not completed** — engineer's request notes the same `pythonjsonlogger` sandbox constraint that's been blocking docker pytest runs all of Phase 2-4. Static review + AST validation stand in |

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Active-teacher filter duplicated in two places.** The Prefetch in `views.py`
   (`role='TEACHER', is_active=True`) and the DB fallback in `serializers.py`
   (`role='TEACHER', is_active=True` inside the User filter) define what counts as an
   "active teacher" twice. If one ever changes (e.g., `is_deleted=False`, or HOD/IB_COORDINATOR
   start counting), the other must change in lockstep or the prefetched and fallback paths will
   silently disagree. **Recommendation (non-blocking):** extract a single `_active_teacher_q()`
   helper or constant on the User model / a shared util:
   ```python
   ACTIVE_TEACHER_FILTERS = {'role': 'TEACHER', 'is_active': True}
   ```
   Both call sites import it. Adds one line of indirection, removes a real drift hazard.

2. **Order of imports in `serializers.py`.** Diff adds `import logging` + `logger = logging...`
   between `from rest_framework import serializers` and `from django.db import transaction`
   (above L8). PEP 8 says module-level constants come *after* all imports. Move the `logger =`
   line below the import block. Cosmetic.

3. **`hasattr` guard is per-group.** `if all(hasattr(g, '_active_teachers') for g in groups)` is
   correct but slightly verbose for the common case. In practice when one group on a queryset
   has the attr, all do (because they came from the same prefetch). The check is defensive but
   safe. No change needed; flagging only because a future contributor might wonder why it isn't
   `if groups and hasattr(groups[0], '_active_teachers')`. Either is fine.

4. **N+1 guard test asserts strict equality** (`queries_with_three == queries_with_one`). The
   strictest possible guarantee — good — but if anyone adds a different feature that introduces
   a per-result query (unrelated to groups), this test will start failing for the wrong reason.
   Loose alternative: `assertLessEqual(queries_with_three, queries_with_one + 1)` to allow one
   extra (e.g., if pagination cursoring adds a count query). Keep as-is; current strictness is
   the right starting point. Just be ready to interpret a future failure thoughtfully.

5. **Test correctness coverage missing one branch:** "no groups + only individual teachers" —
   the early-return at `if not groups: return len(individual_ids)` (serializers.py L185). Already
   covered indirectly by existing `tests_completion_rate.py` per the request, but worth a one-
   liner unit test in this new file to keep the contract local and explicit. Non-blocking.

## Positive Observations

- **`.only('id')` on the nested Prefetch** — minimal data over the wire, since the serializer
  only consumes `m.id`. Real performance discipline.
- **Top-level `_User` import with the leading underscore** signals "private to this module"
  — matches Django conventions for re-exported names. Resolves the prior in-function lazy
  import (which itself was a circular-import workaround that's no longer needed because
  `apps.users.models` doesn't import courses).
- **DB-fallback preserved verbatim** — the serializer remains usable in admin shells, custom
  management commands, or a future view that uses a different queryset. Backward compatible.
- **TDD discipline:** 5 correctness tests cover the four "what counts" rules
  (basic, dedup, inactive-excluded, role-excluded, multi-group) AND a separate N+1 query-count
  guard. Each rule is its own test — failures point right at the broken rule, not "something is
  wrong with the prefetch."
- **Test 4 (non-TEACHER role)** specifically uses `HOD` — a real role that *could* easily slip
  through if the filter was `role__in=[...]` instead of `role='TEACHER'`. Catches a subtle
  bug.
- **Test setUp uses `uuid` suffixes** for tenant subdomain to avoid collisions across test
  classes — consistent with existing patterns in the suite.
- **Comments in views.py and serializers.py explain WHY** the Prefetch shape exists and why
  the prefetch-aware branch precedes the fallback. Future readers don't have to guess.

## Suggested follow-up tickets (not blocking)

- **BE-cleanup-NN**: Extract a single `ACTIVE_TEACHER_FILTERS` constant (or helper) so the
  Prefetch and DB-fallback paths can't drift.
- **BE-perf-NN**: Capture the same query-count guard as a `@pytest.mark.queries` decorator
  in conftest so other endpoints can adopt the pattern. Out of scope here; useful platform-
  wide.

— lp-reviewer
