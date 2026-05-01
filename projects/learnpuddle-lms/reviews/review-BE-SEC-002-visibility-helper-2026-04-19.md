---
tags: [review, task/BE-SEC-002, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-19
---

# Review: BE-SEC-002 follow-up — `_student_can_view_classroom` helper

## Verdict: APPROVE

## Summary

Clean, minimal refactor that closes both non-blocking follow-ups (m1 parity
gap + m2 duplication) from `review-BE-SEC-002-maic-chat-idor.md`. The
visibility logic is now owned by a single canonical helper and both student
endpoints (detail GET + chat POST fallback) delegate to it. TDD-style unit
tests cover every gate. No behaviour regression — existing integration tests
at `tests/courses/test_maic_student_chat.py` already use `status="READY"` +
`audioManifest.status="ready"` fixtures, so they continue to pass.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### m1 (nit, optional) — Test count off by one in request

Request says "13 unit tests"; actual count is **14** (`grep -c 'def test_'`).
Manifest gate has 5 tests (generating / pending / missing / ready / partial),
not 4. Cosmetic — the coverage is right, just a typo in the handoff note.

### m2 (nit, optional) — `student_section in assigned` iterates queryset

`_student_can_view_classroom` L1058-1059:

```python
assigned = classroom.assigned_sections.all()
student_section = getattr(user, "section_fk", None)
if assigned.exists():
    return bool(student_section) and student_section in assigned
```

`assigned.exists()` runs a COUNT query; `student_section in assigned` then
fully evaluates the queryset (fetches every assigned section row) to do a
Python-side membership check. For classrooms with many assigned sections
this is O(n) rows transferred instead of a one-row `EXISTS`. For the
typical case (a handful of sections) this is negligible, but the idiomatic
Django form is one query:

```python
if assigned.exists():
    if not student_section:
        return False
    return assigned.filter(pk=student_section.pk).exists()
```

Non-blocking; same correctness, slightly better shape. Flagging only
because this helper is now on the chat hot path.

### m3 (non-blocking) — Tests are import-only, DB integration untouched

The new `tests_maic_classroom_visibility.py` correctly uses `MagicMock` +
`SimpleNamespace` so it runs without Docker/Postgres, which is appropriate
for a pure-logic helper. Coverage for the **caller integration** (i.e. that
`student_maic_classroom_detail` and `student_maic_chat` actually both call
the helper and return 404 / empty-context respectively on False) lives in
the existing `tests/courses/test_maic_student_chat.py` regression suite,
which I have not re-run here (Docker unavailable in sandbox). Per the
request note, that suite's fixtures are all READY+ready, so nothing is
expected to flip — but please confirm green before merge:

```bash
docker compose exec web pytest \
  apps/courses/tests_maic_classroom_visibility.py \
  tests/courses/test_maic_student_chat.py -v
```

## Positive Observations

- **Parity gap closed**: the chat fallback now rejects GENERATING / FAILED
  / ARCHIVED classrooms and classrooms whose audio manifest is not ready
  or partial — previously the chat endpoint would seed context from any
  of those, even though the detail endpoint correctly 404'd. This closes
  m1 exactly as requested.
- **Single source of truth**: both callers now invoke
  `_student_can_view_classroom(request.user, classroom)` so the rules
  cannot drift. Verified via grep — no residual inline `can_view`
  variable or duplicated section-check block remains in `maic_views.py`.
- **Docstring documents the evaluation order explicitly** (status →
  manifest → section/public). Anyone touching the gate will see the
  contract without reading the callers.
- **Defensive `content or {}`** handles the `content=None` column case,
  and `getattr(user, "section_fk", None)` handles users without the
  attribute. Both edge-cases are exercised by the unit tests.
- **Tests written test-first** per the file docstring — the helper's
  behaviour contract is pinned before callers consume it, and the test
  names read like acceptance criteria.
- **Detail endpoint widened cleanly**: previously the ORM query included
  `status="READY"` as a filter, which would mask the helper's 404 branch
  with a "not found" anyway; now the fetch is tenant-scoped only and the
  helper owns all gate logic, which makes the gate fully auditable from
  one place.
- **Scope discipline**: touches exactly `maic_views.py` + one new test
  file. No rides-along, no unrelated refactors.

## Required before merge

None — both follow-ups from the prior review are implemented correctly
and the change is self-contained.

## Recommended (post-merge, optional)

1. Swap `student_section in assigned` for
   `assigned.filter(pk=student_section.pk).exists()` (m2 nit).
2. Fix test count in any tracking doc (14, not 13).

— lp-reviewer
