"""F2 (P0) — Per-element image task store + WS broadcast tests.

Source: 2026-04-28 OpenMAIC deep-dive followups (F2).

Covers the new ``MAICClassroom.content_image_tasks`` shard + the
``maic.image.task`` channel-layer events emitted by ``fill_classroom_images``:

  * Task seeds ``status='pending'`` for every image element at start.
  * Per-fetch transitions land as ``pending → generating → done`` on
    success and ``pending → generating → failed`` on a fetch exception.
  * One channel event is broadcast per transition.
  * BATCH-6-F7 cross-tenant guard still fires (no regression).
  * Late-joining client sees the full task map via the GET endpoint.

F2 contract alignment (2026-04-28):
  Backend keys MUST match the FE's ``buildElementKey`` output —
  ``"<scene_idx>:<slide_idx>:<element_idx>:<element_id_or_synth>"`` with
  NO walker prefix. Collisions across walker shapes (same logical
  element resolved by multiple data walkers) are deduped to a single
  entry via last-write-wins. See backend ``make_image_element_key``.
"""
import re
from unittest.mock import patch

import pytest

from apps.courses.maic_models import MAICClassroom
from apps.courses.maic_tasks import (
    _enumerate_image_elements,
    make_image_element_key,
    make_slot_image_key,
)


# Regex from the F2 contract: every per-element key in
# ``content_image_tasks`` is exactly four colon-separated segments where
# the first three are non-negative integers. The trailing segment is
# either the element's stable id or the ``idx-N`` fallback.
ELEMENT_KEY_REGEX = re.compile(r"^\d+:\d+:\d+:.+$")
# Slot-aware key shape (Path A) — body-image-right typed slides.
SLOT_KEY_REGEX = re.compile(r"^\d+:\d+:image:slot$")


pytestmark = pytest.mark.django_db


# ───────────── Fixtures ───────────────────────────────────────────────────────


def _classroom_with_two_images(tenant, creator):
    """Build a classroom with exactly two image elements:

      * one at ``content_meta.slides[0].elements[0]`` (production wizard shape)
      * one at ``content_scenes[0].content.slides[0].elements[0]`` (nested)

    Returns the saved instance with ``images_pending=True`` and an empty
    ``content_image_tasks`` shard so the seed step has work to do.
    """
    scenes = [
        {
            "id": "scene-0",
            "type": "lecture",
            "title": "Scene 0",
            "actions": [],
            "content": {
                "type": "slide",
                "slides": [
                    {
                        "id": "slide-nested-0",
                        "elements": [
                            {
                                "type": "image",
                                "id": "img-nested-0",
                                "src": "",
                                "content": "nested keyword",
                            },
                        ],
                    },
                ],
            },
        },
    ]
    flat_slides = [
        {
            "id": "slide-meta-0",
            "elements": [
                {
                    "type": "image",
                    "id": "img-meta-0",
                    "src": "",
                    "content": "meta keyword",
                },
            ],
        },
    ]
    return MAICClassroom.objects.create(
        tenant=tenant,
        creator=creator,
        title="F2 task-store fixture",
        topic="Test",
        status="READY",
        images_pending=True,
        content_scenes=scenes,
        content_meta={"slides": flat_slides},
    )


@pytest.fixture
def maic_enabled_tenant_f2(tenant):
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    return tenant


# ───────────── Tests: enumeration helper ──────────────────────────────────────


def test_enumerate_image_elements_keys_match_frontend_contract():
    """Per-element keys must conform to ``<sceneIdx>:<slideIdx>:<elIdx>:<id>``.

    Post F2 contract alignment (2026-04-28) the walker prefix is dropped:
    every key MUST match the regex ``^\\d+:\\d+:\\d+:.+$`` so the FE's
    ``useMediaTask(buildElementKey(...))`` resolves against the same
    string the backend persists.
    """
    scenes = [
        {
            "id": "s0",
            "slides": [
                {
                    "id": "slide-0",
                    "elements": [
                        {"type": "image", "id": "img-A", "content": "a"},
                    ],
                },
            ],
            "content": {
                "elements": [
                    {"type": "image", "id": "img-B", "content": "b"},
                ],
                "slides": [
                    {
                        "id": "slide-1",
                        "elements": [
                            {"type": "image", "id": "img-C", "content": "c"},
                        ],
                    },
                ],
            },
        },
    ]
    meta_slides = [
        {
            "id": "slide-meta-0",
            "elements": [
                {"type": "image", "id": "img-D", "content": "d"},
            ],
        },
    ]
    elements = _enumerate_image_elements(scenes, meta_slides)
    keys = [t[5] for t in elements]
    # Each fixture uses a distinct element id, so the four walker shapes
    # produce four DISTINCT keys (collision-free in this fixture).
    assert len(keys) == 4, f"expected 4 image elements, got {len(keys)}: {keys}"
    assert len(set(keys)) == 4, f"duplicate keys: {keys}"

    # Every key matches the frontend contract regex.
    for k in keys:
        assert ELEMENT_KEY_REGEX.match(k), (
            f"key {k!r} doesn't match the FE contract regex " f"{ELEMENT_KEY_REGEX.pattern!r}"
        )
    # And explicitly: NO walker prefix (no segment that's a known
    # walker name in the first slot).
    for k in keys:
        first_segment = k.split(":", 1)[0]
        assert first_segment.isdigit(), (
            f"key {k!r} starts with non-digit segment {first_segment!r} — "
            f"walker prefix has leaked back into the on-the-wire key"
        )


def test_enumerate_image_elements_dedupes_collisions_across_walkers():
    """Same logical element described by multiple walker shapes MUST
    collapse to a SINGLE key in the persisted ``content_image_tasks``
    map (last-write-wins). Pre F2 contract alignment the walker prefix
    kept these distinct; that's now a feature, not a bug — the F1 data
    walker writes the same fetched URL into every shape that holds the
    element, so all those shapes describe the same logical element.
    """
    # Scene 0, slide 0, element 0, id "img-shared" — present in BOTH
    # the top-level slides walker AND the nested content.slides walker.
    scenes = [
        {
            "id": "s0",
            "slides": [
                {
                    "id": "slide-0",
                    "elements": [
                        {"type": "image", "id": "img-shared", "content": "x"},
                    ],
                },
            ],
            "content": {
                "slides": [
                    {
                        "id": "slide-0",
                        "elements": [
                            {"type": "image", "id": "img-shared", "content": "x"},
                        ],
                    },
                ],
            },
        },
    ]
    elements = _enumerate_image_elements(scenes, [])
    # Both walkers enumerated — but the on-the-wire key is identical
    # (no walker prefix), so persisting both lands on one entry.
    keys = [t[5] for t in elements]
    assert len(keys) == 2, f"enumerator should still produce two tuples: {keys}"
    assert (
        len(set(keys)) == 1
    ), f"both walkers should produce the SAME key (last-write-wins): {keys}"
    # And the deduped key is the contract shape.
    deduped_key = keys[0]
    assert ELEMENT_KEY_REGEX.match(deduped_key), deduped_key
    assert deduped_key == "0:0:0:img-shared"


def test_make_image_element_key_falls_back_to_idx_when_id_missing():
    """A walker with no element id must still yield a deterministic key
    in the ``<sceneIdx>:<slideIdx>:<elIdx>:idx-N`` shape.
    """
    el_no_id = {"type": "image", "content": "no-id"}
    # scene_idx=None and slide_idx not None → scene_idx collapses to 0.
    key = make_image_element_key(None, 0, 3, el_no_id)
    assert key == "0:0:3:idx-3"
    # Both indices supplied → both flow through verbatim.
    key2 = make_image_element_key(2, 5, 7, el_no_id)
    assert key2 == "2:5:7:idx-7"


def test_make_image_element_key_uses_element_id_when_present():
    """The frontend passes ``el.id`` directly; the backend must too —
    no ``el-`` or ``idx-`` prefix when a stable id is on the element.
    """
    el = {"type": "image", "id": "stable-uuid-123", "content": "x"}
    key = make_image_element_key(0, 0, 0, el)
    assert key == "0:0:0:stable-uuid-123"


def test_make_slot_image_key_matches_frontend_synthesis():
    """Body-image-right slot key must match the FE's
    ``${sceneIndex}:${slideIndex}:image:slot`` synthesis.
    """
    assert make_slot_image_key(2, 5) == "2:5:image:slot"
    # Negative / None inputs collapse to 0 so the key always validates.
    assert make_slot_image_key(-1, 3) == "0:3:image:slot"


# ── WAVE-F2-F6: WalkerTag StrEnum legacy-string parity ─────────────────────


def test_walker_tag_enum_matches_legacy_string_values():
    """REGRESSION (WAVE-F2-F6): ``WalkerTag`` is a ``StrEnum`` whose members
    must compare ``==`` to their legacy bare-string identifiers.  This is the
    backward-compat hinge — every ``_key_lookup`` tuple historically used
    bare strings as the walker segment, and existing fixtures / hashed-key
    lookups will keep working only if the enum members hash and compare
    equal to those strings.

    If a typo lands in ``WalkerTag`` (e.g. ``"slide"`` instead of
    ``"slides"``), this test fails immediately rather than letting the
    bug surface as a silent ``_key_lookup`` miss in production.
    """
    from apps.courses.maic_tasks import WalkerTag

    expected = {
        "SLIDES": "slides",
        "CONTENT_ELEMENTS": "content_elements",
        "CONTENT_SLIDES": "content_slides",
        "META_SLIDES": "meta_slides",
    }
    # Each enum member equals its legacy string value.
    for name, value in expected.items():
        member = getattr(WalkerTag, name)
        assert member == value, (
            f"WalkerTag.{name} != {value!r} — a rename would break "
            f"backward-compat with existing _key_lookup tuples"
        )
        # And hashes match — required for dict-key parity since
        # ``_key_lookup`` is built with ``WalkerTag.X`` and queried
        # historically with bare strings (or vice versa).
        assert hash(member) == hash(value), (
            f"hash(WalkerTag.{name}) != hash({value!r}) — dict-key " f"lookups would silently miss"
        )

    # The enum covers exactly the four walker shapes the data-walker
    # produces — guard against accidental additions/removals.
    assert {m.value for m in WalkerTag} == set(expected.values())


# ───────────── Tests: end-to-end task transitions ─────────────────────────────


def _captured_broadcasts():
    """Patch helper — returns (capture_list, patch_object).

    Use as::

        captured, patcher = _captured_broadcasts()
        with patcher:
            ...
        assert captured == [...]
    """
    captured: list[dict] = []

    def fake_broadcast(classroom_id, element_key, status, **kw):
        captured.append(
            {
                "classroom_id": str(classroom_id),
                "element_key": element_key,
                "status": status,
                **{k: v for k, v in kw.items() if v is not None},
            }
        )

    patcher = patch(
        "apps.courses.maic_tasks._broadcast_image_task",
        side_effect=fake_broadcast,
    )
    return captured, patcher


def test_fill_seeds_pending_for_every_image_element(
    maic_enabled_tenant_f2,
    teacher_user,
):
    """Before the first fetch, every image element must have a ``pending``
    entry in ``content_image_tasks`` and a corresponding broadcast event.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    assert classroom.content_image_tasks == {}

    captured, patcher = _captured_broadcasts()

    with patcher, patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-test",
    ):
        fill_classroom_images(str(classroom.id))

    classroom.refresh_from_db()

    # Every image element should have a final entry.
    assert len(classroom.content_image_tasks) == 2
    for key, entry in classroom.content_image_tasks.items():
        assert entry["status"] == "done"
        assert entry["src"] == "https://images.unsplash.com/photo-test"
        assert "updated_at" in entry

    # First two events should be the pending seed (one per element);
    # subsequent events are generating + done per fetch site.
    statuses = [(e["element_key"], e["status"]) for e in captured]
    pendings = [s for s in statuses if s[1] == "pending"]
    generatings = [s for s in statuses if s[1] == "generating"]
    dones = [s for s in statuses if s[1] == "done"]
    assert len(pendings) == 2, f"expected 2 pending broadcasts: {statuses}"
    assert len(generatings) == 2, f"expected 2 generating broadcasts: {statuses}"
    assert len(dones) == 2, f"expected 2 done broadcasts: {statuses}"


def test_fill_emits_pending_generating_done_in_order(
    maic_enabled_tenant_f2,
    teacher_user,
):
    """For each image element the broadcasts must appear in the order
    ``pending → generating → done``.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    captured, patcher = _captured_broadcasts()

    with patcher, patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-test",
    ):
        fill_classroom_images(str(classroom.id))

    # For every element_key, walk captured events in encounter order and
    # check the status transitions are valid.
    by_key: dict[str, list[str]] = {}
    for ev in captured:
        by_key.setdefault(ev["element_key"], []).append(ev["status"])

    assert len(by_key) == 2, f"expected 2 element keys, got: {list(by_key)}"
    for key, statuses in by_key.items():
        assert statuses == [
            "pending",
            "generating",
            "done",
        ], f"unexpected sequence for {key}: {statuses}"


def test_fill_marks_failed_with_error_code_on_fetch_exception(
    maic_enabled_tenant_f2,
    teacher_user,
):
    """When ``fetch_scene_image`` raises, the corresponding element must
    transition to ``failed`` with an ``error_code``.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    captured, patcher = _captured_broadcasts()

    class RateLimitError(Exception):
        pass

    with patcher, patch(
        "apps.courses.image_service.fetch_scene_image",
        side_effect=RateLimitError("provider 429 rate limited"),
    ):
        fill_classroom_images(str(classroom.id))

    classroom.refresh_from_db()
    assert len(classroom.content_image_tasks) == 2
    for key, entry in classroom.content_image_tasks.items():
        assert entry["status"] == "failed", f"{key} should be failed: {entry}"
        # error_code is mapped from the exception text/name.
        assert entry["error_code"] in {
            "rate_limited",
            "RateLimitError",
        }, f"unexpected error_code for {key}: {entry}"

    # And we got pending→generating→failed broadcasts per element.
    by_key: dict[str, list[str]] = {}
    for ev in captured:
        by_key.setdefault(ev["element_key"], []).append(ev["status"])
    for key, statuses in by_key.items():
        assert statuses == [
            "pending",
            "generating",
            "failed",
        ], f"unexpected sequence for {key}: {statuses}"


# ───────────── Tests: hydration via GET endpoint ─────────────────────────────


def test_get_classroom_detail_surfaces_image_tasks(
    maic_enabled_tenant_f2,
    teacher_user,
    api_client_for,
):
    """A late-joining client hitting the teacher detail GET must receive
    the full ``content_image_tasks`` map so it can hydrate its store
    before connecting the WebSocket.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    captured, patcher = _captured_broadcasts()
    with patcher, patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-late",
    ):
        fill_classroom_images(str(classroom.id))
    classroom.refresh_from_db()
    assert len(classroom.content_image_tasks) == 2

    client = api_client_for(teacher_user, maic_enabled_tenant_f2)
    # The teacher detail endpoint is exposed at
    #   /teacher/maic/classrooms/<uuid>/
    # We build the URL directly rather than calling ``reverse`` because the
    # name is registered under a nested ``maic`` namespace inside
    # ``teacher_urls.py`` and the fully-qualified namespace path
    # (``courses:maic:teacher_maic_classroom_detail``) varies by include order
    # — testing the path string is more robust against future namespace
    # refactors.
    url = f"/api/v1/teacher/maic/classrooms/{classroom.id}/"
    resp = client.get(url)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert "content_image_tasks" in body
    assert len(body["content_image_tasks"]) == 2
    for entry in body["content_image_tasks"].values():
        assert entry["status"] == "done"
        assert entry["src"] == "https://images.unsplash.com/photo-late"


def test_hydration_keys_match_frontend_regex(
    maic_enabled_tenant_f2,
    teacher_user,
    api_client_for,
):
    """Regression (F2 contract alignment, 2026-04-28): every key in the
    GET-classroom-detail ``content_image_tasks`` map MUST match the FE's
    ``buildElementKey`` regex ``^\\d+:\\d+:\\d+:.+$`` — exactly four
    colon-separated segments with non-negative-integer prefixes — so the
    FE's ``useMediaTask(elementKey)`` lookup hits instead of falling
    through to the legacy ``imagesPending`` boolean path.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    captured, patcher = _captured_broadcasts()
    with patcher, patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-regression",
    ):
        fill_classroom_images(str(classroom.id))

    client = api_client_for(teacher_user, maic_enabled_tenant_f2)
    url = f"/api/v1/teacher/maic/classrooms/{classroom.id}/"
    resp = client.get(url)
    assert resp.status_code == 200, resp.content
    body = resp.json()
    image_tasks = body["content_image_tasks"]
    assert image_tasks, "fixture should produce at least one image task"

    for key in image_tasks:
        # The contract regex from the F2 spec.
        assert ELEMENT_KEY_REGEX.match(key), (
            f"hydration key {key!r} fails the FE regression regex "
            f"{ELEMENT_KEY_REGEX.pattern!r} — walker prefix has crept back "
            f"into the persisted key"
        )
        # And the key has EXACTLY four colon-separated segments.
        segments = key.split(":")
        assert len(segments) == 4, f"hydration key {key!r} has {len(segments)} segments, expected 4"


# ───────────── Tests: Path A — body-image-right slot keys ───────────────────


def _classroom_with_body_image_right_slide(tenant, creator):
    """Build a classroom whose meta_slides[0] is a typed body-image-right
    slide — the F4 shape that mirrors a slot-aware image renderer.

    The slide has BOTH:
      * an ``elements[0]`` entry of type 'image' (per-element walker hits)
      * ``slots.image`` (the slot-aware renderer the FE subscribes to)
    so we can verify the backend emits BOTH a per-element key AND a
    matching slot key when the fetch lands.
    """
    flat_slides = [
        {
            "id": "slide-typed-0",
            "template": "body-image-right",
            "slots": {
                "title": {"text": "Hello"},
                "body": {"text": "World"},
                "image": {"src": "", "alt": "demo"},
            },
            "elements": [
                {
                    "type": "image",
                    "id": "img-typed-0",
                    "src": "",
                    "content": "typed slide image",
                },
            ],
        },
    ]
    return MAICClassroom.objects.create(
        tenant=tenant,
        creator=creator,
        title="F2 typed slot fixture",
        topic="Test",
        status="READY",
        images_pending=True,
        content_scenes=[],
        content_meta={
            "slides": flat_slides,
            "sceneSlideBounds": [
                {"sceneIdx": 0, "startSlide": 0, "endSlide": 0},
            ],
        },
    )


def test_fill_emits_slot_key_for_body_image_right_slides(
    maic_enabled_tenant_f2,
    teacher_user,
):
    """Path A: when a body-image-right typed slide receives a fetched URL,
    the backend MUST emit BOTH the per-element key AND the slot key
    (``"<sceneIdx>:<slideIdx>:image:slot"``) so the FE's
    ``BodyImageRightTemplate`` slot-aware renderer sees live transitions.
    """
    from apps.courses.maic_tasks import fill_classroom_images

    classroom = _classroom_with_body_image_right_slide(
        maic_enabled_tenant_f2,
        teacher_user,
    )
    captured, patcher = _captured_broadcasts()

    with patcher, patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-typed",
    ):
        fill_classroom_images(str(classroom.id))

    classroom.refresh_from_db()
    keys = list(classroom.content_image_tasks.keys())

    # Two keys: one per-element + one slot-aware.
    element_keys = [k for k in keys if ELEMENT_KEY_REGEX.match(k)]
    slot_keys = [k for k in keys if SLOT_KEY_REGEX.match(k)]

    assert element_keys, f"expected ≥1 per-element key, got: {keys}"
    assert slot_keys, f"expected slot-aware key for body-image-right slide, got: {keys}"

    # The slot key matches the FE's ``${sceneIndex}:${slideIndex}:image:slot``
    # synthesis. sceneSlideBounds places this slide under sceneIdx=0,
    # slideIdx=0.
    assert "0:0:image:slot" in slot_keys

    # Slot-key entry should have the same final URL as the per-element
    # entry (Path A: emit slot transitions in lockstep).
    slot_entry = classroom.content_image_tasks["0:0:image:slot"]
    assert slot_entry["status"] == "done"
    assert slot_entry["src"] == "https://images.unsplash.com/photo-typed"

    # Slot-key broadcasts also fire — at least one done-status event for
    # the slot key.
    slot_broadcasts = [
        e for e in captured if e["element_key"] == "0:0:image:slot" and e["status"] == "done"
    ]
    assert slot_broadcasts, f"no slot-key done broadcast in: {captured}"


# ───────────── Tests: BATCH-6-F7 cross-tenant guard still fires ──────────────


def test_image_task_persist_respects_cross_tenant_guard(
    maic_enabled_tenant_f2,
    teacher_user,
    tenant_b,
):
    """Calling ``update_content_section('image_tasks', …)`` with a
    different tenant active in the thread-local context must raise
    ``PermissionDenied`` — the BATCH-6-F7 guard owned by the model
    method must NOT have regressed under the new section name.
    """
    from django.core.exceptions import PermissionDenied
    from utils.tenant_middleware import set_current_tenant, clear_current_tenant

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)

    # Activate the OTHER tenant in the thread-local context.
    set_current_tenant(tenant_b)
    try:
        with pytest.raises(PermissionDenied):
            classroom.update_content_section(
                "image_tasks",
                {"some-key": {"status": "pending"}},
                save=False,
            )
    finally:
        clear_current_tenant()


# ───────────── Tests: WS consumer auth ───────────────────────────────────────


def test_consumer_group_name_is_stable():
    """The producer (Celery task) and consumer must use the same group
    name — guard the contract against accidental drift.
    """
    from apps.courses.maic_consumers import maic_classroom_group_name
    from apps.courses.maic_tasks import _IMAGE_TASK_GROUP_TEMPLATE

    cid = "00000000-0000-4000-8000-000000000000"
    assert maic_classroom_group_name(cid) == (_IMAGE_TASK_GROUP_TEMPLATE.format(classroom_id=cid))


# ───────────── Tests: WS consumer connect / auth (WAVE-F2-F2) ────────────────
#
# WAVE-F2-F2 (should-fix) — coverage for the new MAIC classroom WS consumer's
# ``connect()`` and auth branches. The producer-side tests above cover the
# Celery task → store + broadcast path; these tests cover the handshake:
#
#   1. Anonymous (no Bearer subprotocol) → close 4001.
#   2. Cross-tenant authenticated user → close 4003.
#   3. Same-tenant creator → connect, then deliver a ``maic.image.task``
#      event injected via ``channel_layer.group_send`` to the canonical
#      ``maic_classroom_<uuid>`` group name.
#
# We build the same ASGI stack as production (``JWTAuthMiddleware`` wrapping
# the courses ``URLRouter``) so the subprotocol-based JWT auth path runs
# end-to-end. ``InMemoryChannelLayer`` is forced via ``override_settings``
# so ``group_send`` works without a live Redis broker.


def _bearer_token_for(user):
    """Build the ``Bearer.<jwt>`` subprotocol string for *user*.

    Mirrors the FE convention: ``Sec-WebSocket-Protocol: Bearer.<access_jwt>``.
    """
    from rest_framework_simplejwt.tokens import AccessToken
    from apps.notifications.middleware import BEARER_PREFIX

    return f"{BEARER_PREFIX}{AccessToken.for_user(user)}"


def _build_maic_ws_app():
    """Compose the MAIC WS ASGI app for the auth-only test branches.

    We re-build the stack rather than importing ``config.asgi.application``
    directly so we can OMIT the outermost ``AllowedHostsOriginValidator``
    layer present in production. The Channels ``OriginValidator`` REJECTS
    any connection that lacks an ``Origin`` header unless ``*`` is in
    ``settings.ALLOWED_HOSTS`` (see ``valid_origin``: ``parsed_origin is
    None and "*" not in self.allowed_origins`` returns False). Channels'
    ``WebsocketCommunicator`` does not synthesise an ``Origin`` header by
    default, so leaving the validator in place would close every
    handshake at the validator layer before our consumer-level auth /
    visibility checks fire — exactly the layers this helper exists to
    exercise in isolation.

    The auth path we care about for the auth-branch tests
    (``JWTAuthMiddleware`` → URLRouter → consumer) is identical to
    production. The full layer composition (including
    ``AllowedHostsOriginValidator``) is pinned separately by
    ``test_production_asgi_stack_completes_handshake`` below, which
    references the production app and supplies an explicit ``Origin``
    header.
    """
    from channels.routing import URLRouter
    from apps.notifications.middleware import JWTAuthMiddleware
    from apps.courses.routing import websocket_urlpatterns as courses_ws

    return JWTAuthMiddleware(URLRouter(list(courses_ws)))


# Implementation note — these connect/auth tests use Django's
# ``TestCase`` (with ``setUpTestData``) rather than pytest-django's
# default transaction-wrapped ``django_db`` mark because the consumer's
# ``database_sync_to_async`` visibility-check runs in a separate thread.
# Inside an outer test transaction that thread sees a closed connection
# (pytest-django closes the wrapping transaction's connection on commit
# from the other thread). Mirroring the existing
# ``apps/notifications/tests_websocket_auth.py`` pattern — which also
# exercises a ``database_sync_to_async`` JWT path — sidesteps that.

from django.test import TransactionTestCase, override_settings  # noqa: E402
from asgiref.sync import async_to_sync  # noqa: E402
from channels.testing import WebsocketCommunicator  # noqa: E402

# WAVE-8-F3: import the production ASGI app at module-import time so the
# auth backends (which call ``get_user_model()`` on import) resolve the
# ``users.User`` model BEFORE any ``TransactionTestCase`` sets
# ``available_apps = []`` — that flag restricts the app registry during
# the test, and a deferred import inside the test would raise
# ``ImproperlyConfigured: AUTH_USER_MODEL refers to model 'users.User'
# that has not been installed``.
from config.asgi import application as _PROD_ASGI_APPLICATION  # noqa: E402


@override_settings(
    ALLOWED_HOSTS=["*"],
    CHANNEL_LAYERS={
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    },
)
class TestMAICClassroomConsumerConnect(TransactionTestCase):
    """WAVE-F2-F2 connect / auth coverage for ``MAICClassroomConsumer``.

    Three branches under test (all green against the post-WAVE-F2-F1
    visibility contract — peer teachers are owned by F1, NOT this file):

      * anonymous → 4001
      * cross-tenant authenticated user → 4003
      * same-tenant creator → connect + receive a group_send event
    """

    # ``TransactionTestCase`` would normally TRUNCATE every table after
    # each test — but the project's schema has a ``attendance →
    # sections`` FK that PostgreSQL refuses to TRUNCATE without
    # ``CASCADE``, so the default flush errors out. Set ``available_apps``
    # to an empty list to skip the flush; ``setUp`` randomizes slugs +
    # subdomains + emails per-test so leaked rows never collide.
    available_apps = []

    # ``TransactionTestCase`` does NOT support ``setUpTestData`` (which
    # relies on the outer transaction); each test gets a fresh DB via
    # truncate, so build the fixture in ``setUp`` per-test instead. This
    # also means the worker thread spawned by ``database_sync_to_async``
    # CAN see the data — the test data is COMMITTED, not held in an
    # outer transaction the worker thread can't peek into.
    #
    # Slugs / subdomains / emails are randomized per-test so a previous
    # run that dirtied the test DB (e.g. failed before flush) doesn't
    # block a re-run with ``--reuse-db``.
    def setUp(self):
        super().setUp()
        import uuid
        from apps.tenants.models import Tenant
        from apps.users.models import User

        suffix = uuid.uuid4().hex[:8]

        # Tenant A + creator teacher (the classroom owner).
        self.tenant_a = Tenant.objects.create(
            name=f"MAIC WS School A {suffix}",
            slug=f"maic-ws-a-{suffix}",
            subdomain=f"maic-ws-a-{suffix}",
            email=f"ws-a-{suffix}@test.com",
            is_active=True,
            feature_maic=True,
        )
        self.creator = User.objects.create_user(
            email=f"creator-ws-{suffix}@test.com",
            password="testpass123",
            first_name="MAIC",
            last_name="Creator",
            tenant=self.tenant_a,
            role="TEACHER",
        )

        # Tenant B + admin (cross-tenant attacker).
        self.tenant_b = Tenant.objects.create(
            name=f"MAIC WS School B {suffix}",
            slug=f"maic-ws-b-{suffix}",
            subdomain=f"maic-ws-b-{suffix}",
            email=f"ws-b-{suffix}@test.com",
            is_active=True,
            feature_maic=True,
        )
        self.outsider = User.objects.create_user(
            email=f"outsider-ws-{suffix}@test.com",
            password="testpass123",
            first_name="Out",
            last_name="Sider",
            tenant=self.tenant_b,
            role="SCHOOL_ADMIN",
        )

        # Classroom in tenant A, owned by creator. Empty content is fine
        # for the connect/auth path — the consumer's visibility helper
        # only reads ``tenant_id`` + ``creator_id`` for these branches.
        self.classroom = MAICClassroom.objects.create(
            tenant=self.tenant_a,
            creator=self.creator,
            title="WAVE-F2-F2 connect fixture",
            topic="Test",
            status="READY",
            images_pending=False,
            content_scenes=[],
            content_meta={},
        )

    def tearDown(self):
        # ``available_apps = []`` skips the framework flush, so we MUST
        # delete the rows we created in ``setUp`` ourselves — otherwise
        # they leak into adjacent tests in the same file (e.g. those
        # using the shared ``tenant`` fixture from conftest, which has a
        # fixed slug ``test-school-fixture``) and cause spurious
        # ``IntegrityError: duplicate key value violates unique
        # constraint "tenants_slug_key"`` failures.
        try:
            # MAICClassroom uses TenantManager (auto-filter); use
            # all_objects to avoid the thread-local tenant gate, since
            # tests don't activate one.
            MAICClassroom.all_objects.filter(pk=self.classroom.pk).delete()
        except Exception:
            pass
        for user in (getattr(self, "creator", None), getattr(self, "outsider", None)):
            if user is not None:
                try:
                    user.delete()
                except Exception:
                    pass
        for tenant in (getattr(self, "tenant_a", None), getattr(self, "tenant_b", None)):
            if tenant is not None:
                try:
                    tenant.delete()
                except Exception:
                    pass
        super().tearDown()

    # ------------------------------------------------------------------
    # 1. Anonymous connection → close 4001.
    # ------------------------------------------------------------------
    def test_consumer_rejects_anonymous_connection_with_4001(self):
        """No ``Bearer.<jwt>`` subprotocol → handshake closes with 4001.

        Guards the ``user.is_anonymous`` branch in
        ``MAICClassroomConsumer.connect``. ``JWTAuthMiddleware`` falls
        through to ``AnonymousUser`` when no subprotocol is offered, and
        the consumer must reject the connection before any ``accept()``.
        """
        app = _build_maic_ws_app()

        async def run():
            communicator = WebsocketCommunicator(
                app,
                f"/ws/maic/classrooms/{self.classroom.id}/",
            )
            # No subprotocols passed → middleware sets AnonymousUser.
            result = await communicator.connect()
            await communicator.disconnect()
            return result

        connected, close_code = async_to_sync(run)()

        self.assertFalse(
            connected, ("anonymous connection should be rejected during the handshake")
        )
        self.assertEqual(
            close_code, 4001, (f"expected close code 4001 for anonymous, got {close_code!r}")
        )

    # ------------------------------------------------------------------
    # 2. Cross-tenant authenticated user → close 4003.
    # ------------------------------------------------------------------
    def test_consumer_rejects_cross_tenant_user_with_4003(self):
        """JWT for tenant B + classroom in tenant A → close 4003.

        Guards the cross-tenant branch of ``_user_can_view_classroom``:
        the classroom's ``tenant_id`` does NOT match the user's
        ``tenant_id`` and the user is NOT a SUPER_ADMIN, so the
        visibility check returns False and ``connect()`` closes with
        4003 BEFORE ``accept()`` is called.
        """
        subprotocol = _bearer_token_for(self.outsider)
        app = _build_maic_ws_app()

        async def run():
            communicator = WebsocketCommunicator(
                app,
                f"/ws/maic/classrooms/{self.classroom.id}/",
                subprotocols=[subprotocol],
            )
            result = await communicator.connect()
            await communicator.disconnect()
            return result

        connected, close_code = async_to_sync(run)()

        self.assertFalse(connected, ("cross-tenant user must not complete the WS handshake"))
        self.assertEqual(
            close_code, 4003, (f"expected close code 4003 for cross-tenant, got {close_code!r}")
        )

    # ------------------------------------------------------------------
    # 3. Same-tenant creator → connect + receive a group_send event.
    # ------------------------------------------------------------------
    def test_consumer_creator_receives_group_send_event(self):
        """Creator connects, then a ``group_send`` to the canonical
        ``maic_classroom_<uuid>`` group is delivered to the WS client
        as a ``{"type": "maic.image.task", ...}`` JSON frame.

        Asserts the full happy-path:
          * ``Bearer.<jwt>`` subprotocol is accepted (handshake completes,
            and the server echoes the chosen subprotocol back).
          * Consumer joins ``maic_classroom_group_name(classroom.id)``.
          * ``group_send`` with ``{"type": "maic.image.task", ...}``
            triggers the consumer's ``maic_image_task`` handler, which
            forwards the payload (minus the channel-layer ``type`` key,
            with a re-asserted public ``"type": "maic.image.task"``) to
            the client as JSON.
        """
        from channels.layers import get_channel_layer

        from apps.courses.maic_consumers import maic_classroom_group_name

        subprotocol = _bearer_token_for(self.creator)
        app = _build_maic_ws_app()

        sample_event = {
            "type": "maic.image.task",
            "classroom_id": str(self.classroom.id),
            "element_key": "0:0:0:img-creator-0",
            "status": "done",
            "src": "https://images.unsplash.com/photo-creator-recv",
            "updated_at": "2026-04-28T00:00:00Z",
        }

        async def run():
            communicator = WebsocketCommunicator(
                app,
                f"/ws/maic/classrooms/{self.classroom.id}/",
                subprotocols=[subprotocol],
            )
            connected, returned_subprotocol = await communicator.connect()
            try:
                assert connected is True, "creator must complete the WS handshake"
                assert returned_subprotocol == subprotocol, (
                    f"server must echo the Bearer.<jwt> subprotocol back, "
                    f"got {returned_subprotocol!r}"
                )

                # Inject a channel-layer event into the same group the
                # consumer joined — production code path uses the same
                # group name + payload shape via ``_broadcast_image_task``.
                layer = get_channel_layer()
                await layer.group_send(
                    maic_classroom_group_name(self.classroom.id),
                    sample_event,
                )

                received = await communicator.receive_json_from(timeout=2)
            finally:
                await communicator.disconnect()
            return received

        received = async_to_sync(run)()

        # The consumer strips the internal channel-layer ``type`` and
        # re-asserts the public ``"type": "maic.image.task"`` shape, then
        # forwards every other key to the client.
        self.assertEqual(received["type"], "maic.image.task", received)
        self.assertEqual(
            received["classroom_id"],
            str(self.classroom.id),
            received,
        )
        self.assertEqual(
            received["element_key"],
            "0:0:0:img-creator-0",
            received,
        )
        self.assertEqual(received["status"], "done", received)
        self.assertEqual(
            received["src"],
            "https://images.unsplash.com/photo-creator-recv",
            received,
        )
        self.assertEqual(
            received["updated_at"],
            "2026-04-28T00:00:00Z",
            received,
        )

    # ------------------------------------------------------------------
    # 4. WAVE-8-F3: production ASGI stack composition pin.
    # ------------------------------------------------------------------
    def test_production_asgi_stack_completes_handshake(self):
        """Pin the production ASGI layer composition.

        The other tests in this class build the WS app via
        ``_build_maic_ws_app()`` — i.e. ``JWTAuthMiddleware(URLRouter(...))``
        — which omits the outermost ``AllowedHostsOriginValidator`` layer
        present in ``config/asgi.py``. This test references the
        module-level ``_PROD_ASGI_APPLICATION`` (imported BEFORE
        ``available_apps = []`` restricts the app registry inside the
        TransactionTestCase) so that any future re-ordering of layers
        (or a missing ``JWTAuthMiddleware`` / ``URLRouter`` / courses
        websocket routes) breaks this test.

        Channels' ``WebsocketCommunicator`` does NOT synthesise an
        ``Origin`` header by default; the production
        ``AllowedHostsOriginValidator`` (which produces an
        ``OriginValidator`` instance bound to ``settings.ALLOWED_HOSTS``
        at the time ``config.asgi`` is imported) treats a missing
        ``Origin`` as INVALID and closes the handshake unless ``*`` is
        in the allowed list. Because the validator instance snapshots
        ``ALLOWED_HOSTS`` once at construction, this class's
        ``override_settings(ALLOWED_HOSTS=["*"])`` cannot relax it
        retroactively. The handshake half of this test therefore sends
        an explicit ``Origin: http://localhost`` header so the validator
        accepts the connection — the goal is to PIN layer composition
        AND prove a valid Origin survives every intermediate layer to
        reach the consumer's ``accept()``, not to exercise the negative
        rejection branch (the auth-rejection branches are covered by the
        sibling tests above using ``_build_maic_ws_app``).

        Asserts the outermost layer is ``AllowedHostsOriginValidator``
        wrapping ``JWTAuthMiddleware`` wrapping a ``URLRouter`` — so
        any change to the production stack ordering trips this test
        before it even attempts the handshake.
        """
        from channels.routing import URLRouter
        from channels.security.websocket import OriginValidator
        from apps.notifications.middleware import JWTAuthMiddleware

        asgi_application = _PROD_ASGI_APPLICATION

        # ----- 1. Layer-composition pin (cheap, runs before any I/O). -----
        # ``AllowedHostsOriginValidator`` is a factory that returns an
        # ``OriginValidator`` instance bound to ``settings.ALLOWED_HOSTS``,
        # so we check the runtime class.
        ws_app = asgi_application.application_mapping["websocket"]
        self.assertIsInstance(
            ws_app,
            OriginValidator,
            (
                "outermost websocket layer in config.asgi.application MUST be "
                "an OriginValidator (built by AllowedHostsOriginValidator); got "
                f"{type(ws_app).__name__}"
            ),
        )
        jwt_layer = ws_app.application
        self.assertIsInstance(
            jwt_layer,
            JWTAuthMiddleware,
            (
                "AllowedHostsOriginValidator MUST wrap JWTAuthMiddleware; got "
                f"{type(jwt_layer).__name__}"
            ),
        )
        inner = jwt_layer.inner
        self.assertIsInstance(
            inner,
            URLRouter,
            f"JWTAuthMiddleware MUST wrap URLRouter; got {type(inner).__name__}",
        )

        # ----- 2. End-to-end handshake against the production app. -----
        # ``AllowedHostsOriginValidator`` is a factory that reads
        # ``settings.ALLOWED_HOSTS`` ONCE — at the moment ``config.asgi``
        # constructs ``application`` (i.e. when this test module imported
        # ``_PROD_ASGI_APPLICATION`` at the top of the file) — and
        # passes the captured list into a fresh ``OriginValidator``
        # instance (see ``channels.security.websocket``). The instance
        # then stores ``allowed_origins`` as an attribute, so the class
        # decorator's ``override_settings(ALLOWED_HOSTS=["*"])`` does
        # NOT propagate into the already-built validator. We therefore
        # cannot relax the validator at test time; instead we must send
        # an ``Origin`` header that matches the snapshotted list, and
        # ``http://localhost`` is in the ALLOWED_HOSTS default for the
        # local test settings.
        subprotocol = _bearer_token_for(self.creator)
        headers = [(b"origin", b"http://localhost")]

        async def run():
            communicator = WebsocketCommunicator(
                asgi_application,
                f"/ws/maic/classrooms/{self.classroom.id}/",
                subprotocols=[subprotocol],
                headers=headers,
            )
            try:
                connected, returned_subprotocol = await communicator.connect()
            finally:
                await communicator.disconnect()
            return connected, returned_subprotocol

        connected, returned_subprotocol = async_to_sync(run)()

        self.assertTrue(
            connected,
            (
                "creator must complete the WS handshake against the production "
                "config.asgi.application (AllowedHostsOriginValidator → "
                "JWTAuthMiddleware → URLRouter → MAICClassroomConsumer); a "
                "failure here means a layer was reordered or removed"
            ),
        )
        self.assertEqual(
            returned_subprotocol,
            subprotocol,
            (
                "production stack must echo the Bearer.<jwt> subprotocol back, "
                f"got {returned_subprotocol!r} — this proves JWTAuthMiddleware "
                "ran inside the AllowedHostsOriginValidator wrapper"
            ),
        )


# ───────────── WAVE-F2-F1: tightened consumer visibility helper ──────────────
#
# The HTTP ``teacher_maic_classroom_detail`` gates on ``creator=request.user``
# but the WebSocket consumer's ``_user_can_view_classroom`` previously
# returned True for every same-tenant TEACHER / HOD / IB_COORDINATOR. A peer
# teacher who guessed a classroom UUID could subscribe to image-task
# transitions for content they did not own. These tests pin the new shared
# ``_can_view_classroom`` helper that BOTH paths now defer to.
#
# Coordination note for qa-tester (WAVE-F2-F2): the WebsocketCommunicator-based
# connect tests above (rejects-anonymous, rejects-cross-tenant, creator-receives)
# cover the handshake. The synchronous helper tests below cover the role-by-role
# visibility decision tree without spinning up an ASGI stack — together they
# pin the full surface.


@pytest.fixture
def school_admin_user_f2(db, tenant):
    from apps.users.models import User

    return User.objects.create_user(
        email="schooladmin-f2@testschool.com",
        password="AdminPass!123",
        first_name="Admin",
        last_name="F2",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


@pytest.fixture
def super_admin_user_f2(db, tenant):
    from apps.users.models import User

    return User.objects.create_user(
        email="superadmin-f2@learnpuddle.com",
        password="SuperAdmin!123",
        first_name="Super",
        last_name="F2",
        tenant=tenant,
        role="SUPER_ADMIN",
        is_active=True,
    )


@pytest.fixture
def peer_teacher_user_f2(db, tenant):
    """Second TEACHER in the SAME tenant — pins WAVE-F2-F1."""
    from apps.users.models import User

    return User.objects.create_user(
        email="peer-teacher-f2@testschool.com",
        password="TeacherPass!123",
        first_name="Peer",
        last_name="Teach",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def hod_user_f2(db, tenant):
    from apps.users.models import User

    return User.objects.create_user(
        email="hod-f2@testschool.com",
        password="HodPass!123",
        first_name="HOD",
        last_name="F2",
        tenant=tenant,
        role="HOD",
        is_active=True,
    )


@pytest.fixture
def teacher_user_b_f2(db, tenant_b):
    from apps.users.models import User

    return User.objects.create_user(
        email="teacher-b-f2@otherschool.com",
        password="TeacherPass!123",
        first_name="T",
        last_name="B",
        tenant=tenant_b,
        role="TEACHER",
        is_active=True,
    )


def test_consumer_rejects_peer_teacher_in_same_tenant(
    maic_enabled_tenant_f2,
    teacher_user,
    peer_teacher_user_f2,
):
    """WAVE-F2-F1 regression: a different teacher in the SAME tenant
    must NOT be able to view a classroom they did not create. The HTTP
    detail gate has always rejected this; the WS consumer used to allow
    any TEACHER / HOD / IB_COORDINATOR through.
    """
    from apps.courses.maic_views import _can_view_classroom

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)

    # Sanity: tenants match, role is TEACHER, only ``creator_id`` differs.
    assert peer_teacher_user_f2.tenant_id == classroom.tenant_id
    assert peer_teacher_user_f2.role == "TEACHER"
    assert classroom.creator_id != peer_teacher_user_f2.id

    assert _can_view_classroom(peer_teacher_user_f2, classroom) is False


def test_consumer_rejects_peer_hod_in_same_tenant(
    maic_enabled_tenant_f2,
    teacher_user,
    hod_user_f2,
):
    """Same as above but for HOD — the previous coarse allowlist
    treated HOD / IB_COORDINATOR as same-tenant allow. They shouldn't
    subscribe to a peer's image-task events.
    """
    from apps.courses.maic_views import _can_view_classroom

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    assert _can_view_classroom(hod_user_f2, classroom) is False


def test_consumer_allows_creator(
    maic_enabled_tenant_f2,
    teacher_user,
):
    """The user who created the classroom always sees their own work,
    matching the HTTP path's ``creator=request.user`` filter.
    """
    from apps.courses.maic_views import _can_view_classroom

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    assert _can_view_classroom(teacher_user, classroom) is True


def test_consumer_allows_school_admin(
    maic_enabled_tenant_f2,
    teacher_user,
    school_admin_user_f2,
):
    """SCHOOL_ADMIN in the same tenant has tenant-wide oversight."""
    from apps.courses.maic_views import _can_view_classroom

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    assert _can_view_classroom(school_admin_user_f2, classroom) is True


def test_consumer_allows_super_admin(
    maic_enabled_tenant_f2,
    teacher_user,
    super_admin_user_f2,
):
    """SUPER_ADMIN bypasses tenant scope entirely (platform-wide access)."""
    from apps.courses.maic_views import _can_view_classroom

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    assert _can_view_classroom(super_admin_user_f2, classroom) is True


def test_consumer_rejects_cross_tenant_user_helper(
    maic_enabled_tenant_f2,
    teacher_user,
    teacher_user_b_f2,
):
    """Existing cross-tenant rejection (pinned by the connect-path test
    above) MUST still pass under the refactored helper — a teacher in
    tenant_b can never view a classroom that lives in tenant_a,
    regardless of role.
    """
    from apps.courses.maic_views import _can_view_classroom

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    assert teacher_user_b_f2.tenant_id != classroom.tenant_id
    assert _can_view_classroom(teacher_user_b_f2, classroom) is False


def test_consumer_rejects_unknown_role_silently(
    maic_enabled_tenant_f2,
    teacher_user,
):
    """A user with an unknown role in the same tenant must be rejected —
    never fall through to allow.
    """
    from apps.courses.maic_views import _can_view_classroom
    from apps.users.models import User

    weird_user = User.objects.create_user(
        email="weird-f2@testschool.com",
        password="Weird!1234",
        first_name="W",
        last_name="W",
        tenant=maic_enabled_tenant_f2,
        role="UNKNOWN_ROLE",
        is_active=True,
    )
    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)
    assert _can_view_classroom(weird_user, classroom) is False


# ───────────── WAVE-F2-F3: orchestrator-style image-fill lock ────────────────
#
# ``_persist_image_task`` does a read-modify-write on
# ``content_image_tasks`` without a row lock. Two workers processing the
# same classroom (e.g. a deferred re-enqueue overlapping a retry from
# ``autoretry_for``, or a manual re-publish racing an in-flight task)
# both read+write that JSONField and the second writer can clobber the
# first writer's already-persisted transitions.
#
# The fix mirrors the SPRINT-2-BATCH-9-F2 / PERF-P0-5 pattern in
# ``pre_generate_classroom_tts``: a Django cache ``add`` SET-NX lock keyed
# on classroom_id, released in a ``finally`` block on every exit path.


def test_fill_classroom_images_orchestrator_lock_prevents_concurrent_runs(
    maic_enabled_tenant_f2,
    teacher_user,
):
    """Patch ``cache.add`` so the FIRST call returns True (acquire) and
    every subsequent call returns False (lock held). The second
    invocation must early-return with the documented shape and must NOT
    persist any image-task transitions of its own.
    """
    from apps.courses.maic_tasks import fill_classroom_images
    from apps.courses import maic_tasks as _mt

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)

    cache_add_calls = {"count": 0}

    def fake_cache_add(key, value, timeout=None):
        cache_add_calls["count"] += 1
        # First caller wins; everyone after sees lock_held.
        return cache_add_calls["count"] == 1

    real_persist = _mt._persist_image_task
    persist_calls: list[tuple] = []

    def tracking_persist(classroom_arg, key, status, **kw):
        persist_calls.append((key, status))
        return real_persist(classroom_arg, key, status, **kw)

    captured, patcher = _captured_broadcasts()

    with patcher, patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-lock",
    ), patch(
        "apps.courses.maic_tasks.cache.add",
        side_effect=fake_cache_add,
    ), patch(
        "apps.courses.maic_tasks._persist_image_task",
        side_effect=tracking_persist,
    ):
        # First run: acquires the lock and runs to completion.
        result_first = fill_classroom_images(str(classroom.id))
        first_persist_count = len(persist_calls)
        assert (
            first_persist_count > 0
        ), "first run should have persisted at least one transition, got 0"

        # Second run: lock held → early return, no persist calls added.
        result_second = fill_classroom_images(str(classroom.id))

    assert result_second == {
        "skipped": True,
        "reason": "lock_held",
    }, f"second invocation should report lock_held, got: {result_second}"
    assert len(persist_calls) == first_persist_count, (
        "second invocation must NOT have written any image-task "
        f"transitions; expected persist count to remain {first_persist_count}, "
        f"got {len(persist_calls)}"
    )
    # First run completed normally so it returned None (or a non-skip dict).
    assert result_first != {"skipped": True, "reason": "lock_held"}


def test_fill_classroom_images_releases_lock_on_normal_completion(
    maic_enabled_tenant_f2,
    teacher_user,
):
    """Happy path: the lock must be released in the ``finally`` block
    so a subsequent run is unblocked without waiting for the 600s TTL.
    """
    from apps.courses.maic_tasks import (
        _IMAGE_FILL_LOCK_KEY_TEMPLATE,
        fill_classroom_images,
    )

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)

    delete_calls: list[str] = []

    def fake_delete(key):
        delete_calls.append(key)
        return True

    captured, patcher = _captured_broadcasts()
    with patcher, patch(
        "apps.courses.image_service.fetch_scene_image",
        return_value="https://images.unsplash.com/photo-release",
    ), patch(
        "apps.courses.maic_tasks.cache.delete",
        side_effect=fake_delete,
    ):
        fill_classroom_images(str(classroom.id))

    expected_key = _IMAGE_FILL_LOCK_KEY_TEMPLATE.format(classroom_id=str(classroom.id))
    assert expected_key in delete_calls, (
        f"expected cache.delete({expected_key!r}) to be called on normal "
        f"completion, got: {delete_calls}"
    )


def test_fill_classroom_images_releases_lock_on_exception(
    maic_enabled_tenant_f2,
    teacher_user,
):
    """When the inner walker raises, the outer ``finally`` block must
    still call ``cache.delete(lock_key)`` so a retry isn't blocked by
    the TTL.
    """
    from apps.courses.maic_tasks import (
        _IMAGE_FILL_LOCK_KEY_TEMPLATE,
        fill_classroom_images,
    )

    classroom = _classroom_with_two_images(maic_enabled_tenant_f2, teacher_user)

    delete_calls: list[str] = []

    def fake_delete(key):
        delete_calls.append(key)
        return True

    # Force the enumerator to blow up so we exit through the except → raise
    # path. The fail-open recovery branch will run, then the finally will
    # release the lock and re-raise.
    with patch(
        "apps.courses.maic_tasks._enumerate_image_elements",
        side_effect=RuntimeError("boom"),
    ), patch(
        "apps.courses.maic_tasks.cache.delete",
        side_effect=fake_delete,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            fill_classroom_images(str(classroom.id))

    expected_key = _IMAGE_FILL_LOCK_KEY_TEMPLATE.format(classroom_id=str(classroom.id))
    assert expected_key in delete_calls, (
        f"expected cache.delete({expected_key!r}) to be called via the "
        f"finally block when the inner walker raises, got: {delete_calls}"
    )
