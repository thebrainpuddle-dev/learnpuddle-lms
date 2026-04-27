"""Tests for TASK-064b — Translation per-field approval backend.

Coverage (≥10 tests):
 T01. Approve happy path → 200, review_status='approved', audit row emitted.
 T02. Reject happy path → 200, review_status='rejected', audit row emitted.
 T03. Edit happy path → 200, review_status='approved', edited_text saved, audit row emitted.
 T04. Publish happy path → 200, only approved rows get published_at, skipped map correct.
 T05. Non-admin (TEACHER) approve → 403 via @admin_only.
 T06. Non-admin (TEACHER) reject → 403 via @admin_only.
 T07. Cross-tenant approve → 404 (not 403).
 T08. Audit log consolidation: all 4 action types emitted by a single flow.
 T09. Publish semantics: rejected + pending rows are skipped, response skipped map is accurate.
 T10. Publish semantics: already-approved row is promoted; rows_published count is correct.
 T11. Teacher endpoint excludes unpublished (published_at IS NULL) rows.
 T12. Teacher endpoint returns published rows (published_at IS NOT NULL).
 T13. Purge (DELETE) cascades review state — row is gone after purge.
 T14. Edit endpoint validates missing edited_text → 400.
 T15. Invalid field name in URL → 400.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.progress.models import TeacherProgress
from apps.tenants.models import AuditLog, Tenant
from apps.translations.models import (
    ContentTranslation,
    FIELD_BODY,
    FIELD_DESCRIPTION,
    FIELD_TITLE,
    FIELD_TRANSCRIPT,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_PENDING,
    REVIEW_STATUS_REJECTED,
    SOURCE_TYPE_CONTENT,
)

try:
    from django.contrib.auth import get_user_model
    User = get_user_model()
except Exception:
    User = None


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_tenant(name: str = "Review School", subdomain: str = "reviewschool") -> Tenant:
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.test",
        is_active=True,
    )


def _make_admin(tenant: Tenant) -> "User":
    return User.objects.create_user(
        email=f"admin@{tenant.subdomain}.test",
        password="AdminP@ss1234!",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


def _make_teacher(tenant: Tenant, idx: int = 1) -> "User":
    return User.objects.create_user(
        email=f"teacher{idx}@{tenant.subdomain}.test",
        password="Tpass@word123!",
        first_name="Teach",
        last_name=str(idx),
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


def _make_course(tenant: Tenant, admin: "User") -> Course:
    return Course.objects.create(
        tenant=tenant,
        title="Biology 101",
        slug=f"bio-{uuid.uuid4().hex[:8]}",
        description="An intro to biology.",
        created_by=admin,
        is_published=True,
        is_active=True,
    )


def _make_module(course: Course) -> Module:
    return Module.objects.create(
        course=course,
        title="Cells",
        description="",
        order=1,
        is_active=True,
    )


def _make_content(module: Module, title: str = "Photosynthesis") -> Content:
    return Content.objects.create(
        module=module,
        title=title,
        content_type="TEXT",
        order=1,
        text_content="Plants convert light.",
        is_mandatory=True,
        is_active=True,
    )


def _make_translation_row(
    tenant: Tenant,
    content: Content,
    field: str = FIELD_TITLE,
    lang: str = "es",
    review_status: str = REVIEW_STATUS_PENDING,
    published_at=None,
) -> ContentTranslation:
    return ContentTranslation.objects.all_tenants().create(
        tenant=tenant,
        source_type=SOURCE_TYPE_CONTENT,
        source_id=content.id,
        field=field,
        target_language=lang,
        translated_text=f"[TR:{lang}] {field}",
        provider="stub",
        model="stub-1",
        source_hash="h-" + field,
        review_status=review_status,
        published_at=published_at,
    )


def _authed_client(user: "User", tenant: Tenant) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    client.credentials(HTTP_HOST=f"{tenant.subdomain}.localhost")
    return client


# ---------------------------------------------------------------------------
# Base test case with shared fixtures
# ---------------------------------------------------------------------------


@override_settings(TRANSLATION_TARGET_LANGUAGES="es,fr,de,hi,zh-CN,ar")
class ReviewBaseTestCase(TestCase):
    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_admin(self.tenant)
        self.course = _make_course(self.tenant, self.admin)
        self.module = _make_module(self.course)
        self.content = _make_content(self.module)
        self.row = _make_translation_row(self.tenant, self.content, field=FIELD_TITLE, lang="es")

    def _patch_tenant(self, tenant=None):
        return patch(
            "utils.tenant_middleware.get_current_tenant",
            return_value=tenant or self.tenant,
        )

    def _approve_url(self, content_id=None, field="title"):
        cid = content_id or self.content.id
        return f"/api/v1/admin/translations/content/{cid}/fields/{field}/approve/?lang=es"

    def _reject_url(self, content_id=None, field="title"):
        cid = content_id or self.content.id
        return f"/api/v1/admin/translations/content/{cid}/fields/{field}/reject/?lang=es"

    def _edit_url(self, content_id=None, field="title"):
        cid = content_id or self.content.id
        return f"/api/v1/admin/translations/content/{cid}/fields/{field}/edit/?lang=es"

    def _publish_url(self, content_id=None):
        cid = content_id or self.content.id
        return f"/api/v1/admin/translations/content/{cid}/publish/?lang=es"


# ---------------------------------------------------------------------------
# T01. Approve happy path
# ---------------------------------------------------------------------------


class TestApproveHappyPath(ReviewBaseTestCase):
    def test_approve_returns_200_and_updates_status(self):
        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                self._approve_url(),
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["review_status"], REVIEW_STATUS_APPROVED)
        self.assertIsNotNone(data["reviewed_at"])
        self.assertIsNotNone(data["reviewed_by"])

        self.row.refresh_from_db()
        self.assertEqual(self.row.review_status, REVIEW_STATUS_APPROVED)
        self.assertEqual(self.row.reviewed_by_id, self.admin.id)

        # Audit row
        self.assertTrue(
            AuditLog.objects.filter(
                tenant=self.tenant,
                action="TRANSLATION_FIELD_APPROVED",
                target_type="ContentTranslation",
                target_id=str(self.row.id),
            ).exists()
        )


# ---------------------------------------------------------------------------
# T02. Reject happy path
# ---------------------------------------------------------------------------


class TestRejectHappyPath(ReviewBaseTestCase):
    def test_reject_returns_200_and_updates_status(self):
        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                self._reject_url(),
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["review_status"], REVIEW_STATUS_REJECTED)

        self.row.refresh_from_db()
        self.assertEqual(self.row.review_status, REVIEW_STATUS_REJECTED)

        # Audit row
        self.assertTrue(
            AuditLog.objects.filter(
                tenant=self.tenant,
                action="TRANSLATION_FIELD_REJECTED",
                target_type="ContentTranslation",
                target_id=str(self.row.id),
            ).exists()
        )


# ---------------------------------------------------------------------------
# T03. Edit happy path
# ---------------------------------------------------------------------------


class TestEditHappyPath(ReviewBaseTestCase):
    def test_edit_returns_200_saves_edited_text_and_approves(self):
        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                self._edit_url(),
                data={"edited_text": "Fotosíntesis corregida"},
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["review_status"], REVIEW_STATUS_APPROVED)
        self.assertEqual(data["edited_text"], "Fotosíntesis corregida")

        self.row.refresh_from_db()
        self.assertEqual(self.row.edited_text, "Fotosíntesis corregida")
        self.assertEqual(self.row.review_status, REVIEW_STATUS_APPROVED)

        # Audit row
        self.assertTrue(
            AuditLog.objects.filter(
                tenant=self.tenant,
                action="TRANSLATION_FIELD_EDITED",
                target_type="ContentTranslation",
                target_id=str(self.row.id),
            ).exists()
        )


# ---------------------------------------------------------------------------
# T04. Publish happy path
# ---------------------------------------------------------------------------


class TestPublishHappyPath(ReviewBaseTestCase):
    def test_publish_returns_200_with_correct_shape(self):
        # Approve the title row, leave description/body/transcript absent.
        self.row.review_status = REVIEW_STATUS_APPROVED
        self.row.save()

        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.post(
                self._publish_url(),
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIn("published_at", data)
        self.assertIsNotNone(data["published_at"])
        self.assertEqual(data["rows_published"], 1)
        # Non-existent fields land in skipped as 'not_translated'.
        self.assertEqual(data["skipped"][FIELD_DESCRIPTION], "not_translated")
        self.assertEqual(data["skipped"][FIELD_BODY], "not_translated")
        self.assertEqual(data["skipped"][FIELD_TRANSCRIPT], "not_translated")

        # Audit row
        self.assertTrue(
            AuditLog.objects.filter(
                tenant=self.tenant,
                action="TRANSLATION_PUBLISHED",
                target_type="Content",
                target_id=str(self.content.id),
            ).exists()
        )


# ---------------------------------------------------------------------------
# T05. Non-admin approve → 403
# ---------------------------------------------------------------------------


class TestNonAdminApprove(ReviewBaseTestCase):
    def test_teacher_approve_returns_403(self):
        teacher = _make_teacher(self.tenant)
        client = _authed_client(teacher, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                self._approve_url(),
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# T06. Non-admin reject → 403
# ---------------------------------------------------------------------------


class TestNonAdminReject(ReviewBaseTestCase):
    def test_teacher_reject_returns_403(self):
        teacher = _make_teacher(self.tenant, idx=2)
        client = _authed_client(teacher, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                self._reject_url(),
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# T07. Cross-tenant approve → 404 (not 403)
# ---------------------------------------------------------------------------


@override_settings(TRANSLATION_TARGET_LANGUAGES="es,fr,de,hi,zh-CN,ar")
class TestCrossTenantApprove(TestCase):
    def test_cross_tenant_returns_404_not_403(self):
        tenant_a = _make_tenant("TA", "ta-rv")
        tenant_b = _make_tenant("TB", "tb-rv")
        admin_a = _make_admin(tenant_a)
        admin_b = _make_admin(tenant_b)

        course_a = _make_course(tenant_a, admin_a)
        module_a = _make_module(course_a)
        content_a = _make_content(module_a)
        _make_translation_row(tenant_a, content_a)

        # Admin B tries to approve a translation belonging to tenant A's content.
        client = _authed_client(admin_b, tenant_b)
        with patch(
            "utils.tenant_middleware.get_current_tenant", return_value=tenant_b
        ):
            resp = client.put(
                f"/api/v1/admin/translations/content/{content_a.id}/fields/title/approve/?lang=es",
                HTTP_HOST=f"{tenant_b.subdomain}.localhost",
            )
        # Must be 404 — never 403.
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# T08. Audit log consolidation — all 4 action types emitted in a single flow
# ---------------------------------------------------------------------------


class TestAuditConsolidation(ReviewBaseTestCase):
    def test_all_four_audit_actions_emitted(self):
        """Run approve → reject → edit → publish and confirm 4 distinct audit rows."""
        client = _authed_client(self.admin, self.tenant)

        with self._patch_tenant():
            # approve
            client.put(self._approve_url(), HTTP_HOST=f"{self.tenant.subdomain}.localhost")
            # reject
            client.put(self._reject_url(), HTTP_HOST=f"{self.tenant.subdomain}.localhost")
            # edit (auto-approves)
            client.put(
                self._edit_url(),
                data={"edited_text": "Editado"},
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
            # publish (row is now approved)
            client.post(self._publish_url(), HTTP_HOST=f"{self.tenant.subdomain}.localhost")

        for action in (
            "TRANSLATION_FIELD_APPROVED",
            "TRANSLATION_FIELD_REJECTED",
            "TRANSLATION_FIELD_EDITED",
            "TRANSLATION_PUBLISHED",
        ):
            self.assertTrue(
                AuditLog.objects.filter(
                    tenant=self.tenant, action=action
                ).exists(),
                f"Expected audit row with action={action}",
            )


# ---------------------------------------------------------------------------
# T09. Publish skips rejected + pending rows
# ---------------------------------------------------------------------------


class TestPublishSkipsNonApproved(ReviewBaseTestCase):
    def setUp(self):
        super().setUp()
        # title row stays PENDING (self.row).
        # Add a rejected description row.
        self.rejected_row = _make_translation_row(
            self.tenant, self.content, field=FIELD_DESCRIPTION, lang="es",
            review_status=REVIEW_STATUS_REJECTED,
        )
        # Add an approved body row.
        self.approved_row = _make_translation_row(
            self.tenant, self.content, field=FIELD_BODY, lang="es",
            review_status=REVIEW_STATUS_APPROVED,
        )

    def test_publish_only_promotes_approved_rows(self):
        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.post(
                self._publish_url(),
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()

        # Only the approved body row should be published.
        self.assertEqual(data["rows_published"], 1)
        self.assertEqual(data["skipped"][FIELD_TITLE], REVIEW_STATUS_PENDING)
        self.assertEqual(data["skipped"][FIELD_DESCRIPTION], REVIEW_STATUS_REJECTED)
        self.assertEqual(data["skipped"][FIELD_TRANSCRIPT], "not_translated")

        # DB: body row has published_at, others do not.
        self.approved_row.refresh_from_db()
        self.assertIsNotNone(self.approved_row.published_at)

        self.row.refresh_from_db()
        self.assertIsNone(self.row.published_at)

        self.rejected_row.refresh_from_db()
        self.assertIsNone(self.rejected_row.published_at)


# ---------------------------------------------------------------------------
# T10. Publish rows_published count
# ---------------------------------------------------------------------------


class TestPublishRowCount(ReviewBaseTestCase):
    def setUp(self):
        super().setUp()
        # Approve the base title row.
        self.row.review_status = REVIEW_STATUS_APPROVED
        self.row.save()
        # Also create and approve a body row.
        self.body_row = _make_translation_row(
            self.tenant, self.content, field=FIELD_BODY, lang="es",
            review_status=REVIEW_STATUS_APPROVED,
        )

    def test_publish_count_matches_promoted_rows(self):
        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.post(
                self._publish_url(),
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["rows_published"], 2)
        # Both rows have published_at set.
        self.row.refresh_from_db()
        self.assertIsNotNone(self.row.published_at)
        self.body_row.refresh_from_db()
        self.assertIsNotNone(self.body_row.published_at)


# ---------------------------------------------------------------------------
# T11. Teacher endpoint excludes unpublished rows
# ---------------------------------------------------------------------------


@override_settings(TRANSLATION_TARGET_LANGUAGES="es,fr,de,hi,zh-CN,ar")
class TestTeacherExcludesUnpublished(TestCase):
    def setUp(self):
        self.tenant = _make_tenant("Teacher Pub School", "tpubschool")
        self.admin = _make_admin(self.tenant)
        self.teacher = _make_teacher(self.tenant)
        self.course = _make_course(self.tenant, self.admin)
        self.module = _make_module(self.course)
        self.content = _make_content(self.module)
        # Enroll teacher.
        TeacherProgress.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            course=self.course,
            content=self.content,
            status="NOT_STARTED",
        )
        # Pending (unpublished) title row.
        _make_translation_row(
            self.tenant, self.content, field=FIELD_TITLE, lang="es",
            review_status=REVIEW_STATUS_PENDING,
            published_at=None,
        )

    def test_teacher_sees_404_for_unpublished_translation(self):
        client = _authed_client(self.teacher, self.tenant)
        with patch(
            "utils.tenant_middleware.get_current_tenant", return_value=self.tenant
        ):
            resp = client.get(
                f"/api/v1/teacher/content/{self.content.id}/translation/?lang=es",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        # All rows are unpublished → 404.
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"], "TRANSLATION_NOT_AVAILABLE")


# ---------------------------------------------------------------------------
# T12. Teacher endpoint returns published rows
# ---------------------------------------------------------------------------


@override_settings(TRANSLATION_TARGET_LANGUAGES="es,fr,de,hi,zh-CN,ar")
class TestTeacherSeesPublishedRows(TestCase):
    def setUp(self):
        self.tenant = _make_tenant("Teacher Pub2 School", "tpub2school")
        self.admin = _make_admin(self.tenant)
        self.teacher = _make_teacher(self.tenant)
        self.course = _make_course(self.tenant, self.admin)
        self.module = _make_module(self.course)
        self.content = _make_content(self.module)
        TeacherProgress.all_objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            course=self.course,
            content=self.content,
            status="NOT_STARTED",
        )
        # Approved + published title row.
        _make_translation_row(
            self.tenant, self.content, field=FIELD_TITLE, lang="es",
            review_status=REVIEW_STATUS_APPROVED,
            published_at=timezone.now(),
        )

    def test_teacher_sees_200_for_published_translation(self):
        client = _authed_client(self.teacher, self.tenant)
        with patch(
            "utils.tenant_middleware.get_current_tenant", return_value=self.tenant
        ):
            resp = client.get(
                f"/api/v1/teacher/content/{self.content.id}/translation/?lang=es",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIn("[TR:es]", data["title"])


# ---------------------------------------------------------------------------
# T13. Purge (DELETE existing endpoint) cascades review state
# ---------------------------------------------------------------------------


class TestPurgeCascadesReviewState(ReviewBaseTestCase):
    def test_delete_removes_row_with_review_state(self):
        # Give the row some review state to verify it's truly gone.
        self.row.review_status = REVIEW_STATUS_APPROVED
        self.row.reviewed_by = self.admin
        self.row.reviewed_at = timezone.now()
        self.row.save()

        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.delete(
                f"/api/v1/admin/translations/content/{self.content.id}/?lang=es",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 200)
        # Row is gone — includes review state.
        self.assertFalse(
            ContentTranslation.objects.all_tenants()
            .filter(id=self.row.id)
            .exists()
        )


# ---------------------------------------------------------------------------
# T14. Edit endpoint validates missing edited_text → 400
# ---------------------------------------------------------------------------


class TestEditMissingBody(ReviewBaseTestCase):
    def test_edit_without_edited_text_returns_400(self):
        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                self._edit_url(),
                data={},
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 400)

    def test_edit_with_empty_string_returns_400(self):
        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                self._edit_url(),
                data={"edited_text": ""},
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# T15. Invalid field name in URL → 400
# ---------------------------------------------------------------------------


class TestInvalidFieldName(ReviewBaseTestCase):
    def test_unknown_field_approve_returns_400(self):
        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                f"/api/v1/admin/translations/content/{self.content.id}/fields/summary/approve/?lang=es",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"], "invalid_field")


# ---------------------------------------------------------------------------
# T16. TASK-064b M1 — edited_text exceeding 50 000 chars → 413 FIELD_TOO_LARGE
# ---------------------------------------------------------------------------


class TestEditFieldTooLarge(ReviewBaseTestCase):
    """TASK-064b M1: FieldEditSerializer max_length=50_000 guard.

    Verifies that POSTing an edited_text longer than 50 000 characters returns
    HTTP 413 with error='FIELD_TOO_LARGE', and that the DB row is NOT mutated.
    Also verifies that exactly 50 000 chars (boundary value) is still accepted.
    """

    def test_oversized_edited_text_returns_413(self):
        """50 001-character edited_text → 413, error='FIELD_TOO_LARGE'."""
        oversized = "a" * 50_001
        original_edited_text = self.row.edited_text  # None before any edit

        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                self._edit_url(),
                data={"edited_text": oversized},
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )

        self.assertEqual(resp.status_code, 413, resp.content)
        data = resp.json()
        self.assertEqual(data.get("error"), "FIELD_TOO_LARGE")

        # DB row must be unchanged — no partial write.
        self.row.refresh_from_db()
        self.assertEqual(self.row.edited_text, original_edited_text)

    def test_boundary_50000_chars_is_accepted(self):
        """Exactly 50 000-character edited_text → 200, row updated."""
        at_limit = "b" * 50_000

        client = _authed_client(self.admin, self.tenant)
        with self._patch_tenant():
            resp = client.put(
                self._edit_url(),
                data={"edited_text": at_limit},
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        self.row.refresh_from_db()
        self.assertEqual(len(self.row.edited_text), 50_000)


# ---------------------------------------------------------------------------
# T17. TASK-064b-f1 — Admin GET endpoint returns all 5 review fields
# ---------------------------------------------------------------------------


@override_settings(TRANSLATION_TARGET_LANGUAGES="es,fr,de,hi,zh-CN,ar")
class TestAdminGetIncludesReviewFields(TestCase):
    """Regression test for TASK-064b-f1.

    The admin GET /api/v1/admin/translations/content/{id}/?lang=xx must
    include all five TASK-064b review fields in each row item so that the
    frontend can hydrate reviewer identity and review_status on page load
    without falling back to a ``pending`` default.
    """

    def setUp(self):
        self.tenant = _make_tenant("Review Fields School", "rvfieldsschool")
        self.admin = _make_admin(self.tenant)
        self.course = _make_course(self.tenant, self.admin)
        self.module = _make_module(self.course)
        self.content = _make_content(self.module)

        # Row 1: approved with an edited correction
        now = timezone.now()
        self.row_approved = ContentTranslation.objects.all_tenants().create(
            tenant=self.tenant,
            source_type=SOURCE_TYPE_CONTENT,
            source_id=self.content.id,
            field=FIELD_TITLE,
            target_language="es",
            translated_text="[TR:es] title",
            edited_text="Fotosíntesis corregida",
            review_status=REVIEW_STATUS_APPROVED,
            reviewed_by=self.admin,
            reviewed_at=now,
            published_at=now,
            provider="stub",
            model="stub-1",
            source_hash="h-title",
        )

        # Row 2: pending with no review activity
        self.row_pending = _make_translation_row(
            self.tenant,
            self.content,
            field=FIELD_DESCRIPTION,
            lang="es",
            review_status=REVIEW_STATUS_PENDING,
        )

    def _get_url(self):
        return f"/api/v1/admin/translations/content/{self.content.id}/?lang=es"

    def test_admin_get_rows_include_all_five_review_fields(self):
        """All 5 review fields are present in each row of the admin GET response."""
        client = _authed_client(self.admin, self.tenant)
        with patch(
            "utils.tenant_middleware.get_current_tenant",
            return_value=self.tenant,
        ):
            resp = client.get(
                self._get_url(),
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()

        self.assertIn("rows", data)
        self.assertEqual(len(data["rows"]), 2)

        # Build a field → row map for deterministic assertions
        rows_by_field = {r["field"]: r for r in data["rows"]}

        # --- approved row assertions ---
        approved = rows_by_field[FIELD_TITLE]
        self.assertEqual(approved["review_status"], REVIEW_STATUS_APPROVED)
        self.assertEqual(approved["edited_text"], "Fotosíntesis corregida")
        self.assertIsNotNone(approved["reviewed_by"])
        self.assertEqual(approved["reviewed_by_email"], self.admin.email)
        self.assertIsNotNone(approved["reviewed_at"])
        self.assertIsNotNone(approved["published_at"])

        # --- pending row assertions — defaults are None / pending ---
        pending = rows_by_field[FIELD_DESCRIPTION]
        self.assertEqual(pending["review_status"], REVIEW_STATUS_PENDING)
        self.assertIsNone(pending["edited_text"])
        self.assertIsNone(pending["reviewed_by"])
        self.assertIsNone(pending["reviewed_by_email"])
        self.assertIsNone(pending["reviewed_at"])
        self.assertIsNone(pending["published_at"])

        # --- base serializer fields are still present (non-regression) ---
        for row in data["rows"]:
            for base_field in ("translated_text", "provider", "model", "source_hash"):
                self.assertIn(
                    base_field,
                    row,
                    f"Base field '{base_field}' missing from admin GET row",
                )
