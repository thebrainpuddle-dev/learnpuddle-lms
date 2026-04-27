# apps/progress/tests_rubrics.py
#
# TASK-044 — Happy-path tests for Rubric CRUD + clone + evaluate.

from decimal import Decimal

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.courses.models import Course, Module
from apps.progress.models import Assignment, AssignmentSubmission
from apps.progress.rubric_models import (
    Rubric,
    RubricCriterion,
    RubricEvaluation,
    RubricLevel,
)
from apps.tenants.models import Tenant
from apps.users.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class RubricApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="Rubric School",
            slug="rubric-school",
            subdomain="rubric",
            email="rubric@test.com",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            email="admin@rubric.test",
            password="pass123",
            first_name="Ad",
            last_name="Min",
            tenant=self.tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            email="teacher@rubric.test",
            password="pass123",
            first_name="Te",
            last_name="Ach",
            tenant=self.tenant,
            role="TEACHER",
            is_active=True,
        )
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Course",
            slug="course",
            description="d",
            created_by=self.admin,
            is_published=True,
            is_active=True,
            assigned_to_all=True,
        )
        self.module = Module.objects.create(
            course=self.course, title="M", description="", order=1, is_active=True,
        )
        self.assignment = Assignment.objects.create(
            tenant=self.tenant,
            course=self.course,
            module=self.module,
            title="Essay",
            description="Write an essay",
            instructions="",
            max_score=100,
            passing_score=60,
        )
        self.submission = AssignmentSubmission.objects.create(
            tenant=self.tenant,
            assignment=self.assignment,
            teacher=self.teacher,
            submission_text="my essay body",
            status="SUBMITTED",
        )

    # ------------------------------------------------------------------
    def _host(self):
        self.client.defaults["HTTP_HOST"] = "rubric.lms.com"

    def _login(self, email, password="pass123"):
        self._host()
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": email, "password": password},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        access = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def _rubric_payload(self, title="Essay Rubric"):
        return {
            "title": title,
            "description": "General essay rubric",
            "criteria": [
                {
                    "title": "Thesis",
                    "description": "Clarity of thesis",
                    "max_points": "10.00",
                    "order": 0,
                    "levels": [
                        {"title": "Exemplary", "description": "", "points": "10.00", "order": 0},
                        {"title": "Proficient", "description": "", "points": "7.00", "order": 1},
                        {"title": "Developing", "description": "", "points": "4.00", "order": 2},
                    ],
                },
                {
                    "title": "Evidence",
                    "description": "Use of evidence",
                    "max_points": "20.00",
                    "order": 1,
                    "levels": [
                        {"title": "Strong", "description": "", "points": "20.00", "order": 0},
                        {"title": "Weak", "description": "", "points": "10.00", "order": 1},
                    ],
                },
            ],
        }

    # ==================================================================
    # CRUD
    # ==================================================================
    def test_admin_creates_rubric_with_nested_criteria_and_levels(self):
        self._login("admin@rubric.test")

        resp = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload(), format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()

        self.assertEqual(data["title"], "Essay Rubric")
        # Total = 10 + 20
        self.assertEqual(Decimal(str(data["total_points"])), Decimal("30.00"))
        self.assertEqual(len(data["criteria"]), 2)
        levels_0 = data["criteria"][0]["levels"]
        self.assertEqual(len(levels_0), 3)

    def test_admin_lists_and_fetches_rubric(self):
        self._login("admin@rubric.test")
        self.client.post("/api/v1/admin/rubrics/", self._rubric_payload(), format="json")

        list_resp = self.client.get("/api/v1/admin/rubrics/")
        self.assertEqual(list_resp.status_code, 200)
        results = list_resp.json().get("results", [])
        self.assertEqual(len(results), 1)
        rubric_id = results[0]["id"]

        detail = self.client.get(f"/api/v1/admin/rubrics/{rubric_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.json()["criteria"]), 2)

    def test_admin_patches_rubric_replaces_criteria(self):
        self._login("admin@rubric.test")
        resp = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload(), format="json",
        )
        rubric_id = resp.json()["id"]

        patch = {
            "title": "Updated Rubric",
            "criteria": [
                {
                    "title": "Grammar",
                    "max_points": "5.00",
                    "order": 0,
                    "levels": [
                        {"title": "Clean", "points": "5.00", "order": 0},
                    ],
                }
            ],
        }
        resp2 = self.client.patch(
            f"/api/v1/admin/rubrics/{rubric_id}/", patch, format="json",
        )
        self.assertEqual(resp2.status_code, 200, resp2.content)
        self.assertEqual(resp2.json()["title"], "Updated Rubric")
        self.assertEqual(len(resp2.json()["criteria"]), 1)
        self.assertEqual(Decimal(str(resp2.json()["total_points"])), Decimal("5.00"))

    def test_admin_deletes_rubric(self):
        self._login("admin@rubric.test")
        resp = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload(), format="json",
        )
        rubric_id = resp.json()["id"]

        resp2 = self.client.delete(f"/api/v1/admin/rubrics/{rubric_id}/")
        self.assertEqual(resp2.status_code, 204)
        self.assertFalse(Rubric.all_objects.filter(id=rubric_id).exists())

    # ==================================================================
    # Clone
    # ==================================================================
    def test_admin_clones_rubric_deep_copies_criteria_and_levels(self):
        self._login("admin@rubric.test")
        resp = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload(), format="json",
        )
        source_id = resp.json()["id"]

        clone_resp = self.client.post(
            f"/api/v1/admin/rubrics/{source_id}/clone/",
            {"title": "Essay Rubric V2"},
            format="json",
        )
        self.assertEqual(clone_resp.status_code, 201, clone_resp.content)
        clone = clone_resp.json()
        self.assertEqual(clone["title"], "Essay Rubric V2")
        self.assertNotEqual(clone["id"], source_id)
        self.assertEqual(len(clone["criteria"]), 2)
        self.assertEqual(Decimal(str(clone["total_points"])), Decimal("30.00"))

        # Verify DB records are independent (different IDs).
        src = Rubric.all_objects.get(id=source_id)
        cln = Rubric.all_objects.get(id=clone["id"])
        src_crit_ids = set(src.criteria.values_list("id", flat=True))
        cln_crit_ids = set(cln.criteria.values_list("id", flat=True))
        self.assertTrue(src_crit_ids.isdisjoint(cln_crit_ids))

    # ==================================================================
    # Attach rubric to assignment
    # ==================================================================
    def test_admin_attaches_rubric_to_assignment(self):
        self._login("admin@rubric.test")
        resp = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload(), format="json",
        )
        rubric_id = resp.json()["id"]

        resp2 = self.client.post(
            f"/api/v1/admin/assignments/{self.assignment.id}/attach-rubric/",
            {"rubric_id": rubric_id},
            format="json",
        )
        self.assertEqual(resp2.status_code, 200, resp2.content)
        self.assignment.refresh_from_db()
        self.assertEqual(str(self.assignment.rubric_id), rubric_id)

    # ==================================================================
    # Evaluate
    # ==================================================================
    def test_admin_evaluates_submission_with_rubric_computes_total_server_side(self):
        self._login("admin@rubric.test")
        create_resp = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload(), format="json",
        )
        rubric_id = create_resp.json()["id"]
        criteria = create_resp.json()["criteria"]
        c_thesis = criteria[0]
        c_evidence = criteria[1]

        # Attach to assignment.
        self.client.post(
            f"/api/v1/admin/assignments/{self.assignment.id}/attach-rubric/",
            {"rubric_id": rubric_id},
            format="json",
        )

        # Evaluate: Proficient (7) on thesis, Strong (20) on evidence → 27
        evaluate_payload = {
            "scores": [
                {
                    "criterion_id": c_thesis["id"],
                    "level_id": c_thesis["levels"][1]["id"],  # Proficient
                    "comment": "Good thesis",
                },
                {
                    "criterion_id": c_evidence["id"],
                    "level_id": c_evidence["levels"][0]["id"],  # Strong
                    "points": "20.00",
                    "comment": "Solid evidence",
                },
            ],
            "feedback": "Nice work.",
        }
        resp = self.client.post(
            f"/api/v1/admin/submissions/{self.submission.id}/evaluate/",
            evaluate_payload,
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        body = resp.json()
        self.assertEqual(Decimal(str(body["total_score"])), Decimal("27.00"))

        # Client cannot tamper with total: submission is graded with server-computed score.
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.score, Decimal("27.00"))
        self.assertEqual(self.submission.status, "GRADED")
        self.assertEqual(self.submission.graded_by_id, self.admin.id)

        # Re-evaluating by same evaluator updates in place.
        evaluate_payload["scores"][0]["level_id"] = c_thesis["levels"][0]["id"]  # Exemplary
        resp2 = self.client.post(
            f"/api/v1/admin/submissions/{self.submission.id}/evaluate/",
            evaluate_payload,
            format="json",
        )
        self.assertEqual(resp2.status_code, 200, resp2.content)
        self.assertEqual(Decimal(str(resp2.json()["total_score"])), Decimal("30.00"))
        self.assertEqual(RubricEvaluation.objects.count(), 1)

    def test_evaluation_rejects_criterion_from_different_rubric(self):
        self._login("admin@rubric.test")

        # Create and attach rubric A
        create_a = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload("A"), format="json",
        )
        rubric_a_id = create_a.json()["id"]
        self.client.post(
            f"/api/v1/admin/assignments/{self.assignment.id}/attach-rubric/",
            {"rubric_id": rubric_a_id},
            format="json",
        )

        # Create rubric B (not attached to assignment)
        create_b = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload("B"), format="json",
        )
        criterion_b_id = create_b.json()["criteria"][0]["id"]

        # Evaluate the assignment with a criterion from rubric B — must 400.
        resp = self.client.post(
            f"/api/v1/admin/submissions/{self.submission.id}/evaluate/",
            {
                "scores": [
                    {"criterion_id": criterion_b_id, "points": "5.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    def test_evaluation_rejects_points_exceeding_max(self):
        self._login("admin@rubric.test")
        create_resp = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload(), format="json",
        )
        rubric_id = create_resp.json()["id"]
        criterion = create_resp.json()["criteria"][0]
        self.client.post(
            f"/api/v1/admin/assignments/{self.assignment.id}/attach-rubric/",
            {"rubric_id": rubric_id},
            format="json",
        )

        resp = self.client.post(
            f"/api/v1/admin/submissions/{self.submission.id}/evaluate/",
            {
                "scores": [
                    # max_points is 10 — try 99
                    {"criterion_id": criterion["id"], "points": "99.00"},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 400, resp.content)

    # ==================================================================
    # Teacher view
    # ==================================================================
    def test_teacher_views_own_evaluation(self):
        # Admin sets everything up and evaluates.
        self._login("admin@rubric.test")
        create_resp = self.client.post(
            "/api/v1/admin/rubrics/", self._rubric_payload(), format="json",
        )
        rubric_id = create_resp.json()["id"]
        criteria = create_resp.json()["criteria"]
        self.client.post(
            f"/api/v1/admin/assignments/{self.assignment.id}/attach-rubric/",
            {"rubric_id": rubric_id},
            format="json",
        )
        self.client.post(
            f"/api/v1/admin/submissions/{self.submission.id}/evaluate/",
            {
                "scores": [
                    {
                        "criterion_id": criteria[0]["id"],
                        "level_id": criteria[0]["levels"][0]["id"],
                    },
                    {
                        "criterion_id": criteria[1]["id"],
                        "level_id": criteria[1]["levels"][1]["id"],
                    },
                ],
                "feedback": "Well done.",
            },
            format="json",
        )

        # Teacher logs in and views.
        self.client.credentials()  # clear auth
        self._login("teacher@rubric.test")
        resp = self.client.get(
            f"/api/v1/teacher/submissions/{self.submission.id}/evaluation/",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertIsNotNone(body["rubric"])
        self.assertEqual(len(body["evaluations"]), 1)
        self.assertEqual(
            Decimal(str(body["evaluations"][0]["total_score"])), Decimal("20.00"),
        )

    # ==================================================================
    # Tenant isolation
    # ==================================================================
    def test_rubric_list_is_tenant_scoped(self):
        # Create another tenant + admin + rubric.
        other_tenant = Tenant.objects.create(
            name="Other", slug="other", subdomain="other",
            email="o@t.com", is_active=True,
        )
        other_admin = User.objects.create_user(
            email="admin@other.test",
            password="pass123",
            first_name="O", last_name="A",
            tenant=other_tenant,
            role="SCHOOL_ADMIN",
            is_active=True,
        )
        # Create rubric in other tenant directly (bypass thread-local filter).
        other_rubric = Rubric.all_objects.create(
            tenant=other_tenant, title="Other Rubric",
        )

        # Login as rubric-tenant admin; other's rubric must not be visible.
        self._login("admin@rubric.test")
        resp = self.client.get("/api/v1/admin/rubrics/")
        self.assertEqual(resp.status_code, 200)
        ids = [r["id"] for r in resp.json().get("results", [])]
        self.assertNotIn(str(other_rubric.id), ids)
