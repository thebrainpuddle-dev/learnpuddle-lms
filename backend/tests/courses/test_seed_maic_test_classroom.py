"""Tests for the ``seed_maic_test_classroom`` management command.

These tests guard the shape of the seed fixture used by e2e tests. The seed
must use the current sharded MAIC schema and must not stamp fake audio URLs;
the browser should exercise the real live-TTS path when pre-generated audio is
not available.
"""
from io import StringIO

import pytest
from django.core.management import call_command

from apps.courses.maic_models import MAICClassroom, TenantAIConfig
from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db


def _run(*args: str) -> str:
    out = StringIO()
    call_command("seed_maic_test_classroom", *args, stdout=out)
    return out.getvalue()


def test_seed_creates_tenant_users_and_classroom():
    output = _run()

    tenant = Tenant.objects.get(subdomain="demo")
    assert tenant.feature_maic is True
    assert tenant.feature_students is True

    teacher = User.objects.get(email="teacher@demo.learnpuddle.com")
    assert teacher.role == "TEACHER"
    assert teacher.tenant_id == tenant.id
    assert teacher.check_password("Teacher@123")

    student = User.objects.get(email="student@demo.learnpuddle.com")
    assert student.role == "STUDENT"
    assert student.tenant_id == tenant.id
    assert student.check_password("Student@123")

    ai_config = TenantAIConfig.objects.get(tenant=tenant)
    assert ai_config.maic_enabled is True
    assert ai_config.tts_provider == "edge"

    classroom = MAICClassroom.objects.all_tenants().get(
        tenant=tenant, title="E2E Demo Classroom"
    )
    assert classroom.status == "READY"
    assert classroom.is_public is True
    assert classroom.creator_id == teacher.id

    assert classroom.content == {}
    assert len(classroom.content_scenes) == 1
    assert len(classroom.content_agents) == 1
    assert "slides" in classroom.content_meta

    content = classroom.composed_content
    manifest = content["audioManifest"]
    assert manifest["status"] == "partial"
    assert manifest["completedActions"] == 0
    assert manifest["totalActions"] >= 5
    assert manifest["failedAudioIds"] == []

    assert len(content["slides"]) >= 5
    assert content["sceneSlideBounds"] == [
        {"sceneIdx": 0, "startSlide": 0, "endSlide": len(content["slides"]) - 1}
    ]

    # At least 5 speech actions with stable IDs and no fake audio URL.
    speech_actions = [
        a for a in content["scenes"][0]["actions"] if a.get("type") == "speech"
    ]
    assert len(speech_actions) >= 5
    for action in speech_actions:
        assert action["audioId"]
        assert "audioUrl" not in action
        assert action["voiceId"] == "en-IN-PrabhatNeural"

    # And at least one transition action
    transitions = [
        a for a in content["scenes"][0]["actions"] if a.get("type") == "transition"
    ]
    assert len(transitions) >= 1

    # The command should announce the classroom in stdout
    assert "E2E Demo Classroom" in output
    assert str(classroom.id) in output


def test_seed_is_idempotent():
    _run()
    _run()

    # Exactly one tenant, one teacher, one student, one classroom
    assert Tenant.objects.filter(subdomain="demo").count() == 1
    assert User.objects.filter(email="teacher@demo.learnpuddle.com").count() == 1
    assert User.objects.filter(email="student@demo.learnpuddle.com").count() == 1
    assert (
        MAICClassroom.objects.all_tenants()
        .filter(title="E2E Demo Classroom")
        .count()
        == 1
    )


def test_seed_reset_deletes_existing_classroom():
    _run()
    first = MAICClassroom.objects.all_tenants().get(title="E2E Demo Classroom")

    _run("--reset")
    second = MAICClassroom.objects.all_tenants().get(title="E2E Demo Classroom")

    # Reset recreates the row, so the UUID should have changed.
    assert first.id != second.id
    # Still exactly one row after reset.
    assert (
        MAICClassroom.objects.all_tenants()
        .filter(title="E2E Demo Classroom")
        .count()
        == 1
    )
