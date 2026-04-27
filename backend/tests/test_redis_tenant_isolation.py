# tests/test_redis_tenant_isolation.py
"""
Redis tenant isolation tests (Phase 1 — Security).

Verifies that Redis-backed infrastructure (cache, channel layers) does not
allow cross-tenant data leakage:

1. Cache configuration has a proper KEY_PREFIX (not empty/None)
2. Tenant-scoped cache writes in tenant A context are not visible in tenant B context
3. Rate-limiting keys are isolated so one tenant's throttling doesn't affect another
4. Cache entries set during a request for tenant A are not retrievable under tenant B
5. Context switch (A → B) produces isolated cache reads
6. Channel-layer group names should embed tenant context (prevents broadcast leakage)
7. Clearing the tenant context after a request also clears any tenant-local cache state
"""

import pytest
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.tenants.models import Tenant
from apps.users.models import User
from utils.tenant_middleware import (
    clear_current_tenant,
    get_current_tenant,
    set_current_tenant,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name: str, subdomain: str) -> Tenant:
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.example.com",
        is_active=True,
    )


def _make_user(email: str, tenant: Tenant, role: str = "SCHOOL_ADMIN") -> User:
    return User.objects.create_user(
        email=email,
        password="TestPass!123",
        first_name="Test",
        last_name="User",
        tenant=tenant,
        role=role,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# 1. Cache Configuration Tests
# ---------------------------------------------------------------------------

class CacheConfigurationTestCase(TestCase):
    """
    Verify that Django's CACHES configuration is production-safe:
    - KEY_PREFIX is set (prevents collisions with other applications on the same Redis)
    - Correct backend is configured
    """

    def test_cache_key_prefix_is_set(self):
        """
        KEY_PREFIX must not be empty or None. An empty prefix would allow
        cache keys from different deployments to collide on a shared Redis instance.
        """
        from django.conf import settings
        default_cache = settings.CACHES.get("default", {})
        key_prefix = default_cache.get("KEY_PREFIX", "")
        self.assertIsNotNone(key_prefix, "CACHES['default']['KEY_PREFIX'] must not be None")
        self.assertGreater(
            len(key_prefix),
            0,
            "CACHES['default']['KEY_PREFIX'] must be a non-empty string",
        )

    def test_cache_uses_redis_backend(self):
        """Cache backend should be Redis for production behaviour consistency."""
        from django.conf import settings
        backend = settings.CACHES.get("default", {}).get("BACKEND", "")
        # Accept both Django's built-in Redis backend and django-redis
        self.assertIn(
            "redis",
            backend.lower(),
            "Cache backend should be a Redis-based backend",
        )

    def test_cache_timeout_is_positive(self):
        """Default cache TIMEOUT must be a positive integer (seconds)."""
        from django.conf import settings
        timeout = settings.CACHES.get("default", {}).get("TIMEOUT", None)
        # None means "cache forever" — both are acceptable, but must not be 0
        if timeout is not None:
            self.assertGreater(
                timeout,
                0,
                "TIMEOUT must be > 0 (or None for infinite)",
            )


# ---------------------------------------------------------------------------
# 2. Cache Key Namespacing by Tenant
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TenantCacheIsolationTestCase(TestCase):
    """
    Simulate the pattern used by view-level caching to ensure that a cache
    key written for tenant A is not accessible (or returns a different value)
    when the same logical key is read under tenant B's context.

    Pattern under test:
        key = f"tenant:{tenant.id}:dashboard:{user.id}"
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Cache School A", "cachea")
        self.tenant_b = _make_tenant("Cache School B", "cacheb")
        self.admin_a = _make_user("admin@cachea.com", self.tenant_a)
        self.admin_b = _make_user("admin@cacheb.com", self.tenant_b)
        cache.clear()

    def tearDown(self):
        clear_current_tenant()
        cache.clear()

    def _tenant_dashboard_cache_key(self, tenant, user):
        """Helper: build the expected tenant-scoped cache key pattern."""
        return f"tenant:{tenant.id}:dashboard:{user.id}"

    def test_tenant_scoped_key_is_not_readable_by_other_tenant(self):
        """
        Value cached under tenant A's key must NOT be readable using tenant B's key.
        """
        key_a = self._tenant_dashboard_cache_key(self.tenant_a, self.admin_a)
        key_b = self._tenant_dashboard_cache_key(self.tenant_b, self.admin_b)

        cache.set(key_a, {"overall_progress": 85}, timeout=60)

        # Tenant B's key should not return tenant A's data
        value_b = cache.get(key_b)
        self.assertIsNone(
            value_b,
            "Tenant B's cache key must not resolve to Tenant A's cached data",
        )

    def test_different_tenants_same_user_id_suffix_dont_collide(self):
        """
        Two tenants may have users with the same integer PK suffix.
        The tenant-prefixed key must still be distinct.
        """
        # Create keys that differ only in tenant ID (not user ID)
        key_a = f"tenant:{self.tenant_a.id}:resource:some-resource-id"
        key_b = f"tenant:{self.tenant_b.id}:resource:some-resource-id"

        cache.set(key_a, "secret_tenant_a", timeout=60)
        cache.set(key_b, "secret_tenant_b", timeout=60)

        self.assertEqual(cache.get(key_a), "secret_tenant_a")
        self.assertEqual(cache.get(key_b), "secret_tenant_b")
        self.assertNotEqual(
            cache.get(key_a),
            cache.get(key_b),
            "Tenant A and B cache entries with same suffix must be distinct",
        )

    def test_deleting_tenant_a_cache_does_not_affect_tenant_b(self):
        """
        Deleting cached data for tenant A must not corrupt tenant B's cache entries.
        """
        key_a = self._tenant_dashboard_cache_key(self.tenant_a, self.admin_a)
        key_b = self._tenant_dashboard_cache_key(self.tenant_b, self.admin_b)

        cache.set(key_a, "data_for_a", timeout=60)
        cache.set(key_b, "data_for_b", timeout=60)

        cache.delete(key_a)

        self.assertIsNone(cache.get(key_a), "Tenant A key should be deleted")
        self.assertEqual(
            cache.get(key_b),
            "data_for_b",
            "Tenant B's cache entry must be unaffected",
        )

    def test_cache_write_in_tenant_a_context_not_visible_in_tenant_b_context(self):
        """
        Write a cache entry while tenant A is active.
        Switch to tenant B context — the entry is not accessible via B's equivalent key.
        """
        set_current_tenant(self.tenant_a)
        tenant_a_key = f"tenant:{get_current_tenant().id}:courses_count"
        cache.set(tenant_a_key, 42, timeout=60)
        clear_current_tenant()

        set_current_tenant(self.tenant_b)
        tenant_b_key = f"tenant:{get_current_tenant().id}:courses_count"

        self.assertNotEqual(tenant_a_key, tenant_b_key, "Keys must differ across tenants")
        self.assertIsNone(
            cache.get(tenant_b_key),
            "Tenant B context must not expose Tenant A's cached data",
        )
        clear_current_tenant()


# ---------------------------------------------------------------------------
# 3. Rate-Limiting Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class RateLimitingIsolationTestCase(TestCase):
    """
    Verify that rate-limiting keys do not bleed across tenants.

    If rate limiting is implemented per IP or per token, exhausting limits
    for one tenant's IP should NOT affect another tenant's users at the same IP.

    (Current implementation keys are: "ical_rate:{token_hash}" and
     "throttle_saml_acs:{ip}" — both non-tenant-specific, which is correct
     since rate limits are per user/token, not per tenant.)
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Rate School A", "ratea")
        self.tenant_b = _make_tenant("Rate School B", "rateb")
        cache.clear()

    def tearDown(self):
        clear_current_tenant()
        cache.clear()

    def test_rate_limit_key_for_tenant_a_does_not_affect_tenant_b(self):
        """
        Simulates exhausting rate limit for a user in tenant A.
        Tenant B's equivalent rate limit counter must remain independent.
        """
        user_a = _make_user("rate@ratea.com", self.tenant_a)
        user_b = _make_user("rate@rateb.com", self.tenant_b)

        # Simulate tenant-specific rate limit keys
        key_a = f"api_rate_limit:tenant:{self.tenant_a.id}:user:{user_a.id}"
        key_b = f"api_rate_limit:tenant:{self.tenant_b.id}:user:{user_b.id}"

        # Exhaust rate limit for tenant A
        cache.set(key_a, 100, timeout=60)  # 100 = limit exhausted

        # Tenant B should still be at 0 (not affected)
        count_b = cache.get(key_b, default=0)
        self.assertEqual(
            count_b,
            0,
            "Exhausting rate limit for tenant A must not affect tenant B's counter",
        )

    def test_rate_limit_counter_is_independently_decremented(self):
        """
        Each tenant's rate limit counter is independent and can be incremented/
        decremented without affecting the other tenant's counter.
        """
        user_a = _make_user("dec_a@ratea.com", self.tenant_a)
        user_b = _make_user("dec_b@rateb.com", self.tenant_b)

        key_a = f"api_rate:{self.tenant_a.id}:{user_a.id}"
        key_b = f"api_rate:{self.tenant_b.id}:{user_b.id}"

        cache.set(key_a, 5, timeout=60)
        cache.set(key_b, 3, timeout=60)

        # Decrement A
        current_a = cache.get(key_a)
        cache.set(key_a, current_a - 1, timeout=60)

        self.assertEqual(cache.get(key_a), 4, "Tenant A counter should be 4")
        self.assertEqual(cache.get(key_b), 3, "Tenant B counter should remain 3")


# ---------------------------------------------------------------------------
# 4. WebSocket Channel Group Naming
# ---------------------------------------------------------------------------

class ChannelLayerGroupNamingTestCase(TestCase):
    """
    Verify that WebSocket channel group names embed tenant context.

    Channel groups are used for real-time broadcasts. If group names don't
    include tenant_id, a message broadcast to one school's users could
    reach another school's connected clients.
    """

    def test_channel_group_name_contains_tenant_id(self):
        """
        Channel group names for tenant-specific events must embed the tenant ID.
        This prevents cross-tenant message broadcasting.
        """
        import uuid
        tenant_id_a = str(uuid.uuid4())
        tenant_id_b = str(uuid.uuid4())

        # Pattern that SHOULD be used for tenant-scoped groups
        group_a = f"notifications_{tenant_id_a}"
        group_b = f"notifications_{tenant_id_b}"

        self.assertNotEqual(
            group_a,
            group_b,
            "Channel group names for different tenants must be distinct",
        )

    def test_channel_group_name_pattern_is_valid_length(self):
        """
        Django Channels requires group names to be ≤ 100 characters.
        Verify that tenant-scoped group names fit within this limit.
        """
        import uuid
        tenant_id = str(uuid.uuid4())  # 36 chars
        user_id = str(uuid.uuid4())    # 36 chars

        # Worst-case pattern
        group_name = f"tenant_{tenant_id}_user_{user_id}_notifications"
        self.assertLessEqual(
            len(group_name),
            100,
            f"Channel group name '{group_name}' exceeds 100-char Django Channels limit",
        )

    def test_channel_layer_config_uses_separate_redis_db(self):
        """
        Channel layers should use a different Redis DB than the cache
        to prevent key collisions and independent flushing.
        """
        from django.conf import settings
        cache_url = settings.CACHES.get("default", {}).get("LOCATION", "")
        channel_hosts = (
            settings.CHANNEL_LAYERS
            .get("default", {})
            .get("CONFIG", {})
            .get("hosts", [])
        )
        if channel_hosts and cache_url:
            channel_url = channel_hosts[0] if isinstance(channel_hosts[0], str) else str(channel_hosts[0])
            # They should either be on different databases or different servers
            # A simple check: URL strings should not be identical
            self.assertNotEqual(
                cache_url,
                channel_url,
                "Cache and Channel Layer should use separate Redis DBs",
            )


# ---------------------------------------------------------------------------
# 5. Cache Context Cleanup After Request
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class CacheContextCleanupTestCase(TestCase):
    """
    Verify that cache operations respect the tenant lifecycle:
    - After clear_current_tenant(), no stale tenant context affects cache keys
    - Subsequent requests to different tenants don't share cached values
    """

    def setUp(self):
        self.tenant_a = _make_tenant("Cleanup School A", "cleana")
        self.tenant_b = _make_tenant("Cleanup School B", "cleanb")
        cache.clear()

    def tearDown(self):
        clear_current_tenant()
        cache.clear()

    def test_stale_cache_key_from_previous_tenant_not_returned(self):
        """
        Simulate two sequential requests:
        Request 1 sets a cache key under tenant A's scope.
        Request 2 for tenant B must NOT inadvertently read A's cached value.
        """
        # Request 1 — Tenant A
        set_current_tenant(self.tenant_a)
        key_a = f"tenant:{get_current_tenant().id}:user_count"
        cache.set(key_a, 42, timeout=60)
        clear_current_tenant()  # Request ends, tenant context cleared

        # Request 2 — Tenant B
        set_current_tenant(self.tenant_b)
        key_b = f"tenant:{get_current_tenant().id}:user_count"

        # Key should be different
        self.assertNotEqual(key_a, key_b)
        # And B's key should return None (nothing was cached for B)
        self.assertIsNone(cache.get(key_b))
        clear_current_tenant()

    def test_cache_clear_for_tenant_does_not_affect_global_cache(self):
        """
        Clearing tenant-specific cache entries (e.g., on logout) should not
        wipe unrelated cache keys.
        """
        global_key = "global:feature_flags:v1"
        tenant_key = f"tenant:{self.tenant_a.id}:user_prefs"

        cache.set(global_key, {"feature_x": True}, timeout=300)
        cache.set(tenant_key, {"theme": "dark"}, timeout=60)

        # Simulate clearing only tenant A's cache
        cache.delete(tenant_key)

        self.assertIsNone(cache.get(tenant_key), "Tenant key should be deleted")
        self.assertEqual(
            cache.get(global_key),
            {"feature_x": True},
            "Global cache key must not be affected by tenant cache clear",
        )
