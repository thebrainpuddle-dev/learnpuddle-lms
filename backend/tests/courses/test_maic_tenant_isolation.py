"""Cross-tenant + intra-tenant isolation for MAIC classroom endpoints.

TEST-P0-1 (2026-04-23 ultrareview): zero tests existed that verified
tenant A (or a different teacher in tenant A) cannot reach tenant B's
MAIC classroom via GET / PATCH / DELETE / publish / progress / chat.

This suite locks down every mutating + reading MAIC endpoint that takes
a classroom_id so future regressions (drop of `creator=`, drop of
`tenant=`, permission-decorator churn) are caught at CI time.

Two attacker roles per endpoint:
    attacker_cross_tenant — TEACHER in tenant B
    attacker_same_tenant  — different TEACHER in tenant A

Both must receive 404 (MAICClassroom.DoesNotExist maps to 404 via the
existing try/except — never 200). Also both must receive 404 even when
the classroom's tenant matches theirs but the creator does not.

Pairs with the SEC-P1-5 fix to `teacher_maic_chat` (2026-04-23).
"""
from __future__ import annotations

from unittest import mock

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def feature_maic_on(tenant, tenant_b):
    """Enable MAIC on both tenants so `@check_feature('feature_maic')` passes.
    Without this the endpoints short-circuit with 403 upgrade_required and
    we never reach the ownership check."""
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    tenant_b.feature_maic = True
    tenant_b.save(update_fields=["feature_maic"])


@pytest.fixture
def teacher_user_b(db, tenant_b):
    """TEACHER in tenant B (cross-tenant attacker)."""
    from apps.users.models import User
    return User.objects.create_user(
        email="teacher@otherschool.com",
        password="TeacherPass!123",
        first_name="Teacher",
        last_name="OtherTenant",
        tenant=tenant_b,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def teacher_user_a2(db, tenant):
    """A SECOND TEACHER in tenant A (intra-tenant attacker)."""
    from apps.users.models import User
    return User.objects.create_user(
        email="teacher2@testschool.com",
        password="TeacherPass!123",
        first_name="Teacher",
        last_name="Two",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def victim_classroom(tenant, teacher_user):
    """Classroom owned by teacher_user in tenant A. The target of every
    cross-owner probe below."""
    from apps.courses.maic_models import MAICClassroom
    return MAICClassroom.objects.create(
        tenant=tenant,
        creator=teacher_user,
        title="Victim Classroom",
        topic="SSRF + IDOR Test Fixture",
        language="en",
        status="DRAFT",
        config={"sceneCount": 3},
    )


def _client_for(user, host_tenant):
    """Build an authenticated DRF client pointed at a specific tenant host."""
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = f"{host_tenant.subdomain}.lms.com"
    return client


# ─────────────────────────────────────────────────────────────
# Attacker → endpoint matrix
#
# Each test is parametrized over:
#   (attacker_fixture_name, attacker_tenant_fixture_name, label)
#
# `attacker_tenant_fixture_name` controls the Host header the attacker
# uses — which the TenantMiddleware resolves into request.tenant. A
# cross-tenant attacker speaks from tenant_b's subdomain; an intra-tenant
# attacker from tenant's subdomain. This mirrors the real attack shape.
# ─────────────────────────────────────────────────────────────

_ATTACKER_MATRIX = [
    ("teacher_user_b",  "tenant_b", "cross-tenant"),
    ("teacher_user_a2", "tenant",   "intra-tenant-different-creator"),
]


@pytest.fixture
def attacker(request):
    """Yields (attacker_client, label) pairs for each matrix entry.

    Parametrized by `_ATTACKER_MATRIX`. Lookups the fixture by name at
    request time so we can compose user + host-tenant from strings.
    """
    user_name, host_name, label = request.param
    user = request.getfixturevalue(user_name)
    host_tenant = request.getfixturevalue(host_name)
    return _client_for(user, host_tenant), label


# ─────────────────────────────────────────────────────────────
# Endpoint tests
# ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("attacker", _ATTACKER_MATRIX, indirect=True)
def test_classroom_detail_cross_owner_404(attacker, victim_classroom, feature_maic_on):
    client, _label = attacker
    url = f"/api/v1/teacher/maic/classrooms/{victim_classroom.id}/"
    resp = client.get(url)
    assert resp.status_code == 404, (
        f"Attacker reached victim classroom detail (expected 404, got {resp.status_code})"
    )


@pytest.mark.parametrize("attacker", _ATTACKER_MATRIX, indirect=True)
def test_classroom_update_cross_owner_404(attacker, victim_classroom, feature_maic_on):
    client, _label = attacker
    url = f"/api/v1/teacher/maic/classrooms/{victim_classroom.id}/update/"
    resp = client.patch(url, {"title": "HIJACKED"}, format="json")
    assert resp.status_code == 404

    # Also verify the row was NOT mutated.
    from apps.courses.maic_models import MAICClassroom
    victim = MAICClassroom.objects.get(pk=victim_classroom.id)
    assert victim.title == "Victim Classroom"


@pytest.mark.parametrize("attacker", _ATTACKER_MATRIX, indirect=True)
def test_classroom_delete_cross_owner_404(attacker, victim_classroom, feature_maic_on):
    client, _label = attacker
    url = f"/api/v1/teacher/maic/classrooms/{victim_classroom.id}/delete/"
    resp = client.delete(url)
    assert resp.status_code == 404

    from apps.courses.maic_models import MAICClassroom
    # Row must still exist + NOT be archived.
    victim = MAICClassroom.objects.get(pk=victim_classroom.id)
    assert victim.status != "ARCHIVED"


@pytest.mark.parametrize("attacker", _ATTACKER_MATRIX, indirect=True)
def test_classroom_progress_cross_owner_404(attacker, victim_classroom, feature_maic_on):
    client, _label = attacker
    url = f"/api/v1/teacher/maic/classrooms/{victim_classroom.id}/progress/"
    resp = client.post(
        url,
        {"phase": "content", "phase_scene_index": 5, "scenes_ready": 3},
        format="json",
    )
    assert resp.status_code == 404

    # And no progress fields were stamped.
    from apps.courses.maic_models import MAICClassroom
    victim = MAICClassroom.objects.get(pk=victim_classroom.id)
    assert victim.generation_phase == ""
    assert victim.scenes_ready == 0
    assert victim.last_progress_at is None


@pytest.mark.parametrize("attacker", _ATTACKER_MATRIX, indirect=True)
def test_classroom_publish_cross_owner_404(attacker, victim_classroom, feature_maic_on):
    client, _label = attacker
    url = f"/api/v1/teacher/maic/classrooms/{victim_classroom.id}/publish/"
    resp = client.post(url, {}, format="json")
    assert resp.status_code == 404


@pytest.mark.parametrize("attacker", _ATTACKER_MATRIX, indirect=True)
def test_chat_sec_p1_5_classroom_context_cross_owner_404(
    attacker, victim_classroom, feature_maic_on,
):
    """SEC-P1-5 (2026-04-23): sending another teacher's classroomId in the
    chat body used to leak the target classroom's title + agents + scene
    titles as chat context. Now it returns 404 before sidecar / direct-LLM
    paths execute."""
    client, _label = attacker
    # Mock TenantAIConfig so _get_ai_config doesn't 400 — we want to hit
    # the IDOR check, not the feature-flag check.
    from apps.courses.maic_models import TenantAIConfig
    for t in {victim_classroom.tenant, client.handler._force_user.tenant}:
        TenantAIConfig.objects.get_or_create(
            tenant=t,
            defaults={
                "llm_provider": "openrouter",
                "llm_model": "openai/gpt-4o-mini",
                "tts_provider": "disabled",
                "maic_enabled": True,
            },
        )

    resp = client.post(
        "/api/v1/teacher/maic/chat/",
        {
            "message": "summarize this classroom",
            "classroomId": str(victim_classroom.id),
        },
        format="json",
    )
    # Must be 404 (not 200 + classroom context).
    assert resp.status_code == 404, (
        f"Chat IDOR leaked victim classroom context (status={resp.status_code}, "
        f"body={resp.content[:200]!r})"
    )


# ─────────────────────────────────────────────────────────────
# Positive-path regression: OWNER can still access everything.
# Guards against over-tightening the isolation filters.
# ─────────────────────────────────────────────────────────────

def test_owner_can_still_get_detail(
    teacher_client, teacher_user, victim_classroom, feature_maic_on,
):
    # Reset ownership to match the default teacher_user from conftest.
    victim_classroom.creator = teacher_user
    victim_classroom.save(update_fields=["creator"])
    url = f"/api/v1/teacher/maic/classrooms/{victim_classroom.id}/"
    resp = teacher_client.get(url)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(victim_classroom.id)


def test_owner_can_still_patch(
    teacher_client, teacher_user, victim_classroom, feature_maic_on,
):
    victim_classroom.creator = teacher_user
    victim_classroom.save(update_fields=["creator"])
    url = f"/api/v1/teacher/maic/classrooms/{victim_classroom.id}/update/"
    resp = teacher_client.patch(url, {"title": "Owner-renamed"}, format="json")
    assert resp.status_code == 200

    from apps.courses.maic_models import MAICClassroom
    assert MAICClassroom.objects.get(pk=victim_classroom.id).title == "Owner-renamed"


def test_owner_can_still_progress_ping(
    teacher_client, teacher_user, victim_classroom, feature_maic_on,
):
    victim_classroom.creator = teacher_user
    victim_classroom.save(update_fields=["creator"])
    url = f"/api/v1/teacher/maic/classrooms/{victim_classroom.id}/progress/"
    resp = teacher_client.post(
        url,
        {"phase": "content", "phase_scene_index": 1, "scenes_ready": 0},
        format="json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "content"
    assert body["phase_scene_index"] == 1


# ─────────────────────────────────────────────────────────────
# SEC-P1-CROSS-TENANT-IMAGE-FILL — _defer_image_fill must NOT
# write images_pending=True on a classroom in another tenant.
#
# Surface: teacher_maic_generate_scene_content + the student
# variant both forward body['classroomId'] into _defer_image_fill,
# which used to call MAICClassroom.all_objects.filter(id=...).update()
# (no tenant scope). A teacher in tenant A could submit tenant B's
# classroom UUID and flip images_pending plus enqueue a Celery task
# referencing tenant B's row. Both are cross-tenant writes.
# ─────────────────────────────────────────────────────────────

def test_defer_image_fill_skips_cross_tenant_classroom(
    tenant, tenant_b, teacher_user, feature_maic_on, settings, caplog,
):
    """Direct unit test: _defer_image_fill must no-op when given a
    classroom_id that belongs to a different tenant than the caller's
    request.tenant, and must NOT enqueue the Celery task.

    Mirrors the cross-tenant attack shape: caller authenticates against
    tenant_a (passes ``tenant=tenant_a``) but supplies a classroom_id
    that lives in tenant_b.

    Reviewer follow-up (REVIEW-VERDICT-BE-SEC-P1-CROSS-TENANT-IMAGE-FILL-2026-04-25):
      • Use ``call_count == 0`` (more explicit than ``not called``)
      • Add ``caplog`` assertion to confirm the SEC-P1 warning fires
    """
    import logging
    from apps.courses.maic_models import MAICClassroom
    from apps.courses.maic_views import _defer_image_fill

    # Victim classroom lives in tenant_b. images_pending starts False.
    teacher_b_user = type(teacher_user).objects.create_user(
        email="victim_t2@otherschool.com",
        password="VictimPass!123",
        first_name="Victim",
        last_name="OtherTenant",
        tenant=tenant_b,
        role="TEACHER",
        is_active=True,
    )
    victim = MAICClassroom.objects.create(
        tenant=tenant_b,
        creator=teacher_b_user,
        title="Tenant B Victim",
        topic="cross-tenant target",
        language="en",
        status="DRAFT",
        config={"sceneCount": 1},
        images_pending=False,
    )

    # Attacker payload: a slide with one empty-src image element.
    data = {
        "slides": [
            {
                "elements": [
                    {"type": "image", "src": "", "content": "anything"}
                ]
            }
        ]
    }

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_views"):
        with mock.patch(
            "apps.courses.maic_tasks.fill_classroom_images.apply_async"
        ) as mock_enqueue:
            _defer_image_fill(
                data,
                image_provider="unsplash",
                classroom_id=str(victim.id),
                tenant=tenant,  # <-- caller's tenant is A, classroom is in B
            )

    # Celery task MUST NOT be enqueued — no cross-tenant work.
    assert mock_enqueue.call_count == 0, (
        f"fill_classroom_images was enqueued {mock_enqueue.call_count} time(s) "
        "for a classroom in another tenant "
        "(SEC-P1-CROSS-TENANT-IMAGE-FILL regression)"
    )

    # SEC-P1 warning must appear in the log.
    assert any(
        "SEC-P1-CROSS-TENANT-IMAGE-FILL" in msg
        for msg in caplog.messages
    ), (
        "Expected SEC-P1-CROSS-TENANT-IMAGE-FILL warning in log, "
        f"got: {caplog.messages}"
    )

    # Victim row must NOT have been mutated.
    victim.refresh_from_db()
    assert victim.images_pending is False, (
        "images_pending was flipped on a classroom belonging to another tenant "
        "(SEC-P1-CROSS-TENANT-IMAGE-FILL regression)"
    )


def test_defer_image_fill_runs_for_same_tenant_classroom(
    tenant, teacher_user, feature_maic_on,
):
    """Positive control: when classroom is in the caller's tenant, the
    fill is enqueued and images_pending is flipped. Guards against the
    SEC-P1 fix being over-aggressive (e.g. mistakenly scoping out the
    caller's own classrooms)."""
    from apps.courses.maic_models import MAICClassroom
    from apps.courses.maic_views import _defer_image_fill

    own = MAICClassroom.objects.create(
        tenant=tenant,
        creator=teacher_user,
        title="Tenant A Own Classroom",
        topic="positive control",
        language="en",
        status="DRAFT",
        config={"sceneCount": 1},
        images_pending=False,
    )

    data = {
        "slides": [
            {
                "elements": [
                    {"type": "image", "src": "", "content": "ok"}
                ]
            }
        ]
    }

    with mock.patch(
        "apps.courses.maic_tasks.fill_classroom_images.apply_async"
    ) as mock_enqueue:
        _defer_image_fill(
            data,
            image_provider="unsplash",
            classroom_id=str(own.id),
            tenant=tenant,
        )

    assert mock_enqueue.called, (
        "fill_classroom_images was NOT enqueued for the caller's own classroom"
    )
    own.refresh_from_db()
    assert own.images_pending is True, (
        "images_pending was not flipped for caller's own classroom"
    )


# ─────────────────────────────────────────────────────────────
# SEC-P1-CROSS-TENANT-IMAGE-FILL — review follow-up tests
# (REVIEW-VERDICT-BE-SEC-P1-CROSS-TENANT-IMAGE-FILL-2026-04-25.md)
#
#   #1 Harden the ``tenant=None`` legacy arm — re-entry point for
#      the same bug.  Refuse to do the unscoped update; log error.
#   #2 Log the *victim* ``tenant_id`` on cross-tenant miss so SOC
#      can pivot to "did Tenant A try to write to Tenant B's row?"
# ─────────────────────────────────────────────────────────────

def test_defer_image_fill_refuses_when_tenant_none(
    tenant, teacher_user, feature_maic_on, caplog,
):
    """Follow-up #1: when ``classroom_id`` is supplied but ``tenant`` is None,
    ``_defer_image_fill`` MUST NOT touch the DB and MUST NOT enqueue any
    Celery task.  Guards against a future caller silently reintroducing the
    cross-tenant write by forgetting to pass ``tenant=request.tenant``.
    """
    import logging
    from apps.courses.maic_models import MAICClassroom
    from apps.courses.maic_views import _defer_image_fill

    # A real classroom exists in tenant A.  Even though the lookup *would*
    # match if it were unscoped, the function must refuse the call.
    own = MAICClassroom.objects.create(
        tenant=tenant,
        creator=teacher_user,
        title="Tenant A Legacy Caller Test",
        topic="legacy arm",
        language="en",
        status="DRAFT",
        config={"sceneCount": 1},
        images_pending=False,
    )

    data = {
        "slides": [
            {
                "elements": [
                    {"type": "image", "src": "", "content": "anything"}
                ]
            }
        ]
    }

    with caplog.at_level(logging.ERROR, logger="apps.courses.maic_views"):
        with mock.patch(
            "apps.courses.maic_tasks.fill_classroom_images.apply_async"
        ) as mock_enqueue:
            _defer_image_fill(
                data,
                image_provider="unsplash",
                classroom_id=str(own.id),
                tenant=None,  # <-- legacy / mis-wired caller
            )

    # No DB write.
    own.refresh_from_db()
    assert own.images_pending is False, (
        "_defer_image_fill mutated images_pending without a tenant scope "
        "(SEC-P1 legacy-arm regression)"
    )
    # No Celery enqueue.
    assert mock_enqueue.call_count == 0, (
        f"fill_classroom_images was enqueued {mock_enqueue.call_count} time(s) "
        "from the legacy tenant=None arm (SEC-P1 legacy-arm regression)"
    )
    # ERROR log fires with the security tag.
    assert any(
        "SEC-P1-CROSS-TENANT-IMAGE-FILL" in msg and "tenant=None" in msg
        for msg in caplog.messages
    ), (
        "Expected SEC-P1-CROSS-TENANT-IMAGE-FILL error mentioning tenant=None "
        f"in log, got: {caplog.messages}"
    )


def test_defer_image_fill_logs_victim_tenant_id_on_cross_tenant_miss(
    tenant, tenant_b, teacher_user, feature_maic_on, caplog,
):
    """Follow-up #2: on a cross-tenant miss the warning record must carry the
    *victim* tenant_id (the tenant that actually owns the classroom) so SOC
    triage can answer "did Tenant A try to write to Tenant B's row?".
    """
    import logging
    from apps.courses.maic_models import MAICClassroom
    from apps.courses.maic_views import _defer_image_fill

    teacher_b_user = type(teacher_user).objects.create_user(
        email="victim_logfield@otherschool.com",
        password="VictimPass!123",
        first_name="Victim",
        last_name="LogField",
        tenant=tenant_b,
        role="TEACHER",
        is_active=True,
    )
    victim = MAICClassroom.objects.create(
        tenant=tenant_b,
        creator=teacher_b_user,
        title="Tenant B Victim (log field)",
        topic="victim tenant id",
        language="en",
        status="DRAFT",
        config={"sceneCount": 1},
        images_pending=False,
    )

    data = {
        "slides": [
            {
                "elements": [
                    {"type": "image", "src": "", "content": "anything"}
                ]
            }
        ]
    }

    with caplog.at_level(logging.WARNING, logger="apps.courses.maic_views"):
        with mock.patch(
            "apps.courses.maic_tasks.fill_classroom_images.apply_async"
        ) as mock_enqueue:
            _defer_image_fill(
                data,
                image_provider="unsplash",
                classroom_id=str(victim.id),
                tenant=tenant,  # caller in A, victim in B
            )

    assert mock_enqueue.call_count == 0

    # Find the SEC-P1 warning record and assert the victim tenant_id appears
    # in the structured ``extra`` payload.  We use ``records`` (not just
    # ``messages``) so we can inspect the dict shape.
    sec_records = [
        rec for rec in caplog.records
        if "SEC-P1-CROSS-TENANT-IMAGE-FILL" in rec.getMessage()
    ]
    assert sec_records, (
        f"No SEC-P1 warning record found, got: "
        f"{[r.getMessage() for r in caplog.records]}"
    )
    rec = sec_records[0]
    # Structured field on the LogRecord (from ``extra=log_extra(...)``).
    assert getattr(rec, "victim_tenant_id", "") == str(tenant_b.id), (
        f"victim_tenant_id missing or wrong on SEC-P1 warning record. "
        f"Expected {tenant_b.id!s}, got "
        f"{getattr(rec, 'victim_tenant_id', '<missing>')}"
    )
    # The attacker tenant id must also still be present (existing behavior).
    assert getattr(rec, "tenant_id", "") == str(tenant.id), (
        f"attacker tenant_id missing on SEC-P1 warning record. "
        f"Expected {tenant.id!s}, got "
        f"{getattr(rec, 'tenant_id', '<missing>')}"
    )
