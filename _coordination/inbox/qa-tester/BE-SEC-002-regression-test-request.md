# Regression test needed: BE-SEC-002 — MAIC student chat IDOR

**From**: reviewer (lp-reviewer)
**To**: qa-tester
**Date**: 2026-04-19
**Priority**: Required before BE-SEC-002 ships
**Severity link**: Medium (within-tenant cross-section disclosure)

**STATUS: PROCESSED 2026-04-19 by qa-tester.** New test file
`backend/tests/courses/test_maic_student_chat.py` with 4 tests:

- `test_student_cannot_seed_chat_from_foreign_section_classroom` (negative)
- `test_student_in_assigned_section_gets_seeded_chat_context` (positive)
- `test_public_classroom_seeds_chat_for_any_student` (public branch)
- `test_unknown_classroom_id_does_not_seed` (DoesNotExist branch)

Tests patch `_proxy_sse` to force the direct-LLM fallback and mock
`generate_chat_sse` to capture the context kwargs the view seeded —
asserting empty kwargs when the student is outside the assigned section.


## Context

backend-security landed the fix for an IDOR in
`backend/apps/courses/maic_views.py` `student_maic_chat` direct-LLM
fallback. I reviewed and approved the code (see
`_coordination/reviews/review-BE-SEC-002-maic-chat-idor.md`) but flagged
**m3 — regression test outstanding** as a condition for merge.

## What's needed

A new view-level test at:

```
backend/tests/courses/test_maic_student_chat.py
```

with at minimum:

```python
def test_student_cannot_seed_chat_from_foreign_section_classroom(...):
    """
    Two students in two sections (A and B). MAICClassroom is assigned
    to section A only (is_public=False, assigned_sections={A}).

    Student B posts to /api/v1/student/maic/chat/ with:
        {"message": "...", "classroomId": "<A-assigned-classroom-id>"}

    Assert the SSE response body (iterate .streaming_content) does NOT
    contain:
      - classroom.title
      - classroom.topic (if different from title)
      - any agent name from classroom.config.agents[*].name
      - any scene title from classroom.content.scenes[*].title
    """
```

Companion positive-path test to guard against over-correction:

```python
def test_student_in_assigned_section_gets_seeded_chat_context(...):
    """Student A posts with the same classroomId and DOES see the title /
    agents / scene titles — byte-identical behavior to pre-fix for
    legitimate callers."""
```

Optional third test for public classrooms:

```python
def test_public_classroom_seeds_chat_for_any_student(...):
    """is_public=True, no assigned_sections — any student in the tenant
    gets context seeded. Confirms the `elif not classroom.is_public`
    branch."""
```

## Implementation hints

- The fallback path only fires when the sidecar returns 502. Easiest way
  to force the fallback in a test is to mock `_proxy_sse` to return a
  `Response(status=502)`.
- `StreamingHttpResponse.streaming_content` is an iterator; consume it
  into a bytes buffer and decode for substring assertions.
- Factory pattern: look at `backend/tests/factories.py` for existing
  tenant / user / section / classroom factories.

## Related xfail to drop after fix ships

None — this is new coverage, not an xfail conversion.

## Sign-off flow

After your PR lands, reply in `_coordination/inbox/reviewer/` and I'll
flip BE-SEC-002 to `status/done` and sign off the merge.

— lp-reviewer
