# apps/users/tests_admin_views.py
"""
Tests for admin_views.py - teacher management admin endpoints.

Covers:
- teachers_list_view: GET with filters
- teacher_detail_view: GET, PATCH, DELETE
- deleted_teachers_list_view: GET
- restore_teacher_view: POST
- teachers_bulk_import_view: POST (CSV)
- teachers_bulk_action: POST (activate/deactivate/delete)
"""
import io
import csv

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.tenants.models import Tenant
from apps.users.models import User


HOST = "test.lms.com"


def _make_tenant(name, slug, subdomain, email):
    return Tenant.objects.create(
        name=name, slug=slug, subdomain=subdomain, email=email, is_active=True
    )


def _make_user(email, tenant, role="TEACHER", active=True, first="Test", last="User"):
    return User.objects.create_user(
        email=email,
        password="Pass!1234",
        first_name=first,
        last_name=last,
        tenant=tenant,
        role=role,
        is_active=active,
    )


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TeachersListViewTestCase(TestCase):
    """Tests for GET /api/v1/teachers/"""

    def setUp(self):
        self.tenant = _make_tenant("Test School", "ts-list", "test", "admin@test.com")
        self.admin = _make_user("admin@test.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher1 = _make_user("t1@test.com", self.tenant, role="TEACHER", first="Alice", last="Smith")
        self.teacher2 = _make_user("t2@test.com", self.tenant, role="HOD", first="Bob", last="Jones")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.client.defaults["HTTP_HOST"] = HOST

    def test_list_teachers_returns_200(self):
        response = self.client.get("/api/v1/teachers/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_list_teachers_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.get("/api/v1/teachers/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_teachers_teacher_role_returns_403(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher1)
        response = client.get("/api/v1/teachers/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_teachers_excludes_admins(self):
        response = self.client.get("/api/v1/teachers/", HTTP_HOST=HOST)
        emails = [u["email"] for u in response.data.get("results", response.data)]
        self.assertNotIn("admin@test.com", emails)

    def test_filter_by_role(self):
        response = self.client.get("/api/v1/teachers/?role=HOD", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        for item in results:
            self.assertEqual(item["role"], "HOD")

    def test_filter_by_is_active_false(self):
        self.teacher2.is_active = False
        self.teacher2.save()
        response = self.client.get("/api/v1/teachers/?is_active=false", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        for item in results:
            self.assertFalse(item["is_active"])

    def test_search_by_name(self):
        response = self.client.get("/api/v1/teachers/?search=Alice", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertTrue(any(r["first_name"] == "Alice" for r in results))


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class TeacherDetailViewTestCase(TestCase):
    """Tests for GET/PATCH/DELETE /api/v1/teachers/<id>/"""

    def setUp(self):
        self.tenant = _make_tenant("Detail School", "ts-detail", "test", "dadmin@test.com")
        self.admin = _make_user("dadmin@test.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _make_user("teacher@test.com", self.tenant, role="TEACHER", first="Jane", last="Doe")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_get_teacher_returns_200(self):
        response = self.client.get(f"/api/v1/teachers/{self.teacher.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "teacher@test.com")

    def test_get_nonexistent_teacher_returns_404(self):
        import uuid
        response = self.client.get(f"/api/v1/teachers/{uuid.uuid4()}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_teacher_updates_name(self):
        response = self.client.patch(
            f"/api/v1/teachers/{self.teacher.id}/",
            {"first_name": "Janet"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.first_name, "Janet")

    def test_patch_invalid_role_returns_400(self):
        response = self.client.patch(
            f"/api/v1/teachers/{self.teacher.id}/",
            {"role": "SCHOOL_ADMIN"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_valid_role_change(self):
        response = self.client.patch(
            f"/api/v1/teachers/{self.teacher.id}/",
            {"role": "HOD"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.teacher.refresh_from_db()
        self.assertEqual(self.teacher.role, "HOD")

    def test_delete_teacher_soft_deletes(self):
        response = self.client.delete(f"/api/v1/teachers/{self.teacher.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.is_deleted)

    def test_cannot_modify_admin_via_detail_endpoint(self):
        other_admin = _make_user("admin2@test.com", self.tenant, role="SCHOOL_ADMIN")
        response = self.client.get(f"/api/v1/teachers/{other_admin.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class DeletedTeachersListViewTestCase(TestCase):
    """Tests for GET /api/v1/teachers/deleted/"""

    def setUp(self):
        self.tenant = _make_tenant("Del School", "ts-del", "test", "deladmin@test.com")
        self.admin = _make_user("deladmin@test.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _make_user("dtch@test.com", self.tenant, role="TEACHER")
        self.teacher.delete(deleted_by=self.admin)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_list_deleted_returns_200(self):
        response = self.client.get("/api/v1/teachers/deleted/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_deleted_teacher_appears_in_list(self):
        response = self.client.get("/api/v1/teachers/deleted/", HTTP_HOST=HOST)
        results = response.data.get("results", response.data)
        emails = [item["email"] for item in results]
        self.assertIn("dtch@test.com", emails)

    def test_search_deleted_teachers(self):
        response = self.client.get("/api/v1/teachers/deleted/?search=dtch", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class RestoreTeacherViewTestCase(TestCase):
    """Tests for POST /api/v1/teachers/<id>/restore/"""

    def setUp(self):
        self.tenant = _make_tenant("Restore School", "ts-restore", "test", "restadmin@test.com")
        self.admin = _make_user("restadmin@test.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _make_user("restore@test.com", self.tenant, role="TEACHER")
        self.teacher.delete(deleted_by=self.admin)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_restore_teacher_returns_200(self):
        response = self.client.post(f"/api/v1/teachers/{self.teacher.id}/restore/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_restore_teacher_reactivates(self):
        self.client.post(f"/api/v1/teachers/{self.teacher.id}/restore/", HTTP_HOST=HOST)
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.is_deleted)

    def test_restore_nonexistent_teacher_returns_404(self):
        import uuid
        response = self.client.post(f"/api/v1/teachers/{uuid.uuid4()}/restore/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class BulkImportViewTestCase(TestCase):
    """Tests for POST /api/v1/teachers/bulk-import/"""

    def setUp(self):
        self.tenant = _make_tenant("Import School", "ts-import", "test", "importadmin@test.com")
        self.tenant.max_teachers = 100
        self.tenant.save()
        self.admin = _make_user("importadmin@test.com", self.tenant, role="SCHOOL_ADMIN")
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _make_csv(self, rows):
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["email", "first_name", "last_name", "password"])
        writer.writeheader()
        writer.writerows(rows)
        buf.seek(0)
        return io.BytesIO(buf.read().encode("utf-8"))

    def test_bulk_import_requires_file(self):
        response = self.client.post("/api/v1/teachers/bulk-import/", {}, HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_bulk_import_creates_teachers(self):
        csv_file = self._make_csv([
            {"email": "bulk1@test.com", "first_name": "Bulk", "last_name": "One", "password": "Pass!123"},
            {"email": "bulk2@test.com", "first_name": "Bulk", "last_name": "Two", "password": "Pass!123"},
        ])
        response = self.client.post(
            "/api/v1/teachers/bulk-import/",
            {"file": csv_file},
            HTTP_HOST=HOST,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 2)

    def test_bulk_import_skips_duplicate_email(self):
        # Create one first
        _make_user("dup@test.com", self.tenant, role="TEACHER")
        csv_file = self._make_csv([
            {"email": "dup@test.com", "first_name": "Dup", "last_name": "User", "password": "Pass!123"},
        ])
        response = self.client.post(
            "/api/v1/teachers/bulk-import/",
            {"file": csv_file},
            HTTP_HOST=HOST,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 0)

    def test_bulk_import_skips_row_missing_email(self):
        csv_file = self._make_csv([
            {"email": "", "first_name": "No", "last_name": "Email", "password": "Pass!123"},
        ])
        response = self.client.post(
            "/api/v1/teachers/bulk-import/",
            {"file": csv_file},
            HTTP_HOST=HOST,
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 0)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class BulkActionViewTestCase(TestCase):
    """Tests for POST /api/v1/teachers/bulk-action/"""

    def setUp(self):
        self.tenant = _make_tenant("Bulk School", "ts-bulk", "test", "bulkadmin@test.com")
        self.admin = _make_user("bulkadmin@test.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher1 = _make_user("ba1@test.com", self.tenant, role="TEACHER", active=False)
        self.teacher2 = _make_user("ba2@test.com", self.tenant, role="TEACHER", active=True)
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_bulk_activate_teachers(self):
        response = self.client.post(
            "/api/v1/teachers/bulk-action/",
            {"action": "activate", "teacher_ids": [str(self.teacher1.id)]},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.teacher1.refresh_from_db()
        self.assertTrue(self.teacher1.is_active)

    def test_bulk_deactivate_teachers(self):
        response = self.client.post(
            "/api/v1/teachers/bulk-action/",
            {"action": "deactivate", "teacher_ids": [str(self.teacher2.id)]},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.teacher2.refresh_from_db()
        self.assertFalse(self.teacher2.is_active)

    def test_bulk_delete_teachers(self):
        response = self.client.post(
            "/api/v1/teachers/bulk-action/",
            {"action": "delete", "teacher_ids": [str(self.teacher1.id)]},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.teacher1.refresh_from_db()
        self.assertTrue(self.teacher1.is_deleted)

    def test_invalid_action_returns_400(self):
        response = self.client.post(
            "/api/v1/teachers/bulk-action/",
            {"action": "promote", "teacher_ids": [str(self.teacher1.id)]},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_teacher_ids_returns_400(self):
        response = self.client.post(
            "/api/v1/teachers/bulk-action/",
            {"action": "activate", "teacher_ids": []},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_nonexistent_ids_returns_404(self):
        import uuid
        response = self.client.post(
            "/api/v1/teachers/bulk-action/",
            {"action": "activate", "teacher_ids": [str(uuid.uuid4())]},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
