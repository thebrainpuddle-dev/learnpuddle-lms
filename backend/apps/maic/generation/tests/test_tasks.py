"""Tests for `apps.maic.generation.tasks` (MAIC-428.1).

Celery tasks run synchronously in tests via CELERY_TASK_ALWAYS_EAGER
(set in pytest fixtures). The chain entry point + each task is covered:

  - create_job_session → row inserted with the right shape.
  - outline_task → marks in_progress, emits outline_done, returns the
    chain payload.
  - scene_dispatch_task → runs Stage 2 against a stubbed pipeline,
    persists scenes-in-progress.
  - finalize_task → marks succeeded, fills result, completed_at set.
  - mark_job_failed → flips status=failed, persists error message.

Production-real (no mocks of Django ORM, no Celery mocking — only the
LLM call is mocked because real OpenRouter is gated by env var).
"""
from __future__ import annotations

from unittest.mock import patch

import json
import pytest
from django.contrib.auth import get_user_model

from apps.maic.generation.tasks import (
    create_job_session,
    enqueue_generation_chain,
    finalize_task,
    mark_job_failed,
    outline_task,
    scene_dispatch_task,
)
from apps.maic.generation.tests.parity.llm_router import PromptRoutedStub
from apps.maic.models import MaicGenerationJob
from apps.maic_pbl.models import MaicPBLSession
from apps.courses.maic_models import MAICClassroom
from apps.courses.models import Content, Course, Module
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    """A bare Tenant row for the FK on MaicGenerationJob."""
    return Tenant.objects.create(name="test-tenant", slug="test-tenant")


@pytest.fixture
def user(db, tenant):
    User = get_user_model()
    user = User.objects.create_user(
        email="test@example.com",
        password="x",
    )
    user.tenant_id = tenant.id
    user.save(update_fields=["tenant_id"])
    return user


@pytest.fixture
def parity_responses():
    """Re-use the numerator-denominator parity fixture's LLM responses
    so the chain has realistic shape-correct inputs for every prompt
    template the pipeline calls into."""
    from pathlib import Path
    fp = (
        Path(__file__).parent
        / "parity" / "fixtures" / "numerator-denominator" / "llm_responses.json"
    )
    return json.loads(fp.read_text())


# ── create_job_session ────────────────────────────────────────────


def test_create_job_session_inserts_row(db, tenant, user):
    requirements = {"topic": "fractions", "agentCount": 4, "language": "English"}
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=user.id,
        requirements=requirements,
    )
    # Reload to ensure row is committed.
    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.tenant_id == tenant.id
    assert saved.created_by_id == user.id
    assert saved.requirements == requirements
    assert saved.status == MaicGenerationJob.STATUS_PENDING
    assert saved.progress["stage"] == 0


def test_create_job_session_tolerates_no_user(db, tenant):
    """user_id=None is allowed — internal/dev jobs may not have a
    bound user."""
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={"topic": "x"},
    )
    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.created_by_id is None


def test_job_id_is_short_and_url_safe(db, tenant):
    job = create_job_session(
        tenant_id=tenant.id, user_id=None, requirements={}
    )
    # nanoid up to 12 chars per pipeline_runner._generate_session_id
    # (token_urlsafe(9) yields 12 chars before stripping `-` / `_`,
    # so the alphanumeric output may land at 10-12).
    assert 8 <= len(job.id) <= 12
    assert all(c.isalnum() for c in job.id)


# ── outline_task ──────────────────────────────────────────────────


def test_outline_task_marks_in_progress_and_returns_payload(
    db, tenant, parity_responses
):
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={
            "topic": "Numerator and Denominator",
            "agentCount": 4,
            "language": "English",
            "level": "beginner",
            "languageModelId": "stub",
        },
    )
    router = PromptRoutedStub(parity_responses)

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=router
    ):
        payload = outline_task(job_id=job.id)

    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_IN_PROGRESS
    assert saved.progress["stage"] == 1
    assert saved.result["outlines"]
    assert saved.result["languageDirective"]
    assert payload["job_id"] == job.id
    assert len(payload["outlines"]) == 10
    assert payload["languageDirective"]


def test_outline_task_raises_on_pipeline_error(db, tenant):
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={"topic": "T", "languageModelId": "stub"},
    )

    async def _broken(*args, **kwargs):
        return "nope no JSON anywhere"

    with patch(
        "apps.maic.generation.outline_generator.generate_text",
        new=_broken,
    ):
        with pytest.raises(RuntimeError):
            outline_task(job_id=job.id)


# ── scene_dispatch_task ───────────────────────────────────────────


def test_scene_dispatch_task_runs_stage2_inline(
    db, tenant, parity_responses
):
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={
            "topic": "Numerator and Denominator",
            "agentCount": 4,
            "language": "English",
            "languageModelId": "stub",
        },
    )
    router = PromptRoutedStub(parity_responses)

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=router
    ):
        stage1_payload = outline_task(job_id=job.id)

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=router
    ):
        stage2_payload = scene_dispatch_task(stage1_payload)

    assert stage2_payload["job_id"] == job.id
    assert len(stage2_payload["scenes"]) == 10


# ── finalize_task ─────────────────────────────────────────────────


def test_finalize_task_marks_succeeded(db, tenant):
    job = create_job_session(
        tenant_id=tenant.id, user_id=None, requirements={}
    )
    job.result = {"outlines": [{"order": 1}], "languageDirective": "x"}
    job.save()

    finalize_task({"job_id": job.id, "scenes": [{"id": "s1"}, {"id": "s2"}]})

    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_SUCCEEDED
    assert saved.result["scenes"] == [{"id": "s1"}, {"id": "s2"}]
    assert saved.result["outlines"]  # preserved from earlier stage
    assert saved.completed_at is not None
    assert saved.progress["stage"] == 3


def test_finalize_task_materializes_playable_classroom(db, tenant, user):
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=user.id,
        requirements={
            "topic": "Fractions",
            "agentCount": 2,
            "language": "English",
            "languageModelId": "stub",
        },
    )
    scenes = [
        {
            "id": "s1",
            "title": "Intro",
            "order": 1,
            "type": "slide",
            "content": {
                "type": "slide",
                "canvas": {
                    "id": "canvas-1",
                    "elements": [
                        {
                            "id": "el_title",
                            "type": "text",
                            "left": 40,
                            "top": 50,
                            "width": 900,
                            "height": 80,
                            "content": "<h1>Fractions</h1>",
                        }
                    ],
                    "background": {"type": "solid", "color": "#ffffff"},
                },
            },
            "actions": [
                {"id": "a1", "type": "speech", "text": "Welcome."}
            ],
        }
    ]

    result = finalize_task({"job_id": job.id, "scenes": scenes})

    saved = MaicGenerationJob.objects.get(pk=job.id)
    classroom = MAICClassroom.all_objects.get(pk=saved.result["classroomId"])
    assert result["classroomId"] == str(classroom.id)
    assert classroom.tenant_id == tenant.id
    assert classroom.creator_id == user.id
    assert classroom.status == "READY"
    assert classroom.content_scenes[0]["id"] == "s1"
    assert classroom.content_scenes[0]["actions"][0]["agentId"] == "default-1"
    assert classroom.content_meta["slides"][0]["elements"][0]["x"] == 40.0
    assert classroom.content_meta["sceneSlideBounds"] == [
        {"sceneIdx": 0, "startSlide": 0, "endSlide": 0}
    ]
    assert classroom.content_meta["audioManifest"]["status"] == "partial"
    assert saved.result["url"] == f"/teacher/ai-classroom/{classroom.id}"


def test_finalize_task_materializes_course_content_idempotently(
    db, tenant, user
):
    course = Course.objects.create(
        tenant=tenant,
        title="Math",
        description="Math course",
        created_by=user,
    )
    module = Module.objects.create(course=course, title="Unit 1", order=1)
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=user.id,
        requirements={
            "topic": "Ratios",
            "contentTitle": "Ratios classroom",
            "courseId": str(course.id),
            "moduleId": str(module.id),
            "languageModelId": "stub",
        },
    )
    payload = {
        "job_id": job.id,
        "scenes": [
            {
                "id": "s1",
                "title": "Ratios",
                "order": 1,
                "type": "quiz",
                "content": {"type": "quiz", "questions": []},
                "actions": [],
            }
        ],
    }

    first = finalize_task(payload)
    second = finalize_task(payload)

    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert first["classroomId"] == second["classroomId"]
    assert first["contentId"] == second["contentId"]
    assert Content.all_objects.filter(maic_classroom_id=saved.result["classroomId"]).count() == 1

    content = Content.all_objects.get(pk=saved.result["contentId"])
    assert content.module_id == module.id
    assert content.title == "Ratios classroom"
    assert content.content_type == "AI_CLASSROOM"
    assert str(content.maic_classroom_id) == saved.result["classroomId"]


def test_finalize_task_attaches_durable_pbl_session(db, tenant, user):
    job = create_job_session(
        tenant_id=tenant.id,
        user_id=user.id,
        requirements={
            "topic": "Water quality",
            "contentTitle": "Water quality classroom",
            "language": "English",
            "languageModelId": "stub",
        },
    )
    scenes = [
        {
            "id": "pbl-scene-1",
            "title": "Water project",
            "order": 1,
            "type": "pbl",
            "content": {
                "type": "pbl",
                "projectConfig": {
                    "projectInfo": {
                        "title": "Water Quality Investigation",
                        "description": "Investigate water quality.",
                    },
                    "agents": [],
                    "issueboard": {
                        "agent_ids": [],
                        "issues": [
                            {
                                "id": "issue_1",
                                "title": "Collect samples",
                                "description": "Plan sampling.",
                                "person_in_charge": "Researcher",
                                "participants": [],
                                "notes": "",
                                "parent_issue": None,
                                "index": 0,
                                "is_done": False,
                                "is_active": True,
                                "generated_questions": "",
                                "question_agent_name": "Question Agent - issue_1",
                                "judge_agent_name": "Judge Agent - issue_1",
                            }
                        ],
                        "current_issue_id": "issue_1",
                    },
                    "chat": {
                        "messages": [
                            {
                                "id": "msg_welcome",
                                "agent_name": "Question Agent - issue_1",
                                "message": "Welcome.",
                                "timestamp": 1.0,
                                "read_by": [],
                            }
                        ]
                    },
                },
            },
            "actions": [],
        }
    ]

    finalize_task({"job_id": job.id, "scenes": scenes})

    saved = MaicGenerationJob.objects.get(pk=job.id)
    scene = saved.result["scenes"][0]
    session_id = scene["content"]["pblSessionId"]
    assert scene["content"]["pblWsPath"] == f"/ws/maic/pbl/{session_id}/"

    session = MaicPBLSession.objects.all_tenants().get(pk=session_id)
    assert session.tenant_id == tenant.id
    assert session.owner_id == user.id
    assert session.status == MaicPBLSession.STATUS_ACTIVE
    assert session.topic == "Water Quality Investigation"
    assert session.agent_count == 1
    assert session.chat_messages[0]["message"] == "Welcome."

    classroom = MAICClassroom.all_objects.get(pk=saved.result["classroomId"])
    assert classroom.content_scenes[0]["content"]["pblSessionId"] == session_id


# ── mark_job_failed ───────────────────────────────────────────────


def test_mark_job_failed_records_status(db, tenant):
    job = create_job_session(
        tenant_id=tenant.id, user_id=None, requirements={}
    )
    exc = RuntimeError("boom")
    mark_job_failed(request=None, exc=exc, traceback=None, job_id=job.id)

    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_FAILED
    assert "boom" in saved.error
    assert saved.completed_at is not None


def test_mark_job_failed_tolerates_missing_job(db):
    """Idempotent — if the job row was already deleted (e.g. tenant
    purge), the failure handler logs + returns rather than raising."""
    mark_job_failed(
        request=None,
        exc=RuntimeError("ignored"),
        traceback=None,
        job_id="does-not-exist",
    )


# ── Chain integration (eager mode) ────────────────────────────────


def test_enqueue_generation_chain_runs_end_to_end(
    db, settings, tenant, parity_responses
):
    """Eager-mode chain: outline_task → scene_dispatch (chord fan-out)
    → scenes_finalize → finalize all run in-process. Verifies that
    the chain + chord plumbing is wired end-to-end."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

    job = create_job_session(
        tenant_id=tenant.id,
        user_id=None,
        requirements={
            "topic": "Numerator and Denominator",
            "agentCount": 4,
            "language": "English",
            "languageModelId": "stub",
        },
    )

    router = PromptRoutedStub(parity_responses)

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=router
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=router
        ):
            enqueue_generation_chain(job.id)

    saved = MaicGenerationJob.objects.get(pk=job.id)
    assert saved.status == MaicGenerationJob.STATUS_SUCCEEDED
    assert len(saved.result["scenes"]) == 10
    assert saved.completed_at is not None


# ── Chord fan-out (MAIC-428.2) ────────────────────────────────────


def test_scene_task_runs_one_scene(db, parity_responses):
    """A single scene_task call generates one scene from one outline."""
    from apps.maic.generation.tasks import scene_task

    outline = {
        "type": "slide",
        "title": "S1",
        "description": "d",
        "keyPoints": ["a"],
    }
    router = PromptRoutedStub(parity_responses)

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=router
    ):
        result = scene_task(
            index=0,
            outline=outline,
            job_id="test-job-1",
            language_model_id="stub",
            language_directive="",
            agents=[],
            user_profile="",
            stage_id="stage_test",
            total=1,
            all_titles=["S1"],
        )
    assert result["index"] == 0
    assert result["scene"] is not None
    assert result["scene"]["title"] == "S1"


def test_scene_task_returns_none_on_content_failure(db):
    """When _generate_single_scene returns None (content failed),
    scene_task returns {"index": i, "scene": None} so
    scenes_finalize_task can drop it."""
    from apps.maic.generation.tasks import scene_task

    async def _broken(*args, **kwargs):
        return "no JSON anywhere"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_broken
    ):
        result = scene_task(
            index=2,
            outline={
                "type": "slide",
                "title": "BAD",
                "description": "d",
                "keyPoints": [],
            },
            job_id="test-job-2",
            language_model_id="stub",
            language_directive="",
            agents=[],
            user_profile="",
            stage_id="stage_test",
            total=3,
            all_titles=["A", "B", "BAD"],
        )
    assert result["index"] == 2
    assert result["scene"] is None


def test_scenes_finalize_task_sorts_by_index_and_drops_none(db, tenant):
    """The chord callback may receive scenes out of order — finalize
    sorts back to outline order + drops failed scenes."""
    from apps.maic.generation.tasks import scenes_finalize_task

    job = create_job_session(
        tenant_id=tenant.id, user_id=None, requirements={}
    )
    out = scenes_finalize_task(
        [
            {"index": 2, "scene": {"id": "s3", "title": "Third"}},
            {"index": 0, "scene": {"id": "s1", "title": "First"}},
            {"index": 1, "scene": None},
            {"index": 3, "scene": {"id": "s4", "title": "Fourth"}},
        ],
        job_id=job.id,
        total=4,
    )
    assert out["job_id"] == job.id
    titles = [s["title"] for s in out["scenes"]]
    assert titles == ["First", "Third", "Fourth"]


def test_scene_dispatch_handles_empty_outline_list(db, tenant):
    """Empty outline → return {"scenes": []} immediately, don't
    dispatch a no-op chord."""
    from apps.maic.generation.tasks import scene_dispatch_task

    job = create_job_session(
        tenant_id=tenant.id, user_id=None, requirements={}
    )
    payload = scene_dispatch_task(
        {
            "job_id": job.id,
            "outlines": [],
            "languageDirective": "",
            "languageModelId": "stub",
        }
    )
    assert payload == {"job_id": job.id, "scenes": []}


# ── Redis counter helpers ─────────────────────────────────────────


def test_progress_counter_increments_atomically():
    """_incr_progress_counter returns successive integers."""
    from apps.maic.generation.tasks import (
        _incr_progress_counter,
        _reset_progress_counter,
    )
    job_id = "counter-test-1"
    _reset_progress_counter(job_id)
    assert _incr_progress_counter(job_id) == 1
    assert _incr_progress_counter(job_id) == 2
    assert _incr_progress_counter(job_id) == 3
    _reset_progress_counter(job_id)
    assert _incr_progress_counter(job_id) == 1


def test_progress_counter_isolates_per_job():
    """Each job_id has its own counter; concurrent jobs don't
    interfere."""
    from apps.maic.generation.tasks import (
        _incr_progress_counter,
        _reset_progress_counter,
    )
    _reset_progress_counter("job-A")
    _reset_progress_counter("job-B")
    _incr_progress_counter("job-A")
    _incr_progress_counter("job-A")
    _incr_progress_counter("job-B")
    # Counter A == 2; counter B == 1; second incr on B → 2.
    assert _incr_progress_counter("job-A") == 3
    assert _incr_progress_counter("job-B") == 2
