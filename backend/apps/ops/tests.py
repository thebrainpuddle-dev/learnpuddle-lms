from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import Course
from apps.ops.models import OpsIncident, OpsRouteError
from apps.tenants.models import Tenant
from apps.users.models import User


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="learnpuddle.com")
class OpsCenterApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Ops Tenant",
            slug="ops-tenant",
            subdomain="opstenant",
            email="ops@tenant.com",
            is_active=True,
        )
        self.super_admin = User.objects.create_user(
            email="super@learnpuddle.com",
            password="pass1234",
            first_name="Super",
            last_name="Admin",
            role="SUPER_ADMIN",
            is_active=True,
        )
        self.school_admin = User.objects.create_user(
            email="admin@ops.com",
            password="pass1234",
            first_name="School",
            last_name="Admin",
            role="SCHOOL_ADMIN",
            tenant=self.tenant,
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@ops.com",
            password="pass1234",
            first_name="Teacher",
            last_name="One",
            role="TEACHER",
            tenant=self.tenant,
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Ops Course",
            slug="ops-course",
            description="Ops",
            created_by=self.school_admin,
            is_active=True,
            is_published=False,
        )
        self.client.force_authenticate(self.super_admin)

    def test_replay_run_create_dry_run(self):
        response = self.client.post(
            "/api/super-admin/ops/replay-runs/",
            {
                "tenant_id": str(self.tenant.id),
                "portal": "TENANT_ADMIN",
                "cases": [{"case_id": "tenant_admin.dashboard_stats"}],
                "dry_run": True,
                "priority": "NORMAL",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn(response.data["status"], ["COMPLETED", "FAILED"])
        self.assertEqual(response.data["portal"], "TENANT_ADMIN")
        self.assertEqual(response.data["dry_run"], True)

    def test_lock_route_error_creates_incident(self):
        error = OpsRouteError.objects.create(
            tenant=self.tenant,
            portal="TENANT_ADMIN",
            tab_key="courses",
            endpoint="/api/courses/",
            method="GET",
            status_code=500,
            fingerprint=f"{self.tenant.id}:courses:500",
            total_count=1,
            count_1h=1,
            count_24h=1,
        )
        response = self.client.post(
            f"/api/super-admin/ops/errors/{error.id}/lock/",
            {"note": "Lock from test"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertTrue(
            OpsIncident.objects.filter(id=response.data["incident_id"], status="OPEN").exists()
        )

    def test_guarded_action_approval_flow(self):
        execute = self.client.post(
            "/api/super-admin/ops/actions/execute/",
            {
                "tenant_id": str(self.tenant.id),
                "action_key": "replay_course_publish",
                "target": {"course_id": str(self.course.id)},
                "reason": "Test unblock",
                "dry_run": False,
            },
            format="json",
        )
        self.assertEqual(execute.status_code, 202)
        self.assertTrue(execute.data["requires_approval"])
        action_log_id = execute.data["action_log_id"]

        approve = self.client.post(
            f"/api/super-admin/ops/actions/{action_log_id}/approve/",
            {"approval_note": "approved in test"},
            format="json",
        )
        self.assertEqual(approve.status_code, 200)
        self.assertEqual(approve.data["status"], "EXECUTED")

    def test_client_error_ingest_tracks_problematic_codes(self):
        response = self.client.post(
            "/api/ops/client-errors/ingest/",
            {
                "status_code": 500,
                "portal": "TENANT_ADMIN",
                "tab_key": "courses",
                "endpoint": "/api/courses/",
                "method": "GET",
                "route_path": "/admin/courses",
                "request_id": "ops-test-request",
                "payload": {"search": "abc"},
                "response_excerpt": "Internal server error",
            },
            format="json",
            HTTP_HOST="opstenant.learnpuddle.com",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["accepted"])
        self.assertTrue(OpsRouteError.objects.filter(status_code=500, tab_key="courses").exists())

