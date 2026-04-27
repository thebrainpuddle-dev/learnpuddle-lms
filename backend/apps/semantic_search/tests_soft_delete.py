"""
Tests for TASK-057b — Purge embeddings on SoftDeleteMixin.soft_delete().

Covers (≥5 tests):
  1.  test_soft_delete_course_purges_embeddings
        — Course with 3 chunks → soft_delete → 0 remaining.
  2.  test_soft_delete_module_purges_embeddings
        — Module with 2 chunks → soft_delete → 0 remaining.
  3.  test_soft_delete_content_purges_embeddings
        — Content with content + transcript chunks → soft_delete → 0 remaining.
  4.  test_hard_delete_still_works
        — Regression: hard-delete via post_delete still purges embedding rows.
  5.  test_cross_tenant_soft_delete_doesnt_touch_other_tenant_embeddings
        — Soft-deleting course in tenant 1 leaves tenant 2's chunks intact.
  6.  test_soft_delete_course_cascades_to_modules_and_contents
        — Belt-and-braces: course soft_delete purges module + content + transcript rows.
"""

from __future__ import annotations

from django.test import TestCase

from apps.tenants.models import Tenant
from apps.semantic_search.models import (
    EmbeddingChunk,
    SOURCE_TYPE_CONTENT,
    SOURCE_TYPE_COURSE,
    SOURCE_TYPE_MODULE,
    SOURCE_TYPE_TRANSCRIPT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant(name: str, subdomain: str) -> Tenant:
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.test",
        is_active=True,
    )


def _make_course(tenant, title: str = "Course"):
    from apps.courses.models import Course
    slug = title.lower().replace(" ", "-")
    return Course.objects.create(
        tenant=tenant,
        title=title,
        slug=slug,
        description="Test description",
    )


def _make_module(course, title: str = "Module"):
    from apps.courses.models import Module
    return Module.objects.create(course=course, title=title, order=0)


def _make_content(module, title: str = "Content"):
    from apps.courses.models import Content
    return Content.objects.create(
        module=module,
        title=title,
        content_type="TEXT",
        text_content="body text",
    )


def _seed_chunk(tenant, source_type: str, source_id, chunk_index: int = 0) -> EmbeddingChunk:
    return EmbeddingChunk.all_objects.create(
        tenant=tenant,
        source_type=source_type,
        source_id=source_id,
        chunk_index=chunk_index,
        text=f"chunk-{chunk_index}",
        text_hash=("a" * 63 + str(chunk_index % 10)),
        model="stub",
        provider="stub",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSoftDeletePurgesEmbeddings(TestCase):
    """Soft-deleting a Course/Module/Content removes its EmbeddingChunk rows."""

    def setUp(self):
        self.tenant = _make_tenant("Purge School", "purge")
        self.course = _make_course(self.tenant, "Purge Course")
        self.module = _make_module(self.course)
        self.content = _make_content(self.module)

    # ------------------------------------------------------------------
    # 1. Course soft-delete
    # ------------------------------------------------------------------

    def test_soft_delete_course_purges_embeddings(self):
        """Soft-deleting a Course removes exactly its 3 course-type chunks."""
        _seed_chunk(self.tenant, SOURCE_TYPE_COURSE, self.course.id, 0)
        _seed_chunk(self.tenant, SOURCE_TYPE_COURSE, self.course.id, 1)
        _seed_chunk(self.tenant, SOURCE_TYPE_COURSE, self.course.id, 2)

        before = EmbeddingChunk.all_objects.filter(
            tenant=self.tenant,
            source_type=SOURCE_TYPE_COURSE,
            source_id=self.course.id,
        ).count()
        self.assertEqual(before, 3)

        self.course.soft_delete()

        after = EmbeddingChunk.all_objects.filter(
            tenant=self.tenant,
            source_type=SOURCE_TYPE_COURSE,
            source_id=self.course.id,
        ).count()
        self.assertEqual(after, 0)

    # ------------------------------------------------------------------
    # 2. Module soft-delete
    # ------------------------------------------------------------------

    def test_soft_delete_module_purges_embeddings(self):
        """Soft-deleting a Module removes its module-type chunks."""
        _seed_chunk(self.tenant, SOURCE_TYPE_MODULE, self.module.id, 0)
        _seed_chunk(self.tenant, SOURCE_TYPE_MODULE, self.module.id, 1)

        before = EmbeddingChunk.all_objects.filter(
            tenant=self.tenant,
            source_type=SOURCE_TYPE_MODULE,
            source_id=self.module.id,
        ).count()
        self.assertEqual(before, 2)

        self.module.soft_delete()

        after = EmbeddingChunk.all_objects.filter(
            tenant=self.tenant,
            source_type=SOURCE_TYPE_MODULE,
            source_id=self.module.id,
        ).count()
        self.assertEqual(after, 0)

    # ------------------------------------------------------------------
    # 3. Content soft-delete
    # ------------------------------------------------------------------

    def test_soft_delete_content_purges_embeddings(self):
        """Soft-deleting a Content removes content AND transcript chunks."""
        _seed_chunk(self.tenant, SOURCE_TYPE_CONTENT, self.content.id, 0)
        _seed_chunk(self.tenant, SOURCE_TYPE_TRANSCRIPT, self.content.id, 0)
        _seed_chunk(self.tenant, SOURCE_TYPE_TRANSCRIPT, self.content.id, 1)

        before = EmbeddingChunk.all_objects.filter(
            tenant=self.tenant,
            source_id=self.content.id,
        ).count()
        self.assertEqual(before, 3)

        self.content.soft_delete()

        after = EmbeddingChunk.all_objects.filter(
            tenant=self.tenant,
            source_id=self.content.id,
        ).count()
        self.assertEqual(after, 0)

    # ------------------------------------------------------------------
    # 4. Hard delete regression
    # ------------------------------------------------------------------

    def test_hard_delete_still_works(self):
        """
        Regression: hard-deleting Content via the ORM still triggers
        post_delete and purges embedding rows.
        """
        from apps.courses.models import Content

        content2 = _make_content(self.module, "Hard Delete Content")
        _seed_chunk(self.tenant, SOURCE_TYPE_CONTENT, content2.id, 0)
        _seed_chunk(self.tenant, SOURCE_TYPE_TRANSCRIPT, content2.id, 0)

        before = EmbeddingChunk.all_objects.filter(
            source_id=content2.id
        ).count()
        self.assertEqual(before, 2)

        # Hard delete — bypass soft-delete so post_delete fires.
        Content.all_objects.filter(id=content2.id).delete()

        after = EmbeddingChunk.all_objects.filter(
            source_id=content2.id
        ).count()
        self.assertEqual(after, 0)

    # ------------------------------------------------------------------
    # 5. Cross-tenant isolation
    # ------------------------------------------------------------------

    def test_cross_tenant_soft_delete_doesnt_touch_other_tenant_embeddings(self):
        """
        Soft-deleting a Course in tenant 1 must NOT touch embedding rows
        that belong to tenant 2 — even if both use the same source_id UUID.
        """
        tenant2 = _make_tenant("Other School", "other")

        # Seed course-level chunk for tenant 1.
        _seed_chunk(self.tenant, SOURCE_TYPE_COURSE, self.course.id, 0)

        # Seed a chunk for tenant 2 using the SAME source_id UUID to
        # prove cross-tenant isolation.
        _seed_chunk(tenant2, SOURCE_TYPE_COURSE, self.course.id, 0)

        # Verify both exist before soft-delete.
        t1_before = EmbeddingChunk.all_objects.filter(
            tenant=self.tenant,
            source_type=SOURCE_TYPE_COURSE,
            source_id=self.course.id,
        ).count()
        t2_before = EmbeddingChunk.all_objects.filter(
            tenant=tenant2,
            source_type=SOURCE_TYPE_COURSE,
            source_id=self.course.id,
        ).count()
        self.assertEqual(t1_before, 1)
        self.assertEqual(t2_before, 1)

        # Soft-delete the course in tenant 1.
        self.course.soft_delete()

        # Tenant 1's chunk is gone.
        t1_after = EmbeddingChunk.all_objects.filter(
            tenant=self.tenant,
            source_type=SOURCE_TYPE_COURSE,
            source_id=self.course.id,
        ).count()
        self.assertEqual(t1_after, 0)

        # Tenant 2's chunk is untouched.
        t2_after = EmbeddingChunk.all_objects.filter(
            tenant=tenant2,
            source_type=SOURCE_TYPE_COURSE,
            source_id=self.course.id,
        ).count()
        self.assertEqual(t2_after, 1)

    # ------------------------------------------------------------------
    # 6. Cascade: course soft-delete also purges module + content chunks
    # ------------------------------------------------------------------

    def test_soft_delete_course_cascades_to_modules_and_contents(self):
        """
        course.soft_delete() must cascade to purge module, content AND
        transcript chunks belonging to that course's children.
        """
        # Seed one chunk per source type.
        _seed_chunk(self.tenant, SOURCE_TYPE_COURSE, self.course.id)
        _seed_chunk(self.tenant, SOURCE_TYPE_MODULE, self.module.id)
        _seed_chunk(self.tenant, SOURCE_TYPE_CONTENT, self.content.id)
        _seed_chunk(self.tenant, SOURCE_TYPE_TRANSCRIPT, self.content.id)

        total_before = EmbeddingChunk.all_objects.filter(tenant=self.tenant).count()
        self.assertEqual(total_before, 4)

        self.course.soft_delete()

        total_after = EmbeddingChunk.all_objects.filter(tenant=self.tenant).count()
        self.assertEqual(total_after, 0)
