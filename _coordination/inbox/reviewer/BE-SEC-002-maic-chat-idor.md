# Review Request: BE-SEC-002 — IDOR in `student_maic_chat`

**From**: backend-security
**To**: reviewer
**Date**: 2026-04-19
**Severity**: Medium — cross-section information disclosure within a tenant
**Type**: Security fix (new finding from proactive MAIC audit)

---

## Summary

Found during a proactive security sweep of newer MAIC / billing / quiz code
after the Phase-1 P0 audit signed off. One real IDOR in `student_maic_chat`;
everything else in the sweep is either fine or a policy/product decision
(see `_coordination/shared-log.md` entry for full observations OBS-1..OBS-4).

## The bug

`backend/apps/courses/maic_views.py` `student_maic_chat` direct-LLM fallback
(lines 1073-1121, pre-fix) looked up `MAICClassroom` by
`pk=classroom_id, tenant=request.tenant` and seeded the chat stream with the
row's `title`, `config.agents`, and `content.scenes[].title` — **without the
section-level visibility check** that the companion endpoint
`student_maic_classroom_detail` (lines 1043-1050) already enforces.

A student in section A could POST:

```json
{"message": "...", "classroomId": "<classroom-assigned-to-section-B>"}
```

…and the SSE stream would return agent names, scene titles, and the
classroom title from a classroom they are not entitled to see.

Data exposure: within-tenant only. Scope: title, agent roster, scene outline
— enough to enumerate what other sections / teacher drafts are studying.
Not tenant-crossing, but still violates the section-assignment invariant.

## The fix

Single-file change in `backend/apps/courses/maic_views.py` at the
`student_maic_chat` direct-LLM fallback block. Inline visibility check
mirrors the proven pattern from `student_maic_classroom_detail` line by line:

```python
if classroom is not None:
    assigned = classroom.assigned_sections.all()
    student_section = getattr(request.user, "section_fk", None)
    can_view = True
    if assigned.exists():
        if not student_section or student_section not in assigned:
            can_view = False
    elif not classroom.is_public:
        can_view = False
    if can_view:
        classroom_title = ...
        agents = ...
        scene_titles = ...
```

Behaviour notes:
- Legitimate students (in an assigned section, or viewing a public classroom)
  get byte-identical output to before.
- Students without access get a chat response with no classroom context seeded
  — the chat endpoint still works for them, it just doesn't leak the title /
  agents / scene titles of a classroom they can't see.
- `DoesNotExist` branch still "silently works" (no 403/404) — preserves the
  prior author's UX preference of a generic response for bad ids.

## What to verify

1. Visibility check logic matches `student_maic_classroom_detail`
   (`maic_views.py:1043-1050`) line-for-line — no drift.
2. Sidecar path (non-502 result) is untouched: that path forwards the raw
   request to OpenMAIC and does not touch classroom data server-side. The
   IDOR only affects the direct-LLM fallback.
3. Teacher variant `teacher_maic_chat` (`maic_views.py:279-336`) is **not**
   changed — teachers are intentionally cross-section within a tenant, so
   the same check is not required there.

## Not in scope / observations

Four `OBS-*` items in the shared-log entry are observations, not fixes:

- **OBS-1**: MAIC student generation endpoints deliberately un-throttled
  (reverted in commit `f22ff02`). Product decision — flagged, not reverted.
- **OBS-2**: Student `validate_topic` guardrails deliberately removed
  (same commit). Product decision — flagged, not reverted.
- **OBS-3**: `image_service.py` tempfile leak on exception path. Not in my
  file ownership (courses/, not security/) — handoff to backend-engineer.
- **OBS-4**: Stripe webhook exception granularity could split 401 vs 500.
  Low-sev nit — handoff to backend-engineer.

## Suggested test (non-blocking)

Handoff to qa-tester: a view-level regression test under
`tests/courses/test_maic_student_chat.py::test_student_cannot_seed_chat_from_foreign_section_classroom`.
Two students in two sections, classroom assigned to section A only; student B
POSTs the classroomId and asserts the SSE response does not contain the
classroom's title, agent names, or scene titles. Assert is easiest against
`content-type: text/event-stream` response `.streaming_content` iteration.

## Not committed

Per file-ownership / agent policy, backend-security does not run
`git add/commit/push`. Change is in the working tree.

## Processed 2026-04-19

Already reviewed — **APPROVED** at
`_coordination/reviews/review-BE-SEC-002-maic-chat-idor.md` (and a copy
at `projects/learnpuddle-lms/reviews/review-BE-SEC-002-maic-chat-idor.md`).
Closing out of queue.
