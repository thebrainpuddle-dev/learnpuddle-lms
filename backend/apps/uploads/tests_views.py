# apps/uploads/tests_views.py
#
# Tests for upload view endpoints:
#   - Successful file upload (course thumbnail, content file)
#   - File too large rejection
#   - Invalid MIME type rejection
#   - Unauthenticated upload attempt (401)
#   - Teacher role attempting admin-only upload (403)
#   - Tenant isolation on uploads

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User


HOST = "test.lms.com"


def _make_image(name="test.png", size=100, content_type="image/png"):
    """Create a small fake PNG file for upload tests."""
    # Minimal PNG header (8 bytes) followed by padding
    png_header = b"\x89PNG\r\n\x1a\n"
    content = png_header + b"\x00" * max(0, size - len(png_header))
    return SimpleUploadedFile(name, content, content_type=content_type)


def _make_pdf(name="test.pdf", size=200):
    """Create a small fake PDF file for upload tests."""
    content = b"%PDF-1.4" + b"\x00" * max(0, size - 8)
    return SimpleUploadedFile(name, content, content_type="application/pdf")


# ===========================================================================
# Course thumbnail upload
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
    DEFAULT_FILE_STORAGE="django.core.files.storage.InMemoryStorage",
)
class CourseThumbnailUploadTestCase(TestCase):
    """Tests for POST /api/uploads/course-thumbnail/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Upload School",
            slug="upload-school",
            subdomain="test",
            email="upload@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@upload.test",
            password="admin123",
            first_name="Admin",
            last_name="Upload",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@upload.test",
            password="teacher123",
            first_name="Teacher",
            last_name="Upload",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _upload(self, file_obj, user=None):
        if user:
            self.client.force_authenticate(user=user)
        return self.client.post(
            "/api/uploads/course-thumbnail/",
            {"file": file_obj},
            format="multipart",
            HTTP_HOST=HOST,
        )

    def test_admin_can_upload_thumbnail(self):
        f = _make_image("thumb.png", size=500)
        resp = self._upload(f, user=self.admin)
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.json())

    def test_upload_jpeg_thumbnail(self):
        f = _make_image("thumb.jpg", size=500, content_type="image/jpeg")
        resp = self._upload(f, user=self.admin)
        self.assertEqual(resp.status_code, 201)

    def test_upload_webp_thumbnail(self):
        f = _make_image("thumb.webp", size=500, content_type="image/webp")
        resp = self._upload(f, user=self.admin)
        self.assertEqual(resp.status_code, 201)

    def test_unauthenticated_upload_returns_401(self):
        f = _make_image()
        resp = self.client.post(
            "/api/uploads/course-thumbnail/",
            {"file": f},
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(resp.status_code, 401)

    def test_teacher_cannot_upload_thumbnail(self):
        """Course thumbnail upload is admin_only — teachers get 403."""
        f = _make_image()
        resp = self._upload(f, user=self.teacher)
        self.assertEqual(resp.status_code, 403)

    def test_invalid_mime_type_returns_400(self):
        bad_file = SimpleUploadedFile(
            "malware.exe",
            b"\x00" * 100,
            content_type="application/x-msdownload",
        )
        resp = self._upload(bad_file, user=self.admin)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_file_too_large_returns_400(self):
        # MAX_IMAGE_SIZE_MB is 5, so create a ~6 MB file
        large_file = _make_image("big.png", size=6 * 1024 * 1024)
        resp = self._upload(large_file, user=self.admin)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())
        self.assertIn("too large", resp.json()["error"].lower())

    def test_missing_file_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/uploads/course-thumbnail/",
            {},
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())


# ===========================================================================
# Content file upload
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
    DEFAULT_FILE_STORAGE="django.core.files.storage.InMemoryStorage",
)
class ContentFileUploadTestCase(TestCase):
    """Tests for POST /api/uploads/content-file/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Content Upload School",
            slug="content-upload-school",
            subdomain="test",
            email="contentup@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@contentup.test",
            password="admin123",
            first_name="Admin",
            last_name="Content",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@contentup.test",
            password="teacher123",
            first_name="Teacher",
            last_name="Content",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def _upload(self, file_obj, user=None, content_id=None):
        if user:
            self.client.force_authenticate(user=user)
        url = "/api/uploads/content-file/"
        if content_id:
            url += f"?content_id={content_id}"
        return self.client.post(
            url,
            {"file": file_obj},
            format="multipart",
            HTTP_HOST=HOST,
        )

    def test_admin_can_upload_pdf(self):
        f = _make_pdf("document.pdf", size=500)
        resp = self._upload(f, user=self.admin, content_id="content-1")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.json())

    def test_admin_can_upload_image_as_content(self):
        f = _make_image("diagram.png", size=300)
        resp = self._upload(f, user=self.admin)
        self.assertEqual(resp.status_code, 201)

    def test_invalid_mime_type_returns_400(self):
        bad_file = SimpleUploadedFile(
            "script.sh",
            b"#!/bin/bash\necho hacked",
            content_type="application/x-sh",
        )
        resp = self._upload(bad_file, user=self.admin)
        self.assertEqual(resp.status_code, 400)

    def test_file_too_large_returns_400(self):
        # MAX_CONTENT_SIZE_MB is 50, so create a ~51 MB file
        large_pdf = _make_pdf("huge.pdf", size=51 * 1024 * 1024)
        resp = self._upload(large_pdf, user=self.admin)
        self.assertEqual(resp.status_code, 400)
        self.assertIn("too large", resp.json()["error"].lower())

    def test_unauthenticated_upload_returns_401(self):
        f = _make_pdf()
        resp = self.client.post(
            "/api/uploads/content-file/",
            {"file": f},
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(resp.status_code, 401)

    def test_missing_file_returns_400(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.post(
            "/api/uploads/content-file/",
            {},
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# Tenant logo upload
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
    DEFAULT_FILE_STORAGE="django.core.files.storage.InMemoryStorage",
)
class TenantLogoUploadTestCase(TestCase):
    """Tests for POST /api/uploads/tenant-logo/."""

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Logo School",
            slug="logo-school",
            subdomain="test",
            email="logo@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@logo.test",
            password="admin123",
            first_name="Admin",
            last_name="Logo",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@logo.test",
            password="teacher123",
            first_name="Teacher",
            last_name="Logo",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

    def test_admin_can_upload_logo(self):
        self.client.force_authenticate(user=self.admin)
        f = _make_image("logo.png", size=400)
        resp = self.client.post(
            "/api/uploads/tenant-logo/",
            {"file": f},
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.json())

    def test_teacher_cannot_upload_logo(self):
        self.client.force_authenticate(user=self.teacher)
        f = _make_image("logo.png", size=400)
        resp = self.client.post(
            "/api/uploads/tenant-logo/",
            {"file": f},
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(resp.status_code, 403)


# ===========================================================================
# Tenant isolation
# ===========================================================================


@override_settings(
    ALLOWED_HOSTS=["test.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
    DEFAULT_FILE_STORAGE="django.core.files.storage.InMemoryStorage",
)
class UploadTenantIsolationTestCase(TestCase):
    """
    Verify that uploads are stored in tenant-scoped paths.
    Each uploaded file path should contain the tenant ID.
    """

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Iso School",
            slug="iso-school",
            subdomain="test",
            email="iso@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@iso.test",
            password="admin123",
            first_name="Admin",
            last_name="Iso",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.client.force_authenticate(user=self.admin)

    def test_thumbnail_url_contains_tenant_id(self):
        f = _make_image("check.png", size=200)
        resp = self.client.post(
            "/api/uploads/course-thumbnail/",
            {"file": f},
            format="multipart",
            HTTP_HOST=HOST,
        )
        self.assertEqual(resp.status_code, 201)
        url = resp.json()["url"]
        # The storage path helper includes the tenant ID in the URL
        self.assertIn(str(self.tenant.id), url)
