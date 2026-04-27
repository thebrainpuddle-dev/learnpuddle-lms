"""Tests for TASK-047 — SCORM 1.2 import + xAPI LRS.

Covers:
* Zip-slip defense (``../evil.js`` rejected without writing outside target).
* Decompression-bomb defense (huge declared size rejected).
* Happy-path SCORM upload (valid imsmanifest.xml -> Content + SCORMPackage).
* xAPI POST happy path (minimal valid statement).
* xAPI POST malformed rejection (missing actor/verb/object).
* H1 — xAPI actor impersonation is blocked for non-admin users.
* H2 — SCORM commit rate-limit fails closed on cache outage.
* M1 — Launch URL with scheme is rejected at manifest-parse time.
* M3 — xAPI GET actor filter is exact, not substring.
"""

from __future__ import annotations

import io
import zipfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.courses.scorm_models import SCORMPackage
from apps.courses.xapi_models import XAPIStatement
from apps.tenants.models import Tenant


MANIFEST_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST-1" version="1.2"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2">
  <organizations default="DEFAULT_ORG">
    <organization identifier="DEFAULT_ORG">
      <title>Demo</title>
      <item identifier="ITEM1" identifierref="RES1">
        <title>Lesson 1</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="RES1" type="webcontent" href="index.html">
      <file href="index.html"/>
    </resource>
  </resources>
</manifest>
"""


def _make_valid_scorm_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("imsmanifest.xml", MANIFEST_XML)
        zf.writestr("index.html", b"<html><body>Hello SCORM</body></html>")
    return buf.getvalue()


def _make_zipslip_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("imsmanifest.xml", MANIFEST_XML)
        # Evil: traverse outside the package root
        zf.writestr("../../../evil.js", b"pwned")
    return buf.getvalue()


def _make_bomb_zip() -> bytes:
    """Zip whose declared uncompressed size exceeds the 100 MB cap."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("imsmanifest.xml", MANIFEST_XML)
        # 200 MB of zeroes compresses to a tiny zip; declared file_size trips cap.
        zf.writestr("big.bin", b"\0" * (200 * 1024 * 1024))
    return buf.getvalue()


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
)
class SCORMUploadTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Demo School",
            subdomain="demo",
            slug="demo-school",
            is_active=True,
        )
        self.admin = get_user_model().objects.create_user(
            email="admin@demo.test",
            password="Pass@123",
            first_name="A",
            last_name="U",
            role="SCHOOL_ADMIN",
            tenant=self.tenant,
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="SCORM Host",
            slug="scorm-host",
            description="for SCORM",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title="Module 1",
            description="",
            order=1,
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.client.defaults["HTTP_HOST"] = "demo.lms.com"

    # ------------------------------------------------------------------ happy
    def test_happy_path_upload_creates_package_and_content(self):
        data = {
            "course_id": str(self.course.id),
            "module_id": str(self.module.id),
            "title": "SCORM Unit",
            "file": io.BytesIO(_make_valid_scorm_zip()),
        }
        data["file"].name = "pkg.zip"
        resp = self.client.post("/api/v1/admin/scorm/upload/", data, format="multipart")
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(body["launch_url"], "index.html")
        self.assertEqual(body["version"], "1.2")

        content = Content.all_objects.get(id=body["content_id"])
        self.assertEqual(content.content_type, "SCORM")
        pkg = SCORMPackage.objects.get(id=body["package_id"])
        self.assertEqual(pkg.content_id, content.id)
        self.assertEqual(pkg.tenant_id, self.tenant.id)
        self.assertTrue(pkg.package_path.startswith(f"tenant/{self.tenant.id}/scorm/"))

    # ---------------------------------------------------------------- zipslip
    def test_zipslip_payload_is_rejected(self):
        data = {
            "course_id": str(self.course.id),
            "module_id": str(self.module.id),
            "title": "Evil",
            "file": io.BytesIO(_make_zipslip_zip()),
        }
        data["file"].name = "evil.zip"
        resp = self.client.post("/api/v1/admin/scorm/upload/", data, format="multipart")
        self.assertEqual(resp.status_code, 400, resp.content)
        # Ensure we didn't accidentally create a package
        self.assertFalse(SCORMPackage.objects.exists())

    # ------------------------------------------------------------------ bomb
    def test_decompression_bomb_is_rejected(self):
        data = {
            "course_id": str(self.course.id),
            "module_id": str(self.module.id),
            "title": "Bomb",
            "file": io.BytesIO(_make_bomb_zip()),
        }
        data["file"].name = "bomb.zip"
        resp = self.client.post("/api/v1/admin/scorm/upload/", data, format="multipart")
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(SCORMPackage.objects.exists())


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
)
class XAPITestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Demo School",
            subdomain="demo",
            slug="demo-school",
            is_active=True,
        )
        self.teacher = get_user_model().objects.create_user(
            email="teacher@demo.test",
            password="Pass@123",
            first_name="T",
            last_name="U",
            role="TEACHER",
            tenant=self.tenant,
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.teacher)
        self.client.defaults["HTTP_HOST"] = "demo.lms.com"

    def test_valid_statement_is_persisted(self):
        body = {
            "actor": {"mbox": "mailto:teacher@demo.test", "name": "Teacher"},
            "verb": {
                "id": "http://adlnet.gov/expapi/verbs/completed",
                "display": {"en-US": "completed"},
            },
            "object": {
                "id": "http://demo.lms.com/activities/lesson-1",
                "definition": {"name": {"en-US": "Lesson 1"}},
            },
            "result": {"completion": True, "score": {"raw": 90}},
        }
        resp = self.client.post(
            "/api/v1/xapi/statements/",
            body,
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertIn("id", data)

        stmt = XAPIStatement.objects.get(statement_id=data["id"])
        self.assertEqual(stmt.tenant_id, self.tenant.id)
        self.assertEqual(stmt.actor_mbox, "mailto:teacher@demo.test")
        self.assertEqual(stmt.verb_id, "http://adlnet.gov/expapi/verbs/completed")
        self.assertEqual(stmt.object_id, "http://demo.lms.com/activities/lesson-1")

    def test_missing_actor_is_rejected(self):
        body = {
            "verb": {"id": "http://adlnet.gov/expapi/verbs/completed"},
            "object": {"id": "http://demo.lms.com/activities/x"},
        }
        resp = self.client.post(
            "/api/v1/xapi/statements/",
            body,
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(XAPIStatement.objects.exists())

    def test_missing_verb_id_is_rejected(self):
        body = {
            "actor": {"mbox": "mailto:t@demo.test"},
            "verb": {},  # no id
            "object": {"id": "http://demo.lms.com/x"},
        }
        resp = self.client.post(
            "/api/v1/xapi/statements/",
            body,
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(XAPIStatement.objects.exists())

    def test_whitespace_verb_id_is_rejected(self):
        body = {
            "actor": {"mbox": "mailto:teacher@demo.test"},
            "verb": {"id": "   "},
            "object": {"id": "http://demo.lms.com/x"},
        }
        resp = self.client.post(
            "/api/v1/xapi/statements/",
            body,
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(XAPIStatement.objects.exists())

    # -------------------------------------------------------- H1: impersonation
    def test_non_admin_cannot_impersonate_another_actor(self):
        """H1 — a teacher POSTing a statement with another user's mbox
        must have the stored ``actor_mbox`` rewritten to their own email.
        """
        # Different teacher in the same tenant.
        get_user_model().objects.create_user(
            email="other@demo.test",
            password="Pass@123",
            first_name="O",
            last_name="U",
            role="TEACHER",
            tenant=self.tenant,
            is_active=True,
        )
        body = {
            "actor": {
                "mbox": "mailto:other@demo.test",
                "name": "Other Teacher",
            },
            "verb": {"id": "http://adlnet.gov/expapi/verbs/experienced"},
            "object": {"id": "http://demo.lms.com/activities/lesson-2"},
        }
        resp = self.client.post(
            "/api/v1/xapi/statements/",
            body,
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        stmt = XAPIStatement.objects.get(statement_id=resp.json()["id"])
        # Stored mbox must be authed user's email, not the payload's claim.
        self.assertEqual(stmt.actor_mbox, "mailto:teacher@demo.test")
        # The persisted raw payload must also have been patched so downstream
        # analytics cannot reconstruct the spoofed identity.
        self.assertEqual(stmt.raw["actor"]["mbox"], "mailto:teacher@demo.test")

    def test_non_admin_account_shape_cannot_impersonate(self):
        """H1 — ``actor.account`` with another user's email is rewritten."""
        body = {
            "actor": {
                "account": {
                    "homePage": "http://demo.lms.com",
                    "name": "other@demo.test",
                },
            },
            "verb": {"id": "http://adlnet.gov/expapi/verbs/experienced"},
            "object": {"id": "http://demo.lms.com/activities/lesson-2"},
        }
        resp = self.client.post(
            "/api/v1/xapi/statements/",
            body,
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        stmt = XAPIStatement.objects.get(statement_id=resp.json()["id"])
        self.assertEqual(stmt.actor_mbox, "mailto:teacher@demo.test")
        self.assertNotIn("account", stmt.raw["actor"])


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
)
class XAPIAdminTestCase(TestCase):
    """Admin-only behaviours: cross-tenant mbox rejection + GET filtering."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Tenant A", subdomain="a", slug="a", is_active=True
        )
        self.tenant_b = Tenant.objects.create(
            name="Tenant B", subdomain="b", slug="b", is_active=True
        )
        self.admin_a = get_user_model().objects.create_user(
            email="admin@a.test",
            password="Pass@123",
            first_name="A",
            last_name="A",
            role="SCHOOL_ADMIN",
            tenant=self.tenant_a,
            is_active=True,
        )
        self.teacher_a = get_user_model().objects.create_user(
            email="teacher-a@a.test",
            password="Pass@123",
            first_name="T",
            last_name="A",
            role="TEACHER",
            tenant=self.tenant_a,
            is_active=True,
        )
        get_user_model().objects.create_user(
            email="teacher-b@b.test",
            password="Pass@123",
            first_name="T",
            last_name="B",
            role="TEACHER",
            tenant=self.tenant_b,
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin_a)
        self.client.defaults["HTTP_HOST"] = "a.lms.com"

    def test_admin_can_post_on_behalf_of_same_tenant_user(self):
        body = {
            "actor": {"mbox": "mailto:teacher-a@a.test"},
            "verb": {"id": "http://adlnet.gov/expapi/verbs/completed"},
            "object": {"id": "http://demo/x"},
        }
        resp = self.client.post("/api/v1/xapi/statements/", body, format="json")
        self.assertEqual(resp.status_code, 201, resp.content)
        stmt = XAPIStatement.objects.get(statement_id=resp.json()["id"])
        self.assertEqual(stmt.actor_mbox, "mailto:teacher-a@a.test")

    def test_admin_cannot_post_cross_tenant_actor(self):
        body = {
            "actor": {"mbox": "mailto:teacher-b@b.test"},
            "verb": {"id": "http://adlnet.gov/expapi/verbs/completed"},
            "object": {"id": "http://demo/x"},
        }
        resp = self.client.post("/api/v1/xapi/statements/", body, format="json")
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(XAPIStatement.objects.exists())

    def test_get_actor_filter_is_exact_not_substring(self):
        """M3 — ``?actor=`` must exact-match, not substring-match."""
        XAPIStatement.objects.create(
            tenant=self.tenant_a,
            actor_mbox="mailto:teacher-a@a.test",
            verb_id="http://v/1",
            object_id="http://o/1",
        )
        XAPIStatement.objects.create(
            tenant=self.tenant_a,
            actor_mbox="mailto:admin+teacher-a@a.test",
            verb_id="http://v/1",
            object_id="http://o/1",
        )
        # Exact mbox filter must only return the first row (both rows have
        # overlapping substrings but only one has the exact address).
        resp = self.client.get(
            "/api/v1/xapi/statements/?actor=mailto:teacher-a@a.test"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["actor"], "mailto:teacher-a@a.test")

    def test_get_supports_pagination(self):
        for i in range(5):
            XAPIStatement.objects.create(
                tenant=self.tenant_a,
                actor_mbox=f"mailto:u{i}@a.test",
                verb_id="http://v/1",
                object_id="http://o/1",
            )
        resp = self.client.get("/api/v1/xapi/statements/?limit=2&offset=1")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["total"], 5)
        self.assertEqual(data["offset"], 1)
        self.assertEqual(data["limit"], 2)


# ---------------------------------------------------------------------------
# SEC — xAPI POST idempotency must be tenant-scoped.
#
# The ``_create_statement`` helper short-circuits with a 200 response when a
# statement with the same ``statement_id`` already exists.  Because
# ``XAPIStatement.objects`` is a ``TenantManager``, the lookup is implicitly
# scoped to the current tenant — but the implementation MUST also pass
# ``tenant=request.tenant`` explicitly so that:
#
#   1. The code matches the in-line comment ("if (tenant, statement_id)
#      already exists") and the ``xapi_statement_unique_per_tenant``
#      constraint on the model.
#   2. Future refactors (e.g. swapping ``objects`` for ``all_objects`` for
#      an admin view) cannot accidentally re-introduce the cross-tenant
#      leak shape.
#
# Regression: a Tenant B user posting with the same ``statement_id`` as a
# Tenant A row must (a) NOT receive Tenant A's ``stored`` timestamp, and
# (b) end up with a brand-new row in Tenant B (verifying creation, not the
# 200-idempotent short-circuit).
# ---------------------------------------------------------------------------

@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
)
class XAPIIdempotencyTenantIsolationTestCase(TestCase):
    """SEC — POST idempotency cannot return another tenant's statement."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(
            name="Tenant A", subdomain="ta", slug="ta", is_active=True
        )
        self.tenant_b = Tenant.objects.create(
            name="Tenant B", subdomain="tb", slug="tb", is_active=True
        )
        self.teacher_b = get_user_model().objects.create_user(
            email="teacher@tb.test",
            password="Pass@123",
            first_name="T",
            last_name="B",
            role="TEACHER",
            tenant=self.tenant_b,
            is_active=True,
        )
        # Pre-existing Tenant A row with a known statement_id.
        self.shared_statement_id = "11111111-2222-3333-4444-555555555555"
        self.tenant_a_row = XAPIStatement.objects.create(
            tenant=self.tenant_a,
            statement_id=self.shared_statement_id,
            actor_mbox="mailto:victim@ta.test",
            verb_id="http://adlnet.gov/expapi/verbs/completed",
            object_id="http://ta.lms.com/secret-activity",
            result={"score": {"raw": 99}},
            raw={"actor": {"mbox": "mailto:victim@ta.test"}},
        )
        # Tenant B client, posting with the SAME statement_id.
        self.client = APIClient()
        self.client.force_authenticate(user=self.teacher_b)
        self.client.defaults["HTTP_HOST"] = "tb.lms.com"

    def test_idempotency_lookup_scopes_to_request_tenant(self):
        """Tenant B reusing Tenant A's statement_id must NOT receive A's row."""
        body = {
            "id": self.shared_statement_id,
            "actor": {"mbox": "mailto:teacher@tb.test"},
            "verb": {"id": "http://adlnet.gov/expapi/verbs/experienced"},
            "object": {"id": "http://tb.lms.com/lesson-1"},
        }
        resp = self.client.post(
            "/api/v1/xapi/statements/",
            body,
            format="json",
        )
        # 201 = a brand-new Tenant B row was created, NOT a 200 short-circuit
        # echoing Tenant A's existing row.
        self.assertEqual(resp.status_code, 201, resp.content)

        # Two rows now exist with the same statement_id, one per tenant.
        rows = XAPIStatement.all_objects.filter(
            statement_id=self.shared_statement_id
        ).order_by("tenant_id")
        self.assertEqual(rows.count(), 2)
        tenants = sorted(str(r.tenant_id) for r in rows)
        self.assertEqual(
            tenants,
            sorted([str(self.tenant_a.id), str(self.tenant_b.id)]),
        )

        # The Tenant B response must NOT echo Tenant A's stored timestamp
        # (the original cross-tenant leak shape).
        b_row = rows.get(tenant=self.tenant_b)
        self.assertNotEqual(
            b_row.stored.isoformat(),
            self.tenant_a_row.stored.isoformat(),
        )
        # Sanity: response carries Tenant B's stored, not Tenant A's.
        self.assertEqual(resp.json()["stored"], b_row.stored.isoformat())


# ---------------------------------------------------------------------------
# H2 — SCORM commit rate-limit must fail CLOSED when cache is unavailable.
# ---------------------------------------------------------------------------

@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
)
class SCORMCommitRateLimitTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Demo", subdomain="demo", slug="demo", is_active=True
        )
        self.admin = get_user_model().objects.create_user(
            email="admin@demo.test",
            password="Pass@123",
            first_name="A",
            last_name="U",
            role="SCHOOL_ADMIN",
            tenant=self.tenant,
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="H",
            slug="h",
            description="",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title="M",
            description="",
            order=1,
            is_active=True,
        )
        self.content = Content.objects.create(
            module=self.module,
            title="SCORM",
            content_type="SCORM",
            order=1,
            is_mandatory=True,
            is_active=True,
        )
        self.package = SCORMPackage.objects.create(
            tenant=self.tenant,
            content=self.content,
            manifest_path="p/imsmanifest.xml",
            launch_url="index.html",
            version="1.2",
            package_path="p",
            package_size=1,
            uploaded_by=self.admin,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.client.defaults["HTTP_HOST"] = "demo.lms.com"

    def test_cache_outage_on_get_fails_closed_with_503(self):
        """H2 — ``cache.get`` raising must deny the commit (503)."""
        with patch(
            "apps.courses.scorm_views.cache.get",
            side_effect=RuntimeError("redis down"),
        ):
            resp = self.client.post(
                "/api/v1/scorm/commit/",
                {"package_id": str(self.package.id), "cmi": {"lesson_status": "completed"}},
                format="json",
            )
        self.assertEqual(resp.status_code, 503, resp.content)
        self.assertEqual(resp.json().get("error"), "service_unavailable")

    def test_cache_outage_on_set_fails_closed_with_503(self):
        """H2 — ``cache.set`` raising must also deny the commit (503)."""
        with patch(
            "apps.courses.scorm_views.cache.set",
            side_effect=RuntimeError("redis down"),
        ):
            resp = self.client.post(
                "/api/v1/scorm/commit/",
                {"package_id": str(self.package.id), "cmi": {"lesson_status": "completed"}},
                format="json",
            )
        self.assertEqual(resp.status_code, 503, resp.content)


# ---------------------------------------------------------------------------
# M2 — launch URL validation.
# ---------------------------------------------------------------------------

MANIFEST_XML_ABSOLUTE_URL = b"""<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="MANIFEST-1" version="1.2"
          xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2">
  <resources>
    <resource identifier="RES1" type="webcontent"
              href="http://attacker.example/evil.html">
      <file href="http://attacker.example/evil.html"/>
    </resource>
  </resources>
</manifest>
"""


def _make_manifest_absolute_url_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("imsmanifest.xml", MANIFEST_XML_ABSOLUTE_URL)
    return buf.getvalue()


@override_settings(
    PLATFORM_DOMAIN="lms.com",
    ALLOWED_HOSTS=["*"],
)
class SCORMLaunchURLValidationTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Demo", subdomain="demo", slug="demo", is_active=True
        )
        self.admin = get_user_model().objects.create_user(
            email="admin@demo.test",
            password="Pass@123",
            first_name="A",
            last_name="U",
            role="SCHOOL_ADMIN",
            tenant=self.tenant,
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="H",
            slug="h",
            description="",
            created_by=self.admin,
            is_published=True,
            is_active=True,
        )
        self.module = Module.objects.create(
            course=self.course,
            title="M",
            description="",
            order=1,
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)
        self.client.defaults["HTTP_HOST"] = "demo.lms.com"

    def test_absolute_launch_url_is_rejected(self):
        data = {
            "course_id": str(self.course.id),
            "module_id": str(self.module.id),
            "title": "Phish",
            "file": io.BytesIO(_make_manifest_absolute_url_zip()),
        }
        data["file"].name = "phish.zip"
        resp = self.client.post(
            "/api/v1/admin/scorm/upload/", data, format="multipart"
        )
        self.assertEqual(resp.status_code, 400, resp.content)
        self.assertFalse(SCORMPackage.objects.exists())
