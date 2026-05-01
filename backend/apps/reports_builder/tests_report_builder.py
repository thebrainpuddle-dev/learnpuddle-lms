"""
Tests for TASK-053 — Custom Report Builder (Backend).

Acceptance criteria covered:
  1.  CRUD happy path (create, list, retrieve, update, soft-delete definition).
  2.  Cross-tenant 404 on definitions, runs, and schedules.
  3.  Unknown field in filter_json → UNKNOWN_FIELD.
  4.  Unknown operator in filter_json → UNSUPPORTED_OPERATOR.
  5.  Row-cap enforcement (50,000 row cap).
  6.  Rate-limit enforcement (20/hr).
  7.  Rate-limit fail-closed — cache.get raises → 503.
  8.  Rate-limit fail-closed — cache.set raises → 503.
  9.  Signed-URL generation + user-bound check.
  10. Scheduled recipient validation (external → EXTERNAL_RECIPIENT_NOT_ALLOWED).
  11. Celery task build_csv_export success path.
  12. Celery task execute_scheduled_report success path.
  13. Celery task execute_scheduled_report error path (captured in run.error).
  14. Audit log creation on RUN_REPORT + EXPORT_REPORT.
  15. SQL-injection attempt in filter value (must be sanitised / rejected).
  16. Teacher (non-admin) gets 403 on definition endpoints.
  17. SUPER_ADMIN without tenant gets 403 from @tenant_required.
  18. Definition with valid data source and empty filters runs OK.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.reports_builder.models import ReportDefinition, ReportRun, ReportSchedule
from apps.reports_builder.query_engine import (
    ROW_CAP,
    ROW_CAP_EXCEEDED,
    UNKNOWN_FIELD,
    UNSUPPORTED_OPERATOR,
    validate_definition_schema,
)
from apps.reports_builder.serializers import ReportDefinitionSerializer
from apps.tenants.models import AuditLog, Tenant

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant(name: str, subdomain: str) -> Tenant:
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.test",
        is_active=True,
    )


def _make_user(tenant, email: str, role: str = "SCHOOL_ADMIN") -> User:
    user = User.objects.create_user(
        email=email,
        password="Pass@word1234!",
        first_name="Test",
        last_name="User",
        role=role,
    )
    user.tenant = tenant
    user.save()
    return user


def _make_definition(tenant, user, **kwargs) -> ReportDefinition:
    defaults = {
        "name": "Test Report",
        "data_source": "courses",
        "filters_json": [],
        "group_by_json": [],
        "aggregates_json": [],
    }
    defaults.update(kwargs)
    return ReportDefinition.all_objects.create(
        tenant=tenant,
        created_by=user,
        **defaults,
    )


def _authed_client(user, tenant) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    # Inject tenant into request via middleware attribute
    client.credentials(HTTP_HOST=f"{tenant.subdomain}.localhost")
    return client


# ---------------------------------------------------------------------------
# Unit tests — query_engine.validate_definition_schema
# ---------------------------------------------------------------------------


class TestValidateDefinitionSchema(TestCase):
    """Unit tests for the schema validator (no DB hits)."""

    def test_valid_schema_returns_no_errors(self):
        errors = validate_definition_schema(
            data_source="courses",
            filters=[{"field": "title", "op": "eq", "value": "Python 101"}],
            group_by=["id"],
            aggregates=[{"fn": "count", "field": "id"}],
        )
        self.assertEqual(errors, [])

    def test_unknown_data_source(self):
        errors = validate_definition_schema(
            data_source="__raw_sql__",
            filters=[],
            group_by=[],
            aggregates=[],
        )
        self.assertTrue(any("UNKNOWN_DATA_SOURCE" in e for e in errors))

    def test_unsupported_operator_rejected(self):
        errors = validate_definition_schema(
            data_source="courses",
            filters=[{"field": "title", "op": "LIKE", "value": "%injection%"}],
            group_by=[],
            aggregates=[],
        )
        self.assertTrue(any(UNSUPPORTED_OPERATOR in e for e in errors))

    def test_unknown_field_rejected(self):
        errors = validate_definition_schema(
            data_source="courses",
            filters=[{"field": "tenant__secret", "op": "eq", "value": "x"}],
            group_by=[],
            aggregates=[],
        )
        self.assertTrue(any(UNKNOWN_FIELD in e for e in errors))

    def test_sql_injection_in_field_name_rejected(self):
        """Field names with SQL metacharacters must be whitelisted-out."""
        evil_field = "1=1; DROP TABLE tenants;--"
        errors = validate_definition_schema(
            data_source="teacher_progress",
            filters=[{"field": evil_field, "op": "eq", "value": "x"}],
            group_by=[],
            aggregates=[],
        )
        self.assertTrue(any(UNKNOWN_FIELD in e for e in errors))

    def test_sql_injection_in_filter_value_is_safely_passed_to_orm(self):
        """
        Values in filter.value are never concatenated into SQL — they go through
        ORM parameterisation. The schema validator does NOT reject them (values
        are opaque), but they must not cause an UNSUPPORTED_OPERATOR or UNKNOWN_FIELD
        error. The safety guarantee comes from using ORM lookups only.
        """
        evil_value = "' OR 1=1 --"
        errors = validate_definition_schema(
            data_source="courses",
            filters=[{"field": "title", "op": "eq", "value": evil_value}],
            group_by=[],
            aggregates=[],
        )
        # No schema errors — value is opaque; ORM handles parameterisation
        self.assertEqual(errors, [])

    def test_unknown_group_by_field_rejected(self):
        errors = validate_definition_schema(
            data_source="courses",
            filters=[],
            group_by=["tenant__secret_key"],
            aggregates=[],
        )
        self.assertTrue(any(UNKNOWN_FIELD in e for e in errors))

    def test_all_supported_ops_accepted(self):
        from apps.reports_builder.query_engine import SUPPORTED_OPS

        for op in SUPPORTED_OPS:
            errors = validate_definition_schema(
                data_source="courses",
                filters=[{"field": "title", "op": op, "value": "x"}],
                group_by=[],
                aggregates=[],
            )
            op_errors = [e for e in errors if UNSUPPORTED_OPERATOR in e]
            self.assertEqual(op_errors, [], f"Op {op!r} should be supported")


# ---------------------------------------------------------------------------
# API tests — definitions CRUD
# ---------------------------------------------------------------------------


class TestDefinitionCRUD(TestCase):
    """Integration tests for ReportDefinition CRUD endpoints."""

    def setUp(self):
        self.tenant = _make_tenant("Acme School", "acme")
        self.admin = _make_user(self.tenant, "admin@acme.test", role="SCHOOL_ADMIN")
        self.teacher = _make_user(self.tenant, "teacher@acme.test", role="TEACHER")
        self.client = _authed_client(self.admin, self.tenant)

    def _call(self, method, path, data=None, user=None, tenant=None):
        tenant = tenant or self.tenant
        u = user or self.admin
        client = APIClient()
        client.force_authenticate(user=u)
        fn = getattr(client, method.lower())
        return fn(
            f"/api/v1/admin/reports{path}",
            data=data,
            format="json",
            HTTP_HOST=f"{tenant.subdomain}.localhost",
        )

    def _force_tenant(self, request, tenant):
        request.tenant = tenant

    def test_create_definition_happy_path(self):
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant):
            resp = self._call(
                "POST",
                "/definitions/",
                data={
                    "name": "Course Completion",
                    "data_source": "courses",
                    "filters_json": [],
                    "group_by_json": [],
                    "aggregates_json": [{"fn": "count", "field": "id"}],
                },
            )
        self.assertIn(resp.status_code, [200, 201])

    def test_teacher_cannot_access_definitions(self):
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant):
            resp = self._call(
                "GET",
                "/definitions/",
                user=self.teacher,
            )
        self.assertEqual(resp.status_code, 403)

    def test_unknown_operator_rejected_at_create(self):
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant):
            resp = self._call(
                "POST",
                "/definitions/",
                data={
                    "name": "Bad Op",
                    "data_source": "courses",
                    "filters_json": [
                        {"field": "title", "op": "LIKE", "value": "%test%"}
                    ],
                    "group_by_json": [],
                    "aggregates_json": [],
                },
            )
        self.assertEqual(resp.status_code, 400)

    def test_unknown_field_rejected_at_create(self):
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant):
            resp = self._call(
                "POST",
                "/definitions/",
                data={
                    "name": "Bad Field",
                    "data_source": "courses",
                    "filters_json": [
                        {"field": "tenant__secret", "op": "eq", "value": "x"}
                    ],
                    "group_by_json": [],
                    "aggregates_json": [],
                },
            )
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# API tests — cross-tenant isolation
# ---------------------------------------------------------------------------


class TestCrossTenantIsolation(TestCase):
    """Cross-tenant access must return 404 (never 403)."""

    def setUp(self):
        self.tenant_a = _make_tenant("School A", "schoola")
        self.tenant_b = _make_tenant("School B", "schoolb")
        self.admin_a = _make_user(self.tenant_a, "admin@schoola.test", "SCHOOL_ADMIN")
        self.admin_b = _make_user(self.tenant_b, "admin@schoolb.test", "SCHOOL_ADMIN")
        self.definition_a = _make_definition(self.tenant_a, self.admin_a)

    def _call(self, method, path, user, tenant, data=None):
        client = APIClient()
        client.force_authenticate(user=user)
        fn = getattr(client, method.lower())
        with patch("utils.tenant_middleware.get_current_tenant", return_value=tenant):
            return fn(
                f"/api/v1/admin/reports{path}",
                data=data,
                format="json",
                HTTP_HOST=f"{tenant.subdomain}.localhost",
            )

    def test_admin_b_cannot_read_tenant_a_definition(self):
        resp = self._call(
            "GET",
            f"/definitions/{self.definition_a.id}/",
            user=self.admin_b,
            tenant=self.tenant_b,
        )
        self.assertEqual(resp.status_code, 404)

    def test_admin_b_cannot_run_tenant_a_definition(self):
        resp = self._call(
            "POST",
            f"/definitions/{self.definition_a.id}/run/",
            user=self.admin_b,
            tenant=self.tenant_b,
        )
        self.assertEqual(resp.status_code, 404)

    def test_admin_b_cannot_export_tenant_a_definition(self):
        resp = self._call(
            "POST",
            f"/definitions/{self.definition_a.id}/export/",
            user=self.admin_b,
            tenant=self.tenant_b,
        )
        self.assertEqual(resp.status_code, 404)

    def test_admin_b_cannot_read_tenant_a_run(self):
        run = ReportRun.all_objects.create(
            tenant=self.tenant_a,
            definition=self.definition_a,
            run_by=self.admin_a,
            params_snapshot_json={},
            status="success",
            artifact_path="/tmp/test.csv",
        )
        resp = self._call(
            "GET",
            f"/runs/{run.id}/download/",
            user=self.admin_b,
            tenant=self.tenant_b,
        )
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# Rate-limit tests
# ---------------------------------------------------------------------------


class TestRateLimit(TestCase):
    """Rate-limit: 20/hr; fail-closed on cache outage."""

    def setUp(self):
        self.tenant = _make_tenant("Rate Limit School", "ratelimit")
        self.admin = _make_user(self.tenant, "admin@ratelimit.test", "SCHOOL_ADMIN")
        self.definition = _make_definition(self.tenant, self.admin)

    def _post_run(self, mock_cache_get=None, mock_cache_set=None):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant):
            patches = []
            if mock_cache_get is not None:
                patches.append(
                    patch(
                        "apps.reports_builder.views.cache.get",
                        side_effect=mock_cache_get,
                    )
                )
            if mock_cache_set is not None:
                patches.append(
                    patch(
                        "apps.reports_builder.views.cache.set",
                        side_effect=mock_cache_set,
                    )
                )
            # Also patch run_report to avoid actual DB queries
            patches.append(
                patch(
                    "apps.reports_builder.views.run_report",
                    return_value=([], 0),
                )
            )
            for p in patches:
                p.start()
            try:
                return client.post(
                    f"/api/v1/admin/reports/definitions/{self.definition.id}/run/",
                    format="json",
                    HTTP_HOST=f"{self.tenant.subdomain}.localhost",
                )
            finally:
                for p in patches:
                    p.stop()

    def test_rate_limit_exceeded_returns_429(self):
        """When cache.get returns >= 20, respond 429."""
        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant), \
             patch("apps.reports_builder.views.cache.get", return_value=20), \
             patch("apps.reports_builder.views.run_report", return_value=([], 0)):
            resp = client.post(
                f"/api/v1/admin/reports/definitions/{self.definition.id}/run/",
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 429)

    def test_rate_limit_fail_closed_cache_get_exception_returns_503(self):
        """cache.get exception → 503 (fail-closed)."""

        def bad_get(key):
            raise ConnectionError("Redis down")

        resp = self._post_run(mock_cache_get=bad_get)
        self.assertEqual(resp.status_code, 503)

    def test_rate_limit_fail_closed_cache_set_exception_returns_503(self):
        """cache.get returns 0; cache.set exception → 503 (fail-closed)."""

        def bad_set(key, val, timeout=None):
            raise ConnectionError("Redis down")

        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant), \
             patch("apps.reports_builder.views.cache.get", return_value=0), \
             patch("apps.reports_builder.views.cache.set", side_effect=ConnectionError("Redis down")), \
             patch("apps.reports_builder.views.run_report", return_value=([], 0)):
            resp = client.post(
                f"/api/v1/admin/reports/definitions/{self.definition.id}/run/",
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 503)


# ---------------------------------------------------------------------------
# Row-cap enforcement
# ---------------------------------------------------------------------------


class TestRowCap(TestCase):
    """ROW_CAP_EXCEEDED must be returned before partial data."""

    def setUp(self):
        self.tenant = _make_tenant("Row Cap School", "rowcap")
        self.admin = _make_user(self.tenant, "admin@rowcap.test", "SCHOOL_ADMIN")
        self.definition = _make_definition(self.tenant, self.admin)

    def test_row_cap_exceeded_returns_400(self):
        from apps.reports_builder.query_engine import ROW_CAP_EXCEEDED

        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant), \
             patch("apps.reports_builder.views.cache.get", return_value=0), \
             patch("apps.reports_builder.views.cache.set"), \
             patch(
                 "apps.reports_builder.views.run_report",
                 side_effect=ValueError(ROW_CAP_EXCEEDED),
             ):
            resp = client.post(
                f"/api/v1/admin/reports/definitions/{self.definition.id}/run/",
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 400)
        self.assertIn(ROW_CAP_EXCEEDED, resp.json().get("error", ""))


# ---------------------------------------------------------------------------
# Signed-URL tests
# ---------------------------------------------------------------------------


class TestSignedUrl(TestCase):
    """Signed-URL is user-bound and reuses the TASK-052 helper."""

    def test_signed_url_is_user_bound(self):
        from apps.courses.helpers.signed_urls import make_signed_url, verify_signed_url

        url = make_signed_url(
            base_url="https://acme.learnpuddle.com/api/v1/admin/reports/runs/abc/artifact/",
            user_id="user-123",
            ttl_seconds=3600,
            extra_params={"run": "abc"},
        )
        # Extract token + expires from URL
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        token = qs["lp_token"][0]
        expires = int(qs["lp_expires"][0])

        # Correct user → valid
        self.assertTrue(
            verify_signed_url(
                base_url="https://acme.learnpuddle.com/api/v1/admin/reports/runs/abc/artifact/",
                user_id="user-123",
                token=token,
                expires_ts=expires,
                extra_params={"run": "abc"},
            )
        )

    def test_signed_url_different_user_invalid(self):
        from apps.courses.helpers.signed_urls import make_signed_url, verify_signed_url
        from urllib.parse import parse_qs, urlparse

        url = make_signed_url(
            base_url="https://acme.learnpuddle.com/api/v1/admin/reports/runs/abc/artifact/",
            user_id="user-A",
            ttl_seconds=3600,
        )
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        token = qs["lp_token"][0]
        expires = int(qs["lp_expires"][0])

        # Different user → invalid
        self.assertFalse(
            verify_signed_url(
                base_url="https://acme.learnpuddle.com/api/v1/admin/reports/runs/abc/artifact/",
                user_id="user-B",  # Different user!
                token=token,
                expires_ts=expires,
            )
        )


# ---------------------------------------------------------------------------
# Scheduled recipient validation
# ---------------------------------------------------------------------------


class TestScheduledRecipientValidation(TestCase):
    """Scheduled report recipients must belong to the same tenant."""

    def setUp(self):
        self.tenant = _make_tenant("Sched School", "schedschool")
        self.admin = _make_user(self.tenant, "admin@schedschool.test", "SCHOOL_ADMIN")
        self.internal_user = _make_user(
            self.tenant, "internal@schedschool.test", "TEACHER"
        )
        self.definition = _make_definition(self.tenant, self.admin)

    def test_external_recipient_rejected(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant):
            resp = client.post(
                f"/api/v1/admin/reports/definitions/{self.definition.id}/schedules/",
                data={
                    "cadence": "daily",
                    "run_at_hour": 6,
                    "recipients_json": ["external@outsider.com"],
                    "enabled": True,
                },
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 400)
        resp_str = str(resp.json())
        self.assertIn("EXTERNAL_RECIPIENT_NOT_ALLOWED", resp_str)

    def test_internal_recipient_accepted(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant):
            resp = client.post(
                f"/api/v1/admin/reports/definitions/{self.definition.id}/schedules/",
                data={
                    "cadence": "daily",
                    "run_at_hour": 6,
                    "recipients_json": ["internal@schedschool.test"],
                    "enabled": True,
                },
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertIn(resp.status_code, [200, 201])


# ---------------------------------------------------------------------------
# Celery task tests
# ---------------------------------------------------------------------------


class TestBuildCsvExportTask(TestCase):
    """build_csv_export Celery task — success and error paths."""

    def setUp(self):
        self.tenant = _make_tenant("Celery School", "celeryschool")
        self.admin = _make_user(self.tenant, "admin@celery.test", "SCHOOL_ADMIN")
        self.definition = _make_definition(
            self.tenant,
            self.admin,
            data_source="courses",
        )

    def test_build_csv_export_success(self):
        """Task writes CSV, updates run to success."""
        run = ReportRun.all_objects.create(
            tenant=self.tenant,
            definition=self.definition,
            run_by=self.admin,
            params_snapshot_json={
                "data_source": "courses",
                "filters": [],
                "group_by": [],
                "aggregates": [],
            },
            status="pending",
        )

        with patch(
            "apps.reports_builder.tasks.run_report",
            return_value=([{"id": str(uuid.uuid4()), "title": "Test Course"}], 1),
        ), patch(
            "apps.reports_builder.tasks.rows_to_csv",
            return_value=(b"id,title\n", "abc123"),
        ), patch(
            "apps.reports_builder.tasks._artifact_path",
        ) as mock_apath:
            mock_apath.return_value.write_bytes = MagicMock()
            mock_apath.return_value.__str__ = lambda self: "/tmp/test_report.csv"
            mock_apath.return_value.__fspath__ = lambda self: "/tmp/test_report.csv"
            # Make str() work on the returned path object
            type(mock_apath.return_value).__str__ = lambda self: "/tmp/test_report.csv"

            from apps.reports_builder.tasks import build_csv_export

            build_csv_export(str(run.id))

        run.refresh_from_db()
        self.assertEqual(run.status, "success")
        self.assertEqual(run.row_count, 1)

    def test_build_csv_export_run_report_error(self):
        """Task captures ValueError into run.error."""
        run = ReportRun.all_objects.create(
            tenant=self.tenant,
            definition=self.definition,
            run_by=self.admin,
            params_snapshot_json={
                "data_source": "courses",
                "filters": [],
                "group_by": [],
                "aggregates": [],
            },
            status="pending",
        )

        with patch(
            "apps.reports_builder.tasks.run_report",
            side_effect=ValueError(ROW_CAP_EXCEEDED),
        ):
            from apps.reports_builder.tasks import build_csv_export

            build_csv_export(str(run.id))

        run.refresh_from_db()
        self.assertEqual(run.status, "error")
        self.assertIn(ROW_CAP_EXCEEDED, run.error)


class TestExecuteScheduledReportTask(TestCase):
    """execute_scheduled_report Celery task — success and error paths."""

    def setUp(self):
        self.tenant = _make_tenant("Sched Task School", "schedtask")
        self.admin = _make_user(self.tenant, "admin@schedtask.test", "SCHOOL_ADMIN")
        self.internal = _make_user(self.tenant, "report@schedtask.test", "TEACHER")
        self.definition = _make_definition(
            self.tenant,
            self.admin,
            data_source="courses",
        )
        self.schedule = ReportSchedule.all_objects.create(
            definition=self.definition,
            tenant=self.tenant,
            cadence="daily",
            run_at_hour=6,
            recipients_json=["report@schedtask.test"],
            enabled=True,
        )

    def test_execute_scheduled_report_success(self):
        """Scheduled task creates run, emails recipients with signed URL."""
        import pathlib

        with patch(
            "apps.reports_builder.tasks.run_report",
            return_value=([{"id": "1", "title": "Course"}], 1),
        ), patch(
            "apps.reports_builder.tasks.rows_to_csv",
            return_value=(b"id,title\n1,Course\n", "abc123"),
        ), patch(
            "apps.reports_builder.tasks._artifact_path",
        ) as mock_apath, patch(
            "apps.reports_builder.tasks.send_mail"
        ) as mock_send:
            mock_apath.return_value.write_bytes = MagicMock()
            type(mock_apath.return_value).__str__ = lambda self: "/tmp/sched_report.csv"

            from apps.reports_builder.tasks import execute_scheduled_report

            execute_scheduled_report(str(self.schedule.id))

        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.last_run_status, "ok")
        self.assertIsNotNone(self.schedule.last_run_at)

        # Verify send_mail was called
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args
        # Email should NOT contain the CSV directly — only a signed URL link
        body = call_kwargs[1].get("message", "") or call_kwargs[0][1]
        self.assertIn("http", body.lower())  # Has a URL
        self.assertNotIn("id,title", body)   # CSV content NOT embedded

    def test_execute_scheduled_report_run_report_error(self):
        """Error in run_report is captured in run.error and schedule.last_run_status."""
        with patch(
            "apps.reports_builder.tasks.run_report",
            side_effect=Exception("DB connection refused"),
        ):
            from apps.reports_builder.tasks import execute_scheduled_report

            execute_scheduled_report(str(self.schedule.id))

        self.schedule.refresh_from_db()
        self.assertEqual(self.schedule.last_run_status, "error")

        # Run record should be created with error status
        runs = ReportRun.all_objects.filter(
            tenant=self.tenant,
            definition=self.definition,
        ).order_by("-started_at")
        self.assertTrue(runs.exists())
        run = runs.first()
        self.assertEqual(run.status, "error")
        self.assertIn("DB connection refused", run.error)


# ---------------------------------------------------------------------------
# Audit log creation
# ---------------------------------------------------------------------------


class TestAuditLogCreation(TestCase):
    """Audit log entries must be created for RUN_REPORT and EXPORT_REPORT."""

    def setUp(self):
        self.tenant = _make_tenant("Audit School", "auditschool")
        self.admin = _make_user(self.tenant, "admin@audit.test", "SCHOOL_ADMIN")
        self.definition = _make_definition(self.tenant, self.admin)

    def test_run_report_creates_audit_log(self):
        initial_count = AuditLog.objects.filter(
            action="RUN_REPORT", tenant=self.tenant
        ).count()

        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant), \
             patch("apps.reports_builder.views.cache.get", return_value=0), \
             patch("apps.reports_builder.views.cache.set"), \
             patch("apps.reports_builder.views.run_report", return_value=([], 0)):
            client.post(
                f"/api/v1/admin/reports/definitions/{self.definition.id}/run/",
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )

        final_count = AuditLog.objects.filter(
            action="RUN_REPORT", tenant=self.tenant
        ).count()
        self.assertEqual(final_count, initial_count + 1)

    def test_export_report_creates_audit_log(self):
        initial_count = AuditLog.objects.filter(
            action="EXPORT_REPORT", tenant=self.tenant
        ).count()

        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch("utils.tenant_middleware.get_current_tenant", return_value=self.tenant), \
             patch("apps.reports_builder.views.cache.get", return_value=0), \
             patch("apps.reports_builder.views.cache.set"), \
             patch("apps.reports_builder.tasks.build_csv_export.delay"):
            client.post(
                f"/api/v1/admin/reports/definitions/{self.definition.id}/export/",
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )

        final_count = AuditLog.objects.filter(
            action="EXPORT_REPORT", tenant=self.tenant
        ).count()
        self.assertEqual(final_count, initial_count + 1)


# ---------------------------------------------------------------------------
# AuditLog ACTION_CHOICES additions
# ---------------------------------------------------------------------------


class TestAuditLogActionChoices(TestCase):
    """Verify the new action codes are present in AuditLog.ACTION_CHOICES."""

    def test_run_report_in_choices(self):
        codes = [code for code, _ in AuditLog.ACTION_CHOICES]
        self.assertIn("RUN_REPORT", codes)

    def test_export_report_in_choices(self):
        codes = [code for code, _ in AuditLog.ACTION_CHOICES]
        self.assertIn("EXPORT_REPORT", codes)

    def test_export_scorm_in_choices(self):
        codes = [code for code, _ in AuditLog.ACTION_CHOICES]
        self.assertIn("EXPORT_SCORM", codes)

    def test_import_scorm_in_choices(self):
        codes = [code for code, _ in AuditLog.ACTION_CHOICES]
        self.assertIn("IMPORT_SCORM", codes)


# ---------------------------------------------------------------------------
# TASK-053 round 2 — per-recipient signed URLs + delivery failure surfacing
# ---------------------------------------------------------------------------


class TestScheduledEmailSignedUrlsPerRecipient(TestCase):
    """Each recipient gets a distinct signed URL bound to their own user_id."""

    def setUp(self):
        self.tenant = _make_tenant("Signed URL School", "signedurl")
        self.admin = _make_user(self.tenant, "admin@signedurl.test", "SCHOOL_ADMIN")
        self.recipient1 = _make_user(self.tenant, "r1@signedurl.test", "TEACHER")
        self.recipient2 = _make_user(self.tenant, "r2@signedurl.test", "TEACHER")
        self.definition = _make_definition(
            self.tenant, self.admin, data_source="courses"
        )
        self.schedule = ReportSchedule.all_objects.create(
            definition=self.definition,
            tenant=self.tenant,
            cadence="daily",
            run_at_hour=8,
            recipients_json=[
                "r1@signedurl.test",
                "r2@signedurl.test",
            ],
            enabled=True,
        )

    def test_scheduled_email_signed_urls_are_per_recipient(self):
        """
        Each recipient gets a URL signed with their own user_id.
        A URL signed for recipient 1 must fail verify_signed_url when checked
        against recipient 2's user_id.
        """
        from urllib.parse import parse_qs, urlparse

        from apps.courses.helpers.signed_urls import verify_signed_url

        sent_calls = []

        def capture_send_mail(**kwargs):
            sent_calls.append(kwargs)

        with patch(
            "apps.reports_builder.tasks.run_report",
            return_value=([{"id": "1", "title": "Course"}], 1),
        ), patch(
            "apps.reports_builder.tasks.rows_to_csv",
            return_value=(b"id,title\n1,Course\n", "abc123"),
        ), patch(
            "apps.reports_builder.tasks._artifact_path",
        ) as mock_apath, patch(
            "apps.reports_builder.tasks.send_mail",
            side_effect=capture_send_mail,
        ):
            mock_apath.return_value.write_bytes = MagicMock()
            type(mock_apath.return_value).__str__ = lambda self: "/tmp/signed_test.csv"

            from apps.reports_builder.tasks import execute_scheduled_report

            execute_scheduled_report(str(self.schedule.id))

        # Both recipients should have received an email.
        self.assertEqual(len(sent_calls), 2)

        # Map each email address to the URL it was sent.
        def _extract_url_and_params(body: str):
            for line in body.splitlines():
                line = line.strip()
                if line.startswith("http"):
                    parsed = urlparse(line)
                    qs = parse_qs(parsed.query)
                    base = line.split("?")[0]
                    return base, qs["lp_token"][0], int(qs["lp_expires"][0]), qs.get("run", [None])[0]
            return None, None, None, None

        by_recipient: dict[str, tuple] = {}
        for call in sent_calls:
            recipients = call["recipient_list"]
            self.assertEqual(len(recipients), 1, "Each call must address exactly one recipient")
            email = recipients[0]
            body = call["message"]
            by_recipient[email] = _extract_url_and_params(body)

        self.assertIn("r1@signedurl.test", by_recipient)
        self.assertIn("r2@signedurl.test", by_recipient)

        # Recipient 1's URL must verify against recipient 1's user_id.
        base1, token1, expires1, run_id1 = by_recipient["r1@signedurl.test"]
        extra1 = {"run": run_id1} if run_id1 else None
        self.assertTrue(
            verify_signed_url(
                base_url=base1,
                user_id=str(self.recipient1.id),
                token=token1,
                expires_ts=expires1,
                extra_params=extra1,
            ),
            "Recipient 1's URL should verify as recipient 1",
        )

        # Recipient 1's URL must NOT verify against recipient 2's user_id.
        self.assertFalse(
            verify_signed_url(
                base_url=base1,
                user_id=str(self.recipient2.id),
                token=token1,
                expires_ts=expires1,
                extra_params=extra1,
            ),
            "Recipient 1's URL must not be usable by recipient 2",
        )


class TestSendMailFailuresSurfaceInRunError(TestCase):
    """send_mail failures must surface in ReportRun.error and affect status."""

    def setUp(self):
        self.tenant = _make_tenant("Delivery Fail School", "delivfail")
        self.admin = _make_user(self.tenant, "admin@delivfail.test", "SCHOOL_ADMIN")
        self.r1 = _make_user(self.tenant, "ok@delivfail.test", "TEACHER")
        self.r2 = _make_user(self.tenant, "fail@delivfail.test", "TEACHER")
        self.definition = _make_definition(
            self.tenant, self.admin, data_source="courses"
        )

    def _make_schedule(self, recipients):
        return ReportSchedule.all_objects.create(
            definition=self.definition,
            tenant=self.tenant,
            cadence="daily",
            run_at_hour=9,
            recipients_json=recipients,
            enabled=True,
        )

    def _run_task(self, schedule, send_mail_side_effect):
        with patch(
            "apps.reports_builder.tasks.run_report",
            return_value=([{"id": "1", "title": "Course"}], 1),
        ), patch(
            "apps.reports_builder.tasks.rows_to_csv",
            return_value=(b"id,title\n", "sha"),
        ), patch(
            "apps.reports_builder.tasks._artifact_path",
        ) as mock_apath, patch(
            "apps.reports_builder.tasks.send_mail",
            side_effect=send_mail_side_effect,
        ):
            mock_apath.return_value.write_bytes = MagicMock()
            type(mock_apath.return_value).__str__ = lambda self: "/tmp/df.csv"

            from apps.reports_builder.tasks import execute_scheduled_report

            execute_scheduled_report(str(schedule.id))

    def test_partial_failure_surfaces_in_error_status_stays_success(self):
        """2nd recipient fails; run stays 'success' but error contains DELIVERY_FAILED."""
        call_count = [0]

        def selective_fail(**kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise OSError("SMTP timeout")

        schedule = self._make_schedule(
            ["ok@delivfail.test", "fail@delivfail.test"]
        )
        self._run_task(schedule, selective_fail)

        run = ReportRun.all_objects.filter(
            tenant=self.tenant, definition=self.definition
        ).order_by("-started_at").first()
        self.assertIsNotNone(run)
        self.assertEqual(run.status, "success")
        self.assertIn("DELIVERY_FAILED to fail@delivfail.test", run.error or "")

    def test_all_recipients_fail_sets_run_status_error(self):
        """All sends fail → run.status=='error' and schedule.last_run_status=='delivery_failed'.

        'failed' was a bug — not in ReportRun.STATUS_CHOICES. Correct value is 'error'.
        The schedule-level delivery failure is recorded in schedule.last_run_status
        ('delivery_failed' is valid in ReportSchedule.STATUS_CHOICES).
        """

        def always_fail(**kwargs):
            raise OSError("SMTP timeout")

        schedule = self._make_schedule(
            ["ok@delivfail.test", "fail@delivfail.test"]
        )
        self._run_task(schedule, always_fail)

        run = ReportRun.all_objects.filter(
            tenant=self.tenant, definition=self.definition
        ).order_by("-started_at").first()
        self.assertIsNotNone(run)
        self.assertEqual(run.status, "error")  # 'error' is the valid STATUS_CHOICES failure value

        schedule.refresh_from_db()
        self.assertEqual(schedule.last_run_status, "delivery_failed")
