from __future__ import annotations

import pytest


pytestmark = pytest.mark.django_db


def _make_classroom(tenant, teacher_user, **overrides):
    from apps.courses.maic_models import MAICClassroom

    payload = {
        "tenant": tenant,
        "creator": teacher_user,
        "title": "Integrity Regression Classroom",
        "topic": "Neural networks",
        "status": "READY",
        "scene_count": 6,
        "estimated_minutes": 25,
        "content_scenes": [],
        "content_meta": {},
    }
    payload.update(overrides)
    return MAICClassroom.objects.create(**payload)


def _enable_maic(tenant):
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    return tenant


def test_teacher_list_marks_ready_classroom_without_saved_content_as_failed(
    tenant,
    teacher_user,
    teacher_client,
):
    _enable_maic(tenant)
    classroom = _make_classroom(
        tenant,
        teacher_user,
        title="READY shell with no content",
    )

    resp = teacher_client.get("/api/v1/teacher/maic/classrooms/")

    assert resp.status_code == 200, resp.content
    item = next(row for row in resp.json() if row["id"] == str(classroom.id))
    assert item["status"] == "FAILED"
    assert item["scene_count"] == 0
    assert item["estimated_minutes"] == 0
    assert "no generated scenes or slides" in item["error_message"]


def test_teacher_detail_marks_ready_classroom_without_saved_content_as_failed(
    tenant,
    teacher_user,
    teacher_client,
):
    _enable_maic(tenant)
    classroom = _make_classroom(tenant, teacher_user)

    resp = teacher_client.get(f"/api/v1/teacher/maic/classrooms/{classroom.id}/")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["scene_count"] == 0
    assert body["estimated_minutes"] == 0
    assert "no generated scenes or slides" in body["error_message"]


def test_teacher_detail_keeps_ready_status_when_scenes_and_slides_are_saved(
    tenant,
    teacher_user,
    teacher_client,
):
    _enable_maic(tenant)
    classroom = _make_classroom(
        tenant,
        teacher_user,
        title="READY classroom with content",
        content_scenes=[{"id": "scene-1", "slides": [{"id": "slide-1"}]}],
        content_meta={
            "slides": [{"id": "slide-1", "sceneId": "scene-1"}],
            "audioManifest": {"status": "ready"},
        },
    )

    resp = teacher_client.get(f"/api/v1/teacher/maic/classrooms/{classroom.id}/")

    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["status"] == "READY"
    assert body["scene_count"] == 6
    assert body["estimated_minutes"] == 25
    assert body["error_message"] == ""
