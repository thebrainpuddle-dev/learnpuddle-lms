from __future__ import annotations

from django.test import TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.courses.learning_path_models import LearningPath, LearningPathCourse
from apps.courses.models import Content, Course, Module, TeacherGroup
from apps.courses import teacher_views as courses_teacher_views
from apps.media.models import MediaAsset
from apps.progress.models import Assignment
from apps.tenants.models import Tenant
from apps.users.models import User
from utils.tenant_middleware import clear_current_tenant, set_current_tenant


@override_settings(ALLOWED_HOSTS=["testserver", "localhost", "127.0.0.1", ".lms.com"])
class AdminTeacherApiSmokeTestCase(TestCase):
    """
    End-to-end-ish API smoke coverage for the core admin + teacher flows:
    - Admin can list courses, teacher-groups, media, learning-paths
    - Teacher can see assigned courses, dashboard stats, assignments, learning paths

    Also includes a regression test for the historical "double-tenant filter" issue:
    request.tenant != get_current_tenant() should NOT cause empty results for models
    that already use TenantManager/TenantSoftDeleteManager.
    """

    def setUp(self):
        self.client = APIClient()
        self.factory = APIRequestFactory()

        self.tenant = Tenant.objects.create(
            name="Smoke School",
            slug="smoke-school",
            subdomain="smoke",
            email="smoke@test.com",
            is_active=True,
        )
        self.other_tenant = Tenant.objects.create(
            name="Other School",
            slug="other-school",
            subdomain="other",
            email="other@test.com",
            is_active=True,
        )

        self.admin = User.objects.create_user(
            email="admin@smoke.test",
            password="pass123",
            first_name="Admin",
            last_name="Smoke",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@smoke.test",
            password="pass123",
            first_name="Teacher",
            last_name="Smoke",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )

        # Group assignment path
        self.group = TeacherGroup.objects.create(
            tenant=self.tenant,
            name="Math Teachers",
            description="Smoke test group",
            group_type="SUBJECT",
        )
        self.teacher.teacher_groups.add(self.group)

        # Course assigned via BOTH direct teacher assignment and group assignment
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Smoke Course",
            slug="smoke-course",
            description="Smoke course description",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=False,
        )
        self.course.assigned_teachers.add(self.teacher)
        self.course.assigned_groups.add(self.group)

        self.module = Module.objects.create(
            course=self.course,
            title="Module 1",
            description="",
            order=1,
            is_active=True,
        )
        self.content = Content.objects.create(
            module=self.module,
            title="Video 1",
            content_type="VIDEO",
            order=1,
            file_url="https://example.com/video.mp4",
            file_size=1,
            duration=120,
            text_content="",
            is_mandatory=True,
            is_active=True,
        )

        self.assignment = Assignment.objects.create(
            course=self.course,
            module=self.module,
            content=self.content,
            title="Assignment 1",
            description="Smoke assignment",
            instructions="",
            generation_source="MANUAL",
            generation_metadata={},
            is_active=True,
        )

        self.media_asset = MediaAsset.objects.create(
            tenant=self.tenant,
            title="Docs Link",
            media_type="LINK",
            file_url="https://example.com/docs",
            uploaded_by=self.admin,
            is_active=True,
        )

        self.learning_path = LearningPath.objects.create(
            tenant=self.tenant,
            title="Smoke Path",
            description="Smoke learning path",
            is_published=True,
            is_active=True,
            assigned_to_all=False,
            created_by=self.admin,
        )
        self.learning_path.assigned_teachers.add(self.teacher)
        LearningPathCourse.objects.create(
            learning_path=self.learning_path,
            course=self.course,
            order=1,
            is_optional=False,
            min_completion_percentage=100,
        )

    def _login_and_set_bearer(self, *, host: str, email: str, password: str):
        self.client.defaults["HTTP_HOST"] = host
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def test_admin_core_endpoints_return_data(self):
        self._login_and_set_bearer(host="smoke.lms.com", email="admin@smoke.test", password="pass123")

        # Courses list (paginated)
        courses = self.client.get("/api/courses/")
        self.assertEqual(courses.status_code, 200, courses.content)
        results = courses.json().get("results")
        self.assertIsInstance(results, list)
        self.assertIn(str(self.course.id), [c["id"] for c in results])

        # Course detail
        course_detail = self.client.get(f"/api/courses/{self.course.id}/")
        self.assertEqual(course_detail.status_code, 200, course_detail.content)
        self.assertEqual(course_detail.json()["id"], str(self.course.id))

        # Teacher groups list (paginated)
        groups = self.client.get("/api/teacher-groups/")
        self.assertEqual(groups.status_code, 200, groups.content)
        group_results = groups.json().get("results")
        self.assertIsInstance(group_results, list)
        self.assertIn(str(self.group.id), [g["id"] for g in group_results])

        # Media library list (paginated)
        media = self.client.get("/api/media/")
        self.assertEqual(media.status_code, 200, media.content)
        media_results = media.json().get("results")
        self.assertIsInstance(media_results, list)
        self.assertIn(str(self.media_asset.id), [m["id"] for m in media_results])

        # Learning paths list (paginated, under courses/)
        paths = self.client.get("/api/courses/learning-paths/")
        self.assertEqual(paths.status_code, 200, paths.content)
        path_results = paths.json().get("results")
        self.assertIsInstance(path_results, list)
        self.assertIn(str(self.learning_path.id), [p["id"] for p in path_results])

    def test_teacher_core_endpoints_return_data(self):
        self._login_and_set_bearer(host="smoke.lms.com", email="teacher@smoke.test", password="pass123")

        # Teacher course list (non-paginated)
        courses = self.client.get("/api/teacher/courses/")
        self.assertEqual(courses.status_code, 200, courses.content)
        self.assertIsInstance(courses.json(), list)
        self.assertIn(str(self.course.id), [c["id"] for c in courses.json()])

        # Teacher course detail (modules + contents)
        detail = self.client.get(f"/api/teacher/courses/{self.course.id}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["id"], str(self.course.id))
        self.assertGreaterEqual(len(detail.json().get("modules") or []), 1)

        # Dashboard stats
        dashboard = self.client.get("/api/teacher/dashboard/")
        self.assertEqual(dashboard.status_code, 200, dashboard.content)
        self.assertGreaterEqual(int(dashboard.json()["stats"]["total_courses"]), 1)

        # Assignments list
        assignments = self.client.get("/api/teacher/assignments/")
        self.assertEqual(assignments.status_code, 200, assignments.content)
        self.assertIsInstance(assignments.json(), list)
        self.assertIn(str(self.assignment.id), [a["id"] for a in assignments.json()])

        # Learning paths (teacher endpoint under courses/)
        my_paths = self.client.get("/api/courses/my-learning-paths/")
        self.assertEqual(my_paths.status_code, 200, my_paths.content)
        self.assertIsInstance(my_paths.json(), list)
        self.assertIn(str(self.learning_path.id), [p["id"] for p in my_paths.json()])

        my_path_detail = self.client.get(f"/api/courses/my-learning-paths/{self.learning_path.id}/")
        self.assertEqual(my_path_detail.status_code, 200, my_path_detail.content)
        self.assertEqual(my_path_detail.json()["id"], str(self.learning_path.id))

    def test_teacher_course_list_does_not_break_on_request_tenant_mismatch(self):
        """
        Regression: historically, some teacher endpoints did:
          Course.objects.filter(tenant=request.tenant, ...)
        while Course.objects already auto-filters by get_current_tenant() (thread-local).
        If those diverged, the intersection was empty.
        """
        try:
            set_current_tenant(self.tenant)
            req = self.factory.get("/api/teacher/courses/")
            force_authenticate(req, user=self.teacher)
            req.tenant = self.other_tenant  # intentionally wrong

            resp = courses_teacher_views.teacher_course_list(req)
            self.assertEqual(resp.status_code, 200, getattr(resp, "data", None))
            self.assertIsInstance(resp.data, list)
            self.assertIn(str(self.course.id), [c["id"] for c in resp.data])
        finally:
            clear_current_tenant()

