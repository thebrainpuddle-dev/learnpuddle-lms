"""
Tests for TASK-052 — SCORM 1.2 Export (Backend).

Covers all acceptance criteria:
 1.  Happy-path course export → valid SCORM 1.2 zip (manifest parses,
     schemaversion=1.2, resources declared).
 2.  Single-content TEXT export.
 3.  Single-content VIDEO export (launch HTML embeds signed URL).
 4.  Single-content QUIZ export (deep-link stub HTML).
 5.  SCORM re-export refused — 400 + error code CANNOT_REEXPORT_SCORM.
 6.  Cross-tenant 404 on both endpoints.
 7.  Soft-deleted course returns 400 + COURSE_DELETED.
 8.  Size-cap rejection — estimated size > 500 MB → PACKAGE_TOO_LARGE.
 9.  Rate-limit enforcement — 11th request in same hour denied.
10.  Rate-limit fail-closed — cache outage → 503.
11.  Manifest XSD validation against real SCORM 1.2 XSD fixture.
12.  Signed URLs are HMAC-based and user-bound (not plaintext tokens).
13.  Audit log entry created for successful course export.
14.  Teacher (non-admin) gets 403 on both endpoints.
"""

from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.courses.scorm_export import (
    CANNOT_REEXPORT_SCORM,
    COURSE_DELETED,
    PACKAGE_TOO_LARGE,
    ScormExportError,
    build_scorm_package_for_content,
    build_scorm_package_for_course,
)
from apps.courses.helpers.signed_urls import make_signed_url, verify_signed_url
from apps.tenants.models import Tenant

User = get_user_model()

# ---------------------------------------------------------------------------
# Fixture path — SCORM 1.2 XSD
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SCORM12_XSD_PATH = FIXTURES_DIR / "scorm12.xsd"

# IMS CP 1.1.2 namespace used in SCORM 1.2 manifests
SCORM_12_NS = "http://www.imsproject.org/xsd/imscp_rootv1p1p2"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_tenant(name: str, subdomain: str):
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.test",
        is_active=True,
    )


def _make_admin(tenant, email: str):
    return User.objects.create_user(
        email=email,
        password="Pass@123",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


def _make_teacher(tenant, email: str):
    return User.objects.create_user(
        email=email,
        password="Pass@123",
        first_name="Teacher",
        last_name="User",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


def _make_course(tenant, admin, title: str = "Test Course", slug: str = "test-course"):
    return Course.objects.create(
        tenant=tenant,
        title=title,
        slug=slug,
        description="A test course.",
        created_by=admin,
        is_published=True,
        is_active=True,
    )


def _make_module(course):
    return Module.objects.create(
        course=course,
        title="Module 1",
        description="",
        order=1,
        is_active=True,
    )


def _make_content(module, content_type: str = "TEXT", title: str = "Content 1"):
    kwargs = dict(
        module=module,
        title=title,
        content_type=content_type,
        order=1,
        is_mandatory=True,
        is_active=True,
    )
    if content_type == "TEXT":
        kwargs["text_content"] = "<p>Hello from SCORM export test</p>"
    return Content.objects.create(**kwargs)


def _api_client(user, tenant) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


def _parse_manifest_from_zip(zip_bytes: bytes) -> ET.Element:
    """Extract and parse imsmanifest.xml from a zip's bytes."""
    buf = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buf, "r") as zf:
        names = [n.lower() for n in zf.namelist()]
        assert "imsmanifest.xml" in names, "imsmanifest.xml not found in zip"
        xml_bytes = zf.read("imsmanifest.xml")
    return ET.fromstring(xml_bytes)


def _validate_manifest_xsd(xml_bytes: bytes) -> None:
    """Validate manifest XML bytes against the SCORM 1.2 XSD fixture using lxml."""
    from lxml import etree

    assert SCORM12_XSD_PATH.exists(), f"XSD fixture not found: {SCORM12_XSD_PATH}"
    with open(SCORM12_XSD_PATH, "rb") as fh:
        xsd_doc = etree.parse(fh)
    schema = etree.XMLSchema(xsd_doc)
    doc = etree.fromstring(xml_bytes)
    is_valid = schema.validate(doc)
    errors = [str(e) for e in schema.error_log]
    assert is_valid, f"Manifest XSD validation failed:\n" + "\n".join(errors)


# ===========================================================================
# Test 1 — Happy-path course export
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestCourseScormExportHappyPath(TestCase):
    """Course export produces valid SCORM 1.2 zip."""

    def setUp(self):
        self.tenant = _make_tenant("Export School", "export")
        self.admin = _make_admin(self.tenant, "admin@export.test")
        self.course = _make_course(self.tenant, self.admin)
        self.module = _make_module(self.course)
        self.text_content = _make_content(self.module, "TEXT", "Lesson One")
        self.client = _api_client(self.admin, self.tenant)

    def test_course_export_returns_zip(self):
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp["Content-Type"], "application/zip")
        self.assertIn("attachment", resp["Content-Disposition"])
        self.assertIn("scorm12.zip", resp["Content-Disposition"])

    def test_course_export_zip_contains_manifest(self):
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200)
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            self.assertIn("imsmanifest.xml", zf.namelist())

    def test_course_export_manifest_has_correct_schemaversion(self):
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200)
        root = _parse_manifest_from_zip(resp.content)
        ns = SCORM_12_NS
        # Find schemaversion element
        meta = root.find(f"{{{ns}}}metadata")
        self.assertIsNotNone(meta, "metadata element not found")
        sv = meta.find(f"{{{ns}}}schemaversion")
        self.assertIsNotNone(sv, "schemaversion element not found")
        self.assertEqual(sv.text, "1.2")

    def test_course_export_manifest_has_resource_for_content(self):
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200)
        root = _parse_manifest_from_zip(resp.content)
        ns = SCORM_12_NS
        resources = root.find(f"{{{ns}}}resources")
        self.assertIsNotNone(resources)
        resource_list = list(resources.findall(f"{{{ns}}}resource"))
        self.assertGreater(len(resource_list), 0, "No resources declared")

    def test_course_export_zip_contains_launch_html(self):
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200)
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            html_files = [n for n in zf.namelist() if n.endswith(".html")]
        self.assertGreater(len(html_files), 0, "No launch HTML files in zip")


# ===========================================================================
# Test 2 — Single-content TEXT export
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestContentTextExport(TestCase):
    """Single TEXT content export."""

    def setUp(self):
        self.tenant = _make_tenant("Text School", "textschool")
        self.admin = _make_admin(self.tenant, "admin@text.test")
        self.course = _make_course(self.tenant, self.admin, "Text Course", "text-course")
        self.module = _make_module(self.course)
        self.content = _make_content(self.module, "TEXT", "Rich Text Lesson")
        self.client = _api_client(self.admin, self.tenant)

    def test_text_content_export_returns_zip(self):
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp["Content-Type"], "application/zip")

    def test_text_content_html_is_standalone(self):
        """Launch HTML for TEXT must not contain app-specific JS scripts."""
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200)
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            html_files = [n for n in zf.namelist() if n.endswith(".html")]
            self.assertTrue(html_files, "No HTML in zip")
            html = zf.read(html_files[0]).decode("utf-8")
        # Must be valid HTML5
        self.assertIn("<!DOCTYPE html>", html)
        # Must contain the original text content
        self.assertIn("Hello from SCORM export test", html)
        # Must NOT have application-specific JS bundles
        self.assertNotIn("bundle.js", html)
        self.assertNotIn("main.tsx", html)
        self.assertNotIn("react", html.lower()[:500])


# ===========================================================================
# Test 3 — Single-content VIDEO export
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestContentVideoExport(TestCase):
    """Single VIDEO content export embeds signed URL."""

    def setUp(self):
        self.tenant = _make_tenant("Video School", "videoschool")
        self.admin = _make_admin(self.tenant, "admin@video.test")
        self.course = _make_course(
            self.tenant, self.admin, "Video Course", "video-course"
        )
        self.module = _make_module(self.course)
        self.content = Content.objects.create(
            module=self.module,
            title="Video Lesson",
            content_type="VIDEO",
            order=1,
            file_url="https://cdn.lms.com/videos/lesson.mp4",
            is_mandatory=True,
            is_active=True,
        )
        self.client = _api_client(self.admin, self.tenant)

    def test_video_export_returns_zip(self):
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_video_launch_html_contains_signed_url(self):
        """Video HTML must contain a lp_token parameter (HMAC signed URL)."""
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200)
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            html_files = [n for n in zf.namelist() if n.endswith(".html")]
            html = zf.read(html_files[0]).decode("utf-8")
        # Must embed a signed URL with lp_token parameter
        self.assertIn("lp_token=", html)
        # Must NOT embed plaintext tenant secrets
        self.assertNotIn("SECRET_KEY", html)
        self.assertNotIn("tenant_id", html)

    def test_video_html_contains_video_element_or_link(self):
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200)
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            html_files = [n for n in zf.namelist() if n.endswith(".html")]
            html = zf.read(html_files[0]).decode("utf-8")
        # Should have either a <video> tag or an <a> link
        has_video = "<video" in html
        has_link = "<a " in html
        self.assertTrue(has_video or has_link, "No video or link in video launch HTML")


# ===========================================================================
# Test 4 — Single-content LINK export (external-launch stub)
# ===========================================================================
# Note: The Content model has no QUIZ content_type. The SCORM spec refers to
# "QUIZ" loosely; in this codebase, quiz-like external launch content is
# represented as a LINK type. We test the LINK type here to cover the
# external-launch stub path described in the task spec.


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestContentLinkExport(TestCase):
    """LINK content → external deep-link stub HTML (spec: QUIZ path)."""

    def setUp(self):
        self.tenant = _make_tenant("Link School", "linkschool")
        self.admin = _make_admin(self.tenant, "admin@link.test")
        self.course = _make_course(
            self.tenant, self.admin, "Link Course", "link-course"
        )
        self.module = _make_module(self.course)
        # LINK is the external-launch content type in this codebase.
        self.content = Content.objects.create(
            module=self.module,
            title="External Resource",
            content_type="LINK",
            order=1,
            file_url="https://external.example.com/resource/",
            is_mandatory=True,
            is_active=True,
        )
        self.client = _api_client(self.admin, self.tenant)

    def test_link_export_returns_zip(self):
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_link_html_contains_signed_url(self):
        """External-launch HTML must contain a signed token (not plaintext URL)."""
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200)
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            html_files = [n for n in zf.namelist() if n.endswith(".html")]
            html = zf.read(html_files[0]).decode("utf-8")
        # Must contain an HMAC-signed token
        self.assertIn("lp_token=", html)

    def test_link_html_contains_launch_link(self):
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200)
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            html_files = [n for n in zf.namelist() if n.endswith(".html")]
            html = zf.read(html_files[0]).decode("utf-8")
        self.assertIn("<a ", html)


# ===========================================================================
# Test 5 — SCORM re-export refused
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestScormReexportRefused(TestCase):
    """Imported SCORM content cannot be re-exported."""

    def setUp(self):
        self.tenant = _make_tenant("SCORM School", "scormschool")
        self.admin = _make_admin(self.tenant, "admin@scorm.test")
        self.course = _make_course(
            self.tenant, self.admin, "SCORM Course", "scorm-course"
        )
        self.module = _make_module(self.course)
        self.scorm_content = Content.objects.create(
            module=self.module,
            title="Imported SCORM",
            content_type="SCORM",
            order=1,
            is_mandatory=True,
            is_active=True,
        )
        self.client = _api_client(self.admin, self.tenant)

    def test_scorm_content_export_returns_400(self):
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.scorm_content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_scorm_content_export_error_code(self):
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.scorm_content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertEqual(body.get("code"), CANNOT_REEXPORT_SCORM)


# ===========================================================================
# Test 6 — Cross-tenant 404
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestCrossTenant404(TestCase):
    """Cross-tenant requests return 404 — never leak resource existence."""

    def setUp(self):
        self.tenant_a = _make_tenant("School A", "schoola")
        self.tenant_b = _make_tenant("School B", "schoolb")
        self.admin_a = _make_admin(self.tenant_a, "admin@schoola.test")
        self.admin_b = _make_admin(self.tenant_b, "admin@schoolb.test")
        # Course and content belong to tenant B
        self.course_b = _make_course(
            self.tenant_b, self.admin_b, "B's Course", "b-course"
        )
        self.module_b = _make_module(self.course_b)
        self.content_b = _make_content(self.module_b, "TEXT", "B Content")
        # Admin A tries to access Tenant B's resources
        self.client_a = _api_client(self.admin_a, self.tenant_a)

    def test_cross_tenant_course_export_returns_404(self):
        resp = self.client_a.post(
            f"/api/v1/admin/courses/{self.course_b.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 404, resp.content)

    def test_cross_tenant_content_export_returns_404(self):
        resp = self.client_a.post(
            f"/api/v1/admin/contents/{self.content_b.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 404, resp.content)


# ===========================================================================
# Test 7 — Soft-deleted course
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestSoftDeletedCourse(TestCase):
    """Soft-deleted courses cannot be exported."""

    def setUp(self):
        self.tenant = _make_tenant("Delete School", "deleteschool")
        self.admin = _make_admin(self.tenant, "admin@delete.test")
        self.course = _make_course(
            self.tenant, self.admin, "Deleted Course", "deleted-course"
        )
        self.module = _make_module(self.course)
        self.client = _api_client(self.admin, self.tenant)

    def test_deleted_course_export_returns_400(self):
        # Soft-delete the course
        self.course.is_deleted = True
        self.course.save(update_fields=["is_deleted"])

        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertEqual(body.get("code"), COURSE_DELETED)


# ===========================================================================
# Test 8 — Size cap rejection
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestSizeCap(TestCase):
    """Size guard rejects estimated-size > 500 MB."""

    def setUp(self):
        self.tenant = _make_tenant("Large School", "largeschool")
        self.admin = _make_admin(self.tenant, "admin@large.test")
        self.course = _make_course(
            self.tenant, self.admin, "Large Course", "large-course"
        )
        self.module = _make_module(self.course)
        self.content = _make_content(self.module, "TEXT", "Big Content")
        self.client = _api_client(self.admin, self.tenant)

    def test_size_cap_returns_package_too_large(self):
        """Patch _estimate_size to return > 500 MB."""
        from apps.courses import scorm_export

        with patch.object(
            scorm_export, "_estimate_size", return_value=600 * 1024 * 1024
        ):
            resp = self.client.post(
                f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
            )
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertEqual(body.get("code"), PACKAGE_TOO_LARGE)

    def test_size_cap_content_endpoint(self):
        from apps.courses import scorm_export

        with patch.object(
            scorm_export, "_estimate_size", return_value=600 * 1024 * 1024
        ):
            resp = self.client.post(
                f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
            )
        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertEqual(body.get("code"), PACKAGE_TOO_LARGE)


# ===========================================================================
# Test 9 — Rate-limit enforcement
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestRateLimit(TestCase):
    """11th export in same hour is denied (rate = 10/hr/tenant)."""

    def setUp(self):
        self.tenant = _make_tenant("Rate School", "rateschool")
        self.admin = _make_admin(self.tenant, "admin@rate.test")
        self.course = _make_course(
            self.tenant, self.admin, "Rate Course", "rate-course"
        )
        self.module = _make_module(self.course)
        _make_content(self.module, "TEXT", "Some Content")
        self.client = _api_client(self.admin, self.tenant)

    def test_eleventh_request_is_rate_limited(self):
        from django.core.cache import cache

        url = f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        rate_key = f"scorm_export:rate:{self.tenant.id}"
        # Simulate 10 already done
        cache.set(rate_key, 10, timeout=3600)

        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 429, resp.content)

    def tearDown(self):
        from django.core.cache import cache

        cache.delete(f"scorm_export:rate:{self.tenant.id}")


# ===========================================================================
# Test 10 — Rate-limit fail-closed on cache outage → 503
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestRateLimitFailClosed(TestCase):
    """Cache outage → 503 (fail-closed, not open)."""

    def setUp(self):
        self.tenant = _make_tenant("Failclosed School", "failschool")
        self.admin = _make_admin(self.tenant, "admin@fail.test")
        self.course = _make_course(
            self.tenant, self.admin, "Fail Course", "fail-course"
        )
        _make_module(self.course)
        self.client = _api_client(self.admin, self.tenant)

    def test_cache_get_outage_returns_503(self):
        url = f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        with patch(
            "apps.courses.scorm_export_views.cache.get",
            side_effect=RuntimeError("redis down"),
        ):
            resp = self.client.post(url)
        self.assertEqual(resp.status_code, 503, resp.content)

    def test_cache_set_outage_returns_503(self):
        url = f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        # get returns 0 (no prior exports) but set fails
        with patch("apps.courses.scorm_export_views.cache.get", return_value=0):
            with patch(
                "apps.courses.scorm_export_views.cache.set",
                side_effect=RuntimeError("redis down"),
            ):
                resp = self.client.post(url)
        self.assertEqual(resp.status_code, 503, resp.content)


# ===========================================================================
# Test 11 — Manifest XSD validation
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestManifestXSDValidation(TestCase):
    """Exported manifest must validate against the SCORM 1.2 XSD fixture."""

    def setUp(self):
        self.tenant = _make_tenant("XSD School", "xsdschool")
        self.admin = _make_admin(self.tenant, "admin@xsd.test")
        self.course = _make_course(self.tenant, self.admin, "XSD Course", "xsd-course")
        self.module = _make_module(self.course)
        _make_content(self.module, "TEXT", "XSD Lesson")
        self.client = _api_client(self.admin, self.tenant)

    def test_course_manifest_validates_against_xsd(self):
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            manifest_bytes = zf.read("imsmanifest.xml")
        # This must pass — real XSD validation via lxml
        _validate_manifest_xsd(manifest_bytes)

    def test_single_content_manifest_validates_against_xsd(self):
        content = Content.objects.filter(
            module=self.module, content_type="TEXT"
        ).first()
        resp = self.client.post(
            f"/api/v1/admin/contents/{content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf, "r") as zf:
            manifest_bytes = zf.read("imsmanifest.xml")
        _validate_manifest_xsd(manifest_bytes)


# ===========================================================================
# Test 12 — Signed URLs are HMAC-only and user-bound
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-signed-urls",
)
class TestSignedUrlsUnit(TestCase):
    """Unit tests for the signed URL helper."""

    def test_signed_url_contains_token_and_expiry(self):
        url = make_signed_url("https://example.com/video/", "user-1", 3600)
        self.assertIn("lp_token=", url)
        self.assertIn("lp_expires=", url)

    def test_signed_url_verifies_correctly(self):
        from urllib.parse import parse_qs, urlparse

        base_url = "https://example.com/video/"
        user_id = "user-abc"
        signed = make_signed_url(base_url, user_id, 3600)
        parsed = urlparse(signed)
        qs = parse_qs(parsed.query)
        token = qs["lp_token"][0]
        expires = int(qs["lp_expires"][0])
        self.assertTrue(verify_signed_url(base_url, user_id, token, expires))

    def test_wrong_user_id_fails_verification(self):
        from urllib.parse import parse_qs, urlparse

        base_url = "https://example.com/video/"
        signed = make_signed_url(base_url, "user-a", 3600)
        parsed = urlparse(signed)
        qs = parse_qs(parsed.query)
        token = qs["lp_token"][0]
        expires = int(qs["lp_expires"][0])
        # Different user_id must fail
        self.assertFalse(verify_signed_url(base_url, "user-b", token, expires))

    def test_expired_url_fails_verification(self):
        from urllib.parse import parse_qs, urlparse

        base_url = "https://example.com/video/"
        signed = make_signed_url(base_url, "user-a", 1)
        parsed = urlparse(signed)
        qs = parse_qs(parsed.query)
        token = qs["lp_token"][0]
        # Override expires to a past timestamp
        expired_ts = 1  # epoch 1970
        self.assertFalse(verify_signed_url(base_url, "user-a", token, expired_ts))

    def test_ttl_capped_at_24_hours(self):
        """TTL > 24h is silently capped to 24h."""
        import time
        from urllib.parse import parse_qs, urlparse

        base_url = "https://example.com/file/"
        signed = make_signed_url(base_url, "user-x", 999_999)
        parsed = urlparse(signed)
        qs = parse_qs(parsed.query)
        expires = int(qs["lp_expires"][0])
        # Must not be more than 24h + a few seconds from now
        max_allowed = int(time.time()) + 86_400 + 5
        self.assertLessEqual(expires, max_allowed)

    def test_token_does_not_contain_plaintext_secrets(self):
        """Token must not contain SECRET_KEY or tenant info in plaintext."""
        from django.conf import settings

        url = make_signed_url(
            "https://example.com/content/",
            "user-99",
            3600,
            extra_params={"content_id": "abc123"},
        )
        # Secret key must not appear in the token
        self.assertNotIn(settings.SECRET_KEY, url)


# ===========================================================================
# Test 13 — Audit log on successful export
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestAuditLog(TestCase):
    """Successful exports produce an EXPORT_SCORM audit log entry."""

    def setUp(self):
        self.tenant = _make_tenant("Audit School", "auditschool")
        self.admin = _make_admin(self.tenant, "admin@audit.test")
        self.course = _make_course(
            self.tenant, self.admin, "Audit Course", "audit-course"
        )
        self.module = _make_module(self.course)
        _make_content(self.module, "TEXT", "Audit Content")
        self.client = _api_client(self.admin, self.tenant)

    def test_course_export_creates_audit_log(self):
        from apps.tenants.models import AuditLog

        initial_count = AuditLog.objects.filter(
            action="EXPORT_SCORM", tenant=self.tenant
        ).count()

        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        final_count = AuditLog.objects.filter(
            action="EXPORT_SCORM", tenant=self.tenant
        ).count()
        self.assertEqual(final_count, initial_count + 1)


# ===========================================================================
# Test 14 — Teacher (non-admin) gets 403
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="test-secret-key-for-scorm-export",
)
class TestTeacherForbidden(TestCase):
    """Non-admin users cannot access SCORM export endpoints."""

    def setUp(self):
        self.tenant = _make_tenant("Teacher School", "teacherschool")
        self.admin = _make_admin(self.tenant, "admin@teacher.test")
        self.teacher = _make_teacher(self.tenant, "teacher@teacher.test")
        self.course = _make_course(
            self.tenant, self.admin, "Teacher Course", "teacher-course"
        )
        self.module = _make_module(self.course)
        self.content = _make_content(self.module, "TEXT", "Teacher Content")
        self.teacher_client = _api_client(self.teacher, self.tenant)

    def test_teacher_cannot_export_course(self):
        resp = self.teacher_client.post(
            f"/api/v1/admin/courses/{self.course.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_teacher_cannot_export_content(self):
        resp = self.teacher_client.post(
            f"/api/v1/admin/contents/{self.content.id}/scorm-export/"
        )
        self.assertEqual(resp.status_code, 403, resp.content)


# ===========================================================================
# Unit tests for scorm_export module (no HTTP)
# ===========================================================================


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    SECRET_KEY="test-secret-key-for-unit-tests",
)
class TestScormExportUnit(TestCase):
    """Unit tests for build_scorm_package_for_course / _for_content."""

    def setUp(self):
        self.tenant = _make_tenant("Unit School", "unitschool")
        self.admin = _make_admin(self.tenant, "admin@unit.test")
        self.course = _make_course(
            self.tenant, self.admin, "Unit Course", "unit-course"
        )
        self.module = _make_module(self.course)

    def test_course_export_bytes_is_valid_zip(self):
        _make_content(self.module, "TEXT", "Unit Text")
        zip_bytes, filename = build_scorm_package_for_course(
            self.course, self.admin
        )
        self.assertIsInstance(zip_bytes, bytes)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(zip_bytes)))
        self.assertTrue(filename.endswith(".zip"))

    def test_scorm_content_raises_error(self):
        scorm_content = Content.objects.create(
            module=self.module,
            title="SCORM",
            content_type="SCORM",
            order=1,
            is_active=True,
        )
        with self.assertRaises(ScormExportError) as cm:
            build_scorm_package_for_content(scorm_content, self.admin)
        self.assertEqual(cm.exception.code, CANNOT_REEXPORT_SCORM)

    def test_deleted_course_raises_error(self):
        self.course.is_deleted = True
        self.course.save(update_fields=["is_deleted"])
        with self.assertRaises(ScormExportError) as cm:
            build_scorm_package_for_course(self.course, self.admin)
        self.assertEqual(cm.exception.code, COURSE_DELETED)

    def test_course_with_no_contents_exports_empty_manifest(self):
        """A course with no active contents should still produce a valid zip."""
        empty_course = Course.objects.create(
            tenant=self.tenant,
            title="Empty Course",
            slug="empty-course",
            description="",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        zip_bytes, filename = build_scorm_package_for_course(
            empty_course, self.admin
        )
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(zip_bytes)))
        buf = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            self.assertIn("imsmanifest.xml", zf.namelist())
