# tests/uploads/test_upload_validation.py
"""
Tests for file upload endpoints and validation.

Covers:
- POST /api/v1/uploads/tenant-logo/        — PNG/SVG logo upload
- POST /api/v1/uploads/course-thumbnail/   — Course thumbnail upload
- POST /api/v1/uploads/content-file/       — Document/content file upload

Validation rules tested:
- Missing file → 400
- Invalid extension → 400
- Invalid MIME type → 400
- Oversized file → 400
- Authentication required → 401
- Admin/teacher permissions enforced → 403
- Valid upload → 201 with URL in response

Also covers the internal _validate_upload helper function directly.
"""

from io import BytesIO

from django.test import TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.uploads.views import _validate_upload, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, subdomain):
    return Tenant.objects.create(
        name=name, slug=subdomain, subdomain=subdomain,
        email=f"{subdomain}@example.com", is_active=True,
    )


def _make_user(email, tenant, role="SCHOOL_ADMIN"):
    return User.objects.create_user(
        email=email, password="Pass!123",
        first_name="Test", last_name="User",
        tenant=tenant, role=role, is_active=True,
    )


def _fake_png(size_bytes=1024):
    """Return a SimpleUploadedFile that looks like a small PNG image."""
    return SimpleUploadedFile(
        "test.png",
        b"x" * size_bytes,
        content_type="image/png",
    )


def _fake_pdf(size_bytes=1024):
    """Return a SimpleUploadedFile that looks like a small PDF."""
    return SimpleUploadedFile(
        "document.pdf",
        b"x" * size_bytes,
        content_type="application/pdf",
    )


def _client_for(user, tenant_subdomain):
    c = APIClient()
    c.force_authenticate(user=user)
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


def _anon_client(tenant_subdomain):
    c = APIClient()
    c.defaults["HTTP_HOST"] = f"{tenant_subdomain}.lms.com"
    return c


# ===========================================================================
# 1. Unit Tests — _validate_upload helper
# ===========================================================================

class UploadValidationHelperTestCase(TestCase):
    """
    Direct tests of the _validate_upload() helper function.
    No DB or HTTP requests — pure logic tests.
    """

    def test_valid_png_file_passes_validation(self):
        f = _fake_png()
        ok, err = _validate_upload(f, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, 5)
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_invalid_extension_fails_validation(self):
        f = SimpleUploadedFile("script.exe", b"content", content_type="application/octet-stream")
        ok, err = _validate_upload(f, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, 5)
        self.assertFalse(ok)
        self.assertIn(".exe", err)

    def test_invalid_mime_type_fails_validation(self):
        f = SimpleUploadedFile("hack.png", b"content", content_type="application/x-php")
        ok, err = _validate_upload(f, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, 5)
        self.assertFalse(ok)
        self.assertIn("MIME", err)

    def test_oversized_file_fails_validation(self):
        max_mb = 1
        oversized = SimpleUploadedFile(
            "big.png",
            b"x" * (max_mb * 1024 * 1024 + 1),
            content_type="image/png",
        )
        ok, err = _validate_upload(oversized, ALLOWED_IMAGE_EXTENSIONS,
                                   ALLOWED_IMAGE_MIMES, max_size_mb=max_mb)
        self.assertFalse(ok)
        self.assertIn("large", err.lower())

    def test_file_within_size_limit_passes(self):
        within_limit = SimpleUploadedFile(
            "small.png",
            b"x" * 100,
            content_type="image/png",
        )
        ok, err = _validate_upload(
            within_limit,
            ALLOWED_IMAGE_EXTENSIONS,
            ALLOWED_IMAGE_MIMES,
            max_size_mb=5,
        )
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_file_without_extension_or_mime_fails(self):
        f = SimpleUploadedFile("noextension", b"data", content_type="")
        ok, err = _validate_upload(f, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, 5)
        self.assertFalse(ok)

    def test_jpeg_file_passes_validation(self):
        f = SimpleUploadedFile("photo.jpg", b"x" * 512, content_type="image/jpeg")
        ok, err = _validate_upload(f, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, 5)
        self.assertTrue(ok)

    def test_webp_file_passes_validation(self):
        f = SimpleUploadedFile("image.webp", b"x" * 512, content_type="image/webp")
        ok, err = _validate_upload(f, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_IMAGE_MIMES, 5)
        self.assertTrue(ok)


# ===========================================================================
# 2. Course Thumbnail Upload Endpoint
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
    MEDIA_ROOT="/tmp/test_media_uploads/",
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    },
)
class CourseThumbnailUploadTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Upload School", "upload")
        self.admin = _make_user("admin@upload.com", self.tenant)
        self.teacher = _make_user("teacher@upload.com", self.tenant, role="TEACHER")

    def test_upload_thumbnail_requires_authentication(self):
        c = _anon_client("upload")
        r = c.post(
            "/api/v1/uploads/course-thumbnail/",
            {"file": _fake_png()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 401)

    def test_upload_thumbnail_requires_admin_role(self):
        """Teachers must not upload course thumbnails (admin-only endpoint)."""
        c = _client_for(self.teacher, "upload")
        r = c.post(
            "/api/v1/uploads/course-thumbnail/",
            {"file": _fake_png()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 403)

    def test_upload_thumbnail_without_file_returns_400(self):
        c = _client_for(self.admin, "upload")
        r = c.post("/api/v1/uploads/course-thumbnail/", {}, format="multipart")
        self.assertEqual(r.status_code, 400)
        self.assertIn("file", str(r.data).lower())

    def test_upload_thumbnail_with_invalid_extension_returns_400(self):
        f = SimpleUploadedFile("hack.exe", b"data", content_type="application/octet-stream")
        c = _client_for(self.admin, "upload")
        r = c.post(
            "/api/v1/uploads/course-thumbnail/",
            {"file": f},
            format="multipart",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("error", r.data)

    def test_upload_thumbnail_with_invalid_mime_type_returns_400(self):
        f = SimpleUploadedFile("hack.png", b"data", content_type="application/x-php")
        c = _client_for(self.admin, "upload")
        r = c.post(
            "/api/v1/uploads/course-thumbnail/",
            {"file": f},
            format="multipart",
        )
        self.assertEqual(r.status_code, 400)

    def test_upload_thumbnail_with_oversized_file_returns_400(self):
        """Thumbnails have a 5MB limit."""
        oversized = SimpleUploadedFile(
            "big.png",
            b"x" * (6 * 1024 * 1024),  # 6 MB > 5 MB limit
            content_type="image/png",
        )
        c = _client_for(self.admin, "upload")
        r = c.post(
            "/api/v1/uploads/course-thumbnail/",
            {"file": oversized},
            format="multipart",
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("large", r.data.get("error", "").lower())

    def test_upload_thumbnail_with_valid_png_returns_201(self):
        c = _client_for(self.admin, "upload")
        r = c.post(
            "/api/v1/uploads/course-thumbnail/",
            {"file": _fake_png()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201)
        self.assertIn("url", r.data)

    def test_upload_thumbnail_returns_url_in_response(self):
        c = _client_for(self.admin, "upload")
        r = c.post(
            "/api/v1/uploads/course-thumbnail/",
            {"file": _fake_png()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201)
        url = r.data.get("url", "")
        self.assertTrue(url.startswith("http"), f"URL should be absolute, got: {url}")

    def test_upload_thumbnail_accepts_jpeg(self):
        f = SimpleUploadedFile("image.jpg", b"x" * 512, content_type="image/jpeg")
        c = _client_for(self.admin, "upload")
        r = c.post(
            "/api/v1/uploads/course-thumbnail/",
            {"file": f},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201)


# ===========================================================================
# 3. Content File (Document) Upload
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
    MEDIA_ROOT="/tmp/test_media_uploads/",
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    },
)
class ContentFileUploadTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Content School", "content")
        self.admin = _make_user("admin@content.com", self.tenant)

    def test_content_upload_requires_authentication(self):
        c = _anon_client("content")
        r = c.post(
            "/api/v1/uploads/content-file/",
            {"file": _fake_pdf()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 401)

    def test_content_upload_without_file_returns_400(self):
        c = _client_for(self.admin, "content")
        r = c.post("/api/v1/uploads/content-file/", {}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_content_upload_with_invalid_extension_returns_400(self):
        f = SimpleUploadedFile("virus.exe", b"data", content_type="application/octet-stream")
        c = _client_for(self.admin, "content")
        r = c.post(
            "/api/v1/uploads/content-file/",
            {"file": f},
            format="multipart",
        )
        self.assertEqual(r.status_code, 400)

    def test_content_upload_with_pdf_returns_201_for_admin(self):
        c = _client_for(self.admin, "content")
        r = c.post(
            "/api/v1/uploads/content-file/",
            {"file": _fake_pdf()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201)
        self.assertIn("url", r.data)

    def test_content_upload_with_docx_accepted(self):
        f = SimpleUploadedFile(
            "slides.docx", b"docx_data",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        c = _client_for(self.admin, "content")
        r = c.post(
            "/api/v1/uploads/content-file/",
            {"file": f},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201)

    def test_content_upload_with_pptx_accepted(self):
        f = SimpleUploadedFile(
            "slides.pptx", b"pptx_data",
            content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        c = _client_for(self.admin, "content")
        r = c.post(
            "/api/v1/uploads/content-file/",
            {"file": f},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201)


# ===========================================================================
# 4. Tenant Logo Upload
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["*"],
    PLATFORM_DOMAIN="lms.com",
    SECURE_SSL_REDIRECT=False,
    DEFAULT_FILE_STORAGE="django.core.files.storage.FileSystemStorage",
    MEDIA_ROOT="/tmp/test_media_uploads/",
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": {},
    },
)
class TenantLogoUploadTestCase(TestCase):

    def setUp(self):
        self.tenant = _make_tenant("Logo School", "logo")
        self.admin = _make_user("admin@logo.com", self.tenant)
        self.teacher = _make_user("teacher@logo.com", self.tenant, role="TEACHER")

    def test_logo_upload_requires_admin_role(self):
        c = _client_for(self.teacher, "logo")
        r = c.post(
            "/api/v1/uploads/tenant-logo/",
            {"file": _fake_png()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 403)

    def test_logo_upload_requires_authentication(self):
        c = _anon_client("logo")
        r = c.post(
            "/api/v1/uploads/tenant-logo/",
            {"file": _fake_png()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 401)

    def test_logo_upload_without_file_returns_400(self):
        c = _client_for(self.admin, "logo")
        r = c.post("/api/v1/uploads/tenant-logo/", {}, format="multipart")
        self.assertEqual(r.status_code, 400)

    def test_logo_upload_oversized_returns_400(self):
        """Logo limit is 5MB."""
        oversized = SimpleUploadedFile(
            "logo.png",
            b"x" * (6 * 1024 * 1024),
            content_type="image/png",
        )
        c = _client_for(self.admin, "logo")
        r = c.post(
            "/api/v1/uploads/tenant-logo/",
            {"file": oversized},
            format="multipart",
        )
        self.assertEqual(r.status_code, 400)

    def test_logo_upload_valid_png_returns_201(self):
        c = _client_for(self.admin, "logo")
        r = c.post(
            "/api/v1/uploads/tenant-logo/",
            {"file": _fake_png()},
            format="multipart",
        )
        self.assertEqual(r.status_code, 201)
        self.assertIn("url", r.data)
