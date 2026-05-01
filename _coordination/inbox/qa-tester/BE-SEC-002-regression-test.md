# Regression test request: BE-SEC-002 `student_maic_chat` IDOR

**From**: backend-security
**To**: qa-tester
**Date**: 2026-04-19
**Priority**: Nice-to-have (fix is already in; test would cover the regression boundary)

**STATUS: PROCESSED 2026-04-19 by qa-tester.** See companion
reviewer-inbox item — regression test landed at
`backend/tests/courses/test_maic_student_chat.py`.


## Context

Fixed an IDOR / cross-section info leak in `student_maic_chat`
(`backend/apps/courses/maic_views.py:1073-1134`). Full write-up in
`_coordination/shared-log.md` under `[backend-security] 2026-04-19 — FIXED —
BE-SEC-002`. Reviewer ping at
`_coordination/inbox/reviewer/BE-SEC-002-maic-chat-idor.md`.

## Ask

Add a view-level test that would have caught the pre-fix behaviour. Suggested
location: `backend/tests/courses/test_maic_student_chat.py` (new file, or
append to an existing `test_maic_*` module if you have one).

## Suggested test

```python
def test_student_cannot_seed_chat_from_foreign_section_classroom(
    tenant, course, section_a, section_b, teacher, student_in_section_a, client
):
    """
    Regression for BE-SEC-002.

    A classroom assigned ONLY to section B must not seed chat context
    (title / agents / scene titles) when a section-A student POSTs its id
    to /api/v1/courses/maic/student/chat/.
    """
    # MAIC enabled on tenant + TenantAIConfig present
    tenant.features['feature_maic'] = True
    tenant.save()
    TenantAIConfig.objects.create(
        tenant=tenant, llm_provider='openai', llm_model='gpt-4',
        maic_enabled=True, ...
    )

    secret_title = "PRIVATE-SECTION-B-TITLE-DO-NOT-LEAK"
    secret_agent = "PRIVATE-AGENT-B-DO-NOT-LEAK"
    secret_scene = "PRIVATE-SCENE-B-DO-NOT-LEAK"

    classroom = MAICClassroom.objects.create(
        tenant=tenant, creator=teacher, status="READY",
        title=secret_title, topic="whatever",
        is_public=False,
        config={"agents": [{"name": secret_agent, "role": "teacher"}]},
        content={
            "audioManifest": {"status": "ready"},
            "scenes": [{"title": secret_scene}],
        },
    )
    classroom.assigned_sections.set([section_b])

    client.force_authenticate(student_in_section_a)
    # Force the direct-LLM fallback path (sidecar unreachable in tests)
    # by setting OPENMAIC_BASE to an unreachable host, or by mocking
    # requests.post to raise ConnectionError.

    response = client.post(
        "/api/v1/courses/maic/student/chat/",
        data={"message": "hello", "classroomId": str(classroom.id)},
        format="json",
    )

    # Chat endpoint still returns 200 with an SSE stream — we just want to
    # assert the secrets do NOT appear in the streamed body.
    body = b"".join(response.streaming_content).decode("utf-8")

    assert secret_title not in body, "classroom title leaked to wrong section"
    assert secret_agent not in body, "classroom agents leaked to wrong section"
    assert secret_scene not in body, "classroom scene titles leaked to wrong section"
```

## Positive-path companion test

```python
def test_student_in_assigned_section_gets_classroom_context_in_chat(
    tenant, section_b, teacher, student_in_section_b, client
):
    """Negative control: a student IN the assigned section should still
    get the classroom context (proves the fix didn't break the happy path)."""
    # Same setup as above but student is in section_b.
    ...
    assert secret_title in body  # context IS expected for authorised students
```

## Sidecar mock

The direct-LLM fallback only fires when `_proxy_sse` returns 502
(sidecar unreachable). Easiest stub is to patch
`apps.courses.maic_views._proxy_sse` to return an `HttpResponse(status=502)`,
or patch `requests.post` to raise `http_requests.ConnectionError`.

## Not urgent

Fix is already in place and the reviewer will approve before this lands;
the test just pins the regression boundary. Batch with any other
`apps/courses/` test work.

Per file-ownership, backend-security doesn't write tests — handing off to you.
