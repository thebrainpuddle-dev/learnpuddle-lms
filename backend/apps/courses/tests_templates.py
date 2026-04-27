"""Tests for the Course Templates library (TASK-049)."""

from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.courses.template_clone import (
    BLUEPRINT_SCHEMA_VERSION,
    clone_template_to_tenant,
)
from apps.courses.template_models import CourseTemplate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def super_admin_client(super_admin_user):
    client = APIClient()
    client.force_authenticate(user=super_admin_user)
    # Super-admin endpoints don't require tenant Host header.
    return client


def _sample_blueprint():
    return {
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "course": {
            "title": "Sample Template",
            "description": "desc",
            "estimated_hours": 5,
            "is_mandatory": False,
        },
        "modules": [
            {
                "title": "Module A",
                "description": "",
                "order": 1,
                "contents": [
                    {
                        "title": "Intro text",
                        "content_type": "TEXT",
                        "order": 1,
                        "text_content": "Hello",
                        "file_url": "",
                        "duration": None,
                        "is_mandatory": True,
                        "meta_json": {},
                    },
                    {
                        "title": "Intro video",
                        "content_type": "VIDEO",
                        "order": 2,
                        "text_content": "",
                        "file_url": "https://platform-cdn/video.mp4",
                        "duration": 120,
                        "is_mandatory": True,
                        "meta_json": {},
                    },
                ],
            },
            {
                "title": "Module B",
                "description": "",
                "order": 2,
                "contents": [
                    {
                        "title": "SCORM pkg",
                        "content_type": "SCORM",
                        "order": 1,
                        "text_content": "",
                        "file_url": "https://platform-cdn/pkg.zip",
                        "duration": None,
                        "is_mandatory": True,
                        "meta_json": {},
                    },
                ],
            },
        ],
    }


@pytest.fixture
def published_template(db, super_admin_user):
    return CourseTemplate.objects.create(
        slug="sample-template",
        title="Sample Template",
        description="desc",
        category="TEACHING_SKILLS",
        language="en",
        estimated_hours=5,
        level="BEGINNER",
        blueprint_json=_sample_blueprint(),
        is_published=True,
        created_by=super_admin_user,
    )


@pytest.fixture
def unpublished_template(db):
    return CourseTemplate.objects.create(
        slug="unpublished-template",
        title="Unpublished",
        category="OTHER",
        blueprint_json=_sample_blueprint(),
        is_published=False,
    )


# ---------------------------------------------------------------------------
# SUPER_ADMIN CRUD tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_super_admin_can_create_template(super_admin_client):
    resp = super_admin_client.post(
        "/api/v1/super-admin/course-templates/",
        {
            "slug": "new-tpl",
            "title": "New Template",
            "description": "",
            "category": "IB_MYP",
            "language": "en",
            "estimated_hours": 3,
            "level": "BEGINNER",
            "blueprint_json": _sample_blueprint(),
            "is_published": True,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    assert CourseTemplate.objects.filter(slug="new-tpl").exists()


@pytest.mark.django_db
def test_school_admin_cannot_create_template(admin_client):
    # admin_client is SCHOOL_ADMIN, tenant Host set by fixture.
    resp = admin_client.post(
        "/api/v1/super-admin/course-templates/",
        {"slug": "x", "title": "x"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_super_admin_can_list_templates(super_admin_client, published_template, unpublished_template):
    resp = super_admin_client.get("/api/v1/super-admin/course-templates/")
    assert resp.status_code == 200
    slugs = {row["slug"] for row in resp.json()["results"]}
    # Super-admin sees BOTH published and unpublished.
    assert "sample-template" in slugs
    assert "unpublished-template" in slugs


@pytest.mark.django_db
def test_super_admin_can_patch_template(super_admin_client, published_template):
    resp = super_admin_client.patch(
        f"/api/v1/super-admin/course-templates/{published_template.id}/",
        {"title": "Renamed"},
        format="json",
    )
    assert resp.status_code == 200
    published_template.refresh_from_db()
    assert published_template.title == "Renamed"


@pytest.mark.django_db
def test_super_admin_delete_unpublishes_by_default(super_admin_client, published_template):
    resp = super_admin_client.delete(
        f"/api/v1/super-admin/course-templates/{published_template.id}/"
    )
    assert resp.status_code == 200
    published_template.refresh_from_db()
    assert published_template.is_published is False


@pytest.mark.django_db
def test_super_admin_hard_delete(super_admin_client, published_template):
    resp = super_admin_client.delete(
        f"/api/v1/super-admin/course-templates/{published_template.id}/?hard=true"
    )
    assert resp.status_code == 204
    assert not CourseTemplate.objects.filter(id=published_template.id).exists()


# ---------------------------------------------------------------------------
# Tenant SCHOOL_ADMIN visibility tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tenant_admin_sees_only_published(admin_client, published_template, unpublished_template):
    resp = admin_client.get("/api/v1/admin/course-templates/")
    assert resp.status_code == 200
    slugs = {row["slug"] for row in resp.json()["results"]}
    assert "sample-template" in slugs
    assert "unpublished-template" not in slugs


@pytest.mark.django_db
def test_tenant_admin_cannot_preview_unpublished(admin_client, unpublished_template):
    resp = admin_client.get(
        f"/api/v1/admin/course-templates/{unpublished_template.id}/"
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_tenant_admin_preview_returns_blueprint(admin_client, published_template):
    resp = admin_client.get(
        f"/api/v1/admin/course-templates/{published_template.id}/"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "sample-template"
    assert body["blueprint_json"]["schema_version"] == BLUEPRINT_SCHEMA_VERSION
    assert len(body["blueprint_json"]["modules"]) == 2


@pytest.mark.django_db
def test_tenant_admin_list_filters(admin_client, db, super_admin_user):
    CourseTemplate.objects.create(
        slug="ib-a", title="IB A", category="IB_PYP", language="en",
        level="BEGINNER", blueprint_json={}, is_published=True,
    )
    CourseTemplate.objects.create(
        slug="skill-a", title="Skill A", category="TEACHING_SKILLS",
        language="en", level="ADVANCED", blueprint_json={}, is_published=True,
    )
    CourseTemplate.objects.create(
        slug="fr-a", title="Fr A", category="OTHER", language="fr",
        level="BEGINNER", blueprint_json={}, is_published=True,
    )

    resp = admin_client.get("/api/v1/admin/course-templates/?category=IB_PYP")
    assert resp.status_code == 200
    assert [r["slug"] for r in resp.json()["results"]] == ["ib-a"]

    resp = admin_client.get("/api/v1/admin/course-templates/?language=fr")
    assert resp.status_code == 200
    assert [r["slug"] for r in resp.json()["results"]] == ["fr-a"]

    resp = admin_client.get("/api/v1/admin/course-templates/?level=ADVANCED")
    assert resp.status_code == 200
    assert [r["slug"] for r in resp.json()["results"]] == ["skill-a"]


# ---------------------------------------------------------------------------
# Clone tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_tenant_admin_clone_happy_path(admin_client, tenant, published_template):
    before_course_count = Course.all_objects.filter(tenant=tenant).count()
    resp = admin_client.post(
        f"/api/v1/admin/course-templates/{published_template.id}/clone/",
        {"title_override": "Cloned Into Tenant"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert body["title"] == "Cloned Into Tenant"
    new_id = body["id"]

    course = Course.all_objects.get(id=new_id)
    assert course.tenant_id == tenant.id
    assert course.is_published is False
    # Sanity: new UUID, not the template's
    assert str(course.id) != str(published_template.id)
    # Modules + contents materialized
    modules = list(Module.all_objects.filter(course=course).order_by("order"))
    assert len(modules) == 2
    first_mod_contents = list(
        Content.all_objects.filter(module=modules[0]).order_by("order")
    )
    assert len(first_mod_contents) == 2
    assert Course.all_objects.filter(tenant=tenant).count() == before_course_count + 1


@pytest.mark.django_db
def test_clone_flags_placeholder_content_types(admin_client, tenant, published_template):
    resp = admin_client.post(
        f"/api/v1/admin/course-templates/{published_template.id}/clone/",
        {},
        format="json",
    )
    assert resp.status_code == 201
    course = Course.all_objects.get(id=resp.json()["id"])

    # VIDEO + SCORM should be placeholder; TEXT should NOT.
    contents = list(
        Content.all_objects.filter(module__course=course).order_by("module__order", "order")
    )
    by_type = {c.content_type: c for c in contents}
    assert by_type["TEXT"].meta_json.get("is_placeholder") is not True
    assert by_type["VIDEO"].meta_json.get("is_placeholder") is True
    assert by_type["SCORM"].meta_json.get("is_placeholder") is True
    # Placeholder body text present
    assert "Replace me" in by_type["VIDEO"].text_content
    # file_url stripped for placeholder
    assert by_type["VIDEO"].file_url == ""


@pytest.mark.django_db
def test_clone_cannot_see_unpublished(admin_client, unpublished_template):
    resp = admin_client.post(
        f"/api/v1/admin/course-templates/{unpublished_template.id}/clone/",
        {},
        format="json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_clone_is_atomic_on_failure(tenant, admin_user, published_template):
    """If clone raises mid-way, no partial rows survive."""
    before_courses = Course.all_objects.count()
    before_modules = Module.all_objects.count()
    before_contents = Content.all_objects.count()

    original_create = Content.objects.create

    call_count = {"n": 0}

    def flaky_create(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("boom mid-clone")
        return original_create(*args, **kwargs)

    with mock.patch.object(Content.objects, "create", side_effect=flaky_create):
        with pytest.raises(RuntimeError):
            clone_template_to_tenant(
                template=published_template,
                tenant=tenant,
                user=admin_user,
            )

    # Rollback: no new rows of any type.
    assert Course.all_objects.count() == before_courses
    assert Module.all_objects.count() == before_modules
    assert Content.all_objects.count() == before_contents


@pytest.mark.django_db
def test_cross_tenant_isolation_request_tenant_is_authoritative(
    api_client_for, admin_user_b, tenant_b, tenant, published_template,
):
    """
    SCHOOL_ADMIN from tenant_b cloning should produce a Course under tenant_b,
    not tenant — even if they put a different tenant id in the body.
    """
    client = api_client_for(admin_user_b, tenant_b)
    resp = client.post(
        f"/api/v1/admin/course-templates/{published_template.id}/clone/",
        # tenant_id is NOT a valid field, but simulate a malicious client
        # trying to inject one — the server must ignore it.
        {"tenant_id": str(tenant.id)},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    course = Course.all_objects.get(id=resp.json()["id"])
    assert course.tenant_id == tenant_b.id
    assert course.tenant_id != tenant.id


# ---------------------------------------------------------------------------
# Seed command tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_seed_command_creates_three_templates():
    out = StringIO()
    call_command("seed_course_templates", stdout=out)
    assert CourseTemplate.objects.count() == 3


@pytest.mark.django_db
def test_seed_command_is_idempotent():
    call_command("seed_course_templates", stdout=StringIO())
    first_ids = set(CourseTemplate.objects.values_list("id", flat=True))
    assert len(first_ids) == 3

    # Run again — count must stay at 3 and IDs must not change.
    call_command("seed_course_templates", stdout=StringIO())
    second_ids = set(CourseTemplate.objects.values_list("id", flat=True))
    assert second_ids == first_ids
    assert CourseTemplate.objects.count() == 3
