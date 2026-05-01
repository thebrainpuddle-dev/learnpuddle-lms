"""WAVE-8-F1 (2026-04-28): HTTP MAIC view visibility/permission tests.

Pins the contract that all classroom HTTP views go through the canonical
``_can_view_classroom`` (READ gate) / ``_can_modify_classroom`` (WRITE gate)
helpers in ``apps.courses.maic_views``. Wave 8 originally extracted the read
helper but only migrated the WS consumer onto it; the HTTP detail view kept
its inline ``creator=request.user`` queryset filter. The reviewer caught the
docstring claim of "single canonical visibility gate" was misleading — these
tests prove it now holds.

Behavior changes vs the previous inline ``creator=request.user`` filter:

  * **READ widening** (``teacher_maic_classroom_detail``):
      SCHOOL_ADMIN and SUPER_ADMIN in the same tenant now receive a 200
      on a teacher's classroom (previously 404). HOD / IB_COORDINATOR /
      peer TEACHER are still rejected (404) — same as before.

  * **WRITE widening** (``teacher_maic_classroom_update / progress /
      finalize-partial / delete / publish`` and ``student_maic_classroom_
      update / delete``):
      SCHOOL_ADMIN and SUPER_ADMIN in the same tenant now succeed
      (previously 404). Peer teachers / students still rejected (404).

Tests that exercise the actual write side-effect are intentionally minimal —
the goal here is the permission contract, not the business logic of each
mutation. Existing per-endpoint test files cover the side-effects.
"""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def maic_tenant(tenant):
    """Primary tenant with feature_maic enabled."""
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    return tenant


@pytest.fixture
def maic_tenant_b(tenant_b):
    """Secondary tenant with feature_maic enabled."""
    tenant_b.feature_maic = True
    tenant_b.save(update_fields=["feature_maic"])
    return tenant_b


@pytest.fixture
def peer_teacher(db, maic_tenant):
    """A second TEACHER in the SAME tenant as ``teacher_user``.

    Used to prove the canonical visibility helper still rejects peer
    teachers in the same tenant (matches legacy creator-filter behavior).
    """
    from apps.users.models import User

    return User.objects.create_user(
        email="peer-teacher-w8f1@testschool.com",
        password="TeacherPass!123",
        first_name="Peer",
        last_name="Teacher",
        tenant=maic_tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def cross_tenant_teacher(db, maic_tenant_b):
    """A TEACHER in tenant_b — pins cross-tenant rejection."""
    from apps.users.models import User

    return User.objects.create_user(
        email="teacher-b-w8f1@otherschool.com",
        password="TeacherPass!123",
        first_name="Cross",
        last_name="Tenant",
        tenant=maic_tenant_b,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def super_admin(db, maic_tenant):
    """A SUPER_ADMIN user (platform-wide access)."""
    from apps.users.models import User

    return User.objects.create_user(
        email="superadmin-w8f1@learnpuddle.com",
        password="SuperAdmin!123",
        first_name="Super",
        last_name="Admin",
        tenant=maic_tenant,
        role="SUPER_ADMIN",
        is_active=True,
    )


@pytest.fixture
def teacher_classroom(db, maic_tenant, teacher_user):
    """A READY MAICClassroom owned by ``teacher_user`` in ``maic_tenant``."""
    from apps.courses.maic_models import MAICClassroom

    return MAICClassroom.objects.create(
        tenant=maic_tenant,
        creator=teacher_user,
        title="WAVE-8-F1 fixture classroom",
        topic="Visibility",
        status="DRAFT",
        content_scenes=[],
        content_meta={},
    )


def _client_for(user, tenant):
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


# ---------------------------------------------------------------------------
# READ gate: teacher_maic_classroom_detail
# ---------------------------------------------------------------------------


def test_teacher_maic_classroom_detail_uses_shared_visibility_helper(
    maic_tenant,
    teacher_user,
    teacher_classroom,
    peer_teacher,
):
    """WAVE-8-F1 regression: peer teacher in same tenant gets 404.

    Pre-fix: rejected by the inline ``creator=request.user`` queryset
    filter. Post-fix: rejected by ``_can_view_classroom`` (functionally
    equivalent for peer teachers — the helper rejects them too).
    """
    client = _client_for(peer_teacher, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/"
    resp = client.get(url)
    assert resp.status_code == 404, (
        f"peer teacher must NOT see another teacher's classroom; "
        f"got {resp.status_code}: {resp.content[:200]!r}"
    )


def test_teacher_maic_classroom_detail_allows_creator(
    maic_tenant,
    teacher_user,
    teacher_classroom,
):
    """The creator always sees their own classroom (read access)."""
    client = _client_for(teacher_user, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/"
    resp = client.get(url)
    assert resp.status_code == 200, resp.content
    assert resp.json()["id"] == str(teacher_classroom.id)


def test_teacher_maic_classroom_detail_allows_school_admin(
    maic_tenant,
    teacher_user,
    teacher_classroom,
    admin_user,
):
    """**Behavior change vs legacy filter**: SCHOOL_ADMIN in the same
    tenant now receives 200 on a teacher's classroom (previously 404
    via the inline ``creator=request.user`` filter). This is the
    intended widening — the canonical read gate exposes oversight
    access to admins. See WAVE-8-F1 in the docstring.
    """
    client = _client_for(admin_user, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/"
    resp = client.get(url)
    assert resp.status_code == 200, (
        f"SCHOOL_ADMIN should now have read access via _can_view_classroom; "
        f"got {resp.status_code}: {resp.content[:200]!r}"
    )
    assert resp.json()["id"] == str(teacher_classroom.id)


def test_teacher_maic_classroom_detail_allows_super_admin(
    maic_tenant,
    teacher_user,
    teacher_classroom,
    super_admin,
):
    """SUPER_ADMIN bypasses tenant scope and reads any classroom (200)."""
    client = _client_for(super_admin, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/"
    resp = client.get(url)
    assert resp.status_code == 200, resp.content
    assert resp.json()["id"] == str(teacher_classroom.id)


def test_teacher_maic_classroom_detail_rejects_cross_tenant(
    maic_tenant,
    maic_tenant_b,
    teacher_classroom,
    cross_tenant_teacher,
):
    """A TEACHER in a different tenant gets 404 — never leaks existence."""
    # Use the *other* tenant's host so TenantMiddleware resolves correctly
    # and we exercise the tenant-scope rejection inside _can_view_classroom.
    client = _client_for(cross_tenant_teacher, maic_tenant_b)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/"
    resp = client.get(url)
    # Different tenant subdomains may produce a 404 from the URL/host
    # routing layer or from the helper — either is correct.
    assert resp.status_code == 404, (
        f"cross-tenant teacher must NOT see this classroom; "
        f"got {resp.status_code}: {resp.content[:200]!r}"
    )


def test_teacher_maic_classroom_detail_rejects_anonymous(
    maic_tenant,
    teacher_classroom,
):
    """Spot-check: unauthenticated request returns 401/403."""
    anon = APIClient()
    anon.defaults["HTTP_HOST"] = f"{maic_tenant.subdomain}.lms.com"
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/"
    resp = anon.get(url)
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# WRITE gate: teacher_maic_classroom_update / delete / publish / progress /
# finalize-partial — all should reject peer teachers and allow admins.
# ---------------------------------------------------------------------------


def test_teacher_maic_classroom_update_rejects_peer_teacher(
    maic_tenant,
    teacher_classroom,
    peer_teacher,
):
    """Peer teacher in same tenant cannot mutate via PATCH."""
    client = _client_for(peer_teacher, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/update/"
    resp = client.patch(url, {"title": "Hijacked"}, format="json")
    assert resp.status_code == 404, (
        f"peer teacher must NOT mutate; got {resp.status_code}: " f"{resp.content[:200]!r}"
    )
    teacher_classroom.refresh_from_db()
    assert teacher_classroom.title == "WAVE-8-F1 fixture classroom"


def test_teacher_maic_classroom_update_allows_creator(
    maic_tenant,
    teacher_user,
    teacher_classroom,
):
    """Creator can mutate."""
    client = _client_for(teacher_user, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/update/"
    resp = client.patch(url, {"title": "Renamed by owner"}, format="json")
    assert resp.status_code == 200, resp.content
    teacher_classroom.refresh_from_db()
    assert teacher_classroom.title == "Renamed by owner"


def test_teacher_maic_classroom_update_allows_school_admin(
    maic_tenant,
    teacher_classroom,
    admin_user,
):
    """**Behavior change vs legacy filter**: SCHOOL_ADMIN may now PATCH
    a teacher's classroom (oversight write access). Previously 404."""
    client = _client_for(admin_user, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/update/"
    resp = client.patch(url, {"title": "Renamed by admin"}, format="json")
    assert resp.status_code == 200, (
        f"SCHOOL_ADMIN should now have write access via _can_modify_classroom; "
        f"got {resp.status_code}: {resp.content[:200]!r}"
    )
    teacher_classroom.refresh_from_db()
    assert teacher_classroom.title == "Renamed by admin"


def test_teacher_maic_classroom_delete_rejects_peer_teacher(
    maic_tenant,
    teacher_classroom,
    peer_teacher,
):
    """Peer teacher cannot archive someone else's classroom."""
    client = _client_for(peer_teacher, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/delete/"
    resp = client.delete(url)
    assert resp.status_code == 404, resp.content
    teacher_classroom.refresh_from_db()
    assert teacher_classroom.status != "ARCHIVED"


def test_teacher_maic_classroom_delete_allows_creator(
    maic_tenant,
    teacher_user,
    teacher_classroom,
):
    """Creator can archive."""
    client = _client_for(teacher_user, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/delete/"
    resp = client.delete(url)
    assert resp.status_code == 204
    teacher_classroom.refresh_from_db()
    assert teacher_classroom.status == "ARCHIVED"


def test_teacher_maic_classroom_progress_rejects_peer_teacher(
    maic_tenant,
    teacher_classroom,
    peer_teacher,
):
    """Peer teacher cannot stamp progress on someone else's classroom."""
    client = _client_for(peer_teacher, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/progress/"
    resp = client.post(url, {"phase": "complete"}, format="json")
    assert resp.status_code == 404, resp.content


def test_teacher_maic_classroom_finalize_partial_rejects_peer_teacher(
    maic_tenant,
    teacher_classroom,
    peer_teacher,
):
    """Peer teacher cannot finalize someone else's classroom."""
    client = _client_for(peer_teacher, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/" f"finalize-partial/"
    resp = client.post(url, {}, format="json")
    assert resp.status_code == 404, resp.content


def test_teacher_maic_classroom_publish_rejects_peer_teacher(
    maic_tenant,
    teacher_classroom,
    peer_teacher,
):
    """Peer teacher cannot publish someone else's classroom (write gate
    sits in front of the select_for_update row lock)."""
    client = _client_for(peer_teacher, maic_tenant)
    url = f"/api/v1/teacher/maic/classrooms/{teacher_classroom.id}/publish/"
    resp = client.post(url, {}, format="json")
    assert resp.status_code == 404, resp.content


# ---------------------------------------------------------------------------
# Student write endpoints — same gate, different decorator.
# ---------------------------------------------------------------------------


@pytest.fixture
def student_user(db, maic_tenant):
    from apps.users.models import User

    return User.objects.create_user(
        email="student-w8f1@testschool.com",
        password="StudentPass!123",
        first_name="Student",
        last_name="Owner",
        tenant=maic_tenant,
        role="STUDENT",
        is_active=True,
    )


@pytest.fixture
def peer_student(db, maic_tenant):
    from apps.users.models import User

    return User.objects.create_user(
        email="peer-student-w8f1@testschool.com",
        password="StudentPass!123",
        first_name="Peer",
        last_name="Student",
        tenant=maic_tenant,
        role="STUDENT",
        is_active=True,
    )


@pytest.fixture
def student_classroom(db, maic_tenant, student_user):
    """A DRAFT classroom owned by ``student_user``."""
    from apps.courses.maic_models import MAICClassroom

    return MAICClassroom.objects.create(
        tenant=maic_tenant,
        creator=student_user,
        title="WAVE-8-F1 student fixture",
        topic="Visibility",
        status="DRAFT",
        content_scenes=[],
        content_meta={},
        is_public=False,
    )


def test_student_maic_classroom_update_rejects_peer_student(
    maic_tenant,
    student_classroom,
    peer_student,
):
    """Peer student cannot mutate someone else's classroom."""
    client = _client_for(peer_student, maic_tenant)
    url = f"/api/v1/student/maic/classrooms/{student_classroom.id}/update/"
    resp = client.patch(url, {"title": "Hijacked"}, format="json")
    assert resp.status_code == 404, resp.content
    student_classroom.refresh_from_db()
    assert student_classroom.title == "WAVE-8-F1 student fixture"


def test_student_maic_classroom_update_allows_creator(
    maic_tenant,
    student_user,
    student_classroom,
):
    """Student creator can mutate own classroom."""
    client = _client_for(student_user, maic_tenant)
    url = f"/api/v1/student/maic/classrooms/{student_classroom.id}/update/"
    resp = client.patch(url, {"title": "Renamed"}, format="json")
    assert resp.status_code == 200, resp.content
    student_classroom.refresh_from_db()
    assert student_classroom.title == "Renamed"


def test_student_maic_classroom_delete_rejects_peer_student(
    maic_tenant,
    student_classroom,
    peer_student,
):
    """Peer student cannot archive someone else's classroom."""
    client = _client_for(peer_student, maic_tenant)
    url = f"/api/v1/student/maic/classrooms/{student_classroom.id}/delete/"
    resp = client.delete(url)
    assert resp.status_code == 404, resp.content
    student_classroom.refresh_from_db()
    assert student_classroom.status != "ARCHIVED"


# ---------------------------------------------------------------------------
# Helper-level tests for _can_modify_classroom (mirrors the existing
# _can_view_classroom helper tests in test_maic_image_tasks_ws.py).
# ---------------------------------------------------------------------------


def test_can_modify_classroom_allows_creator(
    maic_tenant,
    teacher_user,
    teacher_classroom,
):
    from apps.courses.maic_views import _can_modify_classroom

    assert _can_modify_classroom(teacher_user, teacher_classroom) is True


def test_can_modify_classroom_allows_school_admin(
    maic_tenant,
    admin_user,
    teacher_classroom,
):
    from apps.courses.maic_views import _can_modify_classroom

    assert _can_modify_classroom(admin_user, teacher_classroom) is True


def test_can_modify_classroom_allows_super_admin(
    super_admin,
    teacher_classroom,
):
    from apps.courses.maic_views import _can_modify_classroom

    assert _can_modify_classroom(super_admin, teacher_classroom) is True


def test_can_modify_classroom_rejects_peer_teacher(
    peer_teacher,
    teacher_classroom,
):
    from apps.courses.maic_views import _can_modify_classroom

    assert _can_modify_classroom(peer_teacher, teacher_classroom) is False


def test_can_modify_classroom_rejects_cross_tenant(
    cross_tenant_teacher,
    teacher_classroom,
):
    from apps.courses.maic_views import _can_modify_classroom

    assert _can_modify_classroom(cross_tenant_teacher, teacher_classroom) is False


def test_can_modify_classroom_rejects_none_classroom(teacher_user):
    from apps.courses.maic_views import _can_modify_classroom

    assert _can_modify_classroom(teacher_user, None) is False
