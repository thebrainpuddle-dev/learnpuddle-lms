"""CG-P1-12 — fill_classroom_images must walk content_meta.slides too.

Production wizard saves slides as a FLAT array under
``classroom.content_meta["slides"]`` (with ``sceneSlideBounds`` mapping
slides to scenes). Prior to this fix the Celery task walked ONLY
``content_scenes[i].slides[]`` and ``content_scenes[i].content.elements``
— neither of which exists in production-shaped data — so the task
"succeeded" with 0 image fills then flipped ``images_pending=False``.

The bug was masked by the inline ``_fill_image_urls`` call in
``maic_generation_service.py`` that runs synchronously during scene-
content generation. When a 2026-04-28 working-tree dedup removed that
inline path, every new classroom shipped with empty slide images.

This test guards the contract:
- Build a classroom in production shape (slides in content_meta, not
  embedded in content_scenes[i]).
- Run fill_classroom_images.
- Assert content_meta.slides[*].elements[image].src is filled.
- Assert images_pending=False.
"""
from unittest.mock import patch

import pytest

from apps.courses.maic_models import MAICClassroom


def _production_shape_classroom(tenant, creator, *, n_slides=3):
    """Classroom with slides flat under content_meta — mirrors what the
    wizard's persistPartial PATCH writes."""
    scenes = [
        {
            "id": f"scene-{i}",
            "type": "lecture",
            "title": f"Scene {i}",
            "actions": [{"type": "speech", "agentId": "a1", "text": "hi"}],
            "content": {"type": "slide", "elements": [], "speakerScript": "hi"},
        }
        for i in range(2)
    ]
    flat_slides = []
    for s in range(n_slides):
        flat_slides.append({
            "id": f"slide-flat-{s}",
            "elements": [
                {
                    "type": "image",
                    "id": f"img-{s}",
                    "src": "",
                    "content": f"photosynthesis stage {s}",
                },
                {"type": "text", "id": f"txt-{s}", "src": "", "content": "x"},
            ],
        })
    scene_slide_bounds = [
        {"sceneIdx": 0, "startSlide": 0, "endSlide": 0},
        {"sceneIdx": 1, "startSlide": 1, "endSlide": n_slides - 1},
    ]
    return MAICClassroom.objects.create(
        tenant=tenant,
        creator=creator,
        title="Production-shape classroom",
        topic="Test",
        status="READY",
        images_pending=True,
        content_scenes=scenes,
        content_meta={
            "slides": flat_slides,
            "sceneSlideBounds": scene_slide_bounds,
        },
    )


@pytest.fixture
def maic_enabled_tenant_prod(tenant):
    """Reuse the project's tenant fixture; flip the boolean column."""
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    return tenant


@pytest.mark.django_db
def test_fill_classroom_images_walks_content_meta_slides(
    maic_enabled_tenant_prod, teacher_user,
):
    """REGRESSION: production-shape classroom (slides in content_meta) must
    have all image src filled by fill_classroom_images."""
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _production_shape_classroom(
        maic_enabled_tenant_prod, teacher_user, n_slides=4,
    )
    assert classroom.images_pending is True
    # Sanity: slides ARE in content_meta, NOT in content_scenes
    assert (classroom.content_meta or {}).get("slides")
    for scene in classroom.content_scenes or []:
        assert "slides" not in scene or not scene["slides"], (
            "Test fixture leaked: scene shouldn't carry embedded slides "
            "in production shape"
        )

    with patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-test?w=800",
    ):
        fill_classroom_images(str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.images_pending is False

    # Every image element under content_meta.slides must have non-empty src.
    meta_slides = (classroom.content_meta or {}).get("slides") or []
    img_elements = [
        el for s in meta_slides for el in s.get("elements", [])
        if el.get("type") == "image"
    ]
    assert len(img_elements) == 4, (
        f"expected 4 image elements, got {len(img_elements)}"
    )
    for el in img_elements:
        assert el.get("src"), (
            f"image element {el.get('id')} still has empty src after task ran "
            f"— the task is not walking content_meta.slides"
        )
        assert el["src"].startswith("https://"), (
            f"unexpected src shape: {el['src']!r}"
        )


@pytest.mark.django_db
def test_fill_classroom_images_marks_existing_meta_images_done(
    maic_enabled_tenant_prod, teacher_user,
):
    """Already-materialized media URLs must not stay pending in the FE task map."""
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _production_shape_classroom(
        maic_enabled_tenant_prod, teacher_user, n_slides=2,
    )
    meta = dict(classroom.content_meta or {})
    slides = list(meta["slides"])
    slides[0]["elements"][0]["src"] = "/media/tenant/test/leaf-cycle.jpg"
    slides[1]["elements"][0]["src"] = "/media/tenant/test/water-cycle.jpg"
    classroom.content_meta = {**meta, "slides": slides}
    classroom.save(update_fields=["content_meta", "updated_at"])

    with patch("apps.courses.image_service.fetch_scene_image") as fetch_scene_image:
        fill_classroom_images(str(classroom.id))

    fetch_scene_image.assert_not_called()

    classroom.refresh_from_db()
    assert classroom.images_pending is False
    tasks = classroom.content_image_tasks or {}
    assert tasks["0:0:0:img-0"]["status"] == "done"
    assert tasks["0:0:0:img-0"]["src"] == "/media/tenant/test/leaf-cycle.jpg"
    assert tasks["1:1:0:img-1"]["status"] == "done"
    assert tasks["1:1:0:img-1"]["src"] == "/media/tenant/test/water-cycle.jpg"
