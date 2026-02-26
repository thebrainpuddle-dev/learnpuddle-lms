# apps/uploads/tests.py

import io
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User


@override_settings(ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"], PLATFORM_DOMAIN="lms.com")
class UploadValidationTestCase(TestCase):
    """Tests for file upload type and size validation."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Test School", slug="test-school-up", subdomain="test",
            email="t@t.com", is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@test-up.com", password="admin12345",
            first_name="A", last_name="A", tenant=self.tenant, role="SCHOOL_ADMIN",
        )
        self._login()

    def _login(self):
        resp = self.client.post("/api/users/auth/login/", {
            "email": "admin@test-up.com", "password": "admin12345"
        }, HTTP_HOST="test.lms.com")
        token = resp.data["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def _post(self, url, data, **kwargs):
        return self.client.post(url, data, format="multipart", HTTP_HOST="test.lms.com", **kwargs)

    def _make_file(self, name="test.png", content=b"PNG_DATA", content_type="image/png"):
        f = io.BytesIO(content)
        f.name = name
        f.content_type = content_type
        return f

    def test_upload_logo_valid_image(self):
        f = self._make_file("logo.png", b"\x89PNG\r\n", "image/png")
        resp = self._post("/api/uploads/tenant-logo/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.data)

    def test_upload_logo_rejects_exe(self):
        f = self._make_file("malware.exe", b"MZ\x90", "application/x-executable")
        resp = self._post("/api/uploads/tenant-logo/", {"file": f})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not allowed", resp.data["error"])

    def test_upload_logo_rejects_svg(self):
        f = self._make_file("logo.svg", b"<svg>", "image/svg+xml")
        resp = self._post("/api/uploads/tenant-logo/", {"file": f})
        self.assertEqual(resp.status_code, 400)

    def test_upload_thumbnail_rejects_html(self):
        f = self._make_file("page.html", b"<html>", "text/html")
        resp = self._post("/api/uploads/course-thumbnail/", {"file": f})
        self.assertEqual(resp.status_code, 400)

    def test_upload_content_valid_pdf(self):
        f = self._make_file("doc.pdf", b"%PDF-1.4", "application/pdf")
        resp = self._post("/api/uploads/content-file/", {"file": f})
        self.assertEqual(resp.status_code, 201)

    def test_upload_content_rejects_php(self):
        f = self._make_file("shell.php", b"<?php", "application/x-httpd-php")
        resp = self._post("/api/uploads/content-file/", {"file": f})
        self.assertEqual(resp.status_code, 400)

    def test_upload_missing_file_400(self):
        resp = self._post("/api/uploads/tenant-logo/", {})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error"], "file is required")
