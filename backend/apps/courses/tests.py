# apps/courses/tests.py
"""
Comprehensive tests for the courses app.

Covers:
- Course list, create, detail, update, delete (admin + teacher authoring)
- Module CRUD
- Cross-tenant isolation (security)
- Publish/unpublish flow
- TenantManager auto-filtering
- Soft-delete behavior
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course, Module, Content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, slug, subdomain, email):
    return Tenant.objects.create(
        name=name, slug=slug, subdomain=subdomain, email=email
    )


def _make_user(email, tenant, role='SCHOOL_ADMIN', first='Admin', last='User'):
    return User.objects.create_user(
        email=email, password='pass123',
        first_name=first, last_name=last,
        tenant=tenant, role=role,
    )


def _make_course(tenant, admin, title='Test Course', published=False):
    return Course.objects.create(
        tenant=tenant,
        title=title,
        description='A test course description.',
        is_published=published,
        is_active=True,
        assigned_to_all=True,
        created_by=admin,
    )


def _auth(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


HOST_A = 'test.lms.com'
HOST_B = 'other.lms.com'


# ===========================================================================
# Auth & Access Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class CourseAuthTestCase(TestCase):
    """Tests that course endpoints enforce authentication."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'course-auth', 'test', 'auth@courses.com')
        self.client = APIClient()

    def test_list_courses_requires_auth(self):
        response = self.client.get('/api/v1/courses/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 401)

    def test_course_detail_requires_auth(self):
        import uuid
        response = self.client.get(f'/api/v1/courses/{uuid.uuid4()}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 401)


# ===========================================================================
# Course List & Create Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class CourseListCreateTestCase(TestCase):
    """Tests for GET/POST /api/v1/courses/."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'course-lc', 'test', 'lc@courses.com')
        self.admin = _make_user('admin@courselc.com', self.tenant)
        self.teacher = _make_user('teacher@courselc.com', self.tenant, role='TEACHER', first='Tea')

    def test_admin_can_list_courses(self):
        _make_course(self.tenant, self.admin)
        client = _auth(self.admin)
        response = client.get('/api/v1/courses/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)

    def test_teacher_can_list_courses(self):
        """Teachers can also list courses (teacher_or_admin decorator)."""
        client = _auth(self.teacher)
        response = client.get('/api/v1/courses/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)

    def test_admin_can_create_course(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/courses/',
            {
                'title': 'New Course',
                'description': 'Course description here.',
                'assigned_to_all': True,
            },
            format='json',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['title'], 'New Course')

    def test_create_course_slug_auto_generated(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/courses/',
            {'title': 'Slug Auto Course', 'description': 'Desc', 'assigned_to_all': True},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('slug', response.data)
        self.assertTrue(len(response.data['slug']) > 0)

    def test_create_course_requires_title(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/courses/',
            {'description': 'No title'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertIn(response.status_code, [400, 422])

    def test_list_courses_returns_paginated_response(self):
        _make_course(self.tenant, self.admin, title='C1')
        _make_course(self.tenant, self.admin, title='C2')
        client = _auth(self.admin)
        response = client.get('/api/v1/courses/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        # Paginated response has results/count
        self.assertIn('results', response.data)


# ===========================================================================
# Course Detail Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class CourseDetailTestCase(TestCase):
    """Tests for GET/PATCH/DELETE /api/v1/courses/<id>/."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'course-det', 'test', 'det@courses.com')
        self.admin = _make_user('admin@coursedet.com', self.tenant)
        self.course = _make_course(self.tenant, self.admin, title='Detail Course')

    def test_get_course_detail(self):
        client = _auth(self.admin)
        response = client.get(f'/api/v1/courses/{self.course.id}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Detail Course')

    def test_get_nonexistent_course_returns_404(self):
        import uuid
        client = _auth(self.admin)
        response = client.get(f'/api/v1/courses/{uuid.uuid4()}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 404)

    def test_admin_can_update_course(self):
        client = _auth(self.admin)
        response = client.patch(
            f'/api/v1/courses/{self.course.id}/',
            {'title': 'Updated Course Title'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Updated Course Title')

    def test_admin_can_soft_delete_course(self):
        client = _auth(self.admin)
        response = client.delete(f'/api/v1/courses/{self.course.id}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 204)
        # Soft delete: record exists but is_deleted=True
        # Use all_objects manager to bypass the TenantSoftDeleteManager filter
        from apps.courses.models import Course as C
        course_raw = C.all_objects.all_tenants().get(id=self.course.id)
        self.assertTrue(course_raw.is_deleted)

    def test_deleted_course_not_in_list(self):
        # SoftDeleteMixin overrides delete() to perform a soft delete
        self.course.delete()
        client = _auth(self.admin)
        response = client.get('/api/v1/courses/', HTTP_HOST=HOST_A)
        ids = [c['id'] for c in response.data.get('results', [])]
        self.assertNotIn(str(self.course.id), ids)


# ===========================================================================
# Course Publish/Unpublish Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class CoursePublishTestCase(TestCase):
    """Tests for POST /api/v1/courses/<id>/publish/."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'course-pub', 'test', 'pub@courses.com')
        self.admin = _make_user('admin@coursepub.com', self.tenant)
        self.course = _make_course(self.tenant, self.admin, title='Publish Course')

    def test_admin_can_publish_course(self):
        self.assertFalse(self.course.is_published)
        client = _auth(self.admin)
        response = client.post(
            f'/api/v1/courses/{self.course.id}/publish/',
            {'action': 'publish'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_published)

    def test_admin_can_unpublish_course(self):
        self.course.is_published = True
        self.course.save()
        client = _auth(self.admin)
        response = client.post(
            f'/api/v1/courses/{self.course.id}/publish/',
            {'action': 'unpublish'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.course.refresh_from_db()
        self.assertFalse(self.course.is_published)


# ===========================================================================
# Module CRUD Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class ModuleCRUDTestCase(TestCase):
    """Tests for module create and list endpoints."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'module-crud', 'test', 'mod@courses.com')
        self.admin = _make_user('admin@moduletest.com', self.tenant)
        self.course = _make_course(self.tenant, self.admin, title='Module Course')

    def test_create_module(self):
        client = _auth(self.admin)
        response = client.post(
            f'/api/v1/courses/{self.course.id}/modules/',
            {'title': 'Module One', 'description': 'Intro module', 'order': 1},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['title'], 'Module One')

    def test_list_modules_for_course(self):
        Module.objects.create(
            course=self.course, title='Module A', order=1, is_active=True
        )
        Module.objects.create(
            course=self.course, title='Module B', order=2, is_active=True
        )
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/courses/{self.course.id}/modules/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)

    def test_create_module_requires_title(self):
        client = _auth(self.admin)
        response = client.post(
            f'/api/v1/courses/{self.course.id}/modules/',
            {'order': 1},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertIn(response.status_code, [400, 422])


# ===========================================================================
# Cross-Tenant Isolation Tests (Security)
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class CourseCrossTenantIsolationTestCase(TestCase):
    """
    P0 Security: TenantManager must prevent cross-tenant data access.

    These tests verify:
    1. Users from tenant B get 403 when hitting tenant A's host
    2. TenantManager filters mean tenant B never sees tenant A's courses
    3. Direct ID access to another tenant's resource fails
    """

    def setUp(self):
        self.tenant_a = _make_tenant('School A', 'isol-a', 'test', 'a@isol.com')
        self.tenant_b = _make_tenant('School B', 'isol-b', 'other', 'b@isol.com')

        self.admin_a = _make_user('admin@isol-a.com', self.tenant_a)
        self.admin_b = _make_user('admin@isol-b.com', self.tenant_b)

        self.course_a = _make_course(self.tenant_a, self.admin_a, title='School A Private Course')

    def test_admin_a_sees_own_course(self):
        client = _auth(self.admin_a)
        response = client.get('/api/v1/courses/', HTTP_HOST=HOST_A)
        ids = [c['id'] for c in response.data.get('results', [])]
        self.assertIn(str(self.course_a.id), ids)

    def test_admin_b_cannot_see_tenant_a_courses_in_own_scope(self):
        """Tenant B's course list must not include Tenant A's courses."""
        client = _auth(self.admin_b)
        response = client.get('/api/v1/courses/', HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 200)
        ids = [c['id'] for c in response.data.get('results', [])]
        self.assertNotIn(str(self.course_a.id), ids)

    def test_admin_b_gets_403_accessing_tenant_a_host(self):
        """User from B rejected when hitting A's host."""
        client = _auth(self.admin_b)
        response = client.get('/api/v1/courses/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 403)

    def test_admin_b_cannot_get_tenant_a_course_detail(self):
        """Even with the correct UUID, Tenant B cannot get Tenant A's course."""
        client = _auth(self.admin_b)
        response = client.get(
            f'/api/v1/courses/{self.course_a.id}/',
            HTTP_HOST=HOST_B,
        )
        # TenantManager should filter it out → 404
        self.assertIn(response.status_code, [403, 404])

    def test_admin_b_cannot_delete_tenant_a_course(self):
        client = _auth(self.admin_b)
        response = client.delete(
            f'/api/v1/courses/{self.course_a.id}/',
            HTTP_HOST=HOST_B,
        )
        self.assertIn(response.status_code, [403, 404])
        # Course must still exist and not be marked deleted
        self.assertFalse(
            Course.all_objects.all_tenants().get(id=self.course_a.id).is_deleted
        )


# ===========================================================================
# Course Model Tests
# ===========================================================================

class CourseModelTestCase(TestCase):
    """Unit tests for Course model methods."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Model School', slug='model-course', subdomain='model', email='m@model.com'
        )
        self.admin = User.objects.create_user(
            email='admin@model.com', password='pass',
            first_name='A', last_name='B',
            tenant=self.tenant, role='SCHOOL_ADMIN',
        )

    def test_slug_auto_generated_from_title(self):
        course = Course.objects.create(
            tenant=self.tenant, title='My Great Course',
            description='Desc', created_by=self.admin,
            is_active=True, assigned_to_all=True,
        )
        self.assertEqual(course.slug, 'my-great-course')

    def test_duplicate_slugs_get_suffix(self):
        Course.objects.create(
            tenant=self.tenant, title='Dup Course',
            description='D1', created_by=self.admin,
            is_active=True, assigned_to_all=True,
        )
        course2 = Course.objects.create(
            tenant=self.tenant, title='Dup Course',
            description='D2', created_by=self.admin,
            is_active=True, assigned_to_all=True,
        )
        self.assertNotEqual(course2.slug, 'dup-course')
        self.assertTrue(course2.slug.startswith('dup-course'))

    def test_soft_delete_sets_is_deleted(self):
        course = Course.objects.create(
            tenant=self.tenant, title='Soft Delete',
            description='Desc', created_by=self.admin,
            is_active=True, assigned_to_all=True,
        )
        # SoftDeleteMixin overrides delete() to do a soft delete
        course.delete()
        # Use all_tenants() to bypass tenant AND soft-delete filters
        refreshed = Course.all_objects.all_tenants().get(id=course.id)
        self.assertTrue(refreshed.is_deleted)
        self.assertIsNotNone(refreshed.deleted_at)

    def test_soft_deleted_course_excluded_from_default_queryset(self):
        course = Course.objects.create(
            tenant=self.tenant, title='Hidden Course',
            description='Desc', created_by=self.admin,
            is_active=True, assigned_to_all=True,
        )
        # SoftDeleteMixin overrides delete() to do a soft delete
        course.delete()
        # Default manager (TenantSoftDeleteManager) excludes deleted
        from utils.tenant_middleware import set_current_tenant, clear_current_tenant
        set_current_tenant(self.tenant)
        try:
            qs = Course.objects.all()
            self.assertNotIn(course.id, [c.id for c in qs])
        finally:
            clear_current_tenant()

    def test_str_representation(self):
        course = Course.objects.create(
            tenant=self.tenant, title='Repr Course',
            description='Desc', created_by=self.admin,
            is_active=True, assigned_to_all=True,
        )
        self.assertEqual(str(course), 'Repr Course')
