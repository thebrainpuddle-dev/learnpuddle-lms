"""Tests for content versioning (TASK-048).

Covers:
- post_save signal captures revisions (course / module / content)
- monotonic numbering
- snapshot determinism (no-op save does NOT create a duplicate revision)
- suppression during restore (no loop)
- restore resurrects soft-deleted children
- restore creates a new "restore-from-vN" revision
- cross-tenant 404
- pagination
- admin-only enforcement
- atomic restore rollback on error
- round 2: restore re-applies every captured scalar field
- round 2: concurrent saves both get distinct revision_numbers
- round 2: restore reverts assigned_teachers M2M
"""

import datetime
import threading
from decimal import Decimal
from unittest import mock

from django.contrib.contenttypes.models import ContentType
from django.db import connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.courses.models import Content, Course, Module
from apps.courses.versioning_models import ContentRevision
from apps.courses.versioning_signals import suppress_versioning
from apps.tenants.models import Tenant
from apps.users.models import User


ADMIN_PASSWORD = "VersionPass@123"


def _make_tenant(sub: str, name: str = None) -> Tenant:
    return Tenant.objects.create(
        name=name or sub.title(),
        slug=f"{sub}-school",
        subdomain=sub,
        email=f"{sub}@test.com",
        is_active=True,
    )


def _make_admin(tenant: Tenant, email: str) -> User:
    return User.objects.create_user(
        email=email,
        password=ADMIN_PASSWORD,
        first_name="A",
        last_name="B",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


def _make_teacher(tenant: Tenant, email: str) -> User:
    return User.objects.create_user(
        email=email,
        password=ADMIN_PASSWORD,
        first_name="T",
        last_name="X",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


class VersioningSignalTests(TestCase):
    """Exercise the post_save signal directly (no HTTP)."""

    def setUp(self):
        self.tenant = _make_tenant("demo")
        self.admin = _make_admin(self.tenant, "admin@demo.test")
        # Save uses signal — so this counts as v1 already.
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="Orig",
            description="d",
            created_by=self.admin,
        )

    def test_create_course_captures_v1(self):
        ct = ContentType.objects.get_for_model(Course)
        revs = ContentRevision.all_objects.filter(
            content_type=ct, object_id=self.course.id
        )
        self.assertGreaterEqual(revs.count(), 1)
        first = revs.order_by("revision_number").first()
        self.assertEqual(first.revision_number, 1)

    def test_updates_are_monotonic(self):
        self.course.title = "Second"
        self.course.save()
        self.course.title = "Third"
        self.course.save()

        ct = ContentType.objects.get_for_model(Course)
        numbers = list(
            ContentRevision.all_objects
            .filter(content_type=ct, object_id=self.course.id)
            .order_by("revision_number")
            .values_list("revision_number", flat=True)
        )
        # Should be strictly increasing 1,2,3,... (no gaps from dedup here,
        # because each save did change the title).
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))
        # And at least 3 revisions exist.
        self.assertGreaterEqual(numbers[-1], 3)

    def test_no_op_save_deduplicates(self):
        # First stabilize — a save captures the current tree state.
        self.course.save()
        ct = ContentType.objects.get_for_model(Course)
        before = ContentRevision.all_objects.filter(
            content_type=ct, object_id=self.course.id
        ).count()
        # Re-save with no field change → snapshot is identical, no new revision.
        self.course.save()
        after = ContentRevision.all_objects.filter(
            content_type=ct, object_id=self.course.id
        ).count()
        self.assertEqual(before, after)

    def test_module_and_content_captured(self):
        m = Module.objects.create(course=self.course, title="M1", order=1)
        c = Content.objects.create(
            module=m, title="C1", content_type="TEXT", text_content="hi"
        )
        m_ct = ContentType.objects.get_for_model(Module)
        c_ct = ContentType.objects.get_for_model(Content)
        self.assertTrue(
            ContentRevision.all_objects.filter(
                content_type=m_ct, object_id=m.id
            ).exists()
        )
        self.assertTrue(
            ContentRevision.all_objects.filter(
                content_type=c_ct, object_id=c.id
            ).exists()
        )

    def test_suppress_versioning_blocks_capture(self):
        ct = ContentType.objects.get_for_model(Course)
        before = ContentRevision.all_objects.filter(
            content_type=ct, object_id=self.course.id
        ).count()
        with suppress_versioning():
            self.course.title = "SuppressedChange"
            self.course.save()
        after = ContentRevision.all_objects.filter(
            content_type=ct, object_id=self.course.id
        ).count()
        self.assertEqual(before, after)


class VersioningAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = _make_tenant("demo")
        self.other = _make_tenant("other")
        self.admin = _make_admin(self.tenant, "admin@demo.test")
        self.other_admin = _make_admin(self.other, "admin@other.test")
        self.teacher = _make_teacher(self.tenant, "t@demo.test")

        self.course = Course.objects.create(
            tenant=self.tenant,
            title="C1",
            description="d",
            created_by=self.admin,
        )
        self.module = Module.objects.create(
            course=self.course, title="M1", order=1
        )
        self.content = Content.objects.create(
            module=self.module,
            title="Ct1",
            content_type="TEXT",
            text_content="original",
        )

    # -----------------------------------------------------------------
    # Auth helpers
    # -----------------------------------------------------------------

    def _login(self, host: str, email: str):
        self.client.defaults["HTTP_HOST"] = host
        resp = self.client.post(
            "/api/users/auth/login/",
            {"email": email, "password": ADMIN_PASSWORD},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        token = resp.json()["tokens"]["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # -----------------------------------------------------------------
    # List / detail
    # -----------------------------------------------------------------

    def test_list_course_revisions_admin_ok(self):
        # Make a second revision by updating the title.
        self.course.title = "C1 v2"
        self.course.save()

        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.get(
            f"/api/v1/admin/courses/{self.course.id}/revisions/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        self.assertIn("results", data)
        # Newest first.
        nums = [r["revision_number"] for r in data["results"]]
        self.assertEqual(nums, sorted(nums, reverse=True))
        self.assertGreaterEqual(len(nums), 2)

    def test_cross_tenant_list_returns_404(self):
        self._login("other.lms.com", "admin@other.test")
        resp = self.client.get(
            f"/api/v1/admin/courses/{self.course.id}/revisions/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_non_admin_rejected(self):
        self._login("demo.lms.com", "t@demo.test")
        resp = self.client.get(
            f"/api/v1/admin/courses/{self.course.id}/revisions/"
        )
        self.assertEqual(resp.status_code, 403)

    def test_revision_detail_returns_snapshot(self):
        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.get(
            f"/api/v1/admin/courses/{self.course.id}/revisions/1/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        body = resp.json()
        self.assertIn("snapshot_json", body)
        self.assertEqual(body["snapshot_json"]["id"], str(self.course.id))

    def test_pagination_page_size_50(self):
        # Force a bunch of revisions quickly.
        for i in range(5):
            self.course.title = f"C1 v{i + 2}"
            self.course.save()
        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.get(
            f"/api/v1/admin/courses/{self.course.id}/revisions/?page_size=2"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["results"]), 2)

    # -----------------------------------------------------------------
    # Restore
    # -----------------------------------------------------------------

    def test_restore_course_revives_deleted_child(self):
        # Capture v-something where module+content exist.
        baseline_course_ct = ContentType.objects.get_for_model(Course)
        baseline_rev = (
            ContentRevision.all_objects
            .filter(content_type=baseline_course_ct, object_id=self.course.id)
            .order_by("-revision_number")
            .first()
        )
        # (force a fresh snapshot that *includes* the module+content tree)
        self.course.title = self.course.title + " x"
        self.course.save()
        snap_rev = (
            ContentRevision.all_objects
            .filter(content_type=baseline_course_ct, object_id=self.course.id)
            .order_by("-revision_number")
            .first()
        )
        self.assertIsNotNone(snap_rev)

        # Soft-delete the module (cascades to content via queryset updates
        # in our tree? No — module soft-delete only flips is_deleted on
        # the module row; but Content still lives. Either way, restore
        # must resurrect the module.)
        self.module.delete()  # soft-delete
        self.module.refresh_from_db()
        self.assertTrue(self.module.is_deleted)

        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}"
            f"/revisions/{snap_rev.revision_number}/restore/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        self.module.refresh_from_db()
        self.assertFalse(
            self.module.is_deleted,
            "Restore should resurrect the soft-deleted module",
        )

    def test_restore_creates_new_revision(self):
        # Bump to have at least two revisions.
        self.course.title = "C1 v2"
        self.course.save()

        ct = ContentType.objects.get_for_model(Course)
        before = ContentRevision.all_objects.filter(
            content_type=ct, object_id=self.course.id
        ).count()

        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/revisions/1/restore/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        after = ContentRevision.all_objects.filter(
            content_type=ct, object_id=self.course.id
        ).count()
        # Exactly one new revision with restore-from-v1 summary.
        self.assertEqual(after, before + 1)
        latest = (
            ContentRevision.all_objects
            .filter(content_type=ct, object_id=self.course.id)
            .order_by("-revision_number")
            .first()
        )
        self.assertEqual(latest.change_summary, "restore-from-v1")

    def test_restore_cross_tenant_returns_404(self):
        # Trying to restore demo tenant's course from the other tenant
        # context should 404 (course not resolvable).
        self._login("other.lms.com", "admin@other.test")
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}/revisions/1/restore/"
        )
        self.assertEqual(resp.status_code, 404)

    def test_restore_is_atomic_on_error(self):
        # Ensure a mid-restore exception doesn't leave partial garbage.
        self.course.title = "C1 v2"
        self.course.save()

        ct = ContentType.objects.get_for_model(Course)
        before_count = ContentRevision.all_objects.filter(
            content_type=ct, object_id=self.course.id
        ).count()
        before_title = Course.all_objects.get(pk=self.course.id).title

        self._login("demo.lms.com", "admin@demo.test")

        # Patch _apply_course_snapshot to raise partway through.
        with mock.patch(
            "apps.courses.versioning_views._record_restore_revision",
            side_effect=RuntimeError("boom"),
        ):
            resp = self.client.post(
                f"/api/v1/admin/courses/{self.course.id}/revisions/1/restore/"
            )
        self.assertEqual(resp.status_code, 500)

        # Nothing persisted: title should still be the pre-restore value,
        # and no new revision row should exist.
        self.assertEqual(
            Course.all_objects.get(pk=self.course.id).title, before_title
        )
        after_count = ContentRevision.all_objects.filter(
            content_type=ct, object_id=self.course.id
        ).count()
        self.assertEqual(after_count, before_count)

    def test_module_restore_endpoint(self):
        # Capture a baseline.
        self.module.title = "M1 renamed"
        self.module.save()

        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.get(
            f"/api/v1/admin/modules/{self.module.id}/revisions/"
        )
        self.assertEqual(resp.status_code, 200)
        nums = [r["revision_number"] for r in resp.json()["results"]]
        self.assertGreaterEqual(len(nums), 2)

        # Restore v1.
        resp = self.client.post(
            f"/api/v1/admin/modules/{self.module.id}/revisions/1/restore/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.module.refresh_from_db()
        self.assertEqual(self.module.title, "M1")

    def test_content_restore_endpoint(self):
        self.content.text_content = "edited"
        self.content.save()

        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}/revisions/1/restore/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)
        self.content.refresh_from_db()
        self.assertEqual(self.content.text_content, "original")

    # -----------------------------------------------------------------
    # Round 2 regressions (H1, L1)
    # -----------------------------------------------------------------

    def test_restore_reapplies_all_captured_course_fields(self):
        """H1: every scalar field captured by serialize_course must be
        reverted on restore, not just title/description/is_*.
        """
        # Start with a rich v1 state.
        original_deadline = datetime.date(2030, 1, 1)
        self.course.deadline = original_deadline
        self.course.estimated_hours = Decimal("4.50")
        self.course.is_mandatory = True
        self.course.assigned_to_all = True
        self.course.course_type = "PD"
        self.course.save()

        ct = ContentType.objects.get_for_model(Course)
        v_original = (
            ContentRevision.all_objects
            .filter(content_type=ct, object_id=self.course.id)
            .order_by("-revision_number")
            .first()
            .revision_number
        )

        # Mutate every restorable scalar.
        self.course.deadline = datetime.date(2031, 6, 30)
        self.course.estimated_hours = Decimal("99.99")
        self.course.is_mandatory = False
        self.course.assigned_to_all = False
        self.course.course_type = "ACADEMIC"
        self.course.description = "mutated desc"
        self.course.save()

        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}"
            f"/revisions/{v_original}/restore/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        self.course.refresh_from_db()
        self.assertEqual(self.course.deadline, original_deadline)
        self.assertEqual(self.course.estimated_hours, Decimal("4.50"))
        self.assertTrue(self.course.is_mandatory)
        self.assertTrue(self.course.assigned_to_all)
        self.assertEqual(self.course.course_type, "PD")

    def test_restore_reapplies_content_ai_fks(self):
        """H1: maic_classroom_id / ai_chatbot_id must round-trip."""
        # Leave them null on v1 (the original state), then set them, then
        # restore — expect them to be cleared back to None.
        ct = ContentType.objects.get_for_model(Content)
        v_original = (
            ContentRevision.all_objects
            .filter(content_type=ct, object_id=self.content.id)
            .order_by("-revision_number")
            .first()
            .revision_number
        )

        # Mutate the AI FKs in-memory via update (skip FK real rows —
        # column type is UUID, a bare uuid4 is fine for the persistence
        # round-trip we care about).
        import uuid
        fake_classroom_id = uuid.uuid4()
        Content.all_objects.filter(pk=self.content.pk).update(
            maic_classroom_id=fake_classroom_id,
        )
        # Trigger a save so the signal captures the new snapshot.
        self.content.refresh_from_db()
        self.content.title = "touched"
        self.content.save()

        self.assertEqual(
            Content.all_objects.get(pk=self.content.pk).maic_classroom_id,
            fake_classroom_id,
        )

        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.post(
            f"/api/v1/admin/contents/{self.content.id}"
            f"/revisions/{v_original}/restore/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        self.content.refresh_from_db()
        self.assertIsNone(self.content.maic_classroom_id)

    def test_restore_reverts_assigned_teachers(self):
        """L1: assigned_teachers M2M must be captured and restorable."""
        t1 = _make_teacher(self.tenant, "t1@demo.test")
        t2 = _make_teacher(self.tenant, "t2@demo.test")
        # v-original: only t1 assigned.
        self.course.assigned_teachers.set([t1])
        self.course.title = self.course.title + " snap"
        self.course.save()

        ct = ContentType.objects.get_for_model(Course)
        v_with_t1 = (
            ContentRevision.all_objects
            .filter(content_type=ct, object_id=self.course.id)
            .order_by("-revision_number")
            .first()
            .revision_number
        )
        # Sanity — snapshot should contain t1's id.
        rev = ContentRevision.all_objects.get(
            content_type=ct,
            object_id=self.course.id,
            revision_number=v_with_t1,
        )
        self.assertIn(str(t1.id), rev.snapshot_json.get("assigned_teachers", []))

        # Mutate: swap to t2 only.
        self.course.assigned_teachers.set([t2])
        self.course.title = self.course.title + " x"
        self.course.save()
        self.assertEqual(
            set(self.course.assigned_teachers.values_list("id", flat=True)),
            {t2.id},
        )

        # Restore.
        self._login("demo.lms.com", "admin@demo.test")
        resp = self.client.post(
            f"/api/v1/admin/courses/{self.course.id}"
            f"/revisions/{v_with_t1}/restore/"
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        self.course.refresh_from_db()
        self.assertEqual(
            set(self.course.assigned_teachers.values_list("id", flat=True)),
            {t1.id},
            "Restore should revert assigned_teachers to v-original set",
        )


# ---------------------------------------------------------------------------
# M1 concurrency regression — needs real threaded transactions.
# ---------------------------------------------------------------------------

class VersioningConcurrencyTests(TransactionTestCase):
    """Regression for the revision_number race on concurrent saves (M1).

    Uses TransactionTestCase because TestCase wraps each test in a single
    outer transaction which would defeat the point.
    """

    def test_concurrent_saves_both_get_revisions(self):
        tenant = _make_tenant("conc")
        admin = _make_admin(tenant, "admin@conc.test")
        course = Course.objects.create(
            tenant=tenant,
            title="Race",
            description="d",
            created_by=admin,
        )
        ct = ContentType.objects.get_for_model(Course)
        # Baseline count after create (at least 1).
        baseline = ContentRevision.all_objects.filter(
            content_type=ct, object_id=course.id
        ).count()

        errors: list = []

        def _worker(new_title: str):
            try:
                # Each thread needs its own DB connection and must close
                # it when done (Django test TX handling).
                c = Course.all_objects.get(pk=course.id)
                c.title = new_title
                c.save()
            except Exception as exc:  # pragma: no cover - diagnostics
                errors.append(exc)
            finally:
                connections.close_all()

        t1 = threading.Thread(target=_worker, args=("R1",))
        t2 = threading.Thread(target=_worker, args=("R2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [], f"Worker errors: {errors}")

        # Both concurrent saves must have produced a revision row — no
        # silent drops.
        added = (
            ContentRevision.all_objects
            .filter(content_type=ct, object_id=course.id)
            .count()
            - baseline
        )
        self.assertEqual(
            added,
            2,
            "Both concurrent saves should produce one revision each",
        )

        # And the numbers assigned must be distinct & contiguous off the
        # baseline max.
        nums = list(
            ContentRevision.all_objects
            .filter(content_type=ct, object_id=course.id)
            .order_by("revision_number")
            .values_list("revision_number", flat=True)
        )
        self.assertEqual(len(nums), len(set(nums)), "revision_numbers must be unique")
        # Last two numbers must be the baseline+1, baseline+2 pair.
        self.assertEqual(nums[-2:], [baseline + 1, baseline + 2])


# ---------------------------------------------------------------------------
# L2 — tenant=None log emission
# ---------------------------------------------------------------------------

class VersioningTenantNoneLoggingTests(TestCase):
    def test_missing_tenant_emits_warning(self):
        """L2: the signal logs a warning instead of silently dropping."""
        # Build a Course-like dummy instance the signal can inspect.
        # Using the real signal path via a Course stub with no tenant.
        from apps.courses import versioning_signals as vs

        class _Stub:
            pk = "00000000-0000-0000-0000-000000000000"
            tenant = None
            course = None
            module = None

        with self.assertLogs(vs.logger, level="WARNING") as cm:
            vs.capture_revision(
                sender=type("Fake", (), {"__name__": "Fake"}),
                instance=_Stub(),
                created=True,
            )
        self.assertTrue(
            any("tenant_id=None" in line for line in cm.output),
            f"Expected tenant_id=None warning, got: {cm.output}",
        )
