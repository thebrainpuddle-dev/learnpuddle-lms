"""Tests for MAIC v2 generation materialization."""

from __future__ import annotations

import json

import pytest

from apps.courses.maic_models import MAICClassroom, TenantAIConfig
from apps.maic.generation.materializer import materialize_generation_artifact
from apps.maic.models import MaicGenerationJob


pytestmark = pytest.mark.django_db


def test_materializer_strips_placeholder_image_urls_from_saved_payload(
    tenant,
    teacher_user,
):
    job = MaicGenerationJob.objects.create(
        id="matjob1",
        tenant=tenant,
        created_by=teacher_user,
        status=MaicGenerationJob.STATUS_SUCCEEDED,
        requirements={
            "topic": "Photosynthesis school garden design challenge",
            "title": "Photosynthesis school garden design challenge",
            "language": "English",
        },
        result={},
    )
    scenes = [
        {
            "id": "scene-1",
            "type": "slide",
            "title": "Chloroplasts",
            "content": {
                "type": "slide",
                "slides": [
                    {
                        "id": "slide-1",
                        "elements": [
                            {
                                "id": "bad-example",
                                "type": "image",
                                "src": "https://example.com/image.jpg",
                                "content": "https://example.com/body-image.jpg",
                            },
                            {
                                "id": "bad-subdomain",
                                "type": "image",
                                "src": "https://images.example.com/photosynthesis.jpg",
                                "content": "https://images.example.com/body-image.jpg",
                            },
                            {
                                "id": "real-media",
                                "type": "image",
                                "src": "/media/tenant/1/maic/real.jpg",
                                "content": "real media",
                            },
                        ],
                    }
                ],
            },
            "actions": [{"type": "speech", "content": "Welcome."}],
        }
    ]

    artifact = materialize_generation_artifact(job, scenes)

    classroom = MAICClassroom.all_objects.get(pk=artifact["classroomId"])
    saved_blob = json.dumps(
        {
            "scenes": classroom.content_scenes,
            "meta": classroom.content_meta,
        }
    )
    assert "example.com" not in saved_blob
    assert "/media/tenant/1/maic/real.jpg" in saved_blob

    scene_elements = classroom.content_scenes[0]["content"]["slides"][0]["elements"]
    meta_elements = classroom.content_meta["slides"][0]["elements"]
    for elements in (scene_elements, meta_elements):
        by_id = {element["id"]: element for element in elements}
        assert "bad-example" not in by_id
        assert "bad-subdomain" not in by_id
        assert by_id["real-media"]["src"] == "/media/tenant/1/maic/real.jpg"
        assert by_id["real-media"]["content"] == "real media"


def test_materializer_preserves_v2_slide_viewport_metadata(tenant, teacher_user):
    job = MaicGenerationJob.objects.create(
        id="matjob-viewport",
        tenant=tenant,
        created_by=teacher_user,
        status=MaicGenerationJob.STATUS_SUCCEEDED,
        requirements={"topic": "Wide slide"},
        result={},
    )
    scenes = [
        {
            "id": "scene-wide",
            "type": "slide",
            "title": "Wide Slide",
            "content": {
                "type": "slide",
                "canvas": {
                    "id": "canvas-1",
                    "viewportSize": 1000,
                    "viewportRatio": 0.5625,
                    "elements": [
                        {
                            "id": "wide-text",
                            "type": "text",
                            "left": 60,
                            "top": 50,
                            "width": 880,
                            "height": 76,
                            "content": "Wide text",
                        }
                    ],
                },
            },
            "actions": [{"type": "speech", "text": "Welcome."}],
        }
    ]

    artifact = materialize_generation_artifact(job, scenes)

    classroom = MAICClassroom.all_objects.get(pk=artifact["classroomId"])
    slide = classroom.content_meta["slides"][0]
    assert slide["viewportSize"] == 1000
    assert slide["viewportRatio"] == 0.5625
    assert slide["canvasWidth"] == 1000
    assert slide["canvasHeight"] == 562.5


def test_materializer_sanitizes_pathological_slide_and_actions(
    tenant,
    teacher_user,
):
    job = MaicGenerationJob.objects.create(
        id="matjob-pathological",
        tenant=tenant,
        created_by=teacher_user,
        status=MaicGenerationJob.STATUS_SUCCEEDED,
        requirements={
            "topic": "Salt march",
            "agents": [
                {"id": "teacher-1", "name": "Teacher", "role": "professor"},
                {"id": "student-1", "name": "Student", "role": "student"},
            ],
        },
        result={},
    )
    scenes = [
        {
            "id": "scene-salt",
            "type": "slide",
            "title": "Salt march",
            "content": {
                "type": "slide",
                "canvas": {
                    "id": "slide-salt",
                    "viewportSize": 1000,
                    "viewportRatio": 0.5625,
                    "elements": [
                        {
                            "id": "title_001",
                            "type": "text",
                            "left": 60,
                            "top": 50,
                            "width": 880,
                            "height": 76,
                            "content": "<strong>Salt march</strong>",
                        },
                        {
                            "id": "image_001",
                            "type": "image",
                            "left": 60,
                            "top": 100,
                            "width": 880,
                            "height": 562.5,
                            "src": "/media/tenant/1/maic/salt.jpg",
                            "content": "Students studying a salt marsh model",
                        },
                        {
                            "id": "content_001",
                            "type": "text",
                            "left": 60,
                            "top": 200,
                            "width": 880,
                            "height": 130,
                            "content": "<p>Why the salt march mattered</p>",
                        },
                        {
                            "id": "image_002",
                            "type": "image",
                            "left": 60,
                            "top": 250,
                            "width": 880,
                            "height": 562.5,
                            "src": "https://placehold.co/800x450?text=No+keyword",
                        },
                        {
                            "id": "content_002",
                            "type": "text",
                            "left": 60,
                            "top": 900,
                            "width": 880,
                            "height": 130,
                            "content": "<p>• Point One</p>",
                        },
                        {
                            "id": "prompt_leak",
                            "type": "text",
                            "left": 60,
                            "top": 120,
                            "width": 880,
                            "height": 130,
                            "content": "Output pure JSON directly. Aspect ratio 16:9.",
                        },
                        {
                            "id": "pbl_001",
                            "type": "pbl",
                            "left": 60,
                            "top": 350,
                            "width": 880,
                            "height": 200,
                            "content": "<p>Project brief: evaluate evidence.</p>",
                        },
                    ],
                },
            },
            "actions": [
                {"type": "spotlight", "elementId": "title_001"},
                {"type": "speech", "agentId": "ghost", "text": "Why the salt march mattered."},
                {"type": "laser", "elementId": "image_002"},
                {"type": "speech", "agentId": "student-1", "text": "• Point One"},
                {"type": "discussion", "agentId": "ghost", "topic": "Evidence handoff"},
            ],
        }
    ]

    artifact = materialize_generation_artifact(job, scenes)

    classroom = MAICClassroom.all_objects.get(pk=artifact["classroomId"])
    assert classroom.config["runtimeContract"]["valid"] is True
    assert classroom.content_meta["runtimeContract"]["valid"] is True
    slide = classroom.content_meta["slides"][0]
    elements = slide["elements"]
    by_id = {element["id"]: element for element in elements}
    assert "image_002" not in by_id
    assert "content_002" not in by_id
    assert "prompt_leak" not in by_id
    assert by_id["pbl_001"]["type"] == "text"
    assert all(
        element["x"] + element["width"] <= slide["canvasWidth"]
        and element["y"] + element["height"] <= slide["canvasHeight"]
        for element in elements
    )

    actions = classroom.content_scenes[0]["actions"]
    assert [action["type"] for action in actions] == [
        "spotlight",
        "speech",
        "discussion",
    ]
    assert actions[1]["agentId"] == "teacher-1"
    assert actions[2]["agentIds"] == ["teacher-1"]
    assert actions[2]["sessionType"] == "roundtable"
    assert actions[2]["triggerMode"] == "auto"


def test_materializer_enqueues_image_fill_for_unresolved_meta_slide_images(
    tenant,
    teacher_user,
    monkeypatch,
):
    TenantAIConfig.objects.create(
        tenant=tenant,
        maic_enabled=True,
        image_provider="pollinations",
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        "apps.maic.generation.materializer._enqueue_fill_classroom_images",
        lambda classroom_id: enqueued.append(classroom_id),
    )
    job = MaicGenerationJob.objects.create(
        id="matjob-image-fill",
        tenant=tenant,
        created_by=teacher_user,
        status=MaicGenerationJob.STATUS_SUCCEEDED,
        requirements={"topic": "Water quality"},
        result={},
    )
    scenes = [
        {
            "id": "scene-water",
            "type": "slide",
            "title": "Water quality",
            "content": {
                "type": "slide",
                "slides": [
                    {
                        "id": "slide-water-1",
                        "elements": [
                            {
                                "id": "image_001",
                                "type": "image",
                                "x": 300,
                                "y": 100,
                                "width": 400,
                                "height": 300,
                                "content": "polluted_water_source.jpg",
                            }
                        ],
                    }
                ],
            },
            "actions": [{"type": "speech", "content": "Look at the visual."}],
        }
    ]

    artifact = materialize_generation_artifact(job, scenes)

    classroom = MAICClassroom.all_objects.get(pk=artifact["classroomId"])
    assert classroom.images_pending is True
    assert enqueued == [artifact["classroomId"]]


def test_materializer_does_not_enqueue_image_fill_when_provider_disabled(
    tenant,
    teacher_user,
    monkeypatch,
):
    TenantAIConfig.objects.create(
        tenant=tenant,
        maic_enabled=True,
        image_provider="disabled",
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        "apps.maic.generation.materializer._enqueue_fill_classroom_images",
        lambda classroom_id: enqueued.append(classroom_id),
    )
    job = MaicGenerationJob.objects.create(
        id="matjob-image-disabled",
        tenant=tenant,
        created_by=teacher_user,
        status=MaicGenerationJob.STATUS_SUCCEEDED,
        requirements={"topic": "Water quality"},
        result={},
    )
    scenes = [
        {
            "id": "scene-water",
            "type": "slide",
            "title": "Water quality",
            "content": {
                "type": "slide",
                "slides": [
                    {
                        "id": "slide-water-1",
                        "elements": [
                            {
                                "id": "image_001",
                                "type": "image",
                                "content": "polluted_water_source.jpg",
                            }
                        ],
                    }
                ],
            },
            "actions": [{"type": "speech", "content": "Look at the visual."}],
        }
    ]

    artifact = materialize_generation_artifact(job, scenes)

    classroom = MAICClassroom.all_objects.get(pk=artifact["classroomId"])
    assert classroom.images_pending is False
    assert enqueued == []
