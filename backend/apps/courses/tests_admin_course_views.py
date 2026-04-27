# apps/courses/tests_admin_course_views.py
"""
Tests for courses/views.py admin endpoints:
  - course_list_create: GET/POST /api/v1/courses/
  - course_detail: GET/PATCH/DELETE /api/v1/courses/<id>/
  - module_list_create: POST /api/v1/courses/<id>/modules/
  - module_detail: GET/PATCH/DELETE /api/v1/courses/<id>/modules/<mid>/
  - content_list_create: POST /api/v1/courses/<id>/modules/<mid>/contents/

Auth: requires SCHOOL_ADMIN or higher.
"""
import uuid
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course, Module, Content


HOST = "test.lms.com"


def _tenant(name, slug, sub, email):
    return Tenant.objects.create(name=name, slug=slug, subdomain=sub, email=email, is_active=True)


def _user(email, tenant, role="SCHOOL_ADMIN"):
    return User.objects.create_user(
        email=email, password="Pass!1234",
        first_name="T", last_name="U",
        tenant=tenant, role=role, is_active=True,
    )


def _course(tenant, admin, title="Test Course", published=True, slug_suffix=""):
    return Course.objects.create(
        tenant=tenant, title=title,
        slug=f"test-course-{uuid.uuid4().hex[:6]}{slug_suffix}",
        description="Test course", created_by=admin,
        is_published=published, is_active=True,
    )


def _module(course, title="Module 1"):
    return Module.objects.create(course=course, title=title, order=1, is_active=True)


def _content(module, title="Content 1", ctype="TEXT"):
    return Content.objects.create(
        module=module, title=title, content_type=ctype,
        order=1, text_content="<p>Hello</p>", is_active=True,
    )


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class CourseListCreateTestCase(TestCase):
    """Tests for GET/POST /api/v1/courses/"""

    def setUp(self):
        self.tenant = _tenant("Course School", "cs-list", "test", "admin@cs.com")
        self.admin = _user("admin@cs.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _user("teacher@cs.com", self.tenant, role="TEACHER")
        self.course = _course(self.tenant, self.admin)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    def test_unauthenticated_returns_401(self):
        response = APIClient().get("/api/v1/courses/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_list_courses(self):
        response = self.admin_client.get("/api/v1/courses/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertTrue(any(r["title"] == "Test Course" for r in results))

    def test_filter_by_is_published_true(self):
        response = self.admin_client.get("/api/v1/courses/?is_published=true", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        for r in results:
            self.assertTrue(r["is_published"])

    def test_filter_by_is_published_false(self):
        _course(self.tenant, self.admin, title="Draft", published=False)
        response = self.admin_client.get("/api/v1/courses/?is_published=false", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        for r in results:
            self.assertFalse(r["is_published"])

    def test_search_by_title(self):
        _course(self.tenant, self.admin, title="Unique XYZ Course")
        response = self.admin_client.get("/api/v1/courses/?search=Unique+XYZ", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        self.assertTrue(any("Unique XYZ" in r["title"] for r in results))

    def test_admin_can_create_course(self):
        response = self.admin_client.post(
            "/api/v1/courses/",
            {
                "title": "New Course",
                "description": "A new course",
                "is_published": False,
                "assigned_to_all": False,
            },
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "New Course")

    def test_create_course_missing_title_returns_400(self):
        response = self.admin_client.post(
            "/api/v1/courses/",
            {"description": "No title"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class CourseDetailTestCase(TestCase):
    """Tests for GET/PATCH/DELETE /api/v1/courses/<id>/"""

    def setUp(self):
        self.tenant = _tenant("Detail School", "cs-detail", "test", "admin@csd.com")
        self.admin = _user("admin@csd.com", self.tenant, role="SCHOOL_ADMIN")
        self.teacher = _user("teacher@csd.com", self.tenant, role="TEACHER")
        self.course = _course(self.tenant, self.admin)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    def test_admin_can_get_course(self):
        response = self.admin_client.get(f"/api/v1/courses/{self.course.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.course.id))

    def test_get_nonexistent_course_returns_404(self):
        response = self.admin_client.get(f"/api/v1/courses/{uuid.uuid4()}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_patch_course_title(self):
        response = self.admin_client.patch(
            f"/api/v1/courses/{self.course.id}/",
            {"title": "Updated Title"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.course.refresh_from_db()
        self.assertEqual(self.course.title, "Updated Title")

    def test_admin_can_delete_course(self):
        response = self.admin_client.delete(f"/api/v1/courses/{self.course.id}/", HTTP_HOST=HOST)
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])

    def test_unauthenticated_returns_401(self):
        response = APIClient().get(f"/api/v1/courses/{self.course.id}/", HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class ModuleListCreateTestCase(TestCase):
    """Tests for POST /api/v1/courses/<id>/modules/"""

    def setUp(self):
        self.tenant = _tenant("Module School", "cs-mod", "test", "admin@csm.com")
        self.admin = _user("admin@csm.com", self.tenant, role="SCHOOL_ADMIN")
        self.course = _course(self.tenant, self.admin)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    def test_unauthenticated_returns_401(self):
        response = APIClient().post(
            f"/api/v1/courses/{self.course.id}/modules/",
            {"title": "Module"},
            HTTP_HOST=HOST,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_create_module(self):
        response = self.admin_client.post(
            f"/api/v1/courses/{self.course.id}/modules/",
            {"title": "New Module", "description": "Module description", "order": 1},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "New Module")

    def test_create_module_for_nonexistent_course_returns_404(self):
        response = self.admin_client.post(
            f"/api/v1/courses/{uuid.uuid4()}/modules/",
            {"title": "Module"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class ModuleDetailTestCase(TestCase):
    """Tests for GET/PATCH/DELETE /api/v1/courses/<id>/modules/<mid>/"""

    def setUp(self):
        self.tenant = _tenant("Mod Detail School", "cs-moddet", "test", "admin@csmdet.com")
        self.admin = _user("admin@csmdet.com", self.tenant, role="SCHOOL_ADMIN")
        self.course = _course(self.tenant, self.admin)
        self.module = _module(self.course)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)

    def test_admin_can_get_module(self):
        response = self.admin_client.get(
            f"/api/v1/courses/{self.course.id}/modules/{self.module.id}/", HTTP_HOST=HOST
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_patch_module_title(self):
        response = self.admin_client.patch(
            f"/api/v1/courses/{self.course.id}/modules/{self.module.id}/",
            {"title": "Updated Module"},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.module.refresh_from_db()
        self.assertEqual(self.module.title, "Updated Module")

    def test_admin_can_delete_module(self):
        response = self.admin_client.delete(
            f"/api/v1/courses/{self.course.id}/modules/{self.module.id}/", HTTP_HOST=HOST
        )
        self.assertIn(response.status_code, [status.HTTP_200_OK, status.HTTP_204_NO_CONTENT])


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class ContentListCreateTestCase(TestCase):
    """Tests for POST /api/v1/courses/<id>/modules/<mid>/contents/"""

    def setUp(self):
        self.tenant = _tenant("Content School", "cs-cont", "test", "admin@cscont.com")
        self.admin = _user("admin@cscont.com", self.tenant, role="SCHOOL_ADMIN")
        self.course = _course(self.tenant, self.admin)
        self.module = _module(self.course)
        self.admin_client = APIClient()
        self.admin_client.force_authenticate(user=self.admin)
        self.url = f"/api/v1/courses/{self.course.id}/modules/{self.module.id}/contents/"

    def test_unauthenticated_returns_401(self):
        response = APIClient().post(self.url, {"title": "Content"}, HTTP_HOST=HOST)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_can_create_text_content(self):
        response = self.admin_client.post(
            self.url,
            {
                "title": "Text Lesson",
                "content_type": "TEXT",
                "order": 1,
                "text_content": "<p>Hello world</p>",
            },
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "Text Lesson")

    def test_create_content_missing_type_returns_400(self):
        response = self.admin_client.post(
            self.url,
            {"title": "No Type", "order": 1},
            HTTP_HOST=HOST,
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
