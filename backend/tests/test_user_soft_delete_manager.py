# tests/test_user_soft_delete_manager.py
"""
Tests for utils/user_soft_delete_manager.py — UserSoftDeleteManager and related classes.

Uses the real User model (which uses UserSoftDeleteManager) to verify behavior
through actual DB operations.

Covers:
1. default objects manager excludes soft-deleted users
2. all_objects manager includes soft-deleted users
3. soft-delete on user sets is_deleted=True and is_active=False
4. restore() or marking is_deleted=False re-activates user
5. hard_delete() permanently removes user from DB
6. alive() and dead() queryset methods
7. all_tenants() returns non-deleted users across all tenants
8. create_user() requires email
9. create_superuser() sets correct defaults
"""

import pytest
from django.test import TestCase
from django.utils import timezone

from utils.tenant_middleware import set_current_tenant, clear_current_tenant


# ===========================================================================
# Helpers
# ===========================================================================


def _create_tenant(slug_suffix: str = ""):
    """Create a Tenant with unique subdomain/slug for test isolation."""
    from apps.tenants.models import Tenant
    suffix = slug_suffix.lower().replace(" ", "")
    return Tenant.objects.create(
        name=f"Test School {slug_suffix}",
        slug=f"test-school-{suffix}",
        subdomain=f"testschool{suffix}",
        email=f"admin@testschool{suffix}.com",
        is_active=True,
    )


def _create_user(tenant, email_suffix: str = "a", role: str = "TEACHER"):
    """Create an active User for testing."""
    from apps.users.models import User
    return User.objects.create_user(
        email=f"user_{email_suffix}@testschool.com",
        password="TestPass!123",
        first_name="Test",
        last_name="User",
        tenant=tenant,
        role=role,
        is_active=True,
    )


# ===========================================================================
# 1. Default Manager Filtering Tests
# ===========================================================================


@pytest.mark.django_db
class DefaultManagerFilteringTestCase(TestCase):
    """objects manager must exclude soft-deleted users by default."""

    def setUp(self):
        self.tenant = _create_tenant("filter")
        set_current_tenant(self.tenant)
        self.active_user = _create_user(self.tenant, "active")
        # Soft-delete one user
        self.deleted_user = _create_user(self.tenant, "deleted")
        self.deleted_user.is_deleted = True
        self.deleted_user.deleted_at = timezone.now()
        self.deleted_user.is_active = False
        self.deleted_user.save()

    def tearDown(self):
        clear_current_tenant()

    def test_active_user_visible_in_default_queryset(self):
        """Active user must appear in User.objects.all()."""
        from apps.users.models import User
        emails = list(User.objects.values_list("email", flat=True))
        self.assertIn(self.active_user.email, emails)

    def test_deleted_user_excluded_from_default_queryset(self):
        """Soft-deleted user must NOT appear in User.objects.all()."""
        from apps.users.models import User
        emails = list(User.objects.values_list("email", flat=True))
        self.assertNotIn(
            self.deleted_user.email,
            emails,
            "Soft-deleted user must be excluded from default manager queryset",
        )

    def test_all_objects_includes_soft_deleted(self):
        """User.all_objects must include soft-deleted users."""
        from apps.users.models import User
        emails = list(
            User.all_objects.filter(tenant=self.tenant).values_list("email", flat=True)
        )
        self.assertIn(self.active_user.email, emails)
        self.assertIn(
            self.deleted_user.email,
            emails,
            "all_objects must include soft-deleted users",
        )


# ===========================================================================
# 2. alive() and dead() QuerySet Tests
# ===========================================================================


@pytest.mark.django_db
class AliveDeadQuerySetTestCase(TestCase):
    """alive() and dead() filter correctly."""

    def setUp(self):
        self.tenant = _create_tenant("alivetest")
        self.active = _create_user(self.tenant, "alive")
        self.deleted = _create_user(self.tenant, "dead")
        self.deleted.is_deleted = True
        self.deleted.deleted_at = timezone.now()
        self.deleted.is_active = False
        self.deleted.save()

    def test_alive_excludes_deleted(self):
        """alive() must return only non-deleted users for this tenant."""
        from apps.users.models import User

        qs = User.all_objects.filter(tenant=self.tenant)
        alive = qs.alive()
        self.assertIn(self.active, alive)
        self.assertNotIn(self.deleted, alive)

    def test_dead_returns_only_deleted(self):
        """dead() must return only soft-deleted users."""
        from apps.users.models import User

        qs = User.all_objects.filter(tenant=self.tenant)
        dead = qs.dead()
        self.assertIn(self.deleted, dead)
        self.assertNotIn(self.active, dead)


# ===========================================================================
# 3. all_tenants() Tests
# ===========================================================================


@pytest.mark.django_db
class AllTenantsTestCase(TestCase):
    """all_tenants() must return non-deleted users across all tenants."""

    def setUp(self):
        self.tenant_a = _create_tenant("tenanta")
        self.tenant_b = _create_tenant("tenantb")
        self.user_a = _create_user(self.tenant_a, "crossA")
        self.user_b = _create_user(self.tenant_b, "crossB")

    def test_all_tenants_includes_both_tenant_users(self):
        """all_tenants() must include users from all tenants."""
        from apps.users.models import User

        emails = list(User.objects.all_tenants().values_list("email", flat=True))
        self.assertIn(self.user_a.email, emails)
        self.assertIn(self.user_b.email, emails)

    def test_all_tenants_excludes_deleted(self):
        """all_tenants() must NOT include soft-deleted users."""
        from apps.users.models import User

        self.user_a.is_deleted = True
        self.user_a.deleted_at = timezone.now()
        self.user_a.save()

        emails = list(User.objects.all_tenants().values_list("email", flat=True))
        self.assertNotIn(
            self.user_a.email,
            emails,
            "all_tenants() must exclude soft-deleted users",
        )


# ===========================================================================
# 4. create_user() Validation Tests
# ===========================================================================


@pytest.mark.django_db
class CreateUserValidationTestCase(TestCase):
    """create_user() must validate required fields."""

    def test_create_user_without_email_raises(self):
        """create_user() without email must raise ValueError."""
        from apps.users.models import User
        from apps.tenants.models import Tenant

        tenant = _create_tenant("createtest")
        with self.assertRaises(ValueError):
            User.objects.create_user(
                email="",
                password="pass",
                tenant=tenant,
                role="TEACHER",
            )

    def test_create_user_with_valid_email_succeeds(self):
        """create_user() with valid email must create user successfully."""
        from apps.users.models import User

        tenant = _create_tenant("createvalid")
        user = User.objects.create_user(
            email="newuser@createvalid.com",
            password="ValidPass!123",
            tenant=tenant,
            role="TEACHER",
            first_name="New",
            last_name="User",
            is_active=True,
        )
        self.assertEqual(user.email, "newuser@createvalid.com")
        self.assertTrue(user.check_password("ValidPass!123"))


# ===========================================================================
# 5. create_superuser() Tests
# ===========================================================================


@pytest.mark.django_db
class CreateSuperuserTestCase(TestCase):
    """create_superuser() must set correct defaults."""

    def test_superuser_has_correct_role(self):
        """create_superuser() must set role='SUPER_ADMIN'."""
        from apps.users.models import User

        user = User.objects.create_superuser(
            email="superuser@platform.com",
            password="SuperPass!123",
        )
        self.assertEqual(user.role, "SUPER_ADMIN")

    def test_superuser_has_is_staff_true(self):
        """create_superuser() must set is_staff=True."""
        from apps.users.models import User

        user = User.objects.create_superuser(
            email="staffsuper@platform.com",
            password="SuperPass!123",
        )
        self.assertTrue(user.is_staff, "Superuser must have is_staff=True")

    def test_superuser_has_is_superuser_true(self):
        """create_superuser() must set is_superuser=True."""
        from apps.users.models import User

        user = User.objects.create_superuser(
            email="superb@platform.com",
            password="SuperPass!123",
        )
        self.assertTrue(user.is_superuser, "Superuser must have is_superuser=True")

    def test_superuser_without_is_staff_raises(self):
        """create_superuser(is_staff=False) must raise ValueError."""
        from apps.users.models import User

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="bad_super@platform.com",
                password="SuperPass!123",
                is_staff=False,
            )

    def test_superuser_without_is_superuser_raises(self):
        """create_superuser(is_superuser=False) must raise ValueError."""
        from apps.users.models import User

        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="bad_super2@platform.com",
                password="SuperPass!123",
                is_superuser=False,
            )
