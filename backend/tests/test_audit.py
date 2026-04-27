# tests/test_audit.py
"""
Tests for utils/audit.py — AuditLog creation utility.

Covers:
1. log_audit() creates an AuditLog record with correct fields
2. Actor is inferred from request.user when not passed explicitly
3. Tenant is inferred from request.tenant when not passed explicitly
4. IP address extracted from REMOTE_ADDR (direct connection)
5. IP address extracted from X-Forwarded-For (behind proxy)
6. User agent captured from HTTP_USER_AGENT
7. Silent failure when AuditLog creation fails (no exception propagated)
8. Passing explicit actor/tenant overrides request values
9. _get_client_ip helper function works correctly
"""

import pytest
from django.test import TestCase


# ===========================================================================
# Helpers
# ===========================================================================

def _make_request(
    remote_addr="1.2.3.4",
    xff=None,
    user_agent="TestAgent/1.0",
    user=None,
    tenant=None,
    request_id="req-abc123",
):
    """Build a minimal mock request for audit tests.

    When ``user`` is a real Django User instance, it is attached directly so
    that Django FK assignment works correctly.  When ``user`` is None a tiny
    anonymous stub is used.
    """
    from types import SimpleNamespace

    class AnonymousUser:
        """Minimal stub for an unauthenticated request user."""
        is_authenticated = False

    meta = {
        "REMOTE_ADDR": remote_addr,
        "HTTP_USER_AGENT": user_agent,
    }
    if xff:
        meta["HTTP_X_FORWARDED_FOR"] = xff

    request = SimpleNamespace(
        META=meta,
        user=user if user is not None else AnonymousUser(),
        tenant=tenant,
        request_id=request_id,
    )
    return request


# ===========================================================================
# 1. AuditLog Record Creation Tests
# ===========================================================================


@pytest.mark.django_db
class AuditLogCreationTestCase(TestCase):
    """log_audit() must create AuditLog records with correct field values."""

    def _create_tenant(self):
        from apps.tenants.models import Tenant
        return Tenant.objects.create(
            name="Audit Test School",
            slug="audit-test-school",
            subdomain="audittest",
            email="admin@audittest.com",
            is_active=True,
        )

    def _create_user(self, tenant):
        from apps.users.models import User
        return User.objects.create_user(
            email="actor@audittest.com",
            password="pass123",
            tenant=tenant,
            role="SCHOOL_ADMIN",
            first_name="Actor",
            last_name="User",
            is_active=True,
        )

    def test_audit_log_created_with_action_and_target_type(self):
        """log_audit() must create a record with the given action and target_type."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        initial_count = AuditLog.objects.count()

        log_audit(
            action="CREATE",
            target_type="Course",
            tenant=tenant,
        )

        self.assertEqual(
            AuditLog.objects.count(),
            initial_count + 1,
            "log_audit() must create exactly one AuditLog record",
        )
        entry = AuditLog.objects.latest("id")
        self.assertEqual(entry.action, "CREATE")
        self.assertEqual(entry.target_type, "Course")

    def test_audit_log_captures_target_id_and_repr(self):
        """target_id and target_repr must be stored correctly."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()

        log_audit(
            action="UPDATE",
            target_type="User",
            target_id="some-uuid-123",
            target_repr="User(admin@test.com)",
            tenant=tenant,
        )

        entry = AuditLog.objects.latest("id")
        self.assertEqual(entry.target_id, "some-uuid-123")
        self.assertEqual(entry.target_repr, "User(admin@test.com)")

    def test_audit_log_captures_changes(self):
        """changes dict must be stored in the AuditLog record."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        changes = {"title": {"from": "Old Title", "to": "New Title"}}

        log_audit(
            action="UPDATE",
            target_type="Course",
            changes=changes,
            tenant=tenant,
        )

        entry = AuditLog.objects.latest("id")
        self.assertEqual(entry.changes, changes)

    def test_audit_log_empty_changes_stored_as_empty_dict(self):
        """When changes is None, it should be stored as {}."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        log_audit(action="DELETE", target_type="Module", tenant=tenant)

        entry = AuditLog.objects.latest("id")
        self.assertEqual(entry.changes, {})

    def test_explicit_actor_stored_correctly(self):
        """Explicitly passed actor must be stored in the AuditLog."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        user = self._create_user(tenant)

        log_audit(
            action="CREATE",
            target_type="Assignment",
            actor=user,
            tenant=tenant,
        )

        entry = AuditLog.objects.latest("id")
        self.assertEqual(entry.actor_id, user.id)

    def test_actor_inferred_from_request_user(self):
        """When actor is not passed, request.user must be used as actor."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        user = self._create_user(tenant)

        request = _make_request(user=user, tenant=tenant)
        log_audit(
            action="RUN_REPORT",
            target_type="Dashboard",
            request=request,
        )

        entry = AuditLog.objects.latest("id")
        self.assertEqual(
            entry.actor_id,
            user.id,
            "actor must be inferred from request.user when not explicitly passed",
        )

    def test_tenant_inferred_from_request(self):
        """When tenant is not passed, request.tenant must be used."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        request = _make_request(tenant=tenant)

        log_audit(
            action="CREATE",
            target_type="Content",
            request=request,
        )

        entry = AuditLog.objects.latest("id")
        self.assertEqual(
            entry.tenant_id,
            tenant.id,
            "tenant must be inferred from request.tenant when not explicitly passed",
        )


# ===========================================================================
# 2. IP Address Extraction Tests
# ===========================================================================


@pytest.mark.django_db
class IPAddressExtractionTestCase(TestCase):
    """log_audit() must correctly extract client IP from request metadata."""

    def _create_tenant(self):
        from apps.tenants.models import Tenant
        return Tenant.objects.create(
            name="IP Test School",
            slug="ip-test-school",
            subdomain="iptestschool",
            email="admin@iptestschool.com",
            is_active=True,
        )

    def test_ip_extracted_from_remote_addr(self):
        """Direct connection: REMOTE_ADDR must be used as IP."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        request = _make_request(remote_addr="10.20.30.40", tenant=tenant)

        log_audit(action="LOGIN", target_type="Session", request=request)

        entry = AuditLog.objects.latest("id")
        self.assertEqual(
            entry.ip_address,
            "10.20.30.40",
            "IP must be extracted from REMOTE_ADDR for direct connections",
        )

    def test_ip_extracted_from_x_forwarded_for_single(self):
        """Behind a single proxy: X-Forwarded-For must take precedence."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        request = _make_request(
            remote_addr="172.16.0.1",  # internal proxy IP
            xff="203.0.113.1",
            tenant=tenant,
        )

        log_audit(action="LOGIN", target_type="Session", request=request)

        entry = AuditLog.objects.latest("id")
        self.assertEqual(
            entry.ip_address,
            "203.0.113.1",
            "X-Forwarded-For must take precedence over REMOTE_ADDR",
        )

    def test_ip_extracted_from_x_forwarded_for_chain(self):
        """X-Forwarded-For with multiple IPs: first (client) IP must be used."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        # Multiple proxies: original client, then proxy IPs
        request = _make_request(
            remote_addr="10.0.0.1",
            xff="203.0.113.1, 10.1.1.1, 10.2.2.2",
            tenant=tenant,
        )

        log_audit(action="EXPORT_REPORT", target_type="Report", request=request)

        entry = AuditLog.objects.latest("id")
        self.assertEqual(
            entry.ip_address,
            "203.0.113.1",
            "First IP in X-Forwarded-For chain is the client IP",
        )

    def test_ip_none_when_no_request(self):
        """When no request is passed, IP must be None."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.create(
            name="No-Request School",
            slug="no-request-school",
            subdomain="norequestschool",
            email="admin@norequestschool.com",
            is_active=True,
        )

        log_audit(action="SETTINGS_CHANGE", target_type="Job", tenant=tenant)

        entry = AuditLog.objects.latest("id")
        self.assertIsNone(entry.ip_address)


# ===========================================================================
# 3. User Agent Capture Tests
# ===========================================================================


@pytest.mark.django_db
class UserAgentCaptureTestCase(TestCase):
    """log_audit() must capture the user agent string."""

    def _create_tenant(self):
        from apps.tenants.models import Tenant
        return Tenant.objects.create(
            name="UA Test School",
            slug="ua-test-school",
            subdomain="uatestschool",
            email="admin@uatestschool.com",
            is_active=True,
        )

    def test_user_agent_captured(self):
        """User agent string must be stored in the AuditLog."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        request = _make_request(
            user_agent="Mozilla/5.0 (compatible; LearnPuddleBot/1.0)",
            tenant=tenant,
        )

        log_audit(action="RUN_REPORT", target_type="Course", request=request)

        entry = AuditLog.objects.latest("id")
        self.assertEqual(
            entry.user_agent,
            "Mozilla/5.0 (compatible; LearnPuddleBot/1.0)",
        )

    def test_long_user_agent_truncated_to_500_chars(self):
        """User agents over 500 chars must be truncated (not cause DB error)."""
        from utils.audit import log_audit
        from apps.tenants.models import AuditLog

        tenant = self._create_tenant()
        long_ua = "A" * 1000

        request = _make_request(user_agent=long_ua, tenant=tenant)
        log_audit(action="RUN_REPORT", target_type="Course", request=request)

        entry = AuditLog.objects.latest("id")
        self.assertLessEqual(
            len(entry.user_agent),
            500,
            "User agent must be truncated to 500 characters",
        )


# ===========================================================================
# 4. Silent Failure Tests
# ===========================================================================


class AuditSilentFailureTestCase(TestCase):
    """log_audit() must not raise even when AuditLog creation fails."""

    def test_no_exception_raised_on_failure(self):
        """
        If AuditLog.objects.create() fails (e.g., DB constraint), log_audit()
        must catch the exception and not propagate it. Audit failure must not
        break the request that triggered it.
        """
        from unittest.mock import patch
        from utils.audit import log_audit

        with patch("apps.tenants.models.AuditLog.objects.create") as mock_create:
            mock_create.side_effect = Exception("Simulated DB error")

            # Must not raise
            try:
                log_audit(action="CREATE", target_type="Resilience")
            except Exception:
                self.fail("log_audit() must not raise even when AuditLog.create() fails")


# ===========================================================================
# 5. _get_client_ip Unit Tests
# ===========================================================================


class GetClientIPTestCase(TestCase):
    """Unit tests for the _get_client_ip helper function."""

    def test_returns_remote_addr_without_xff(self):
        """Without X-Forwarded-For, REMOTE_ADDR must be returned."""
        from utils.audit import _get_client_ip
        from types import SimpleNamespace

        request = SimpleNamespace(META={"REMOTE_ADDR": "5.6.7.8"})
        self.assertEqual(_get_client_ip(request), "5.6.7.8")

    def test_returns_first_xff_ip_with_multiple(self):
        """With X-Forwarded-For chain, first IP must be returned."""
        from utils.audit import _get_client_ip
        from types import SimpleNamespace

        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "10.0.0.1",
                "HTTP_X_FORWARDED_FOR": "203.0.113.5, 10.0.0.2, 10.0.0.3",
            }
        )
        self.assertEqual(_get_client_ip(request), "203.0.113.5")

    def test_xff_single_ip_without_chain(self):
        """X-Forwarded-For with single IP must return that IP."""
        from utils.audit import _get_client_ip
        from types import SimpleNamespace

        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "10.0.0.1",
                "HTTP_X_FORWARDED_FOR": "198.51.100.1",
            }
        )
        self.assertEqual(_get_client_ip(request), "198.51.100.1")

    def test_xff_with_whitespace_stripped(self):
        """Leading/trailing whitespace in XFF IPs must be stripped."""
        from utils.audit import _get_client_ip
        from types import SimpleNamespace

        request = SimpleNamespace(
            META={
                "REMOTE_ADDR": "10.0.0.1",
                "HTTP_X_FORWARDED_FOR": "  203.0.113.99  , 10.0.0.2",
            }
        )
        self.assertEqual(_get_client_ip(request), "203.0.113.99")
