# apps/progress/tests_certification_views.py
#
# Comprehensive tests for the Certifications API:
#   - CertificationType CRUD (admin only)
#   - Certification issue / list / detail / revoke / renew
#   - Expiry check endpoint
#   - Auth guards (401 / 403)
#   - Cross-tenant isolation (404 / 403)

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Course
from apps.tenants.models import Tenant
from apps.users.models import User

from .certification_models import CertificationType, TeacherCertification


HOST = "cert.lms.com"
HOST_OTHER = "rival.lms.com"


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class _CertBase(TestCase):
    """
    Fixtures: two tenants, admin + teacher per primary tenant, one
    CertificationType, one active TeacherCertification, one rival tenant.
    """

    @classmethod
    def setUpTestData(cls):
        # Primary tenant
        cls.tenant = Tenant.objects.create(
            name="Cert School",
            slug="cert-school",
            subdomain="cert",
            email="cert@school.com",
            is_active=True,
        )
        cls.admin = User.objects.create_user(
            email="admin@cert.com",
            password="Admin!Pass123",
            first_name="Cert",
            last_name="Admin",
            tenant=cls.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        cls.teacher = User.objects.create_user(
            email="teacher@cert.com",
            password="Teacher!Pass123",
            first_name="Cert",
            last_name="Teacher",
            tenant=cls.tenant,
            role="TEACHER",
            is_active=True,
        )
        cls.teacher2 = User.objects.create_user(
            email="teacher2@cert.com",
            password="Teacher2!Pass123",
            first_name="Cert",
            last_name="Teacher2",
            tenant=cls.tenant,
            role="TEACHER",
            is_active=True,
        )

        # Rival tenant (for cross-tenant isolation)
        cls.tenant_b = Tenant.objects.create(
            name="Rival School",
            slug="rival-school",
            subdomain="rival",
            email="rival@school.com",
            is_active=True,
        )
        cls.admin_b = User.objects.create_user(
            email="admin@rival.com",
            password="Admin!Pass123",
            first_name="Rival",
            last_name="Admin",
            tenant=cls.tenant_b,
            role="SCHOOL_ADMIN",
            is_active=True,
        )

        # CertificationType in primary tenant
        cls.cert_type = CertificationType.all_objects.create(
            tenant=cls.tenant,
            name="Python Certification",
            description="Certifies Python proficiency",
            validity_months=12,
            auto_renew=False,
        )

        # CertificationType in rival tenant (must not be visible to primary)
        cls.cert_type_b = CertificationType.all_objects.create(
            tenant=cls.tenant_b,
            name="Rival Cert",
            description="Rival cert",
            validity_months=6,
        )

        # Active TeacherCertification for cls.teacher
        cls.cert = TeacherCertification.all_objects.create(
            teacher=cls.teacher,
            certification_type=cls.cert_type,
            tenant=cls.tenant,
            expires_at=timezone.now() + timedelta(days=365),
            status="active",
            issued_by=cls.admin,
        )

    def _admin_client(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        client.defaults["HTTP_HOST"] = HOST
        return client

    def _teacher_client(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        client.defaults["HTTP_HOST"] = HOST
        return client

    def _teacher2_client(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher2)
        client.defaults["HTTP_HOST"] = HOST
        return client

    def _admin_b_client(self):
        """Admin from Tenant B hitting primary tenant's host."""
        client = APIClient()
        client.force_authenticate(user=self.admin_b)
        client.defaults["HTTP_HOST"] = HOST
        return client

    def _anon_client(self):
        client = APIClient()
        client.defaults["HTTP_HOST"] = HOST
        return client


# ---------------------------------------------------------------------------
# CertificationType CRUD
# ---------------------------------------------------------------------------

class CertTypeListCreateTests(_CertBase):

    def test_cert_type_list_returns_200(self):
        resp = self._admin_client().get("/api/v1/certifications/types/")
        self.assertEqual(resp.status_code, 200)

    def test_cert_type_list_scoped_to_tenant(self):
        resp = self._admin_client().get("/api/v1/certifications/types/")
        body = resp.json()
        results = body.get("results", [])
        names = [r["name"] for r in results]
        self.assertIn("Python Certification", names)
        self.assertNotIn("Rival Cert", names)

    def test_cert_type_list_teacher_gets_403(self):
        resp = self._teacher_client().get("/api/v1/certifications/types/")
        self.assertEqual(resp.status_code, 403)

    def test_cert_type_list_anon_gets_401(self):
        resp = self._anon_client().get("/api/v1/certifications/types/")
        self.assertEqual(resp.status_code, 401)

    def test_cert_type_create_returns_201(self):
        resp = self._admin_client().post(
            "/api/v1/certifications/types/create/",
            data={
                "name": "Data Science Cert",
                "description": "For data scientists",
                "validity_months": 24,
                "auto_renew": False,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["name"], "Data Science Cert")
        self.assertEqual(body["validity_months"], 24)
        # Cleanup
        CertificationType.all_objects.filter(
            name="Data Science Cert", tenant=self.tenant
        ).delete()

    def test_cert_type_create_teacher_gets_403(self):
        resp = self._teacher_client().post(
            "/api/v1/certifications/types/create/",
            data={"name": "Test Cert", "validity_months": 12},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


class CertTypeDetailUpdateDeleteTests(_CertBase):

    def test_cert_type_detail_returns_200(self):
        resp = self._admin_client().get(
            f"/api/v1/certifications/types/{self.cert_type.id}/"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Python Certification")

    def test_cert_type_detail_cross_tenant_returns_404(self):
        resp = self._admin_client().get(
            f"/api/v1/certifications/types/{self.cert_type_b.id}/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_cert_type_detail_nonexistent_returns_404(self):
        resp = self._admin_client().get(
            f"/api/v1/certifications/types/{uuid.uuid4()}/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_cert_type_update_returns_200(self):
        resp = self._admin_client().patch(
            f"/api/v1/certifications/types/{self.cert_type.id}/update/",
            data={"description": "Updated description"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["description"], "Updated description")

    def test_cert_type_update_teacher_gets_403(self):
        resp = self._teacher_client().patch(
            f"/api/v1/certifications/types/{self.cert_type.id}/update/",
            data={"description": "Teacher update"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_cert_type_delete_returns_204(self):
        throwaway = CertificationType.all_objects.create(
            tenant=self.tenant,
            name="Throwaway Cert Type",
            validity_months=1,
        )
        resp = self._admin_client().delete(
            f"/api/v1/certifications/types/{throwaway.id}/delete/"
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(
            CertificationType.all_objects.filter(id=throwaway.id).exists()
        )

    def test_cert_type_delete_teacher_gets_403(self):
        resp = self._teacher_client().delete(
            f"/api/v1/certifications/types/{self.cert_type.id}/delete/"
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Certification issue
# ---------------------------------------------------------------------------

class CertIssueTests(_CertBase):

    def test_cert_issue_returns_201(self):
        # Issue a cert to teacher2 (who has no active cert yet)
        resp = self._admin_client().post(
            "/api/v1/certifications/issue/",
            data={
                "teacher_id": str(self.teacher2.id),
                "certification_type_id": str(self.cert_type.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["status"], "active")
        # Cleanup
        TeacherCertification.all_objects.filter(
            teacher=self.teacher2, certification_type=self.cert_type
        ).delete()

    def test_cert_issue_sets_expiry_from_validity_months(self):
        resp = self._admin_client().post(
            "/api/v1/certifications/issue/",
            data={
                "teacher_id": str(self.teacher2.id),
                "certification_type_id": str(self.cert_type.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertIsNotNone(body.get("expires_at"))
        # Cleanup
        TeacherCertification.all_objects.filter(
            teacher=self.teacher2, certification_type=self.cert_type
        ).delete()

    def test_cert_issue_duplicate_active_returns_400(self):
        # cls.teacher already has an active cert of this type
        resp = self._admin_client().post(
            "/api/v1/certifications/issue/",
            data={
                "teacher_id": str(self.teacher.id),
                "certification_type_id": str(self.cert_type.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_cert_issue_teacher_gets_403(self):
        resp = self._teacher_client().post(
            "/api/v1/certifications/issue/",
            data={
                "teacher_id": str(self.teacher2.id),
                "certification_type_id": str(self.cert_type.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_cert_issue_anon_gets_401(self):
        resp = self._anon_client().post(
            "/api/v1/certifications/issue/",
            data={
                "teacher_id": str(self.teacher2.id),
                "certification_type_id": str(self.cert_type.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Certification list
# ---------------------------------------------------------------------------

class CertListTests(_CertBase):

    def test_cert_list_admin_sees_all_returns_200(self):
        resp = self._admin_client().get("/api/v1/certifications/")
        self.assertEqual(resp.status_code, 200)

    def test_cert_list_admin_includes_fixture_cert(self):
        resp = self._admin_client().get("/api/v1/certifications/")
        body = resp.json()
        results = body.get("results", [])
        cert_ids = [r["id"] for r in results]
        self.assertIn(str(self.cert.id), cert_ids)

    def test_cert_list_teacher_sees_own_only(self):
        resp = self._teacher_client().get("/api/v1/certifications/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        results = body.get("results", [])
        # Teacher sees their own cert
        for r in results:
            self.assertEqual(r["teacher"], str(self.teacher.id))

    def test_cert_list_teacher2_sees_empty(self):
        """Teacher2 has no certs yet."""
        resp = self._teacher2_client().get("/api/v1/certifications/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        results = body.get("results", [])
        self.assertEqual(len(results), 0)

    def test_cert_list_admin_teacher_id_filter(self):
        resp = self._admin_client().get(
            f"/api/v1/certifications/?teacher_id={self.teacher.id}"
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for r in body.get("results", []):
            self.assertEqual(r["teacher"], str(self.teacher.id))

    def test_cert_list_status_filter(self):
        resp = self._admin_client().get("/api/v1/certifications/?status=active")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for r in body.get("results", []):
            self.assertEqual(r["status"], "active")

    def test_cert_list_anon_gets_401(self):
        resp = self._anon_client().get("/api/v1/certifications/")
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Certification detail
# ---------------------------------------------------------------------------

class CertDetailTests(_CertBase):

    def test_cert_detail_admin_returns_200(self):
        resp = self._admin_client().get(f"/api/v1/certifications/{self.cert.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "active")

    def test_cert_detail_teacher_own_returns_200(self):
        resp = self._teacher_client().get(f"/api/v1/certifications/{self.cert.id}/")
        self.assertEqual(resp.status_code, 200)

    def test_cert_detail_teacher_others_returns_403(self):
        """Teacher2 should not see Teacher1's certification."""
        resp = self._teacher2_client().get(f"/api/v1/certifications/{self.cert.id}/")
        self.assertEqual(resp.status_code, 403)

    def test_cert_detail_cross_tenant_returns_404(self):
        """Admin B on primary host cannot access rival's certifications."""
        cert_b = TeacherCertification.all_objects.create(
            teacher=self.admin_b,
            certification_type=self.cert_type_b,
            tenant=self.tenant_b,
            expires_at=timezone.now() + timedelta(days=180),
            status="active",
        )
        resp = self._admin_client().get(f"/api/v1/certifications/{cert_b.id}/")
        self.assertEqual(resp.status_code, 404)
        cert_b.delete()

    def test_cert_detail_nonexistent_returns_404(self):
        resp = self._admin_client().get(f"/api/v1/certifications/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# Certification revoke
# ---------------------------------------------------------------------------

class CertRevokeTests(_CertBase):

    def _issue_cert_for_teacher2(self):
        return TeacherCertification.all_objects.create(
            teacher=self.teacher2,
            certification_type=self.cert_type,
            tenant=self.tenant,
            expires_at=timezone.now() + timedelta(days=365),
            status="active",
            issued_by=self.admin,
        )

    def test_cert_revoke_returns_200(self):
        tc = self._issue_cert_for_teacher2()
        resp = self._admin_client().post(
            f"/api/v1/certifications/{tc.id}/revoke/",
            data={"reason": "Misconduct"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "revoked")
        tc.delete()

    def test_cert_revoke_sets_reason(self):
        tc = self._issue_cert_for_teacher2()
        self._admin_client().post(
            f"/api/v1/certifications/{tc.id}/revoke/",
            data={"reason": "Test reason"},
            format="json",
        )
        tc.refresh_from_db()
        self.assertEqual(tc.revoked_reason, "Test reason")
        tc.delete()

    def test_cert_revoke_already_revoked_returns_400(self):
        tc = self._issue_cert_for_teacher2()
        tc.status = "revoked"
        tc.save()
        resp = self._admin_client().post(
            f"/api/v1/certifications/{tc.id}/revoke/",
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        tc.delete()

    def test_cert_revoke_teacher_gets_403(self):
        resp = self._teacher_client().post(
            f"/api/v1/certifications/{self.cert.id}/revoke/",
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Certification renew
# ---------------------------------------------------------------------------

class CertRenewTests(_CertBase):

    def test_cert_renew_returns_200(self):
        resp = self._admin_client().post(
            f"/api/v1/certifications/{self.cert.id}/renew/",
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["renewal_count"], 1)

    def test_cert_renew_extends_expiry(self):
        old_expiry = self.cert.expires_at
        resp = self._admin_client().post(
            f"/api/v1/certifications/{self.cert.id}/renew/",
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.cert.refresh_from_db()
        self.assertGreater(self.cert.expires_at, old_expiry)

    def test_cert_renew_revoked_returns_400(self):
        tc = TeacherCertification.all_objects.create(
            teacher=self.teacher2,
            certification_type=self.cert_type,
            tenant=self.tenant,
            expires_at=timezone.now() + timedelta(days=365),
            status="revoked",
            issued_by=self.admin,
        )
        resp = self._admin_client().post(
            f"/api/v1/certifications/{tc.id}/renew/",
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        tc.delete()

    def test_cert_renew_teacher_gets_403(self):
        resp = self._teacher_client().post(
            f"/api/v1/certifications/{self.cert.id}/renew/",
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Expiry check
# ---------------------------------------------------------------------------

class CertExpiryCheckTests(_CertBase):

    def test_expiry_check_returns_200(self):
        resp = self._admin_client().post(
            "/api/v1/certifications/expiry-check/",
            data={"days": 30},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_expiry_check_structure(self):
        resp = self._admin_client().post(
            "/api/v1/certifications/expiry-check/",
            data={"days": 30},
            format="json",
        )
        body = resp.json()
        self.assertIn("expiring_soon", body)
        self.assertIn("already_expired", body)
        self.assertIn("threshold_days", body)
        self.assertEqual(body["threshold_days"], 30)

    def test_expiry_check_catches_expiring_certs(self):
        """A cert expiring in 10 days should appear in expiring_soon for days=30."""
        expiring_tc = TeacherCertification.all_objects.create(
            teacher=self.teacher2,
            certification_type=self.cert_type,
            tenant=self.tenant,
            expires_at=timezone.now() + timedelta(days=10),
            status="active",
        )
        resp = self._admin_client().post(
            "/api/v1/certifications/expiry-check/",
            data={"days": 30},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        expiring_ids = [r["id"] for r in body["expiring_soon"]]
        self.assertIn(str(expiring_tc.id), expiring_ids)
        expiring_tc.delete()

    def test_expiry_check_catches_already_expired(self):
        """A cert that already expired should appear in already_expired."""
        expired_tc = TeacherCertification.all_objects.create(
            teacher=self.teacher2,
            certification_type=self.cert_type,
            tenant=self.tenant,
            expires_at=timezone.now() - timedelta(days=5),  # already expired
            status="active",  # status not yet updated
        )
        resp = self._admin_client().post(
            "/api/v1/certifications/expiry-check/",
            data={"days": 30},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        expired_ids = [r["id"] for r in body["already_expired"]]
        self.assertIn(str(expired_tc.id), expired_ids)
        # Should auto-update status to 'expired'
        expired_tc.refresh_from_db()
        self.assertEqual(expired_tc.status, "expired")
        expired_tc.delete()

    def test_expiry_check_invalid_days_returns_400(self):
        resp = self._admin_client().post(
            "/api/v1/certifications/expiry-check/",
            data={"days": 999},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_expiry_check_non_integer_days_returns_400(self):
        resp = self._admin_client().post(
            "/api/v1/certifications/expiry-check/",
            data={"days": "not_a_number"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_expiry_check_teacher_gets_403(self):
        resp = self._teacher_client().post(
            "/api/v1/certifications/expiry-check/",
            data={"days": 30},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_expiry_check_anon_gets_401(self):
        resp = self._anon_client().post(
            "/api/v1/certifications/expiry-check/",
            data={"days": 30},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------

class CertCrossTenantIsolationTests(_CertBase):

    def test_admin_a_cannot_access_rival_cert_type(self):
        resp = self._admin_client().get(
            f"/api/v1/certifications/types/{self.cert_type_b.id}/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_admin_a_cert_type_list_excludes_rival(self):
        resp = self._admin_client().get("/api/v1/certifications/types/")
        body = resp.json()
        results = body.get("results", [])
        names = [r["name"] for r in results]
        self.assertNotIn("Rival Cert", names)

    def test_admin_b_on_primary_host_gets_403(self):
        """Admin B (tenant_b) hitting primary tenant host should be denied."""
        resp = self._admin_b_client().get("/api/v1/certifications/")
        self.assertIn(resp.status_code, [403, 404])
