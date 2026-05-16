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
    # 2026-05-16: PR #41 Codex review expanded the seed to ship three
    # deterministic scenes (base slide bundle, image slide, PBL scene) so
    # acceptance tests for image-element render and PBL flow stop silently
    # skipping. See backend/apps/courses/demo_maic_seed.py
    # `build_demo_maic_content`. The 3-scene contract is canonical now —
    # do NOT shrink the seed to make this test smaller; widen the test.
    assert len(classroom.content_scenes) == 3
    scene_types = [s["type"] for s in classroom.content_scenes]
    assert scene_types == ["slide", "slide", "pbl"], (
        f"unexpected scene shape: {scene_types}"
    )
    assert len(classroom.content_agents) == 1
    assert "slides" in classroom.content_meta

    content = classroom.composed_content
    manifest = content["audioManifest"]
    assert manifest["status"] == "partial"
    assert manifest["completedActions"] == 0
    # Five speech actions on scene-1 (original bundle) + one on scene-2
    # (image slide narration). PBL scene has no speech actions of its own.
    assert manifest["totalActions"] >= 6
    assert manifest["failedAudioIds"] == []

    # Six slides total: five from the original bundle + one for the image
    # scene. PBL is sceneless from a slide-bounds perspective.
    assert len(content["slides"]) >= 6
    bounds = content["sceneSlideBounds"]
    assert len(bounds) == 3
    # Scene 0 covers slides 0..N-2 (everything except the image slide
    # which belongs to scene 1).
    assert bounds[0]["sceneIdx"] == 0
    assert bounds[0]["startSlide"] == 0
    assert bounds[0]["endSlide"] == len(content["slides"]) - 2
    # Scene 1 (image slide) covers exactly the last slide.
    assert bounds[1]["sceneIdx"] == 1
    assert bounds[1]["startSlide"] == len(content["slides"]) - 1
    assert bounds[1]["endSlide"] == len(content["slides"]) - 1
    # Scene 2 (PBL) has no own slides; its bound entry tracks the prior
    # slide so a stale currentSlideIndex during transit resolves
    # sensibly. The exact value is the image slide index.
    assert bounds[2]["sceneIdx"] == 2

    # Scene 1 (original bundle) carries the original ≥5 speech actions.
    speech_actions = [
        a for a in content["scenes"][0]["actions"] if a.get("type") == "speech"
    ]
    assert len(speech_actions) >= 5
    for action in speech_actions:
        assert action["audioId"]
        assert "audioUrl" not in action
        assert action["voiceId"] == "en-IN-PrabhatNeural"

    # And at least one transition action on scene 0
    transitions = [
        a for a in content["scenes"][0]["actions"] if a.get("type") == "transition"
    ]
    assert len(transitions) >= 1

    # Scene 2 (image slide) carries at least one speech action so the
    # player has narration on the image-render scene too.
    image_scene_speech = [
        a for a in content["scenes"][1]["actions"] if a.get("type") == "speech"
    ]
    assert len(image_scene_speech) >= 1
    for action in image_scene_speech:
        assert action["audioId"]
        assert "audioUrl" not in action
        assert action["voiceId"] == "en-IN-PrabhatNeural"

    # The image slide must carry a real <image> element with a non-empty,
    # non-placeholder src — this is the seed fixture the Playwright
    # "image element renders" assertion in maic-full-playback.spec.js
    # depends on.
    image_scene_elements = content["scenes"][1]["content"]["elements"]
    image_elements = [e for e in image_scene_elements if e.get("type") == "image"]
    assert len(image_elements) >= 1
    for img in image_elements:
        src = img.get("src", "")
        assert src, "image element src must be non-empty"
        assert not src.startswith("gen_img_"), (
            f"image element src must not be an unresolved placeholder: {src!r}"
        )
        assert not src.startswith("gen_vid_"), (
            f"image element src must not be an unresolved placeholder: {src!r}"
        )

    # Scene 3 (PBL) must carry a real PBLProjectConfig that parses against
    # the upstream-mirrored Pydantic types. Pinned so a future seed
    # regression (drop a required field, change a literal) surfaces here
    # rather than as a silent E2E failure.
    from apps.maic_pbl.types import PBLProjectConfig
    pbl_scene = content["scenes"][2]
    project_config_dict = pbl_scene["content"]["projectConfig"]
    parsed = PBLProjectConfig.model_validate(project_config_dict)
    # At least one selectable (development, non-system) role so the role
    # panel in PBLRenderer renders.
    selectable = [a for a in parsed.agents if a.is_user_role and not a.is_system_agent]
    assert len(selectable) >= 1, "PBL seed must include >=1 selectable role"
    # Exactly one active issue (PBL invariant — the current_issue_id
    # binds to that single active issue).
    active = [i for i in parsed.issueboard.issues if i.is_active]
    assert len(active) == 1, f"expected exactly one active PBL issue, got {len(active)}"
    assert parsed.issueboard.current_issue_id == active[0].id
    # The active issue must carry a non-empty `generated_questions` so the
    # PBL chat panel has a welcome message on first render.
    assert active[0].generated_questions, (
        "active PBL issue must have generated_questions populated"
    )

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
