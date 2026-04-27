# apps/progress/tests_skills_views.py
#
# Comprehensive tests for the Skills API:
#   - Skill CRUD (admin only)
#   - Skill categories
#   - CourseSkill mapping CRUD
#   - Teacher skill matrix (teacher + admin access)
#   - Teacher skill assign / update / delete / bulk-update
#   - Skill gap analysis
#   - Auth guards (401 / 403) and cross-tenant isolation (404)

import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import Course, Module
from apps.tenants.models import Tenant
from apps.users.models import User

from .skills_models import CourseSkill, Skill, TeacherSkill


HOST = "test.lms.com"
HOST_OTHER = "other.lms.com"


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class _SkillsBase(TestCase):
    """
    Shared fixtures: two tenants, admin + teacher per tenant, one skill,
    one course, one course-skill mapping, one teacher-skill assignment.
    """

    @classmethod
    def setUpTestData(cls):
        # Tenant A
        cls.tenant = Tenant.objects.create(
            name="Alpha School",
            slug="alpha-school",
            subdomain="test",
            email="alpha@school.com",
            is_active=True,
        )
        cls.admin = User.objects.create_user(
            email="admin@alpha.com",
            password="Admin!Pass123",
            first_name="Alpha",
            last_name="Admin",
            tenant=cls.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        cls.teacher = User.objects.create_user(
            email="teacher@alpha.com",
            password="Teacher!Pass123",
            first_name="Alpha",
            last_name="Teacher",
            tenant=cls.tenant,
            role="TEACHER",
            is_active=True,
        )

        # Tenant B (for cross-tenant isolation tests)
        cls.tenant_b = Tenant.objects.create(
            name="Beta School",
            slug="beta-school",
            subdomain="other",
            email="beta@school.com",
            is_active=True,
        )
        cls.admin_b = User.objects.create_user(
            email="admin@beta.com",
            password="Admin!Pass123",
            first_name="Beta",
            last_name="Admin",
            tenant=cls.tenant_b,
            role="SCHOOL_ADMIN",
            is_active=True,
        )

        # Skill in Tenant A
        cls.skill = Skill.all_objects.create(
            tenant=cls.tenant,
            name="Python Programming",
            description="Core Python skills",
            category="Technology",
            level_required=3,
        )

        # Skill in Tenant B (must NOT be visible from Tenant A)
        cls.skill_b = Skill.all_objects.create(
            tenant=cls.tenant_b,
            name="Secret Skill",
            description="Tenant B only",
            category="Other",
            level_required=1,
        )

        # Course in Tenant A
        cls.course = Course.objects.create(
            tenant=cls.tenant,
            title="Python Fundamentals",
            slug="python-fundamentals",
            description="Learn Python",
            created_by=cls.admin,
            is_published=True,
            is_active=True,
        )

        # Course-skill mapping
        cls.course_skill = CourseSkill.objects.create(
            course=cls.course,
            skill=cls.skill,
            level_taught=2,
        )

        # Teacher-skill assignment
        cls.teacher_skill = TeacherSkill.all_objects.create(
            teacher=cls.teacher,
            skill=cls.skill,
            tenant=cls.tenant,
            current_level=1,
            target_level=3,
        )

    def _admin_client(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        client.defaults["HTTP_HOST"] = HOST
        return client

    def _teacher_client(self):
        client = APIClient()
        client.force_authenticate(user=self.teacher)
        client.defaults["HTTP_HOST"] = HOST
        return client

    def _admin_b_client(self):
        """Admin from Tenant B hitting Tenant A's subdomain."""
        client = APIClient()
        client.force_authenticate(user=self.admin_b)
        client.defaults["HTTP_HOST"] = HOST  # Tenant A's host
        return client

    def _anon_client(self):
        client = APIClient()
        client.defaults["HTTP_HOST"] = HOST
        return client


# ---------------------------------------------------------------------------
# Skill CRUD — admin-only
# ---------------------------------------------------------------------------

class SkillListCreateTests(_SkillsBase):

    def test_skill_list_admin_returns_200(self):
        resp = self._admin_client().get("/api/v1/skills/")
        self.assertEqual(resp.status_code, 200)

    def test_skill_list_returns_tenant_skills_only(self):
        resp = self._admin_client().get("/api/v1/skills/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", data.get("data", []))
        names = [r["name"] for r in results]
        self.assertIn("Python Programming", names)
        self.assertNotIn("Secret Skill", names)

    def test_skill_list_category_filter(self):
        resp = self._admin_client().get("/api/v1/skills/?category=Technology")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", [])
        for r in results:
            self.assertEqual(r["category"], "Technology")

    def test_skill_list_search_filter(self):
        resp = self._admin_client().get("/api/v1/skills/?search=Python")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results", [])
        names = [r["name"] for r in results]
        self.assertIn("Python Programming", names)

    def test_skill_list_teacher_gets_403(self):
        resp = self._teacher_client().get("/api/v1/skills/")
        self.assertEqual(resp.status_code, 403)

    def test_skill_list_anon_gets_401(self):
        resp = self._anon_client().get("/api/v1/skills/")
        self.assertEqual(resp.status_code, 401)

    def test_skill_create_returns_201(self):
        resp = self._admin_client().post(
            "/api/v1/skills/create/",
            data={"name": "Data Analysis", "category": "Analytics", "level_required": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["name"], "Data Analysis")
        self.assertEqual(body["category"], "Analytics")
        # Cleanup
        Skill.all_objects.filter(name="Data Analysis", tenant=self.tenant).delete()

    def test_skill_create_duplicate_name_returns_400(self):
        resp = self._admin_client().post(
            "/api/v1/skills/create/",
            data={"name": "Python Programming", "category": "Technology", "level_required": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_skill_create_teacher_gets_403(self):
        resp = self._teacher_client().post(
            "/api/v1/skills/create/",
            data={"name": "New Skill", "category": "Tech", "level_required": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


class SkillDetailUpdateDeleteTests(_SkillsBase):

    def test_skill_detail_returns_200(self):
        resp = self._admin_client().get(f"/api/v1/skills/{self.skill.id}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Python Programming")

    def test_skill_detail_cross_tenant_returns_404(self):
        # Admin from Tenant B hitting Tenant A — skill_b doesn't belong to test host
        resp = self._admin_b_client().get(f"/api/v1/skills/{self.skill_b.id}/")
        # tenant B's skill should not be found when hitting tenant A
        self.assertEqual(resp.status_code, 404)

    def test_skill_detail_nonexistent_returns_404(self):
        resp = self._admin_client().get(f"/api/v1/skills/{uuid.uuid4()}/")
        self.assertEqual(resp.status_code, 404)

    def test_skill_update_returns_200(self):
        resp = self._admin_client().patch(
            f"/api/v1/skills/{self.skill.id}/update/",
            data={"description": "Updated description"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["description"], "Updated description")

    def test_skill_update_teacher_gets_403(self):
        resp = self._teacher_client().patch(
            f"/api/v1/skills/{self.skill.id}/update/",
            data={"description": "Teacher update"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_skill_delete_returns_204(self):
        # Create a throwaway skill to delete
        throwaway = Skill.all_objects.create(
            tenant=self.tenant,
            name="To Delete",
            category="Temp",
            level_required=1,
        )
        resp = self._admin_client().delete(f"/api/v1/skills/{throwaway.id}/delete/")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(Skill.all_objects.filter(id=throwaway.id).exists())

    def test_skill_delete_teacher_gets_403(self):
        resp = self._teacher_client().delete(f"/api/v1/skills/{self.skill.id}/delete/")
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Skill categories
# ---------------------------------------------------------------------------

class SkillCategoriesTests(_SkillsBase):

    def test_skill_categories_returns_200(self):
        resp = self._admin_client().get("/api/v1/skills/categories/")
        self.assertEqual(resp.status_code, 200)

    def test_skill_categories_includes_technology(self):
        resp = self._admin_client().get("/api/v1/skills/categories/")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("Technology", body["categories"])

    def test_skill_categories_no_duplicates(self):
        # Create a second skill in the same category
        extra = Skill.all_objects.create(
            tenant=self.tenant,
            name="Advanced Python",
            category="Technology",
            level_required=5,
        )
        resp = self._admin_client().get("/api/v1/skills/categories/")
        body = resp.json()
        cats = body["categories"]
        self.assertEqual(len(cats), len(set(cats)))
        # Cleanup
        extra.delete()

    def test_skill_categories_teacher_gets_403(self):
        resp = self._teacher_client().get("/api/v1/skills/categories/")
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# CourseSkill mapping
# ---------------------------------------------------------------------------

class CourseSkillTests(_SkillsBase):

    def test_course_skill_list_returns_200(self):
        resp = self._admin_client().get("/api/v1/skills/course-mappings/")
        self.assertEqual(resp.status_code, 200)

    def test_course_skill_list_includes_existing_mapping(self):
        resp = self._admin_client().get("/api/v1/skills/course-mappings/")
        body = resp.json()
        results = body.get("results", [])
        skill_ids = [r["skill"] for r in results]
        self.assertIn(str(self.skill.id), skill_ids)

    def test_course_skill_list_course_id_filter(self):
        resp = self._admin_client().get(
            f"/api/v1/skills/course-mappings/?course_id={self.course.id}"
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for r in body.get("results", []):
            self.assertEqual(r["course"], str(self.course.id))

    def test_course_skill_create_returns_201(self):
        # Need another skill to map
        new_skill = Skill.all_objects.create(
            tenant=self.tenant,
            name="Project Management",
            category="Management",
            level_required=2,
        )
        resp = self._admin_client().post(
            "/api/v1/skills/course-mappings/create/",
            data={"course": str(self.course.id), "skill": str(new_skill.id), "level_taught": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        # Cleanup
        CourseSkill.objects.filter(course=self.course, skill=new_skill).delete()
        new_skill.delete()

    def test_course_skill_create_duplicate_returns_400(self):
        # Same course+skill already exists
        resp = self._admin_client().post(
            "/api/v1/skills/course-mappings/create/",
            data={"course": str(self.course.id), "skill": str(self.skill.id), "level_taught": 3},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_course_skill_delete_returns_204(self):
        # Create a throwaway mapping
        extra_skill = Skill.all_objects.create(
            tenant=self.tenant,
            name="Leadership",
            category="Soft Skills",
            level_required=2,
        )
        mapping = CourseSkill.objects.create(
            course=self.course, skill=extra_skill, level_taught=1,
        )
        resp = self._admin_client().delete(
            f"/api/v1/skills/course-mappings/{mapping.id}/delete/"
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(CourseSkill.objects.filter(id=mapping.id).exists())
        extra_skill.delete()

    def test_course_skill_teacher_gets_403(self):
        resp = self._teacher_client().get("/api/v1/skills/course-mappings/")
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Teacher skill matrix
# ---------------------------------------------------------------------------

class TeacherSkillMatrixTests(_SkillsBase):

    def test_matrix_admin_sees_all_returns_200(self):
        resp = self._admin_client().get("/api/v1/skills/matrix/")
        self.assertEqual(resp.status_code, 200)

    def test_matrix_admin_sees_teacher_assignments(self):
        resp = self._admin_client().get("/api/v1/skills/matrix/")
        body = resp.json()
        results = body.get("results", [])
        skill_ids = [r["skill"] for r in results]
        self.assertIn(str(self.skill.id), skill_ids)

    def test_matrix_teacher_sees_own_returns_200(self):
        resp = self._teacher_client().get("/api/v1/skills/matrix/")
        self.assertEqual(resp.status_code, 200)

    def test_matrix_teacher_scoped_to_own(self):
        """A second teacher in the same tenant should not see the first teacher's rows."""
        teacher2 = User.objects.create_user(
            email="teacher2@alpha.com",
            password="Teacher2!Pass123",
            first_name="Alpha",
            last_name="Teacher2",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        client = APIClient()
        client.force_authenticate(user=teacher2)
        client.defaults["HTTP_HOST"] = HOST
        resp = client.get("/api/v1/skills/matrix/")
        body = resp.json()
        results = body.get("results", [])
        # teacher2 has no assignments — should see empty list
        self.assertEqual(len(results), 0)
        teacher2.delete()

    def test_matrix_gaps_only_filter(self):
        resp = self._admin_client().get("/api/v1/skills/matrix/?gaps_only=true")
        self.assertEqual(resp.status_code, 200)
        # Our fixture: current_level=1, target_level=3 → gap exists
        body = resp.json()
        results = body.get("results", [])
        for r in results:
            self.assertLess(r["current_level"], r["target_level"])

    def test_matrix_anon_gets_401(self):
        resp = self._anon_client().get("/api/v1/skills/matrix/")
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Teacher skill assign / update / delete
# ---------------------------------------------------------------------------

class TeacherSkillAssignTests(_SkillsBase):

    def test_teacher_skill_assign_returns_201(self):
        new_skill = Skill.all_objects.create(
            tenant=self.tenant,
            name="Classroom Management",
            category="Pedagogy",
            level_required=3,
        )
        resp = self._admin_client().post(
            "/api/v1/skills/assign/",
            data={
                "teacher": str(self.teacher.id),
                "skill": str(new_skill.id),
                "current_level": 1,
                "target_level": 3,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["current_level"], 1)
        self.assertEqual(body["target_level"], 3)
        # Cleanup
        TeacherSkill.all_objects.filter(teacher=self.teacher, skill=new_skill).delete()
        new_skill.delete()

    def test_teacher_skill_assign_duplicate_returns_400(self):
        # self.teacher already has self.skill assigned
        resp = self._admin_client().post(
            "/api/v1/skills/assign/",
            data={
                "teacher": str(self.teacher.id),
                "skill": str(self.skill.id),
                "current_level": 0,
                "target_level": 2,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_teacher_skill_assign_invalid_level_returns_400(self):
        new_skill = Skill.all_objects.create(
            tenant=self.tenant,
            name="Temp Skill 999",
            category="Test",
            level_required=1,
        )
        resp = self._admin_client().post(
            "/api/v1/skills/assign/",
            data={
                "teacher": str(self.teacher.id),
                "skill": str(new_skill.id),
                "current_level": 99,  # invalid
                "target_level": 1,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
        new_skill.delete()

    def test_teacher_skill_assign_missing_fields_returns_400(self):
        resp = self._admin_client().post(
            "/api/v1/skills/assign/",
            data={},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_teacher_skill_assign_teacher_gets_403(self):
        resp = self._teacher_client().post(
            "/api/v1/skills/assign/",
            data={"teacher": str(self.teacher.id), "skill": str(self.skill.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_teacher_skill_update_returns_200(self):
        resp = self._admin_client().patch(
            f"/api/v1/skills/teacher/{self.teacher_skill.id}/update/",
            data={"current_level": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["current_level"], 2)

    def test_teacher_skill_update_sets_last_assessed(self):
        resp = self._admin_client().patch(
            f"/api/v1/skills/teacher/{self.teacher_skill.id}/update/",
            data={"current_level": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.teacher_skill.refresh_from_db()
        self.assertIsNotNone(self.teacher_skill.last_assessed)

    def test_teacher_skill_update_nonexistent_returns_404(self):
        resp = self._admin_client().patch(
            f"/api/v1/skills/teacher/{uuid.uuid4()}/update/",
            data={"current_level": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_teacher_skill_delete_returns_204(self):
        # Create a throwaway assignment to delete
        extra_skill = Skill.all_objects.create(
            tenant=self.tenant,
            name="Temporary For Delete",
            category="Test",
            level_required=1,
        )
        ts = TeacherSkill.all_objects.create(
            teacher=self.teacher,
            skill=extra_skill,
            tenant=self.tenant,
            current_level=0,
            target_level=1,
        )
        resp = self._admin_client().delete(
            f"/api/v1/skills/teacher/{ts.id}/delete/"
        )
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(TeacherSkill.all_objects.filter(id=ts.id).exists())
        extra_skill.delete()


# ---------------------------------------------------------------------------
# Bulk update
# ---------------------------------------------------------------------------

class TeacherSkillBulkUpdateTests(_SkillsBase):

    def test_bulk_update_returns_200(self):
        resp = self._admin_client().post(
            "/api/v1/skills/bulk-update/",
            data={
                "updates": [
                    {
                        "teacher_skill_id": str(self.teacher_skill.id),
                        "current_level": 2,
                        "target_level": 4,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["updated"], 1)
        self.assertEqual(body["errors"], [])

    def test_bulk_update_unknown_id_returns_error_entry(self):
        resp = self._admin_client().post(
            "/api/v1/skills/bulk-update/",
            data={
                "updates": [
                    {
                        "teacher_skill_id": str(uuid.uuid4()),
                        "current_level": 2,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["updated"], 0)
        self.assertEqual(len(body["errors"]), 1)

    def test_bulk_update_teacher_gets_403(self):
        resp = self._teacher_client().post(
            "/api/v1/skills/bulk-update/",
            data={"updates": []},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------

class SkillGapAnalysisTests(_SkillsBase):

    def test_gap_analysis_returns_200(self):
        resp = self._admin_client().get("/api/v1/skills/gap-analysis/")
        self.assertEqual(resp.status_code, 200)

    def test_gap_analysis_includes_teacher_gap(self):
        resp = self._admin_client().get("/api/v1/skills/gap-analysis/")
        body = resp.json()
        results = body.get("results", [])
        # Our fixture: current_level=1, target_level=3 → gap_size=2
        found = any(
            r["skill_id"] == str(self.skill.id) and r["gap_size"] > 0
            for r in results
        )
        self.assertTrue(found, "Expected a gap for the fixture teacher-skill")

    def test_gap_analysis_includes_recommended_courses(self):
        resp = self._admin_client().get("/api/v1/skills/gap-analysis/")
        body = resp.json()
        results = body.get("results", [])
        # course_skill maps course → skill at level 2
        gap_row = next(
            (r for r in results if r["skill_id"] == str(self.skill.id)),
            None,
        )
        self.assertIsNotNone(gap_row)
        # Should have at least one recommended course
        self.assertGreater(len(gap_row["recommended_courses"]), 0)

    def test_gap_analysis_total_gaps_key_present(self):
        resp = self._admin_client().get("/api/v1/skills/gap-analysis/")
        self.assertIn("total_gaps", resp.json())

    def test_gap_analysis_teacher_filter(self):
        resp = self._admin_client().get(
            f"/api/v1/skills/gap-analysis/?teacher_id={self.teacher.id}"
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for r in body.get("results", []):
            self.assertEqual(r["teacher_id"], str(self.teacher.id))

    def test_gap_analysis_teacher_gets_403(self):
        resp = self._teacher_client().get("/api/v1/skills/gap-analysis/")
        self.assertEqual(resp.status_code, 403)

    def test_gap_analysis_anon_gets_401(self):
        resp = self._anon_client().get("/api/v1/skills/gap-analysis/")
        self.assertEqual(resp.status_code, 401)


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------

class SkillCrossTenantIsolationTests(_SkillsBase):

    def test_admin_a_cannot_see_tenant_b_skills(self):
        """Admin A should not see Tenant B skills even by direct UUID."""
        resp = self._admin_client().get(f"/api/v1/skills/{self.skill_b.id}/")
        self.assertEqual(resp.status_code, 404)

    def test_admin_b_on_tenant_a_host_sees_tenant_a_skills_only(self):
        """
        Admin B authenticated, hitting Tenant A's host:
        the TenantManager should scope skill_list to Tenant A's skills.
        """
        resp = self._admin_b_client().get("/api/v1/skills/")
        # Admin B is from tenant_b — hitting tenant_a's host should give 403
        # because @tenant_required checks request.user.tenant_id == tenant.id
        self.assertIn(resp.status_code, [403, 404])
