"""
CG-P1-7 backend dedup closeout: tests covering removal of the
``_fill_image_urls`` duplicate / collision in the MAIC generation pipeline.

Background (CG-P0-3 + CG-P1-7):

  Before this dedup, scene-content generation went through TWO image-fill
  paths on the same request:

    * Service-layer ``_fill_image_urls`` inside ``generate_scene_content``
      (synchronous, blocking, called ``fetch_scene_image`` for every empty
      ``src``).
    * View-layer ``_defer_image_fill`` enqueueing ``fill_classroom_images``
      (asynchronous, runs again 60s later in a Celery worker).

  Net effect: every classroom paid the latency cost of the inline fetch
  AND the Celery task re-fetched the same images on top.  Idempotency in
  the Celery task hid the bug from production but the duplicated work +
  the timing window between sync write and async read created possible
  URL drift.

This test file pins the new contract:

  * The view endpoints (teacher + student) MUST NOT call
    ``fetch_scene_image`` synchronously while serving a request.
  * The service-layer ``_fill_image_urls`` is now a *scrub-only* helper:
    it strips unsafe ``src`` values and stamps ``meta.imageProviderDisabled``
    when the tenant turned image generation off, but never reaches out to
    the image provider on its own.
  * ``fill_classroom_images`` (Celery task) is the sole caller of
    ``fetch_scene_image`` — image fetching is deferred to it exclusively.
  * The duplicate ``_fill_image_urls`` in ``apps/courses/maic_views.py``
    is gone (only ``_defer_image_fill`` remains in the view layer).
  * Tenant scoping: a body-supplied ``classroomId`` belonging to another
    tenant must NOT cause the deferred fill to flip ``images_pending`` or
    enqueue work for that tenant's classroom.
  * Idempotency: a second call to ``fill_classroom_images`` for a
    classroom with ``images_pending=False`` is a no-op (regression guard
    inherited from CG-P0-3).
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest
from rest_framework.test import APIClient

from apps.courses.maic_models import MAICClassroom, TenantAIConfig

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def maic_enabled_tenant(tenant):
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    return tenant


@pytest.fixture
def maic_enabled_tenant_b(tenant_b):
    tenant_b.feature_maic = True
    tenant_b.save(update_fields=["feature_maic"])
    return tenant_b


@pytest.fixture
def ai_config(maic_enabled_tenant):
    return TenantAIConfig.objects.create(
        tenant=maic_enabled_tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        tts_provider="disabled",
        image_provider="pollinations",
        maic_enabled=True,
    )


@pytest.fixture
def ai_config_disabled_images(maic_enabled_tenant):
    return TenantAIConfig.objects.create(
        tenant=maic_enabled_tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        tts_provider="disabled",
        image_provider="disabled",
        maic_enabled=True,
    )


@pytest.fixture
def teacher_client(teacher_user, maic_enabled_tenant):
    client = APIClient()
    client.force_authenticate(user=teacher_user)
    client.defaults["HTTP_HOST"] = f"{maic_enabled_tenant.subdomain}.lms.com"
    return client


@pytest.fixture
def student_user(maic_enabled_tenant):
    from apps.users.models import User
    return User.objects.create_user(
        email="student@testschool.com",
        password="StudentPass!123",
        first_name="Stu",
        last_name="Dent",
        tenant=maic_enabled_tenant,
        role="STUDENT",
        is_active=True,
    )


@pytest.fixture
def student_client(student_user, maic_enabled_tenant):
    client = APIClient()
    client.force_authenticate(user=student_user)
    client.defaults["HTTP_HOST"] = f"{maic_enabled_tenant.subdomain}.lms.com"
    return client


def _make_classroom(tenant, creator, *, images_pending=False, n_scenes=1):
    scenes = []
    for i in range(n_scenes):
        scenes.append({
            "id": f"scene-{i}",
            "title": f"Scene {i}",
            "slides": [
                {
                    "id": f"slide-{i}-0",
                    "elements": [
                        {"type": "image", "id": f"img-{i}-0", "src": "",
                         "content": f"photosynthesis scene {i}"},
                    ],
                }
            ],
        })
    return MAICClassroom.objects.create(
        tenant=tenant,
        creator=creator,
        title="Dedup test classroom",
        topic="Dedup",
        status="READY",
        images_pending=images_pending,
        content_scenes=scenes,
    )


# ---------------------------------------------------------------------------
# 1. Teacher scene-content endpoint must not inline-fetch images.
# ---------------------------------------------------------------------------


def test_teacher_scene_content_does_not_inline_fetch_images(
    teacher_client, maic_enabled_tenant, teacher_user, ai_config
):
    """Calling the teacher scene-content endpoint while the LLM produces a
    valid multi-slide payload must not call ``fetch_scene_image`` even
    once.  All image fetches belong to the Celery task now."""
    classroom = _make_classroom(maic_enabled_tenant, teacher_user)
    classroom_id = str(classroom.id)

    # Stub the LLM call so the service synthesises a real scene without
    # reaching out to OpenRouter.
    fake_parsed = {
        "slides": [
            {
                "id": "slide-1",
                "title": "Hello",
                "elements": [
                    {"type": "image", "id": "img-1", "src": "",
                     "content": "photosynthesis"},
                    {"type": "text", "id": "txt-1", "src": "",
                     "content": "Plants convert light to sugar."},
                ],
                "background": "#fff",
                "duration": 30,
                "speakerScript": "Welcome to photosynthesis.",
            }
        ]
    }

    with patch(
        "apps.courses.maic_generation_service._call_llm_with_json_retry",
        return_value=(fake_parsed, "raw"),
    ), patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://example.com/leak.jpg",
    ) as mock_fetch, patch(
        "apps.courses.maic_views._proxy_json",
        return_value=MagicMock(status_code=502),
    ), patch(
        "apps.courses.maic_tasks.fill_classroom_images.apply_async",
    ):
        resp = teacher_client.post(
            "/api/v1/teacher/maic/generate/scene-content/",
            {
                "scene": {"id": "scene-1", "title": "Intro", "type": "lecture",
                          "slideCount": 3, "agentIds": []},
                "agents": [{"id": "a1", "name": "Prof", "role": "professor"}],
                "language": "en",
                "classroomId": classroom_id,
            },
            format="json",
        )

    assert resp.status_code == 200, resp.content
    assert mock_fetch.call_count == 0, (
        f"fetch_scene_image must not be called inline during the wizard "
        f"request (got {mock_fetch.call_count} calls)"
    )

    data = resp.json()
    # Image src is left empty for the Celery task to fill later.
    img_el = next(
        el for slide in data["slides"]
        for el in slide["elements"] if el["type"] == "image"
    )
    assert img_el.get("src", "") == "", (
        "image src must remain empty so the deferred fill can populate it"
    )


# ---------------------------------------------------------------------------
# 2. Student scene-content endpoint must not inline-fetch images.
# ---------------------------------------------------------------------------


def test_student_scene_content_does_not_inline_fetch_images(
    student_client, maic_enabled_tenant, teacher_user, ai_config
):
    """Same contract as the teacher endpoint, asserted independently because
    student views go through ``student_or_admin`` and their own classroom
    queryset."""
    classroom = _make_classroom(maic_enabled_tenant, teacher_user)
    classroom_id = str(classroom.id)

    fake_parsed = {
        "slides": [
            {
                "id": "slide-1",
                "title": "Hello",
                "elements": [
                    {"type": "image", "id": "img-s-1", "src": "",
                     "content": "ecosystem"},
                ],
                "background": "#fff",
                "duration": 30,
                "speakerScript": "Welcome.",
            }
        ]
    }

    with patch(
        "apps.courses.maic_generation_service._call_llm_with_json_retry",
        return_value=(fake_parsed, "raw"),
    ), patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://example.com/leak.jpg",
    ) as mock_fetch, patch(
        "apps.courses.maic_views._proxy_json",
        return_value=MagicMock(status_code=502),
    ), patch(
        "apps.courses.maic_tasks.fill_classroom_images.apply_async",
    ):
        resp = student_client.post(
            "/api/v1/student/maic/generate/scene-content/",
            {
                "scene": {"id": "scene-1", "title": "Intro", "type": "lecture",
                          "slideCount": 3, "agentIds": []},
                "agents": [{"id": "a1", "name": "Prof", "role": "professor"}],
                "language": "en",
                "classroomId": classroom_id,
            },
            format="json",
        )

    assert resp.status_code == 200, resp.content
    assert mock_fetch.call_count == 0, (
        "fetch_scene_image must not run inline on the student endpoint"
    )


# ---------------------------------------------------------------------------
# 3. Service-layer ``_fill_image_urls`` is scrub-only — never calls the
#    image provider directly.
# ---------------------------------------------------------------------------


def test_service_fill_image_urls_does_not_call_fetch_scene_image():
    """``_fill_image_urls`` in maic_generation_service is now scrub-only.

    Even when called with empty ``src`` and a non-disabled provider, it
    must NOT reach into ``fetch_scene_image``.  The Celery task owns
    that contract exclusively.
    """
    from apps.courses import maic_generation_service as svc

    parsed = {
        "slides": [
            {
                "id": "slide-1",
                "elements": [
                    {"type": "image", "id": "img-1", "src": "",
                     "content": "ecosystem"},
                    # SEC-P0-4: an unsafe src must still be scrubbed.
                    {"type": "image", "id": "img-2",
                     "src": "javascript:alert(1)",
                     "content": "exploit"},
                ],
            }
        ]
    }

    with patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://example.com/should-not-be-used.jpg",
    ) as mock_fetch:
        svc._fill_image_urls(
            parsed,
            scene_id="scene-1",
            image_provider="pollinations",
        )

    assert mock_fetch.call_count == 0, (
        "service-layer _fill_image_urls must be scrub-only after CG-P1-7"
    )
    # Unsafe src still scrubbed (defense-in-depth).
    el2 = parsed["slides"][0]["elements"][1]
    assert el2["src"] == "", "unsafe src must be stripped"
    # Empty src stays empty for the deferred fill.
    el1 = parsed["slides"][0]["elements"][0]
    assert el1.get("src", "") == ""


def test_service_fill_image_urls_disabled_provider_stamps_meta():
    """When provider is ``disabled`` the service-layer scrubber must
    still stamp ``meta.imageProviderDisabled = True`` so the renderer
    shows an honest "AI images off" placeholder."""
    from apps.courses import maic_generation_service as svc

    parsed = {
        "slides": [
            {
                "id": "slide-1",
                "elements": [
                    {"type": "image", "id": "img-1", "src": "",
                     "content": "anything"},
                ],
            }
        ]
    }

    with patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://example.com/disabled.jpg",
    ) as mock_fetch:
        svc._fill_image_urls(
            parsed,
            scene_id="scene-1",
            image_provider="disabled",
        )

    assert mock_fetch.call_count == 0
    el = parsed["slides"][0]["elements"][0]
    assert el.get("meta", {}).get("imageProviderDisabled") is True


def test_service_fill_image_urls_strips_placeholder_hosts():
    """LLM responses must not bypass the tenant image pipeline with generic
    placeholder CDN URLs or random external fallbacks."""
    from apps.courses import maic_generation_service as svc

    parsed = {
        "slides": [
            {
                "id": "slide-1",
                "elements": [
                    {"type": "image", "id": "img-placehold", "src": "https://placehold.co/800x450"},
                    {"type": "image", "id": "img-unsplash", "src": "https://source.unsplash.com/800x450/?math"},
                    {"type": "image", "id": "img-media", "src": "/media/tenant/1/videos/asset.jpg"},
                ],
            }
        ]
    }

    svc._fill_image_urls(parsed, scene_id="scene-1", image_provider="pollinations")

    elements = parsed["slides"][0]["elements"]
    assert elements[0]["src"] == ""
    assert elements[1]["src"] == ""
    assert elements[2]["src"] == "/media/tenant/1/videos/asset.jpg"


# ---------------------------------------------------------------------------
# 4. View-layer duplicate _fill_image_urls is gone.
# ---------------------------------------------------------------------------


def test_views_fill_image_urls_is_removed():
    """The view-layer duplicate ``_fill_image_urls`` from
    ``apps/courses/maic_views.py`` was deleted as part of CG-P1-7.  The
    surviving boundary in views is ``_defer_image_fill`` only — verifying
    that here pins the refactor so a future revert can't silently re-add
    the dupe.
    """
    from apps.courses import maic_views

    assert not hasattr(maic_views, "_fill_image_urls"), (
        "_fill_image_urls in maic_views.py was deduped — only "
        "_defer_image_fill should remain at the view boundary."
    )
    # The deferred-fill helper is still there — that's the canonical entry.
    assert hasattr(maic_views, "_defer_image_fill")


# ---------------------------------------------------------------------------
# 5. Tenant scoping survives the dedup.
# ---------------------------------------------------------------------------


def test_defer_image_fill_does_not_leak_across_tenants(
    teacher_client, maic_enabled_tenant, maic_enabled_tenant_b,
    teacher_user, ai_config
):
    """``_defer_image_fill`` must not flip ``images_pending`` or enqueue a
    Celery task when the body-supplied ``classroomId`` belongs to a
    different tenant (SEC-P1-CROSS-TENANT-IMAGE-FILL).
    """
    # Build the victim classroom in tenant B.
    from apps.users.models import User
    teacher_b = User.objects.create_user(
        email="teacher-b@otherschool.com",
        password="TeacherPass!123",
        first_name="T",
        last_name="B",
        tenant=maic_enabled_tenant_b,
        role="TEACHER",
        is_active=True,
    )
    victim = _make_classroom(maic_enabled_tenant_b, teacher_b)
    assert victim.images_pending is False

    fake_parsed = {
        "slides": [
            {
                "id": "slide-1",
                "title": "X",
                "elements": [
                    {"type": "image", "id": "img-1", "src": "",
                     "content": "leaf"},
                ],
                "background": "#fff",
                "duration": 30,
                "speakerScript": "Hi.",
            }
        ]
    }

    with patch(
        "apps.courses.maic_generation_service._call_llm_with_json_retry",
        return_value=(fake_parsed, "raw"),
    ), patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://example.com/leak.jpg",
    ) as mock_fetch, patch(
        "apps.courses.maic_views._proxy_json",
        return_value=MagicMock(status_code=502),
    ), patch(
        "apps.courses.maic_tasks.fill_classroom_images.apply_async",
    ) as mock_enqueue:
        resp = teacher_client.post(
            "/api/v1/teacher/maic/generate/scene-content/",
            {
                "scene": {"id": "scene-1", "title": "Intro", "type": "lecture",
                          "slideCount": 3, "agentIds": []},
                "agents": [{"id": "a1", "name": "Prof", "role": "professor"}],
                "language": "en",
                # Hostile body: tenant B's classroom UUID.
                "classroomId": str(victim.id),
            },
            format="json",
        )

    assert resp.status_code == 200, resp.content
    # No inline fetch.
    assert mock_fetch.call_count == 0
    # No cross-tenant enqueue.
    assert mock_enqueue.call_count == 0, (
        "fill_classroom_images.apply_async must not run for a classroom "
        "in another tenant"
    )
    # Victim row untouched.
    victim.refresh_from_db()
    assert victim.images_pending is False


# ---------------------------------------------------------------------------
# 6. Idempotency: second fill_classroom_images call is a no-op when
#    images_pending=False (regression guard from CG-P0-3).
# ---------------------------------------------------------------------------


def test_fill_classroom_images_second_call_is_noop_when_not_pending(
    maic_enabled_tenant, teacher_user
):
    """A second invocation of ``fill_classroom_images`` for a classroom
    that has already been filled (``images_pending=False``) must NOT
    re-fetch images.  Pinned here so a future refactor of the dedup
    can't silently regress the early-exit guard.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _make_classroom(
        maic_enabled_tenant, teacher_user, images_pending=False,
    )

    fetch_calls = {"n": 0}

    def spy_fetch(keyword, *args, **kwargs):
        fetch_calls["n"] += 1
        return f"https://example.com/{keyword}.jpg"

    with patch(
        "apps.courses.image_service.fetch_scene_image",
        side_effect=spy_fetch,
    ):
        # Already filled → must early-exit without fetching.
        fill_classroom_images(str(classroom.id))

    assert fetch_calls["n"] == 0, (
        f"fill_classroom_images must early-exit when images_pending=False "
        f"(got {fetch_calls['n']} fetches)"
    )


# ---------------------------------------------------------------------------
# 7. Regression: legacy test_metrics monkeypatch boundary still works.
# ---------------------------------------------------------------------------


def test_legacy_fill_image_urls_monkeypatch_still_callable():
    """``backend/tests/test_metrics.py`` monkeypatches
    ``svc._fill_image_urls`` to a no-op stub to keep the metrics test
    hermetic.  After the dedup that monkeypatch must remain meaningful:
    the function still exists in the service module and replacing it
    must not raise.  This is a thin regression guard for legacy mocks.
    """
    from apps.courses import maic_generation_service as svc

    assert hasattr(svc, "_fill_image_urls")
    # The legacy stub signature was ``lambda *a, **kw: None``.  Confirm
    # the real function tolerates the same call shape (positional scene_id
    # + kwargs) so test stubs that drop the return value remain valid.
    parsed = {"slides": []}
    out = svc._fill_image_urls(parsed, "scene-x", image_provider="disabled")
    # The real function returns the parsed dict; stubs returning None are
    # also fine because the views path doesn't read the return value.
    assert out is parsed or out is None
