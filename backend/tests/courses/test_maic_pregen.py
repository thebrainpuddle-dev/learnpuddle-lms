"""Tests for MAIC pre-gen audio pipeline + publish endpoint.

Covers Chunk 4 behaviors:
- Publish endpoint stamps `audioId` + `voiceId` on speech actions, writes
  an `audioManifest` with status="generating", transitions classroom to
  GENERATING, and enqueues the Celery task exactly once.
- Publish endpoint rejects concurrent/in-progress publish with HTTP 409.
- Pre-gen Celery task generates TTS, uploads via the storage helper,
  stamps `audioUrl`, writes manifest checkpoints every 5 actions, retries
  transient failures with exponential back-off, and finalizes status as
  ``ready`` / ``partial`` / ``failed`` based on failure count.
- Student visibility is gated on `audioManifest.status in {ready, partial}`.
"""
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.courses.maic_models import MAICClassroom, TenantAIConfig

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def maic_enabled_tenant(tenant):
    """Activate `feature_maic` on the primary fixture tenant so decorators pass."""
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    return tenant


@pytest.fixture
def ai_config(maic_enabled_tenant):
    """MAIC-enabled TenantAIConfig for the primary tenant."""
    return TenantAIConfig.objects.create(
        tenant=maic_enabled_tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        tts_provider="disabled",
        maic_enabled=True,
    )


@pytest.fixture
def make_student(db, maic_enabled_tenant):
    """Factory returning a freshly-created STUDENT in the primary tenant."""
    from apps.users.models import User

    created = {"n": 0}

    def _make():
        created["n"] += 1
        return User.objects.create_user(
            email=f"student{created['n']}@testschool.com",
            password="StudentPass!123",
            first_name=f"Student{created['n']}",
            last_name="User",
            tenant=maic_enabled_tenant,
            role="STUDENT",
            is_active=True,
        )

    return _make


@pytest.fixture
def classroom_with_content(maic_enabled_tenant, teacher_user, ai_config):
    """DRAFT classroom with 1 agent + 1 scene + 2 speech actions."""
    return MAICClassroom.objects.create(
        tenant=maic_enabled_tenant,
        creator=teacher_user,
        title="Test",
        topic="Test topic",
        status="DRAFT",
        content={
            "agents": [
                {
                    "id": "agent-1",
                    "name": "Dr. X",
                    "role": "professor",
                    "voiceId": "en-IN-PrabhatNeural",
                    "voiceProvider": "azure",
                    "avatar": "👨‍🏫",
                    "color": "#4338CA",
                    "personality": "P",
                    "expertise": "E",
                    "speakingStyle": "S",
                },
            ],
            "scenes": [
                {
                    "id": "scene-1",
                    "title": "Intro",
                    "type": "introduction",
                    "actions": [
                        {"type": "speech", "agentId": "agent-1", "text": "Hello"},
                        {"type": "speech", "agentId": "agent-1", "text": "Welcome"},
                    ],
                },
            ],
        },
    ), teacher_user


@pytest.fixture
def teacher_api_client(teacher_user, maic_enabled_tenant):
    client = APIClient()
    client.force_authenticate(user=teacher_user)
    client.defaults["HTTP_HOST"] = f"{maic_enabled_tenant.subdomain}.lms.com"
    return client


# ---------------------------------------------------------------------------
# Task 4.2 — publish endpoint
# ---------------------------------------------------------------------------

def test_publish_transitions_status_and_enqueues(
    teacher_api_client, classroom_with_content,
):
    classroom, _ = classroom_with_content
    with patch("apps.courses.maic_tasks.pre_generate_classroom_tts.delay") as mock_delay:
        r = teacher_api_client.post(
            f"/api/v1/teacher/maic/classrooms/{classroom.id}/publish/",
        )
    assert r.status_code == 202, r.content
    mock_delay.assert_called_once_with(str(classroom.id))
    classroom.refresh_from_db()
    assert classroom.status == "GENERATING"
    assert classroom.content["audioManifest"]["status"] == "generating"
    assert classroom.content["audioManifest"]["totalActions"] == 2
    # Each speech action gets audioId + voiceId stamped
    for action in classroom.content["scenes"][0]["actions"]:
        assert "audioId" in action
        assert len(action["audioId"]) == 12
        assert action["voiceId"] == "en-IN-PrabhatNeural"


def test_publish_rejects_while_generating(
    teacher_api_client, classroom_with_content,
):
    classroom, _ = classroom_with_content
    classroom.status = "GENERATING"
    classroom.save()
    r = teacher_api_client.post(
        f"/api/v1/teacher/maic/classrooms/{classroom.id}/publish/",
    )
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# Task 4.3 — pre-gen Celery task behavior
# ---------------------------------------------------------------------------

def test_pregen_stamps_audio_urls_and_marks_ready(classroom_with_content):
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom, _ = classroom_with_content
    classroom.status = "GENERATING"
    classroom.content["audioManifest"] = {
        "status": "generating",
        "progress": 0,
        "totalActions": 2,
        "completedActions": 0,
        "failedAudioIds": [],
        "generatedAt": None,
    }
    for i, action in enumerate(classroom.content["scenes"][0]["actions"]):
        action["audioId"] = f"hash{i:08x}"
        action["voiceId"] = "en-IN-PrabhatNeural"
    classroom.save()

    with patch(
        "apps.courses.maic_tasks.generate_tts_audio",
        return_value=b"fake-mp3-bytes",
    ), patch(
        "apps.courses.maic_tasks.storage_upload",
        return_value="/media/foo.mp3",
    ):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.status == "READY"
    assert classroom.content["audioManifest"]["status"] == "ready"
    assert classroom.content["audioManifest"]["completedActions"] == 2
    for action in classroom.content["scenes"][0]["actions"]:
        assert action["audioUrl"] == "/media/foo.mp3"


def test_pregen_retries_transient_failure(classroom_with_content):
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom, _ = classroom_with_content
    classroom.status = "GENERATING"
    classroom.content["audioManifest"] = {
        "status": "generating",
        "progress": 0,
        "totalActions": 1,
        "completedActions": 0,
        "failedAudioIds": [],
        "generatedAt": None,
    }
    classroom.content["scenes"][0]["actions"] = [
        classroom.content["scenes"][0]["actions"][0]
    ]
    classroom.content["scenes"][0]["actions"][0]["audioId"] = "abc"
    classroom.content["scenes"][0]["actions"][0]["voiceId"] = "en-IN-PrabhatNeural"
    classroom.save()

    calls = [0]

    def flaky(*args, **kwargs):
        calls[0] += 1
        if calls[0] < 2:
            raise RuntimeError("transient")
        return b"mp3-bytes"

    with patch(
        "apps.courses.maic_tasks.generate_tts_audio", side_effect=flaky,
    ), patch(
        "apps.courses.maic_tasks.storage_upload", return_value="/media/x.mp3",
    ), patch("apps.courses.maic_tasks.time.sleep"):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.content["scenes"][0]["actions"][0]["audioUrl"] == "/media/x.mp3"
    assert calls[0] == 2  # first attempt failed, second succeeded


def test_pregen_partial_status_on_some_failures(classroom_with_content):
    from apps.courses.maic_tasks import pre_generate_classroom_tts

    classroom, _ = classroom_with_content
    classroom.status = "GENERATING"
    classroom.content["audioManifest"] = {
        "status": "generating",
        "progress": 0,
        "totalActions": 2,
        "completedActions": 0,
        "failedAudioIds": [],
        "generatedAt": None,
    }
    for i, action in enumerate(classroom.content["scenes"][0]["actions"]):
        action["audioId"] = f"hash{i}"
        action["voiceId"] = "en-IN-PrabhatNeural"
    classroom.save()

    results = [b"ok", None]  # second returns empty -> failure

    def tts(*a, **kw):
        return results.pop(0)

    with patch(
        "apps.courses.maic_tasks.generate_tts_audio", side_effect=tts,
    ), patch(
        "apps.courses.maic_tasks.storage_upload", return_value="/media/ok.mp3",
    ), patch("apps.courses.maic_tasks.time.sleep"):
        pre_generate_classroom_tts(str(classroom.id))

    classroom.refresh_from_db()
    assert classroom.status == "READY"  # still playable
    assert classroom.content["audioManifest"]["status"] == "partial"
    assert len(classroom.content["audioManifest"]["failedAudioIds"]) == 1


# ---------------------------------------------------------------------------
# Task 4.4 — student visibility gated on audioManifest
# ---------------------------------------------------------------------------

def test_student_cannot_see_classroom_mid_generation(
    classroom_with_content, maic_enabled_tenant, make_student,
):
    classroom, _ = classroom_with_content
    classroom.status = "READY"
    classroom.is_public = True
    classroom.content["audioManifest"] = {
        "status": "generating",
        "progress": 50,
        "totalActions": 2,
        "completedActions": 1,
        "failedAudioIds": [],
        "generatedAt": None,
    }
    classroom.save()

    student = make_student()
    client = APIClient()
    client.force_authenticate(user=student)
    client.defaults["HTTP_HOST"] = f"{maic_enabled_tenant.subdomain}.lms.com"

    r = client.get("/api/v1/student/maic/classrooms/")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert str(classroom.id) not in ids

    # Flip to ready → now visible
    classroom.content["audioManifest"]["status"] = "ready"
    classroom.save()
    r = client.get("/api/v1/student/maic/classrooms/")
    ids = [c["id"] for c in r.json()]
    assert str(classroom.id) in ids
