"""Regression tests for BE-SEC-002 — IDOR in ``student_maic_chat``
direct-LLM fallback.

The fallback path in ``apps.courses.maic_views.student_maic_chat`` (triggered
when the OpenMAIC sidecar returns 502) previously seeded chat context
(classroom title, agent names, scene titles) from any MAICClassroom id in
the same tenant, regardless of whether the student was in an assigned
section. This was a within-tenant cross-section information disclosure.

The fix mirrors the visibility rules already enforced by
``student_maic_classroom_detail``:

* If ``assigned_sections`` is non-empty → student's ``section_fk`` must
  be in that set.
* Else if ``is_public=False`` → deny.
* Else (public) → allow.

These tests pin that boundary:

1. Student in section A with a classroom assigned to section B only:
   SSE body MUST NOT contain the classroom's title / agent names / scene
   titles.
2. Student IN the assigned section: SSE body DOES contain the context
   (positive control — proves the fix didn't over-correct).
3. Public classroom: any student in the tenant gets the context.

Implementation notes:

* We force the direct-LLM fallback path by patching
  ``apps.courses.maic_views._proxy_sse`` to return a 502 response.
* The direct LLM is also patched so we do not need a real API key / HTTP
  call — we can inspect what context was *passed* to ``generate_chat_sse``.
* Test uses plain pytest + APIClient + factories from
  ``backend/tests/factories.py`` plus local fixtures for Grade/Section.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest
from django.http import HttpResponse, StreamingHttpResponse
from rest_framework.test import APIClient

from tests.factories import TenantFactory, UserFactory


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Local fixtures — Grade / Section / AI config / Classroom
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant():
    """Tenant with MAIC feature flag enabled."""
    t = TenantFactory.create()
    t.feature_maic = True
    t.save(update_fields=["feature_maic"])
    return t


@pytest.fixture
def ai_config(tenant):
    """TenantAIConfig with MAIC enabled — required by ``_get_ai_config``."""
    from apps.courses.maic_models import TenantAIConfig
    return TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        tts_provider="disabled",
        maic_enabled=True,
    )


@pytest.fixture
def grade(tenant):
    from apps.academics.models import Grade
    return Grade.objects.create(
        tenant=tenant,
        name="Grade 9",
        short_code="G9",
        order=9,
    )


@pytest.fixture
def section_a(tenant, grade):
    from apps.academics.models import Section
    return Section.objects.create(
        tenant=tenant, grade=grade, name="A", academic_year="2026-27",
    )


@pytest.fixture
def section_b(tenant, grade):
    from apps.academics.models import Section
    return Section.objects.create(
        tenant=tenant, grade=grade, name="B", academic_year="2026-27",
    )


@pytest.fixture
def teacher(tenant):
    return UserFactory.create_teacher(tenant)


@pytest.fixture
def student_a(tenant, section_a):
    return UserFactory.create(
        tenant, role="STUDENT", section_fk=section_a,
    )


@pytest.fixture
def student_b(tenant, section_b):
    return UserFactory.create(
        tenant, role="STUDENT", section_fk=section_b,
    )


@pytest.fixture
def student_no_section(tenant):
    """Student with no section assignment — used for the public-classroom test."""
    return UserFactory.create(tenant, role="STUDENT")


# Sentinel strings — any appearance in the streamed body is a leak.
SECRET_TITLE = "PRIVATE-SECTION-B-TITLE-DO-NOT-LEAK"
SECRET_TOPIC = "PRIVATE-SECTION-B-TOPIC-DO-NOT-LEAK"
SECRET_AGENT = "PRIVATE-AGENT-B-DO-NOT-LEAK"
SECRET_SCENE = "PRIVATE-SCENE-B-DO-NOT-LEAK"


def _make_classroom(tenant, teacher, *, title, topic, agent, scene, **kwargs):
    from apps.courses.maic_models import MAICClassroom
    defaults = dict(
        tenant=tenant,
        creator=teacher,
        status="READY",
        title=title,
        topic=topic,
        is_public=False,
        config={"agents": [{"name": agent, "role": "professor"}]},
        content={
            "audioManifest": {"status": "ready"},
            "scenes": [{"title": scene}],
        },
    )
    defaults.update(kwargs)
    return MAICClassroom.objects.create(**defaults)


@pytest.fixture
def section_b_classroom(tenant, teacher, section_b):
    """Classroom visible ONLY to section B."""
    room = _make_classroom(
        tenant, teacher,
        title=SECRET_TITLE, topic=SECRET_TOPIC,
        agent=SECRET_AGENT, scene=SECRET_SCENE,
        is_public=False,
    )
    room.assigned_sections.set([section_b])
    return room


@pytest.fixture
def public_classroom(tenant, teacher):
    """Public classroom with no section restrictions."""
    return _make_classroom(
        tenant, teacher,
        title="PUBLIC-TITLE", topic="PUBLIC-TOPIC",
        agent="PUBLIC-AGENT", scene="PUBLIC-SCENE",
        is_public=True,
    )


def _authed_client(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


# ---------------------------------------------------------------------------
# Fallback-forcing patch helpers
# ---------------------------------------------------------------------------

def _force_fallback_and_capture():
    """Return (proxy_patch, chat_patch, captured) where:

    * ``proxy_patch`` forces ``_proxy_sse`` to return 502 so the view
      enters the direct-LLM branch.
    * ``chat_patch`` replaces ``generate_chat_sse`` with a stub that
      records the kwargs it was called with and yields one dummy chunk.
      We assert on the *captured* kwargs (what the view seeded as
      context), which is the exact surface the IDOR affected.
    * ``captured`` is a dict populated on first call.
    """
    captured: dict = {}

    def _fake_proxy_sse(request, path, config):  # noqa: ARG001
        return HttpResponse(
            json.dumps({"error": "forced for test"}),
            status=502,
            content_type="application/json",
        )

    def _fake_generate_chat_sse(**kwargs):
        captured.update(kwargs)
        yield b"data: {}\n\n"

    return (
        mock.patch("apps.courses.maic_views._proxy_sse", side_effect=_fake_proxy_sse),
        mock.patch(
            "apps.courses.maic_views.generate_chat_sse",
            side_effect=_fake_generate_chat_sse,
        ),
        captured,
    )


def _consume(response) -> bytes:
    """Flatten a StreamingHttpResponse body to bytes for substring checks."""
    if isinstance(response, StreamingHttpResponse):
        return b"".join(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
                        for chunk in response.streaming_content)
    return response.content


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_student_cannot_seed_chat_from_foreign_section_classroom(
    tenant, ai_config, section_a, section_b, student_a, section_b_classroom,
):
    """Regression for BE-SEC-002.

    Student A (section A) POSTs a classroomId belonging to a section-B-only
    classroom. The SSE body MUST NOT leak the classroom's title, topic,
    agent name, or scene title — and the direct-LLM branch must have been
    called with *empty* context, mirroring the visibility rules of
    ``student_maic_classroom_detail``.
    """
    client = _authed_client(student_a, tenant)
    proxy_patch, chat_patch, captured = _force_fallback_and_capture()

    with proxy_patch, chat_patch:
        resp = client.post(
            "/api/v1/student/maic/chat/",
            data={"message": "hello", "classroomId": str(section_b_classroom.id)},
            format="json",
        )

    # Response itself is a stream — the endpoint is not supposed to 403/404
    # on bad ids (silent-no-context UX). Consume the body for assertions.
    body = _consume(resp).decode("utf-8", errors="replace")

    # Nothing from the private classroom may appear in the streamed body.
    assert SECRET_TITLE not in body, "classroom title leaked to wrong section"
    assert SECRET_TOPIC not in body, "classroom topic leaked to wrong section"
    assert SECRET_AGENT not in body, "classroom agent name leaked to wrong section"
    assert SECRET_SCENE not in body, "classroom scene title leaked to wrong section"

    # Defence-in-depth: inspect the kwargs the view passed into
    # generate_chat_sse. Pre-fix these would be populated; post-fix they
    # must be empty / no-op values.
    assert captured.get("classroom_title", "") == ""
    assert captured.get("agents") in (None, [], ())
    assert captured.get("scene_titles") in (None, [], ())


def test_student_in_assigned_section_gets_seeded_chat_context(
    tenant, ai_config, section_b, student_b, section_b_classroom,
):
    """Positive control — student B is IN the assigned section, so the
    classroom context MUST still be seeded. Guards against the fix
    over-correcting and denying legitimate callers.
    """
    client = _authed_client(student_b, tenant)
    proxy_patch, chat_patch, captured = _force_fallback_and_capture()

    with proxy_patch, chat_patch:
        resp = client.post(
            "/api/v1/student/maic/chat/",
            data={"message": "hello", "classroomId": str(section_b_classroom.id)},
            format="json",
        )

    _consume(resp)  # drain

    # Title is set either to title or topic (topic fallback when title empty).
    assert captured.get("classroom_title") == SECRET_TITLE
    agents = captured.get("agents") or []
    assert any(a.get("name") == SECRET_AGENT for a in agents), \
        f"Expected agent {SECRET_AGENT!r} in seeded context, got {agents!r}"
    assert SECRET_SCENE in (captured.get("scene_titles") or [])


def test_public_classroom_seeds_chat_for_any_student(
    tenant, ai_config, student_no_section, public_classroom,
):
    """Public classrooms (``is_public=True``, no ``assigned_sections``)
    should seed context for any student in the tenant — including
    students without a section assignment. Exercises the
    ``elif not classroom.is_public`` branch's false path.
    """
    client = _authed_client(student_no_section, tenant)
    proxy_patch, chat_patch, captured = _force_fallback_and_capture()

    with proxy_patch, chat_patch:
        resp = client.post(
            "/api/v1/student/maic/chat/",
            data={"message": "hello", "classroomId": str(public_classroom.id)},
            format="json",
        )

    _consume(resp)

    assert captured.get("classroom_title") == "PUBLIC-TITLE"
    assert any(
        a.get("name") == "PUBLIC-AGENT"
        for a in (captured.get("agents") or [])
    )
    assert "PUBLIC-SCENE" in (captured.get("scene_titles") or [])


def test_unknown_classroom_id_does_not_seed(
    tenant, ai_config, student_a,
):
    """A classroomId that doesn't resolve (not in tenant) must also seed
    an empty context. Pre-existing behaviour preserved; the IDOR fix added
    a second guard on top.
    """
    import uuid

    client = _authed_client(student_a, tenant)
    proxy_patch, chat_patch, captured = _force_fallback_and_capture()

    with proxy_patch, chat_patch:
        resp = client.post(
            "/api/v1/student/maic/chat/",
            data={"message": "hello", "classroomId": str(uuid.uuid4())},
            format="json",
        )

    _consume(resp)
    assert captured.get("classroom_title", "") == ""
    assert captured.get("agents") in (None, [], ())
    assert captured.get("scene_titles") in (None, [], ())
