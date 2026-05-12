"""
Tests for the iCal feed endpoint + builder.

Covers acceptance criteria:
 - valid ICS round-trip (icalendar.Calendar.from_ical)
 - missing/invalid token → 404 (no 401, no leak)
 - token revocation + rotation flow
 - cross-tenant isolation via token binding
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.integrations_calendar.ical_builder import build_ical_feed
from apps.integrations_calendar.models import ICalToken


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def make_tenant(name="iCal School", subdomain="ical-school"):
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name=name,
        subdomain=subdomain,
        slug=subdomain,
        email=f"admin@{subdomain}.example.com",
    )


def make_user(tenant, role="TEACHER", email=None):
    from apps.users.models import User
    email = email or f"{role.lower()}-{uuid.uuid4().hex[:6]}@{tenant.subdomain}.example.com"
    return User.objects.create_user(
        email=email,
        password="Passw0rd!123",
        tenant=tenant,
        role=role,
    )


def _always_allow_rate_limit(*_args, **_kwargs):
    return True


# ---------------------------------------------------------------------------
# 1. Builder round-trips through icalendar parser (ACCEPTANCE)
# ---------------------------------------------------------------------------


class TestICalBuilderRoundtrip(TestCase):
    def setUp(self):
        self.tenant = make_tenant(name="Builder School", subdomain="builder-school")
        self.user = make_user(self.tenant)

    def test_feed_parses_as_valid_ics(self):
        """
        build_ical_feed must emit bytes that the icalendar library can
        parse back into a Calendar object (RFC 5545 conformance).
        """
        from icalendar import Calendar

        ics_bytes = build_ical_feed(user=self.user)
        self.assertIsInstance(ics_bytes, bytes)

        cal = Calendar.from_ical(ics_bytes)
        # VCALENDAR-level properties.
        self.assertEqual(str(cal.get("version")), "2.0")
        self.assertIn("LearnPuddle", str(cal.get("prodid")))

    def test_feed_always_emits_calscale_method(self):
        """Essential RFC 5545 fields are present even with zero events."""
        from icalendar import Calendar

        ics_bytes = build_ical_feed(user=self.user)
        cal = Calendar.from_ical(ics_bytes)
        self.assertEqual(str(cal.get("calscale")), "GREGORIAN")
        self.assertEqual(str(cal.get("method")), "PUBLISH")

    def test_feed_includes_assignments_from_assigned_courses(self):
        """Regression: calendar feeds now use Course assignment fields."""
        from django.utils import timezone
        from icalendar import Calendar
        from apps.courses.models import Course
        from apps.progress.models import Assignment

        course = Course.objects.create(
            tenant=self.tenant,
            title="Assigned Calendar Course",
            description="Calendar course",
            is_published=True,
            is_active=True,
            created_by=self.user,
        )
        course.assigned_teachers.add(self.user)
        assignment = Assignment.objects.create(
            tenant=self.tenant,
            course=course,
            title="Assigned iCal due date",
            description="Should appear in the feed.",
            due_date=timezone.now() + timezone.timedelta(days=3),
            is_active=True,
        )

        cal = Calendar.from_ical(build_ical_feed(user=self.user))
        events = cal.walk("VEVENT")

        self.assertEqual(len(events), 1)
        self.assertIn("Assigned iCal due date", str(events[0].get("summary")))
        self.assertIn(str(assignment.id), str(events[0].get("uid")))


# ---------------------------------------------------------------------------
# 2. Missing / invalid token → 404 (no 401, no leak)
# ---------------------------------------------------------------------------


class TestICalFeedTokenAuth(TestCase):
    def setUp(self):
        self.tenant = make_tenant(name="Feed School", subdomain="feed-school")
        self.user = make_user(self.tenant)
        self.client = APIClient()
        # Always allow — rate limit is a separate concern.
        self.rate_patch = patch(
            "apps.integrations_calendar.views._rate_limit_ical",
            side_effect=_always_allow_rate_limit,
        )
        self.rate_patch.start()

    def tearDown(self):
        self.rate_patch.stop()

    def test_invalid_token_returns_404(self):
        """
        An iCal feed URL with an unknown token must return 404 — never
        401, to avoid leaking the existence of the user.
        """
        url = f"/api/v1/calendar/ical/{self.user.pk}/nonexistent-token.ics"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_unknown_user_returns_404(self):
        """Unknown user UUID → 404, same as bad token."""
        random_uuid = uuid.uuid4()
        url = f"/api/v1/calendar/ical/{random_uuid}/anytoken.ics"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_valid_token_returns_ics(self):
        """Valid token → 200 with text/calendar content type."""
        token_instance, raw_token = ICalToken.generate(user=self.user)

        url = f"/api/v1/calendar/ical/{self.user.pk}/{raw_token}.ics"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp["Content-Type"].startswith("text/calendar"))
        self.assertIn(b"BEGIN:VCALENDAR", resp.content)
        self.assertIn(b"END:VCALENDAR", resp.content)

    def test_revoked_token_returns_404(self):
        """A revoked ICalToken must not grant feed access."""
        from django.utils import timezone

        token_instance, raw_token = ICalToken.generate(user=self.user)
        token_instance.revoked_at = timezone.now()
        token_instance.save(update_fields=["revoked_at"])

        url = f"/api/v1/calendar/ical/{self.user.pk}/{raw_token}.ics"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# 3. Cross-tenant isolation — user B cannot subscribe via user A's UUID
# ---------------------------------------------------------------------------


class TestICalCrossTenantIsolation(TestCase):
    """
    Acceptance: cross-tenant user cannot subscribe to another user's iCal
    even if they somehow guessed the UUID. The token check is bound to
    the specific user row, so a token minted for user B of tenant B
    cannot authenticate user A's feed URL.
    """

    def setUp(self):
        self.tenant_a = make_tenant(name="Alpha Tenant", subdomain="alpha-tenant")
        self.tenant_b = make_tenant(name="Beta Tenant", subdomain="beta-tenant")
        self.user_a = make_user(self.tenant_a, email="a@alpha-tenant.example.com")
        self.user_b = make_user(self.tenant_b, email="b@beta-tenant.example.com")
        self.client = APIClient()
        self.rate_patch = patch(
            "apps.integrations_calendar.views._rate_limit_ical",
            side_effect=_always_allow_rate_limit,
        )
        self.rate_patch.start()

    def tearDown(self):
        self.rate_patch.stop()

    def test_user_b_token_on_user_a_url_returns_404(self):
        """
        Token belongs to user B; using it in user A's URL must 404 (token
        lookup is tenant-isolated via the user FK).
        """
        _token_b, raw_token_b = ICalToken.generate(user=self.user_b)
        url = f"/api/v1/calendar/ical/{self.user_a.pk}/{raw_token_b}.ics"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# 4. Revoke endpoint — rotates token, invalidates previous, returns new URL
# ---------------------------------------------------------------------------


class TestICalRevokeEndpoint(TestCase):
    def setUp(self):
        self.tenant = make_tenant(name="Rotate School", subdomain="rotate-school")
        self.user = make_user(self.tenant)
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.rate_patch = patch(
            "apps.integrations_calendar.views._rate_limit_ical",
            side_effect=_always_allow_rate_limit,
        )
        self.rate_patch.start()

    def tearDown(self):
        self.rate_patch.stop()

    def test_revoke_rotates_token_and_invalidates_previous(self):
        """
        POST /calendar/ical/revoke/ must:
          - revoke all active ICalToken rows for the caller
          - issue a brand-new token
          - return a feed URL containing that new token
        The previous raw token must no longer be accepted by the feed.
        """
        # Issue the first token out-of-band (simulating a prior subscription).
        _first, first_raw = ICalToken.generate(user=self.user)

        host = f"{self.tenant.subdomain}.localhost"

        # Confirm the old token works right now (iCal feed is AllowAny —
        # no tenant membership enforced, but the middleware still needs
        # a resolvable host).
        first_url = f"/api/v1/calendar/ical/{self.user.pk}/{first_raw}.ics"
        resp1 = self.client.get(first_url, HTTP_HOST=host)
        self.assertEqual(resp1.status_code, 200)

        # Rotate.
        rotate_resp = self.client.post(
            "/api/v1/calendar/ical/revoke/", HTTP_HOST=host,
        )
        self.assertEqual(rotate_resp.status_code, 200)
        self.assertIn("feed_url", rotate_resp.json())
        # feed_url must carry a *different* token than the original.
        self.assertNotIn(first_raw, rotate_resp.json()["feed_url"])

        # Old token is now revoked → feed URL returns 404.
        resp2 = self.client.get(first_url, HTTP_HOST=host)
        self.assertEqual(resp2.status_code, 404)

    def test_revoke_requires_authentication(self):
        """Unauthenticated callers cannot rotate someone's token."""
        anon = APIClient()
        resp = anon.post(
            "/api/v1/calendar/ical/revoke/",
            HTTP_HOST=f"{self.tenant.subdomain}.localhost",
        )
        self.assertIn(resp.status_code, (401, 403))


# ---------------------------------------------------------------------------
# 5. Cache header present (10-minute cache semantic)
# ---------------------------------------------------------------------------


class TestICalCacheHeader(TestCase):
    """
    Acceptance: iCal URL cached 10 min.  The view emits
    ``Cache-Control: private, max-age=600`` which downstream calendar
    clients and CDN caches honour — this unit test asserts the header
    is present, documenting contract with upstream poll-heavy clients.
    """

    def setUp(self):
        self.tenant = make_tenant(name="Cache School", subdomain="cache-school")
        self.user = make_user(self.tenant)
        self.client = APIClient()
        self.rate_patch = patch(
            "apps.integrations_calendar.views._rate_limit_ical",
            side_effect=_always_allow_rate_limit,
        )
        self.rate_patch.start()

    def tearDown(self):
        self.rate_patch.stop()

    def test_response_advertises_10_minute_cache(self):
        _token, raw = ICalToken.generate(user=self.user)
        resp = self.client.get(f"/api/v1/calendar/ical/{self.user.pk}/{raw}.ics")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("max-age=600", resp["Cache-Control"])
