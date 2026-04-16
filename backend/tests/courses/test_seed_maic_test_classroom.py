"""Tests for the ``seed_maic_test_classroom`` management command.

These tests guard the shape of the seed fixture used by e2e tests — if the
seed diverges from the contract the student player expects (speech actions
with ``audioId`` + ``audioUrl``, ``audioManifest.status == "ready"``, etc.),
e2e suites silently break.
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

    teacher = User.objects.get(email="teacher@demo.test")
    assert teacher.role == "TEACHER"
    assert teacher.tenant_id == tenant.id
    assert teacher.check_password("demo1234")

    student = User.objects.get(email="student@demo.test")
    assert student.role == "STUDENT"
    assert student.tenant_id == tenant.id
    assert student.check_password("demo1234")

    ai_config = TenantAIConfig.objects.get(tenant=tenant)
    assert ai_config.maic_enabled is True
    assert ai_config.tts_provider == "azure"

    classroom = MAICClassroom.objects.all_tenants().get(
        tenant=tenant, title="E2E Demo Classroom"
    )
    assert classroom.status == "READY"
    assert classroom.is_public is True
    assert classroom.creator_id == teacher.id

    content = classroom.content
    manifest = content["audioManifest"]
    assert manifest["status"] == "ready"
    assert manifest["completedActions"] == manifest["totalActions"]
    assert manifest["failedAudioIds"] == []

    # At least 5 speech actions with audioId + fake audioUrl
    speech_actions = [
        a for a in content["scenes"][0]["actions"] if a.get("type") == "speech"
    ]
    assert len(speech_actions) >= 5
    for action in speech_actions:
        assert action["audioId"]
        assert action["audioUrl"].startswith("/media/fixt")
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
    assert User.objects.filter(email="teacher@demo.test").count() == 1
    assert User.objects.filter(email="student@demo.test").count() == 1
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
