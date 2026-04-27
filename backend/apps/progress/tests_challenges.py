# apps/progress/tests_challenges.py
#
# TASK-017 — Daily / Weekly Challenges (TDD)
#
# Covers:
#   - Models: tenant FK + TenantManager, choice validation, active-window
#   - Engine: progress increment, completion detection, reward issuance,
#             idempotency dedup, cross-tenant isolation, opt-out suppression
#   - API: admin CRUD, teacher list/progress, cross-tenant isolation
#   - Signal wiring: TeacherProgress COMPLETED bumps complete_lessons;
#                    AssignmentSubmission bumps submit_assignments;
#                    XPTransaction bumps earn_xp challenges.

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.progress.challenge_engine import (
    active_challenges,
    evaluate_streak_challenge,
    record_event,
    serialize_challenge_for_teacher,
)
from apps.progress.challenge_models import (
    Challenge,
    ChallengeParticipation,
)
from apps.progress.gamification_engine import (
    award_xp,
    get_or_create_config,
)
from apps.progress.gamification_models import (
    BadgeDefinition,
    TeacherBadge,
    TeacherStreak,
    TeacherXPSummary,
    XPTransaction,
)
from apps.progress.models import (
    Assignment,
    AssignmentSubmission,
    TeacherProgress,
)
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CTR = {"n": 0}


def _u():
    _CTR["n"] += 1
    return _CTR["n"]


def _tenant(name="Challenge School", subdomain=None):
    sub = subdomain or f"ch{_u()}"
    return Tenant.objects.create(
        name=name, slug=sub, subdomain=sub,
        email=f"{sub}@test.com", is_active=True,
    )


def _teacher(tenant, idx=None):
    idx = idx if idx is not None else _u()
    return User.objects.create_user(
        email=f"t{idx}-{tenant.subdomain}@test.com",
        password="pass123",
        first_name="Teacher", last_name=str(idx),
        tenant=tenant, role="TEACHER", is_active=True,
    )


def _admin(tenant, idx=None):
    idx = idx if idx is not None else _u()
    return User.objects.create_user(
        email=f"a{idx}-{tenant.subdomain}@test.com",
        password="pass123",
        first_name="Admin", last_name=str(idx),
        tenant=tenant, role="SCHOOL_ADMIN", is_active=True,
    )


def _challenge(
    tenant, goal_type="complete_lessons", goal_target=3, reward_xp=25,
    challenge_type="DAILY", start_offset_min=-60, end_offset_min=60,
    reward_badge=None, goal_reference_id=None, is_active=True,
):
    now = timezone.now()
    return Challenge.all_objects.create(
        tenant=tenant,
        title=f"Test {goal_type}",
        description="desc",
        challenge_type=challenge_type,
        goal_type=goal_type,
        goal_target=goal_target,
        goal_reference_id=goal_reference_id,
        start_at=now + timedelta(minutes=start_offset_min),
        end_at=now + timedelta(minutes=end_offset_min),
        reward_xp=reward_xp,
        reward_badge=reward_badge,
        is_active=is_active,
    )


def _course(tenant, admin, idx=None):
    idx = idx if idx is not None else _u()
    return Course.objects.create(
        tenant=tenant,
        title=f"Course {idx}",
        slug=f"c-{tenant.subdomain}-{idx}",
        description="d",
        created_by=admin,
        is_published=True,
        is_active=True,
        assigned_to_all=True,
    )


def _module(course, idx=1):
    return Module.objects.create(
        course=course, title=f"M{idx}", description="", order=idx, is_active=True,
    )


def _content(module, idx=1):
    return Content.objects.create(
        module=module, title=f"C{idx}", content_type="TEXT",
        order=idx, file_url="", file_size=0, duration=10,
        text_content="x", is_mandatory=True, is_active=True,
    )


# ===========================================================================
# 1. Model tests
# ===========================================================================

class ChallengeModelTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant)

    def test_challenge_requires_tenant_and_fields(self):
        ch = _challenge(self.tenant)
        self.assertEqual(ch.tenant, self.tenant)
        self.assertEqual(ch.goal_type, "complete_lessons")
        self.assertEqual(ch.challenge_type, "DAILY")

    def test_tenant_manager_isolates_challenges(self):
        other = _tenant(subdomain="otherch")
        _challenge(self.tenant)
        _challenge(other)
        self.assertEqual(Challenge.all_objects.count(), 2)
        # Per-tenant filtering still available via explicit tenant filter.
        self.assertEqual(
            Challenge.all_objects.filter(tenant=self.tenant).count(), 1,
        )

    def test_is_active_now_respects_window(self):
        past = _challenge(
            self.tenant, start_offset_min=-120, end_offset_min=-60,
        )
        self.assertFalse(past.is_active_now())

        future = _challenge(
            self.tenant, start_offset_min=60, end_offset_min=120,
        )
        self.assertFalse(future.is_active_now())

        now = _challenge(
            self.tenant, start_offset_min=-30, end_offset_min=30,
        )
        self.assertTrue(now.is_active_now())

        inactive = _challenge(
            self.tenant, start_offset_min=-30, end_offset_min=30, is_active=False,
        )
        self.assertFalse(inactive.is_active_now())

    def test_participation_unique_per_teacher_and_challenge(self):
        from django.db import IntegrityError, transaction as dj_transaction

        ch = _challenge(self.tenant)
        ChallengeParticipation.all_objects.create(
            tenant=self.tenant, challenge=ch, teacher=self.teacher,
        )
        with self.assertRaises(IntegrityError):
            with dj_transaction.atomic():
                ChallengeParticipation.all_objects.create(
                    tenant=self.tenant, challenge=ch, teacher=self.teacher,
                )


# ===========================================================================
# 2. Engine tests
# ===========================================================================

class ChallengeEngineTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant)
        self.config = get_or_create_config(self.tenant)

    def test_record_event_increments_progress(self):
        ch = _challenge(self.tenant, goal_target=3)
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        p = ChallengeParticipation.all_objects.get(challenge=ch, teacher=self.teacher)
        self.assertEqual(p.progress_value, 1)
        self.assertIsNone(p.completed_at)

    def test_record_event_is_idempotent_on_same_reference(self):
        ch = _challenge(self.tenant, goal_target=5)
        ref = uuid.uuid4()
        for _ in range(3):
            record_event(
                self.teacher, "content_completion",
                reference_id=ref, reference_type="content",
            )
        p = ChallengeParticipation.all_objects.get(challenge=ch, teacher=self.teacher)
        self.assertEqual(p.progress_value, 1, "Duplicate reference must not double-count")

    def test_record_event_completes_on_target(self):
        ch = _challenge(self.tenant, goal_target=2, reward_xp=50)
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        p = ChallengeParticipation.all_objects.get(challenge=ch, teacher=self.teacher)
        self.assertEqual(p.progress_value, 2)
        self.assertIsNotNone(p.completed_at)
        self.assertTrue(p.reward_issued)
        # Reward XP should have been awarded via the XP ledger.
        xp = XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="challenge_reward",
        ).first()
        self.assertIsNotNone(xp)
        self.assertEqual(xp.xp_amount, 50)

    def test_reward_issuance_is_idempotent(self):
        ch = _challenge(self.tenant, goal_target=1, reward_xp=10)
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        # Additional events after completion should be no-ops.
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        rewards = XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="challenge_reward",
        ).count()
        self.assertEqual(rewards, 1)

    def test_finish_course_filters_by_goal_reference_id(self):
        other_course_id = uuid.uuid4()
        target_course_id = uuid.uuid4()
        ch = _challenge(
            self.tenant, goal_type="finish_course",
            goal_target=1, goal_reference_id=target_course_id,
        )
        record_event(
            self.teacher, "course_completion",
            reference_id=other_course_id, reference_type="course",
        )
        p = ChallengeParticipation.all_objects.filter(
            challenge=ch, teacher=self.teacher,
        ).first()
        # Non-matching course is a no-op — participation may not exist at all.
        self.assertTrue(p is None or p.progress_value == 0)

        record_event(
            self.teacher, "course_completion",
            reference_id=target_course_id, reference_type="course",
        )
        p = ChallengeParticipation.all_objects.get(challenge=ch, teacher=self.teacher)
        self.assertEqual(p.progress_value, 1)
        self.assertIsNotNone(p.completed_at)

    def test_opt_out_teacher_records_no_progress(self):
        _challenge(self.tenant, goal_target=1, reward_xp=10)
        TeacherXPSummary.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, opted_out=True,
        )
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        self.assertFalse(
            ChallengeParticipation.all_objects.filter(teacher=self.teacher).exists(),
        )

    def test_cross_tenant_isolation(self):
        other = _tenant(subdomain="iso-other")
        other_teacher = _teacher(other)
        _challenge(self.tenant, goal_target=3)
        # Firing an event for a teacher in a DIFFERENT tenant must not bump
        # our tenant's challenge.
        record_event(
            other_teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        self.assertFalse(
            ChallengeParticipation.all_objects.filter(tenant=self.tenant).exists(),
        )

    def test_earn_xp_challenge_progresses_by_amount(self):
        ch = _challenge(self.tenant, goal_type="earn_xp", goal_target=100, reward_xp=0)
        record_event(
            self.teacher, "earn_xp",
            reference_id=uuid.uuid4(), reference_type="xp_transaction",
            amount=40,
        )
        record_event(
            self.teacher, "earn_xp",
            reference_id=uuid.uuid4(), reference_type="xp_transaction",
            amount=80,
        )
        p = ChallengeParticipation.all_objects.get(challenge=ch, teacher=self.teacher)
        # progress is clamped at target
        self.assertEqual(p.progress_value, 100)
        self.assertIsNotNone(p.completed_at)

    def test_maintain_streak_evaluation_progresses(self):
        ch = _challenge(
            self.tenant, goal_type="maintain_streak", goal_target=5, reward_xp=15,
        )
        evaluate_streak_challenge(self.teacher, current_streak=3)
        p = ChallengeParticipation.all_objects.get(challenge=ch, teacher=self.teacher)
        self.assertEqual(p.progress_value, 3)
        self.assertIsNone(p.completed_at)

        evaluate_streak_challenge(self.teacher, current_streak=6)
        p.refresh_from_db()
        self.assertEqual(p.progress_value, 5)
        self.assertIsNotNone(p.completed_at)

    def test_reward_badge_is_granted_on_completion(self):
        badge = BadgeDefinition.all_objects.create(
            tenant=self.tenant,
            name="Challenge Champion",
            category="special",
            rarity="rare",
            criteria_type="manual",
            criteria_value=0,
        )
        _challenge(
            self.tenant, goal_target=1, reward_xp=0, reward_badge=badge,
        )
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        self.assertTrue(
            TeacherBadge.all_objects.filter(
                teacher=self.teacher, badge=badge,
            ).exists(),
        )

    def test_serialize_shape(self):
        ch = _challenge(self.tenant, goal_target=4)
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        data = serialize_challenge_for_teacher(ch, self.teacher)
        self.assertEqual(data["id"], str(ch.id))
        self.assertEqual(data["goal_target"], 4)
        self.assertEqual(data["progress_value"], 1)
        self.assertEqual(data["progress_percent"], 25)
        self.assertIn("start_at", data)
        self.assertIn("end_at", data)


# ===========================================================================
# 3. Signal wiring tests
# ===========================================================================

class ChallengeSignalTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.admin = _admin(self.tenant)
        self.teacher = _teacher(self.tenant)
        self.course = _course(self.tenant, self.admin)
        self.module = _module(self.course)
        self.content = _content(self.module)
        get_or_create_config(self.tenant)

    def test_teacher_progress_completion_advances_lesson_challenge(self):
        ch = _challenge(self.tenant, goal_type="complete_lessons", goal_target=2)
        tp = TeacherProgress.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, course=self.course,
            content=self.content, status="COMPLETED",
            progress_percentage=100,
        )
        p = ChallengeParticipation.all_objects.get(
            challenge=ch, teacher=self.teacher,
        )
        self.assertEqual(p.progress_value, 1)

        # Re-saving the same completed row should not double-count.
        tp.save()
        p.refresh_from_db()
        self.assertEqual(p.progress_value, 1, "Re-save must be idempotent")

    def test_assignment_submission_advances_assignment_challenge(self):
        ch = _challenge(
            self.tenant, goal_type="submit_assignments", goal_target=1, reward_xp=10,
        )
        assignment = Assignment.all_objects.create(
            tenant=self.tenant, course=self.course,
            title="A1", description="", instructions="",
        )
        AssignmentSubmission.all_objects.create(
            tenant=self.tenant, assignment=assignment, teacher=self.teacher,
            submission_text="done", status="SUBMITTED",
        )
        p = ChallengeParticipation.all_objects.get(
            challenge=ch, teacher=self.teacher,
        )
        self.assertEqual(p.progress_value, 1)
        self.assertIsNotNone(p.completed_at)

    def test_award_xp_advances_earn_xp_challenge(self):
        ch = _challenge(
            self.tenant, goal_type="earn_xp", goal_target=50, reward_xp=0,
        )
        award_xp(
            teacher=self.teacher, reason="admin_adjust",
            xp_amount=50, description="bootstrap",
        )
        p = ChallengeParticipation.all_objects.get(
            challenge=ch, teacher=self.teacher,
        )
        self.assertEqual(p.progress_value, 50)
        self.assertIsNotNone(p.completed_at)

    def test_award_xp_challenge_reward_does_not_recurse(self):
        """
        When the challenge engine issues reward XP via award_xp, the resulting
        XPTransaction must NOT feed back into earn_xp challenges (otherwise a
        reward completes a second challenge and infinite-loops).
        """
        ch = _challenge(
            self.tenant, goal_type="earn_xp", goal_target=10, reward_xp=5,
        )
        award_xp(
            teacher=self.teacher, reason="admin_adjust",
            xp_amount=10, description="x",
        )
        # Only one reward event should exist for this challenge.
        rewards = XPTransaction.all_objects.filter(
            teacher=self.teacher, reason="challenge_reward",
            reference_id=ch.id,
        ).count()
        self.assertEqual(rewards, 1)

    def test_inactive_challenge_ignored(self):
        _challenge(
            self.tenant, goal_type="complete_lessons", goal_target=1,
            is_active=False,
        )
        TeacherProgress.all_objects.create(
            tenant=self.tenant, teacher=self.teacher, course=self.course,
            content=self.content, status="COMPLETED",
            progress_percentage=100,
        )
        self.assertFalse(
            ChallengeParticipation.all_objects.filter(teacher=self.teacher).exists(),
        )


# ===========================================================================
# 4. API tests
# ===========================================================================

@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class ChallengeAdminApiTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.admin = _admin(self.tenant)
        self.teacher = _teacher(self.tenant)
        self.host = f"{self.tenant.subdomain}.lms.com"
        self.client = APIClient()

    def _admin_client(self):
        c = APIClient()
        c.force_authenticate(user=self.admin)
        return c

    def _teacher_client(self):
        c = APIClient()
        c.force_authenticate(user=self.teacher)
        return c

    def _payload(self, **overrides):
        now = timezone.now()
        base = {
            "title": "Daily Hustle",
            "description": "Knock out 3 lessons today",
            "challenge_type": "DAILY",
            "goal_type": "complete_lessons",
            "goal_target": 3,
            "start_at": (now - timedelta(hours=1)).isoformat(),
            "end_at": (now + timedelta(hours=6)).isoformat(),
            "reward_xp": 20,
        }
        base.update(overrides)
        return base

    def test_admin_create_challenge(self):
        client = self._admin_client()
        resp = client.post(
            "/api/v1/gamification/admin/challenges/create/",
            self._payload(), format="json", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertEqual(data["title"], "Daily Hustle")
        self.assertEqual(data["goal_target"], 3)

    def test_admin_list_includes_created(self):
        client = self._admin_client()
        client.post(
            "/api/v1/gamification/admin/challenges/create/",
            self._payload(title="Alpha"), format="json", HTTP_HOST=self.host,
        )
        client.post(
            "/api/v1/gamification/admin/challenges/create/",
            self._payload(title="Beta"), format="json", HTTP_HOST=self.host,
        )
        resp = client.get(
            "/api/v1/gamification/admin/challenges/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        titles = {c["title"] for c in resp.json()["results"]}
        self.assertEqual(titles, {"Alpha", "Beta"})

    def test_admin_update_and_delete(self):
        client = self._admin_client()
        create = client.post(
            "/api/v1/gamification/admin/challenges/create/",
            self._payload(), format="json", HTTP_HOST=self.host,
        )
        ch_id = create.json()["id"]
        patch = client.patch(
            f"/api/v1/gamification/admin/challenges/{ch_id}/",
            {"title": "Renamed", "goal_target": 5},
            format="json", HTTP_HOST=self.host,
        )
        self.assertEqual(patch.status_code, 200)
        self.assertEqual(patch.json()["title"], "Renamed")
        self.assertEqual(patch.json()["goal_target"], 5)

        delete = client.delete(
            f"/api/v1/gamification/admin/challenges/{ch_id}/delete/",
            HTTP_HOST=self.host,
        )
        self.assertEqual(delete.status_code, 204)
        ch = Challenge.all_objects.get(id=ch_id)
        self.assertFalse(ch.is_active)

    def test_admin_create_rejects_invalid_goal_type(self):
        client = self._admin_client()
        resp = client.post(
            "/api/v1/gamification/admin/challenges/create/",
            self._payload(goal_type="not_a_real_goal"),
            format="json", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 400)

    def test_admin_create_rejects_end_before_start(self):
        client = self._admin_client()
        now = timezone.now()
        resp = client.post(
            "/api/v1/gamification/admin/challenges/create/",
            self._payload(
                start_at=(now + timedelta(hours=2)).isoformat(),
                end_at=(now + timedelta(hours=1)).isoformat(),
            ),
            format="json", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 400)

    def test_teacher_cannot_access_admin_endpoints(self):
        client = self._teacher_client()
        resp = client.post(
            "/api/v1/gamification/admin/challenges/create/",
            self._payload(), format="json", HTTP_HOST=self.host,
        )
        self.assertIn(resp.status_code, (401, 403))


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class ChallengeTeacherApiTest(TestCase):
    def setUp(self):
        self.tenant = _tenant()
        self.teacher = _teacher(self.tenant)
        self.host = f"{self.tenant.subdomain}.lms.com"
        self.client = APIClient()
        self.client.force_authenticate(user=self.teacher)

    def test_active_list_returns_current_challenges(self):
        _challenge(self.tenant, goal_target=4)
        _challenge(
            self.tenant, start_offset_min=-120, end_offset_min=-60,  # past
        )
        resp = self.client.get(
            "/api/v1/gamification/challenges/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()["results"]
        self.assertEqual(len(data), 1, "Expired challenge must be filtered out")
        self.assertEqual(data[0]["goal_target"], 4)

    def test_progress_reflected_in_response(self):
        _challenge(self.tenant, goal_target=3)
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        resp = self.client.get(
            "/api/v1/gamification/challenges/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["results"][0]
        self.assertEqual(data["progress_value"], 1)
        self.assertGreater(data["progress_percent"], 0)

    def test_completed_list(self):
        _challenge(self.tenant, goal_target=1, reward_xp=5)
        record_event(
            self.teacher, "content_completion",
            reference_id=uuid.uuid4(), reference_type="content",
        )
        resp = self.client.get(
            "/api/v1/gamification/challenges/completed/", HTTP_HOST=self.host,
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()["results"]
        self.assertEqual(len(data), 1)
        self.assertIsNotNone(data[0]["completed_at"])


@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")
class ChallengeCrossTenantApiTest(TestCase):
    def test_teacher_cannot_see_other_tenant_challenges(self):
        tenant_a = _tenant(subdomain="txa")
        tenant_b = _tenant(subdomain="txb")
        teacher_b = _teacher(tenant_b)
        _challenge(tenant_a)  # belongs to A only

        c = APIClient()
        c.force_authenticate(user=teacher_b)
        resp = c.get(
            "/api/v1/gamification/challenges/",
            HTTP_HOST=f"{tenant_b.subdomain}.lms.com",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["results"], [])

    def test_admin_cannot_patch_other_tenant_challenge(self):
        tenant_a = _tenant(subdomain="isoa")
        tenant_b = _tenant(subdomain="isob")
        admin_b = _admin(tenant_b)
        ch_a = _challenge(tenant_a)

        c = APIClient()
        c.force_authenticate(user=admin_b)
        resp = c.patch(
            f"/api/v1/gamification/admin/challenges/{ch_a.id}/",
            {"title": "Hacked"},
            format="json",
            HTTP_HOST=f"{tenant_b.subdomain}.lms.com",
        )
        self.assertEqual(resp.status_code, 404)
        ch_a.refresh_from_db()
        self.assertNotEqual(ch_a.title, "Hacked")
