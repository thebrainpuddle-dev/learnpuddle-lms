"""F1 (P0) — fill_classroom_images full data-walk regression test.

Source: 2026-04-28 OpenMAIC deep-dive followups (F1).

The audit identified that ``fill_classroom_images`` was walking only
``content_scenes[i]["slides"]`` (legacy embedded shape used by old tests)
while production-shape rows have:

  * ``content_scenes[i]`` — scene dict with keys ``id, type, title,
    actions, content, multiAgent`` (NO top-level ``slides`` key).
  * ``content_meta["slides"]`` — flat list of slides with ``elements``.
  * ``content_scenes[i]["content"]["slides"][j]["elements"]`` — possible
    nested per-scene shape (audit spec — defensive walk required).

This test guards the contract that the task fills image ``src`` for image
elements at ALL THREE locations *in the same classroom* and flips
``images_pending`` to False after a successful run.

CG-P1-12 (the prior fix) covered the ``content_meta["slides"]`` walker.
The remaining gap is ``content_scenes[i]["content"]["slides"]`` — see
audit doc finding F1.
"""
from unittest.mock import patch

import pytest

from apps.courses.maic_models import MAICClassroom


pytestmark = pytest.mark.django_db


def _hybrid_shape_classroom(tenant, creator):
    """Build a classroom that exercises ALL THREE image-element locations:

    1. ``content_scenes[i]["content"]["slides"][j]["elements"]`` — nested
       per-scene shape (audit spec).
    2. ``content_meta["slides"][k]["elements"]`` — production wizard shape
       (CG-P1-12).
    3. ``content_scenes[i]["slides"][j]["elements"]`` — legacy embedded
       shape (still supported).

    Each location carries one image element with empty ``src``. After the
    task runs, all three must be filled.
    """
    scenes = [
        {
            "id": "scene-0",
            "type": "lecture",
            "title": "Scene 0",
            "actions": [{"type": "speech", "agentId": "a1", "text": "hi"}],
            # Nested per-scene shape — audit said this can also exist.
            "content": {
                "type": "slide",
                "slides": [
                    {
                        "id": "slide-nested-0-0",
                        "elements": [
                            {
                                "type": "image",
                                "id": "img-nested-0",
                                "src": "",
                                "content": "nested keyword 0",
                            },
                            {"type": "text", "id": "txt-nested-0", "src": "", "content": "x"},
                        ],
                    },
                    {
                        "id": "slide-nested-0-1",
                        "elements": [
                            {
                                "type": "image",
                                "id": "img-nested-1",
                                "src": "",
                                "content": "nested keyword 1",
                            },
                        ],
                    },
                ],
            },
        },
        {
            "id": "scene-1",
            "type": "lecture",
            "title": "Scene 1",
            "actions": [],
            # Legacy embedded shape — top-level ``slides`` key on the scene.
            "slides": [
                {
                    "id": "slide-legacy-1-0",
                    "elements": [
                        {
                            "type": "image",
                            "id": "img-legacy-1",
                            "src": "",
                            "content": "legacy keyword",
                        },
                    ],
                },
            ],
            "content": {"type": "slide", "elements": [], "speakerScript": ""},
        },
    ]
    # Production wizard's flat slides shape — slides under content_meta.
    flat_slides = [
        {
            "id": "slide-meta-0",
            "elements": [
                {
                    "type": "image",
                    "id": "img-meta-0",
                    "src": "",
                    "content": "meta keyword 0",
                },
            ],
        },
        {
            "id": "slide-meta-1",
            "elements": [
                {
                    "type": "image",
                    "id": "img-meta-1",
                    "src": "",
                    "content": "meta keyword 1",
                },
            ],
        },
    ]
    return MAICClassroom.objects.create(
        tenant=tenant,
        creator=creator,
        title="Hybrid-shape classroom (F1 regression)",
        topic="Test",
        status="READY",
        images_pending=True,
        content_scenes=scenes,
        content_meta={
            "slides": flat_slides,
            "sceneSlideBounds": [
                {"sceneIdx": 0, "startSlide": 0, "endSlide": 0},
                {"sceneIdx": 1, "startSlide": 1, "endSlide": 1},
            ],
        },
    )


@pytest.fixture
def maic_enabled_tenant_f1(tenant):
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    return tenant


def test_fill_images_walks_all_three_locations(
    maic_enabled_tenant_f1,
    teacher_user,
):
    """REGRESSION (F1): the task must fill image src at ALL three locations
    in the same classroom and flip images_pending to False.

    Locations covered (one image element each, except nested which has 2):
        - content_scenes[0].content.slides[0..1].elements[0]   (2 images)
        - content_scenes[1].slides[0].elements[0]              (1 image)
        - content_meta.slides[0..1].elements[0]                (2 images)
    Total: 5 image elements.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _hybrid_shape_classroom(maic_enabled_tenant_f1, teacher_user)
    classroom_id = str(classroom.id)
    assert classroom.images_pending is True

    fetched_keywords: list[str] = []

    def fetch(keyword, **_kwargs):
        fetched_keywords.append(keyword)
        # Distinct URL per keyword so we can assert proper routing.
        return f"https://images.unsplash.com/photo-{keyword.replace(' ', '-')}"

    with patch(
        "apps.courses.image_service.fetch_scene_image",
        side_effect=fetch,
    ):
        fill_classroom_images(classroom_id)

    classroom.refresh_from_db()

    # ── Idempotency-flip ───────────────────────────────────────────────────
    assert (
        classroom.images_pending is False
    ), "images_pending must be cleared after a successful full run"

    # ── 1. Nested content_scenes[0].content.slides[*].elements ─────────────
    nested_slides = classroom.content_scenes[0]["content"]["slides"]
    nested_imgs = [
        el
        for slide in nested_slides
        for el in slide.get("elements", [])
        if el.get("type") == "image"
    ]
    assert len(nested_imgs) == 2, "fixture leak — expected 2 nested images"
    for el in nested_imgs:
        src = el.get("src", "")
        assert src, (
            f"REGRESSION (F1): nested content_scenes[i].content.slides "
            f"image element {el.get('id')!r} not filled — task is not "
            f"walking the nested per-scene shape. src={src!r}"
        )
        assert src.startswith(
            "https://"
        ), f"unexpected src shape for nested image {el.get('id')!r}: {src!r}"

    # ── 2. Legacy content_scenes[1].slides[*].elements ─────────────────────
    legacy_imgs = [
        el
        for slide in classroom.content_scenes[1].get("slides", [])
        for el in slide.get("elements", [])
        if el.get("type") == "image"
    ]
    assert len(legacy_imgs) == 1, "fixture leak — expected 1 legacy image"
    legacy_src = legacy_imgs[0].get("src", "")
    assert legacy_src and legacy_src.startswith(
        "https://"
    ), f"legacy embedded scene.slides image not filled; src={legacy_src!r}"

    # ── 3. content_meta.slides[*].elements ─────────────────────────────────
    meta_slides = (classroom.content_meta or {}).get("slides") or []
    meta_imgs = [
        el for slide in meta_slides for el in slide.get("elements", []) if el.get("type") == "image"
    ]
    assert len(meta_imgs) == 2, "fixture leak — expected 2 meta-slide images"
    for el in meta_imgs:
        src = el.get("src", "")
        assert src and src.startswith(
            "https://"
        ), f"meta-slide image {el.get('id')!r} not filled; src={src!r}"

    # ── 4. Routing sanity — each image's keyword reached fetch_scene_image ─
    expected_keywords = {
        "nested keyword 0",
        "nested keyword 1",
        "legacy keyword",
        "meta keyword 0",
        "meta keyword 1",
    }
    assert expected_keywords.issubset(set(fetched_keywords)), (
        f"Not all keywords were fetched. Missing: "
        f"{expected_keywords - set(fetched_keywords)}; got: {fetched_keywords}"
    )


def test_fill_images_nested_content_slides_only(
    maic_enabled_tenant_f1,
    teacher_user,
):
    """Narrow regression: a classroom whose images live ONLY in
    ``content_scenes[i]["content"]["slides"]`` (no top-level scene.slides,
    no content_meta.slides) must still get all images filled.

    This isolates the audit's F1 "missing nested walker" gap from the
    other two walkers so a future regression can be pinpointed quickly.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    scenes = [
        {
            "id": "scene-only-nested",
            "type": "lecture",
            "title": "Only nested",
            "actions": [],
            "content": {
                "type": "slide",
                "slides": [
                    {
                        "id": "slide-only-nested-0",
                        "elements": [
                            {
                                "type": "image",
                                "id": "img-only-nested",
                                "src": "",
                                "content": "only nested keyword",
                            },
                        ],
                    },
                ],
            },
        },
    ]
    classroom = MAICClassroom.objects.create(
        tenant=maic_enabled_tenant_f1,
        creator=teacher_user,
        title="Only-nested classroom",
        topic="Test",
        status="READY",
        images_pending=True,
        content_scenes=scenes,
        content_meta={},  # No content_meta.slides on purpose.
    )

    with patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-only-nested",
    ):
        fill_classroom_images(str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.images_pending is False
    nested_img = classroom.content_scenes[0]["content"]["slides"][0]["elements"][0]
    assert (
        nested_img["src"] == "https://images.unsplash.com/photo-only-nested"
    ), f"Nested-only walk failed; src={nested_img.get('src')!r}"


# ── F4 (P0) — typed slide schema: mirror url to slots.image.src ─────────────


def test_fill_images_mirrors_url_to_slots_image_src(
    maic_enabled_tenant_f1,
    teacher_user,
):
    """F4: when a slide carries ``template == 'body-image-right'`` AND its
    ``slots.image.src`` is empty AND the elements[] image gets filled, the
    same URL must also land in ``slots.image.src`` so the slot-based
    renderer doesn't show a broken image while ``elements[]`` already has
    the URL.

    Covers the production-shape walker (``content_meta.slides``) which is
    the path real classrooms exercise.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    flat_slides = [
        {
            "id": "slide-typed",
            "template": "body-image-right",
            "slots": {
                "title": {"text": "Energy in cells"},
                "image": {"src": "", "alt": "mitochondrion"},
            },
            "elements": [
                {
                    "type": "image",
                    "id": "img-typed",
                    "src": "",
                    "content": "mitochondrion diagram",
                },
            ],
        },
    ]
    classroom = MAICClassroom.objects.create(
        tenant=maic_enabled_tenant_f1,
        creator=teacher_user,
        title="F4 typed-schema classroom",
        topic="Test",
        status="READY",
        images_pending=True,
        content_scenes=[],
        content_meta={
            "slides": flat_slides,
            "sceneSlideBounds": [],
        },
    )

    fetched_url = "https://images.unsplash.com/photo-mito"
    with patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value=fetched_url,
    ):
        fill_classroom_images(str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.images_pending is False

    saved_slide = classroom.content_meta["slides"][0]

    # 1. Legacy elements[] path got the URL (single source of truth).
    assert (
        saved_slide["elements"][0]["src"] == fetched_url
    ), f"elements[].src not filled; got {saved_slide['elements'][0].get('src')!r}"

    # 2. F4 mirror: slots.image.src must carry the same URL.
    assert saved_slide["slots"]["image"]["src"] == fetched_url, (
        f"REGRESSION (F4): slots.image.src not mirrored; "
        f"got {saved_slide['slots']['image'].get('src')!r}"
    )
    # alt was preserved from the original slot — NOT overwritten by the mirror.
    assert saved_slide["slots"]["image"]["alt"] == "mitochondrion"


# ── WAVE-6-F4-F5: _maybe_mirror_url_to_slots_image accepted-prefix parity ──


def test_maybe_mirror_url_to_slots_image_accepts_site_relative_static():
    """REGRESSION (WAVE-6-F4-F5): the backend's "already filled" prefix list
    in ``_maybe_mirror_url_to_slots_image`` MUST stay in parity with the FE
    allow-list in ``frontend/src/components/maic/SlideRenderer.tsx`` (which
    accepts ANY site-relative path starting with ``/``).

    Pre-fix the backend only skipped on ``https://``/``http://``/``/media/``
    so a slot already pre-filled with ``/static/foo.png`` would be
    silently overwritten on every fill pass.  This test pins the new
    parity: ``/static/...`` is recognised as already-filled.
    """
    from apps.courses.maic_tasks import _maybe_mirror_url_to_slots_image

    # 1. Existing /static/ URL → treat as already filled, do NOT overwrite.
    slide_with_static = {
        "template": "body-image-right",
        "slots": {"image": {"src": "/static/foo.png"}},
    }
    mutated = _maybe_mirror_url_to_slots_image(
        slide_with_static, "https://images.unsplash.com/photo-x"
    )
    assert mutated is False, "/static/ URL must be recognised as already filled"
    assert slide_with_static["slots"]["image"]["src"] == "/static/foo.png"

    # 2. Empty existing src + a /static/ incoming URL → mirror happens.
    slide_empty = {
        "template": "body-image-right",
        "slots": {"image": {"src": ""}},
    }
    mutated_empty = _maybe_mirror_url_to_slots_image(slide_empty, "/static/foo.png")
    assert mutated_empty is True
    assert slide_empty["slots"]["image"]["src"] == "/static/foo.png"


def test_maybe_mirror_url_to_slots_image_existing_https_and_media_still_skipped():
    """Sibling to the /static/ test — pin that the legacy prefixes
    (``https://``, ``http://``, ``/media/``) are still recognised as
    already-filled after the WAVE-6-F4-F5 widening.
    """
    from apps.courses.maic_tasks import _maybe_mirror_url_to_slots_image

    for existing in (
        "https://images.unsplash.com/photo-cell",
        "http://example.com/foo.png",
        "/media/tenant/1/uploads/x.png",
    ):
        slide = {
            "template": "body-image-right",
            "slots": {"image": {"src": existing}},
        }
        mutated = _maybe_mirror_url_to_slots_image(
            slide, "https://images.unsplash.com/photo-replace"
        )
        assert mutated is False, f"{existing!r} must still be recognised as already filled"
        assert slide["slots"]["image"]["src"] == existing


def test_fill_images_does_not_mirror_when_template_absent(
    maic_enabled_tenant_f1,
    teacher_user,
):
    """F4 negative case: a slide WITHOUT ``template`` (legacy free-form)
    must NOT get a ``slots`` dict synthesized just because the image was
    filled. Backwards compat invariant — the mirror is template-gated.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    flat_slides = [
        {
            "id": "slide-legacy",
            "elements": [
                {
                    "type": "image",
                    "id": "img-legacy",
                    "src": "",
                    "content": "legacy keyword",
                },
            ],
        },
    ]
    classroom = MAICClassroom.objects.create(
        tenant=maic_enabled_tenant_f1,
        creator=teacher_user,
        title="F4 legacy-no-mirror classroom",
        topic="Test",
        status="READY",
        images_pending=True,
        content_scenes=[],
        content_meta={"slides": flat_slides},
    )

    with patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-legacy",
    ):
        fill_classroom_images(str(classroom.id))

    classroom.refresh_from_db()
    saved_slide = classroom.content_meta["slides"][0]
    # Legacy elements[] path got filled.
    assert saved_slide["elements"][0]["src"].startswith("https://")
    # And we did NOT synthesize a slots dict on the legacy slide.
    assert "slots" not in saved_slide
