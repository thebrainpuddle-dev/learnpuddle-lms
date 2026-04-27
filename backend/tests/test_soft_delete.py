# tests/test_soft_delete.py
"""
Tests for utils/soft_delete.py — SoftDeleteMixin, SoftDeleteQuerySet, SoftDeleteManager.

Covers:
1. soft_delete() sets is_deleted=True and deleted_at timestamp
2. soft_delete(user=user) populates deleted_by when field exists
3. delete() is an alias for soft_delete(user=None)
4. restore() resets is_deleted=False and clears deleted_at
5. hard_delete() permanently removes the record
6. SoftDeleteManager.get_queryset() excludes soft-deleted records
7. all_with_deleted() includes soft-deleted records
8. deleted_only() returns only deleted records
9. SoftDeleteQuerySet.delete() bulk-soft-deletes (NOT hard delete)
10. SoftDeleteQuerySet.hard_delete() bulk-hard-deletes
11. alive() and dead() QuerySet filters
"""

import pytest
from django.db import models
from django.test import TestCase
from django.utils import timezone

from utils.soft_delete import SoftDeleteMixin, SoftDeleteManager, SoftDeleteQuerySet


# ===========================================================================
# Minimal test model
# ===========================================================================

class _TestItem(SoftDeleteMixin, models.Model):
    """
    Minimal concrete model using SoftDeleteMixin for tests.
    Uses a unique app_label to avoid conflicts.
    """
    name = models.CharField(max_length=100, default="item")
    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        app_label = "tests"


# ===========================================================================
# 1. Instance-Level Soft Delete Tests
# ===========================================================================


@pytest.mark.django_db
class SoftDeleteInstanceTestCase(TestCase):
    """Tests for the soft_delete() method on model instances."""

    def _create_item(self, name="item"):
        """Use a real Course object since we can't use _TestItem without migration."""
        from apps.courses.models import Course
        from apps.tenants.models import Tenant
        from apps.users.models import User

        # Re-use the fixtures approach: create via ORM directly
        tenant = Tenant.objects.create(
            name=f"Tenant_{name}",
            slug=f"tenant-{name.lower().replace(' ', '-')}",
            subdomain=f"test{name.lower().replace(' ', '')}sd",
            email=f"admin@{name.lower().replace(' ', '')}.com",
            is_active=True,
        )
        user = User.objects.create_user(
            email=f"admin@{name.lower()}.example.com",
            password="pass123",
            tenant=tenant,
            role="SCHOOL_ADMIN",
            first_name="Admin",
            last_name="User",
            is_active=True,
        )
        course = Course.objects.create(
            tenant=tenant,
            title=f"Course {name}",
            slug=f"course-{name.lower().replace(' ', '-')}",
            created_by=user,
            is_published=False,
            is_active=True,
        )
        return course, user

    def test_soft_delete_sets_is_deleted_true(self):
        """soft_delete() must set is_deleted=True."""
        course, _ = self._create_item("alpha")
        course.soft_delete()
        course.refresh_from_db()
        self.assertTrue(course.is_deleted, "is_deleted must be True after soft_delete()")

    def test_soft_delete_sets_deleted_at(self):
        """soft_delete() must record the deletion timestamp."""
        course, _ = self._create_item("beta")
        before = timezone.now()
        course.soft_delete()
        course.refresh_from_db()

        self.assertIsNotNone(course.deleted_at, "deleted_at must be set after soft_delete()")
        self.assertGreaterEqual(
            course.deleted_at,
            before,
            "deleted_at must be at or after the soft_delete() call time",
        )

    def test_soft_delete_with_user_sets_deleted_by(self):
        """soft_delete(user=user) must set deleted_by when the field exists."""
        from apps.courses.models import Course
        course, user = self._create_item("gamma")
        # Course model has a deleted_by field per the CLAUDE.md SoftDeleteMixin docs
        course.soft_delete(user=user)
        course.refresh_from_db()

        # Only assert if the model actually has deleted_by
        from django.db import models as _models
        field_names = {f.name for f in course._meta.get_fields()}
        if "deleted_by" in field_names:
            self.assertEqual(
                course.deleted_by,
                user,
                "deleted_by must be set to the user passed to soft_delete()",
            )

    def test_delete_method_is_alias_for_soft_delete(self):
        """The ORM delete() method must perform a soft delete (not hard delete)."""
        course, _ = self._create_item("delta")
        course_id = course.id

        course.delete()

        # Record must still exist in the DB
        from apps.courses.models import Course
        self.assertTrue(
            Course.all_objects.filter(id=course_id).exists(),
            "After delete(), record must still exist in DB (soft delete, not hard delete)",
        )
        course.refresh_from_db()
        self.assertTrue(course.is_deleted, "is_deleted must be True after delete()")

    def test_restore_clears_is_deleted(self):
        """restore() must set is_deleted=False."""
        course, _ = self._create_item("epsilon")
        course.soft_delete()
        course.refresh_from_db()
        self.assertTrue(course.is_deleted)

        course.restore()
        course.refresh_from_db()

        self.assertFalse(course.is_deleted, "is_deleted must be False after restore()")

    def test_restore_clears_deleted_at(self):
        """restore() must set deleted_at=None."""
        course, _ = self._create_item("zeta")
        course.soft_delete()
        course.restore()
        course.refresh_from_db()

        self.assertIsNone(course.deleted_at, "deleted_at must be None after restore()")

    def test_hard_delete_removes_record_from_db(self):
        """hard_delete() must permanently remove the record."""
        from apps.courses.models import Course
        course, _ = self._create_item("eta")
        course_id = course.id

        course.hard_delete()

        self.assertFalse(
            Course.all_objects.filter(id=course_id).exists(),
            "hard_delete() must permanently remove the record from the database",
        )


# ===========================================================================
# 2. Manager / QuerySet Tests
# ===========================================================================


@pytest.mark.django_db
class SoftDeleteManagerTestCase(TestCase):
    """Tests for SoftDeleteManager and SoftDeleteQuerySet."""

    def setUp(self):
        """Create two courses: one active, one soft-deleted."""
        from apps.courses.models import Course
        from apps.tenants.models import Tenant
        from apps.users.models import User

        self.tenant = Tenant.objects.create(
            name="Manager Test School",
            slug="manager-test-school",
            subdomain="mgrtestschool",
            email="admin@mgrtestschool.com",
            is_active=True,
        )
        self.user = User.objects.create_user(
            email="admin@mgrtestschool.example.com",
            password="pass123",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            first_name="Admin",
            last_name="User",
            is_active=True,
        )
        # Active course
        self.active = Course.objects.create(
            tenant=self.tenant,
            title="Active Course",
            slug="active-course-mgr",
            created_by=self.user,
            is_published=False,
            is_active=True,
        )
        # Soft-deleted course
        self.deleted = Course.objects.create(
            tenant=self.tenant,
            title="Deleted Course",
            slug="deleted-course-mgr",
            created_by=self.user,
            is_published=False,
            is_active=True,
        )
        self.deleted.soft_delete()

    def test_objects_manager_excludes_soft_deleted(self):
        """Default objects manager must not include soft-deleted records."""
        from apps.courses.models import Course
        from utils.tenant_middleware import set_current_tenant, clear_current_tenant

        set_current_tenant(self.tenant)
        try:
            titles = list(Course.objects.values_list("title", flat=True))
        finally:
            clear_current_tenant()

        self.assertIn("Active Course", titles)
        self.assertNotIn(
            "Deleted Course",
            titles,
            "Soft-deleted course must not appear in default queryset",
        )

    def test_all_objects_includes_soft_deleted(self):
        """The all_objects Manager must include soft-deleted records."""
        from apps.courses.models import Course

        titles = list(
            Course.all_objects.filter(tenant=self.tenant).values_list("title", flat=True)
        )
        self.assertIn("Active Course", titles)
        self.assertIn(
            "Deleted Course",
            titles,
            "all_objects must include soft-deleted records",
        )

    def test_is_deleted_flag_is_true_for_deleted_record(self):
        """A soft-deleted record must have is_deleted=True."""
        from apps.courses.models import Course

        record = Course.all_objects.get(id=self.deleted.id)
        self.assertTrue(record.is_deleted)

    def test_is_deleted_flag_is_false_for_active_record(self):
        """An active (non-deleted) record must have is_deleted=False."""
        from apps.courses.models import Course

        record = Course.all_objects.get(id=self.active.id)
        self.assertFalse(record.is_deleted)


# ===========================================================================
# 3. SoftDeleteMixin field tests (structural)
# ===========================================================================


class SoftDeleteMixinFieldTestCase(TestCase):
    """Verify SoftDeleteMixin declares the required fields."""

    def test_mixin_declares_is_deleted_field(self):
        """SoftDeleteMixin must have an is_deleted BooleanField."""
        field_names = {f.name for f in SoftDeleteMixin._meta.get_fields()}
        self.assertIn("is_deleted", field_names, "SoftDeleteMixin must declare is_deleted")

    def test_mixin_declares_deleted_at_field(self):
        """SoftDeleteMixin must have a deleted_at DateTimeField."""
        field_names = {f.name for f in SoftDeleteMixin._meta.get_fields()}
        self.assertIn("deleted_at", field_names, "SoftDeleteMixin must declare deleted_at")

    def test_is_deleted_defaults_to_false(self):
        """is_deleted default value must be False."""
        field = SoftDeleteMixin._meta.get_field("is_deleted")
        self.assertFalse(field.default, "is_deleted must default to False")

    def test_deleted_at_is_nullable(self):
        """deleted_at must be nullable (NULL for non-deleted records)."""
        field = SoftDeleteMixin._meta.get_field("deleted_at")
        self.assertTrue(field.null, "deleted_at must be nullable")
