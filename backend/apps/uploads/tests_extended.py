# apps/uploads/tests_extended.py
#
# Supplementary tests for the uploads app.
# These tests EXTEND (do NOT modify) the existing tests.py.
#
# Coverage added here:
#   - UploadAuthTestCase           : unauthenticated requests → 401
#   - UploadAdminOnlyTestCase      : TEACHER on admin-only endpoints → 403
#   - UploadFileSizeTestCase       : oversized file rejection + edge-case acceptance
#   - UploadValidTypeTestCase      : additional valid MIME/extension combos → 201
#   - EditorImageUploadTestCase    : full coverage of editor-image endpoint

import io

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import RichTextImageAsset
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Shared setUp mixin so each test class doesn't repeat boilerplate
# ---------------------------------------------------------------------------

class _UploadTestBase(TestCase):
    """
    Common fixtures shared across all upload test classes.
    Subclasses must apply @override_settings themselves (class-level decorator
    cannot be inherited in a useful way across separate test classes, so we
    keep the mixin free of it and let each concrete class declare it).
    """

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Upload School",
            slug="upload-school-ext",
            subdomain="upload",
            email="upload@test.example",
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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_file(self, name="test.png", content=b"PNG", content_type="image/png", size_bytes=None):
        if size_bytes is not None:
            data = b"X" * size_bytes
        else:
            data = content
        f = io.BytesIO(data)
        f.name = name
        f.content_type = content_type
        return f

    def _post(self, url, data=None, **extra):
        """POST multipart to the given URL with HTTP_HOST set to the test tenant."""
        return self.client.post(
            url,
            data or {},
            format="multipart",
            HTTP_HOST="upload.lms.com",
            **extra,
        )


# ===========================================================================
# 1. Unauthenticated access (all 4 endpoints → 401)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["upload.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class UploadAuthTestCase(_UploadTestBase):
    """All upload endpoints must reject unauthenticated requests with 401."""

    _ENDPOINTS = [
        "/api/uploads/tenant-logo/",
        "/api/uploads/course-thumbnail/",
        "/api/uploads/content-file/",
        "/api/uploads/editor-image/",
    ]

    def setUp(self):
        super().setUp()
        # Ensure no credentials are set
        self.client.force_authenticate(user=None)

    def test_tenant_logo_unauthenticated_returns_401(self):
        resp = self._post("/api/uploads/tenant-logo/")
        self.assertEqual(resp.status_code, 401)

    def test_course_thumbnail_unauthenticated_returns_401(self):
        resp = self._post("/api/uploads/course-thumbnail/")
        self.assertEqual(resp.status_code, 401)

    def test_content_file_unauthenticated_returns_401(self):
        resp = self._post("/api/uploads/content-file/")
        self.assertEqual(resp.status_code, 401)

    def test_editor_image_unauthenticated_returns_401(self):
        resp = self._post("/api/uploads/editor-image/")
        self.assertEqual(resp.status_code, 401)


# ===========================================================================
# 2. Admin-only enforcement (TEACHER → 403 on admin-only endpoints)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["upload.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class UploadAdminOnlyTestCase(_UploadTestBase):
    """
    logo and thumbnail endpoints are @admin_only.
    A TEACHER (role='TEACHER') must receive 403.
    """

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.teacher)

    def test_teacher_cannot_upload_tenant_logo(self):
        f = self._make_file("logo.png", b"\x89PNG\r\n", "image/png")
        resp = self._post("/api/uploads/tenant-logo/", {"file": f})
        self.assertEqual(resp.status_code, 403)

    def test_teacher_cannot_upload_course_thumbnail(self):
        f = self._make_file("thumb.png", b"\x89PNG\r\n", "image/png")
        resp = self._post("/api/uploads/course-thumbnail/", {"file": f})
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_upload_tenant_logo(self):
        """Sanity check: admin does NOT receive 403 on the same endpoint."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file("logo.png", b"\x89PNG\r\n", "image/png")
        resp = self._post("/api/uploads/tenant-logo/", {"file": f})
        self.assertNotEqual(resp.status_code, 403)

    def test_admin_can_upload_course_thumbnail(self):
        """Sanity check: admin does NOT receive 403 on the same endpoint."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file("thumb.png", b"\x89PNG\r\n", "image/png")
        resp = self._post("/api/uploads/course-thumbnail/", {"file": f})
        self.assertNotEqual(resp.status_code, 403)


# ===========================================================================
# 3. File-size validation
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["upload.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class UploadFileSizeTestCase(_UploadTestBase):
    """Tests for oversized file rejection and edge-case acceptance."""

    # MAX_IMAGE_SIZE_MB = 5  (applies to logo and thumbnail)
    # MAX_CONTENT_SIZE_MB = 50 (applies to content-file)
    _5MB = 5 * 1024 * 1024
    _50MB = 50 * 1024 * 1024

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def test_logo_over_5mb_rejected_with_file_too_large(self):
        """A logo that is 1 byte over 5 MB must be rejected with HTTP 400."""
        f = self._make_file(
            name="big-logo.png",
            content_type="image/png",
            size_bytes=self._5MB + 1,
        )
        resp = self._post("/api/uploads/tenant-logo/", {"file": f})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("File too large", resp.data.get("error", ""))

    def test_thumbnail_over_5mb_rejected_with_file_too_large(self):
        """A thumbnail that is 1 byte over 5 MB must be rejected with HTTP 400."""
        f = self._make_file(
            name="big-thumb.png",
            content_type="image/png",
            size_bytes=self._5MB + 1,
        )
        resp = self._post("/api/uploads/course-thumbnail/", {"file": f})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("File too large", resp.data.get("error", ""))

    def test_content_file_minimal_pdf_accepted(self):
        """A 1-byte PDF (edge-case minimal size) must be accepted with HTTP 201."""
        f = self._make_file(
            name="tiny.pdf",
            content=b"%",  # 1 byte — well under the 50 MB limit
            content_type="application/pdf",
        )
        resp = self._post("/api/uploads/content-file/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.data)

    def test_content_file_over_50mb_rejected(self):
        """A content file 1 byte over 50 MB must be rejected with HTTP 400."""
        f = self._make_file(
            name="huge-doc.pdf",
            content_type="application/pdf",
            size_bytes=self._50MB + 1,
        )
        resp = self._post("/api/uploads/content-file/", {"file": f})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("File too large", resp.data.get("error", ""))


# ===========================================================================
# 4. Additional valid file types not covered by existing tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["upload.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class UploadValidTypeTestCase(_UploadTestBase):
    """
    Valid MIME / extension combinations that are not yet exercised in tests.py.
    All should result in HTTP 201.
    """

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.admin)

    def test_thumbnail_valid_jpeg_accepted(self):
        f = self._make_file(
            name="thumb.jpg",
            content=b"\xff\xd8\xff",  # JPEG magic bytes
            content_type="image/jpeg",
        )
        resp = self._post("/api/uploads/course-thumbnail/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.data)

    def test_thumbnail_valid_webp_accepted(self):
        f = self._make_file(
            name="thumb.webp",
            content=b"RIFF\x00\x00\x00\x00WEBP",
            content_type="image/webp",
        )
        resp = self._post("/api/uploads/course-thumbnail/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.data)

    def test_content_file_docx_accepted(self):
        """DOCX files (Office Open XML) must be accepted for content uploads."""
        f = self._make_file(
            name="lesson.docx",
            content=b"PK\x03\x04",  # ZIP magic (DOCX is a ZIP-based format)
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            ),
        )
        resp = self._post("/api/uploads/content-file/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.data)

    def test_content_file_pptx_accepted(self):
        """PPTX files (Office Open XML) must be accepted for content uploads."""
        f = self._make_file(
            name="slides.pptx",
            content=b"PK\x03\x04",
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".presentationml.presentation"
            ),
        )
        resp = self._post("/api/uploads/content-file/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.data)

    def test_content_file_xlsx_accepted(self):
        """XLSX files (Office Open XML) must be accepted for content uploads."""
        f = self._make_file(
            name="data.xlsx",
            content=b"PK\x03\x04",
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )
        resp = self._post("/api/uploads/content-file/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.data)

    def test_content_file_plain_text_accepted(self):
        f = self._make_file(
            name="notes.txt",
            content=b"Hello, teacher!",
            content_type="text/plain",
        )
        resp = self._post("/api/uploads/content-file/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.data)

    def test_content_file_csv_accepted(self):
        f = self._make_file(
            name="results.csv",
            content=b"name,score\nAlice,95\n",
            content_type="text/csv",
        )
        resp = self._post("/api/uploads/content-file/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("url", resp.data)


# ===========================================================================
# 5. Editor image upload — zero existing tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=["upload.lms.com", "testserver", "localhost"],
    PLATFORM_DOMAIN="lms.com",
)
class EditorImageUploadTestCase(_UploadTestBase):
    """
    Comprehensive tests for /api/uploads/editor-image/.

    Behaviour under test:
    - Unauthenticated            → 401
    - Admin, valid PNG           → 201, correct response shape, DB record created
    - Admin, invalid type (PDF)  → 400
    - Admin, missing file        → 400
    - Teacher, no feature flag   → 403 with upgrade_required=True
    - Teacher, feature flag on   → 201
    - Editor-image size limit    → 400 for files > 8 MB (MAX_EDITOR_IMAGE_SIZE_MB)
    """

    _8MB = 8 * 1024 * 1024

    def setUp(self):
        super().setUp()

    # ------------------------------------------------------------------
    # Auth gate
    # ------------------------------------------------------------------

    def test_unauthenticated_returns_401(self):
        """No credentials → 401."""
        self.client.force_authenticate(user=None)
        resp = self._post("/api/uploads/editor-image/")
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------------
    # Admin — happy path
    # ------------------------------------------------------------------

    def test_admin_upload_valid_png_returns_201(self):
        """Admin with a valid PNG should receive 201 with the expected payload."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 201)

    def test_admin_upload_response_contains_asset_ref(self):
        """Response must include asset_ref starting with 'rtimg:'."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        asset_ref = resp.data.get("asset_ref", "")
        self.assertTrue(
            asset_ref.startswith("rtimg:"),
            msg=f"Expected asset_ref to start with 'rtimg:', got: {asset_ref!r}",
        )

    def test_admin_upload_response_contains_preview_url(self):
        """Response must include a non-empty preview_url."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("preview_url", resp.data)
        self.assertTrue(resp.data["preview_url"], "preview_url must not be empty")

    def test_admin_upload_response_contains_file_size(self):
        """Response must include file_size."""
        self.client.force_authenticate(user=self.admin)
        png_bytes = b"\x89PNG\r\n\x1a\n"
        f = self._make_file("inline.png", png_bytes, "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        self.assertIn("file_size", resp.data)

    def test_admin_upload_creates_db_record(self):
        """A successful upload must persist a RichTextImageAsset in the database."""
        self.client.force_authenticate(user=self.admin)
        before_count = RichTextImageAsset.all_objects.filter(tenant=self.tenant).count()
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        after_count = RichTextImageAsset.all_objects.filter(tenant=self.tenant).count()
        self.assertEqual(after_count, before_count + 1)

    def test_admin_upload_db_record_matches_asset_id(self):
        """The returned asset_id must correspond to a real DB record."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        asset_id = resp.data.get("asset_id")
        self.assertIsNotNone(asset_id)
        self.assertTrue(
            RichTextImageAsset.all_objects.filter(id=asset_id).exists(),
            msg=f"No RichTextImageAsset found with id={asset_id}",
        )

    # ------------------------------------------------------------------
    # Admin — rejection cases
    # ------------------------------------------------------------------

    def test_admin_upload_pdf_rejected_400(self):
        """PDF is not a valid image for the editor-image endpoint → 400."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file("doc.pdf", b"%PDF-1.4", "application/pdf")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.data)

    def test_admin_upload_svg_rejected_400(self):
        """SVG is not in ALLOWED_IMAGE_MIMES → 400."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file("icon.svg", b"<svg/>", "image/svg+xml")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 400)

    def test_admin_upload_missing_file_returns_400(self):
        """Omitting the file field entirely must return 400 with descriptive error."""
        self.client.force_authenticate(user=self.admin)
        resp = self._post("/api/uploads/editor-image/", {})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data.get("error"), "file is required")

    def test_admin_upload_over_8mb_rejected(self):
        """Images larger than 8 MB must be rejected for the editor endpoint."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file(
            name="massive.png",
            content_type="image/png",
            size_bytes=self._8MB + 1,
        )
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("File too large", resp.data.get("error", ""))

    def test_admin_upload_exactly_8mb_accepted(self):
        """A file that is exactly 8 MB (the limit) must be accepted."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file(
            name="exact-limit.png",
            content_type="image/png",
            size_bytes=self._8MB,
        )
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 201)

    # ------------------------------------------------------------------
    # Teacher — feature-flag gate
    # ------------------------------------------------------------------

    def test_teacher_without_feature_flag_gets_403(self):
        """
        A TEACHER whose tenant does NOT have feature_teacher_authoring enabled
        must receive 403 with upgrade_required=True.
        """
        self.tenant.feature_teacher_authoring = False
        self.tenant.save()
        self.client.force_authenticate(user=self.teacher)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(
            resp.data.get("upgrade_required"),
            msg="Expected upgrade_required=True in 403 response",
        )

    def test_teacher_with_feature_flag_can_upload(self):
        """
        A TEACHER whose tenant HAS feature_teacher_authoring=True must be
        able to upload editor images (HTTP 201).
        """
        self.tenant.feature_teacher_authoring = True
        self.tenant.save()
        self.client.force_authenticate(user=self.teacher)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        asset_ref = resp.data.get("asset_ref", "")
        self.assertTrue(asset_ref.startswith("rtimg:"))

    def test_teacher_with_feature_flag_response_shape(self):
        """
        When a teacher is permitted, the response payload must contain all
        required fields: asset_id, asset_ref, preview_url, file_size.
        """
        self.tenant.feature_teacher_authoring = True
        self.tenant.save()
        self.client.force_authenticate(user=self.teacher)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 201)
        for field in ("asset_id", "asset_ref", "preview_url", "file_size"):
            self.assertIn(
                field,
                resp.data,
                msg=f"Response missing expected field: {field!r}",
            )

    def test_teacher_without_flag_no_db_record_created(self):
        """A rejected teacher upload must NOT create a RichTextImageAsset record."""
        self.tenant.feature_teacher_authoring = False
        self.tenant.save()
        self.client.force_authenticate(user=self.teacher)
        before_count = RichTextImageAsset.all_objects.filter(tenant=self.tenant).count()
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        self._post("/api/uploads/editor-image/", {"file": f})
        after_count = RichTextImageAsset.all_objects.filter(tenant=self.tenant).count()
        self.assertEqual(
            before_count,
            after_count,
            msg="A rejected upload should not persist a RichTextImageAsset",
        )

    # ------------------------------------------------------------------
    # HOD / IB_COORDINATOR — same feature-flag enforcement
    # ------------------------------------------------------------------

    def test_hod_without_feature_flag_gets_403(self):
        hod = User.objects.create_user(
            email="hod@upload.test",
            password="hod12345",
            first_name="Hod",
            last_name="Upload",
            tenant=self.tenant,
            role="HOD",
            is_active=True,
        )
        self.tenant.feature_teacher_authoring = False
        self.tenant.save()
        self.client.force_authenticate(user=hod)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.data.get("upgrade_required"))

    def test_ib_coordinator_without_feature_flag_gets_403(self):
        ibc = User.objects.create_user(
            email="ibc@upload.test",
            password="ibc12345",
            first_name="IBC",
            last_name="Upload",
            tenant=self.tenant,
            role="IB_COORDINATOR",
            is_active=True,
        )
        self.tenant.feature_teacher_authoring = False
        self.tenant.save()
        self.client.force_authenticate(user=ibc)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"file": f})
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp.data.get("upgrade_required"))

    # ------------------------------------------------------------------
    # Alternate field name ("image" instead of "file")
    # ------------------------------------------------------------------

    def test_admin_can_upload_using_image_field_name(self):
        """The view accepts both 'file' and 'image' as the multipart field name."""
        self.client.force_authenticate(user=self.admin)
        f = self._make_file("inline.png", b"\x89PNG\r\n\x1a\n", "image/png")
        resp = self._post("/api/uploads/editor-image/", {"image": f})
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data.get("asset_ref", "").startswith("rtimg:"))
