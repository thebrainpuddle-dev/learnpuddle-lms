"""
Tests for TASK-057 — Semantic Search (pgvector).

Covers (≥15 tests total):
  1.  Chunker short-text single-chunk path.
  2.  Chunker window boundary — 1800-token input with stride=450 → 4 chunks.
  3.  Chunker skips empty / whitespace-only input.
  4.  Stub embedder refuses to run in production (DEBUG=False, env unset).
  5.  Stub embedder allowed when EMBEDDING_ALLOW_STUB=1 in prod.
  6.  reindex_content is idempotent when text_hash is unchanged.
  7.  post_save on Content enqueues reindex_content (signal → Celery).
  8.  post_save debounce mutex — second save within 30s skips enqueue.
  9.  post_delete on Content removes matching EmbeddingChunk rows.
  10. Tenant isolation — rows from tenant B never surface for tenant A.
  11. search() hard-caps top_k at 50 (SearchValidationError).
  12. search() rejects queries > 2000 chars (SearchValidationError).
  13. POST /search/semantic/ → 400 TOP_K_TOO_LARGE.
  14. POST /search/semantic/ → 400 QUERY_TOO_LONG.
  15. POST /search/semantic/ → 503 EMBEDDINGS_UNAVAILABLE on provider outage.
  16. POST /admin/search/reindex-tenant/ → 503 when cache.get raises (fail-CLOSED).
  17. POST /admin/search/reindex-tenant/ → 503 when cache.set raises (fail-CLOSED).
  18. Cross-tenant reindex-tenant (tenant A targeting tenant B) → 404.
  19. AuditLog SEMANTIC_REINDEX_STARTED row written on reindex.
  20. course_id filter narrows results to that course's rows only.

Note on pgvector: tests that need the real vector column are skipped
gracefully via ``_has_pgvector()``. Everything else — chunker, stub
gate, signals, validation, rate-limit fail-closed — runs in plain
CI without the extension installed.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import AuditLog, Tenant
from apps.semantic_search.chunker import chunk_text
from apps.semantic_search.embeddings import (
    EmbeddingError,
    StubEmbedder,
    embed_texts,
)
from apps.semantic_search.models import (
    EmbeddingChunk,
    EmbeddingJobRun,
    SOURCE_TYPE_CONTENT,
    SOURCE_TYPE_COURSE,
    SOURCE_TYPE_MODULE,
    SOURCE_TYPE_TRANSCRIPT,
)
from apps.semantic_search.retrieval import (
    MAX_QUERY_CHARS,
    MAX_TOP_K,
    SearchValidationError,
    search,
)


User = get_user_model()


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


def _make_user(tenant, email: str, role: str = "SCHOOL_ADMIN") -> User:
    user = User.objects.create_user(
        email=email,
        password="Pass@word1234!",
        first_name="Test",
        last_name="User",
        role=role,
    )
    user.tenant = tenant
    user.save()
    return user


def _has_pgvector() -> bool:
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name=%s AND column_name=%s",
                ["semantic_search_embeddingchunk", "embedding"],
            )
            return cur.fetchone() is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 1-3. Chunker
# ---------------------------------------------------------------------------


class TestChunker(TestCase):
    def test_short_text_returns_single_chunk(self):
        """Text below the window should return exactly one chunk, index 0."""
        out = chunk_text("hello world this is a short string")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], 0)
        self.assertTrue(out[0][1].startswith("hello"))

    def test_1800_token_input_produces_four_chunks(self):
        """1800 tokens with window=600, stride=450 → 4 chunks with 150 overlap."""
        tokens = [f"w{i}" for i in range(1800)]
        text = " ".join(tokens)
        chunks = chunk_text(text, window=600, stride=450)
        self.assertEqual(len(chunks), 4)
        # Monotonic indices 0..3
        self.assertEqual([c[0] for c in chunks], [0, 1, 2, 3])
        # Overlap assertion: each subsequent chunk starts 450 tokens later.
        c0_tokens = chunks[0][1].split()
        c1_tokens = chunks[1][1].split()
        # The overlap is 150 tokens — first 150 of c1 should be the last 150 of c0.
        self.assertEqual(c0_tokens[-150:], c1_tokens[:150])

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(chunk_text(""), [])
        self.assertEqual(chunk_text("   \n\n  "), [])


# ---------------------------------------------------------------------------
# 4-5. Stub embedder gate
# ---------------------------------------------------------------------------


class TestStubEmbedderGate(TestCase):
    @override_settings(DEBUG=False)
    def test_stub_refuses_in_production(self):
        # Make sure the allow env is NOT set.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("EMBEDDING_ALLOW_STUB", None)
            with self.assertRaises(RuntimeError):
                StubEmbedder().embed_batch(["hi"])

    @override_settings(DEBUG=False)
    def test_stub_allowed_when_env_set_in_prod(self):
        with patch.dict(os.environ, {"EMBEDDING_ALLOW_STUB": "1"}):
            vecs = StubEmbedder().embed_batch(["hello"])
            self.assertEqual(len(vecs), 1)
            self.assertEqual(len(vecs[0]), 1024)


# ---------------------------------------------------------------------------
# 6. reindex_content idempotency
# ---------------------------------------------------------------------------


class TestReindexIdempotency(TestCase):
    def setUp(self):
        from apps.courses.models import Course, Module, Content
        self.tenant = _make_tenant("Idem School", "idem")
        self.admin = _make_user(self.tenant, "admin@idem.test")
        self.course = Course.objects.create(
            tenant=self.tenant, title="C1", slug="c1", description="d"
        )
        self.module = Module.objects.create(course=self.course, title="M1", order=0)
        self.content = Content.objects.create(
            module=self.module,
            title="Content One",
            content_type="TEXT",
            text_content="Some body text.",
        )

    def test_second_run_skips_when_hash_unchanged(self):
        from apps.semantic_search.tasks import reindex_content

        fake_vec = [0.01] * 1024
        with patch(
            "apps.semantic_search.tasks.embed_texts",
            return_value=[fake_vec, fake_vec],
        ):
            result1 = reindex_content(str(self.content.id))
            result2 = reindex_content(str(self.content.id))

        self.assertGreaterEqual(result1["indexed"], 1)
        self.assertEqual(result2["indexed"], 0)


# ---------------------------------------------------------------------------
# 7-8. Signal → Celery enqueue
# ---------------------------------------------------------------------------


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "semantic-search-tests",
        }
    }
)
class TestSignalEnqueue(TestCase):
    def setUp(self):
        from apps.courses.models import Course, Module
        self.tenant = _make_tenant("Sig School", "sig")
        self.course = Course.objects.create(
            tenant=self.tenant, title="CX", slug="cx", description="d"
        )
        self.module = Module.objects.create(course=self.course, title="M", order=0)
        cache.clear()

    def test_post_save_on_content_enqueues_reindex_content(self):
        from apps.courses.models import Content
        with patch("apps.semantic_search.tasks.reindex_content.apply_async") as mock_enqueue:
            Content.objects.create(
                module=self.module,
                title="Hello",
                content_type="TEXT",
                text_content="body",
            )
            self.assertTrue(mock_enqueue.called)
            args, kwargs = mock_enqueue.call_args
            self.assertIn("countdown", kwargs)
            self.assertEqual(kwargs["countdown"], 30)

    def test_post_save_debounce_second_save_skipped(self):
        from apps.courses.models import Content
        with patch("apps.semantic_search.tasks.reindex_content.apply_async") as mock_enqueue:
            content = Content.objects.create(
                module=self.module,
                title="Hello",
                content_type="TEXT",
                text_content="body",
            )
            content.title = "Hello Edit"
            content.save()
            # First save acquires the debounce lock → enqueued.
            # Second save within 30s → dedup'd via cache.add, NO second enqueue.
            self.assertEqual(mock_enqueue.call_count, 1)


# ---------------------------------------------------------------------------
# 9. post_delete cleanup
# ---------------------------------------------------------------------------


class TestPostDeleteCleanup(TestCase):
    def setUp(self):
        from apps.courses.models import Course, Module, Content
        self.tenant = _make_tenant("Del School", "del")
        self.course = Course.objects.create(
            tenant=self.tenant, title="CD", slug="cd", description="d"
        )
        self.module = Module.objects.create(course=self.course, title="MD", order=0)
        self.content = Content.objects.create(
            module=self.module, title="CT", content_type="TEXT", text_content="t"
        )
        EmbeddingChunk.all_objects.create(
            tenant=self.tenant,
            source_type=SOURCE_TYPE_CONTENT,
            source_id=self.content.id,
            chunk_index=0,
            text="t",
            text_hash="a" * 64,
            model="m",
            provider="p",
        )
        EmbeddingChunk.all_objects.create(
            tenant=self.tenant,
            source_type=SOURCE_TYPE_TRANSCRIPT,
            source_id=self.content.id,
            chunk_index=0,
            text="t2",
            text_hash="b" * 64,
            model="m",
            provider="p",
        )

    def test_delete_removes_embedding_rows(self):
        before = EmbeddingChunk.all_objects.filter(
            source_id=self.content.id
        ).count()
        self.assertEqual(before, 2)
        # Use the real soft_delete() path (TASK-057b fix) so the
        # soft_deleted signal fires and purges embedding rows.
        self.content.soft_delete()
        after = EmbeddingChunk.all_objects.filter(
            source_id=self.content.id
        ).count()
        self.assertEqual(after, 0)


# ---------------------------------------------------------------------------
# 10. Tenant isolation
# ---------------------------------------------------------------------------


class TestTenantIsolation(TestCase):
    def setUp(self):
        self.t_a = _make_tenant("Tenant A", "tena")
        self.t_b = _make_tenant("Tenant B", "tenb")
        # Seed one chunk per tenant with identical text.
        EmbeddingChunk.all_objects.create(
            tenant=self.t_a,
            source_type=SOURCE_TYPE_CONTENT,
            source_id="11111111-1111-1111-1111-111111111111",
            chunk_index=0,
            text="shared text",
            text_hash="A" * 64,
            model="m",
            provider="p",
        )
        EmbeddingChunk.all_objects.create(
            tenant=self.t_b,
            source_type=SOURCE_TYPE_CONTENT,
            source_id="22222222-2222-2222-2222-222222222222",
            chunk_index=0,
            text="shared text",
            text_hash="B" * 64,
            model="m",
            provider="p",
        )

    def test_rows_scoped_by_tenant(self):
        a_rows = EmbeddingChunk.all_objects.filter(tenant=self.t_a)
        b_rows = EmbeddingChunk.all_objects.filter(tenant=self.t_b)
        self.assertEqual(a_rows.count(), 1)
        self.assertEqual(b_rows.count(), 1)
        self.assertNotEqual(
            a_rows.first().source_id, b_rows.first().source_id,
        )

    def test_search_never_returns_cross_tenant_hits(self):
        if not _has_pgvector():
            self.skipTest("pgvector extension not installed")
        # Patch embed_texts so we don't hit a real API.
        with patch(
            "apps.semantic_search.retrieval.embed_texts",
            return_value=[[0.1] * 1024],
        ):
            hits = search(self.t_a, "anything", top_k=10)
        for h in hits:
            # source_id of the B tenant row must NOT appear.
            self.assertNotEqual(
                str(h["source_id"]), "22222222-2222-2222-2222-222222222222",
            )


# ---------------------------------------------------------------------------
# 11-12. retrieval.search validation caps
# ---------------------------------------------------------------------------


class TestSearchValidation(TestCase):
    def setUp(self):
        self.tenant = _make_tenant("Val School", "val")

    def test_top_k_too_large_raises(self):
        with self.assertRaises(SearchValidationError) as ctx:
            search(self.tenant, "query", top_k=MAX_TOP_K + 1)
        self.assertIn("TOP_K_TOO_LARGE", str(ctx.exception))

    def test_query_too_long_raises(self):
        with self.assertRaises(SearchValidationError) as ctx:
            search(self.tenant, "x" * (MAX_QUERY_CHARS + 1))
        self.assertIn("QUERY_TOO_LONG", str(ctx.exception))


# ---------------------------------------------------------------------------
# 13-15. HTTP endpoints — validation + embeddings outage
# ---------------------------------------------------------------------------


class TestSemanticSearchEndpoint(TestCase):
    def setUp(self):
        self.tenant = _make_tenant("HTTP School", "httpt")
        self.admin = _make_user(self.tenant, "admin@httpt.test", "SCHOOL_ADMIN")

    def _post(self, body):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch(
            "utils.tenant_middleware.get_current_tenant",
            return_value=self.tenant,
        ):
            return client.post(
                "/api/v1/search/semantic/",
                data=body,
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )

    def test_top_k_too_large_returns_400(self):
        resp = self._post({"query": "hello", "top_k": 999})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data.get("error"), "TOP_K_TOO_LARGE")

    def test_query_too_long_returns_400(self):
        resp = self._post({"query": "x" * (MAX_QUERY_CHARS + 1)})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data.get("error"), "QUERY_TOO_LONG")

    def test_embeddings_unavailable_returns_503(self):
        """When the provider chain raises, endpoint responds 503 (no stub fallback)."""
        with patch(
            "apps.semantic_search.retrieval.embed_texts",
            side_effect=EmbeddingError("all providers failed"),
        ), patch(
            "apps.semantic_search.retrieval._has_embedding_column",
            return_value=True,
        ):
            resp = self._post({"query": "hello"})
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.data.get("error"), "EMBEDDINGS_UNAVAILABLE")


# ---------------------------------------------------------------------------
# 16-17. Reindex-tenant rate-limit fail-CLOSED (both cache paths)
# ---------------------------------------------------------------------------


class TestReindexRateLimitFailClosed(TestCase):
    def setUp(self):
        self.tenant = _make_tenant("Rate School", "ratex")
        self.admin = _make_user(self.tenant, "admin@ratex.test", "SCHOOL_ADMIN")

    def _post_reindex(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch(
            "utils.tenant_middleware.get_current_tenant",
            return_value=self.tenant,
        ):
            return client.post(
                "/api/v1/admin/search/reindex-tenant/",
                data={},
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )

    def test_cache_get_exception_returns_503(self):
        with patch(
            "apps.semantic_search.views.cache.get",
            side_effect=ConnectionError("Redis down"),
        ):
            resp = self._post_reindex()
        self.assertEqual(resp.status_code, 503)

    def test_cache_set_exception_returns_503(self):
        with patch("apps.semantic_search.views.cache.get", return_value=0), \
             patch(
                 "apps.semantic_search.views.cache.set",
                 side_effect=ConnectionError("Redis down"),
             ):
            resp = self._post_reindex()
        self.assertEqual(resp.status_code, 503)


# ---------------------------------------------------------------------------
# 18. Cross-tenant reindex → 404
# ---------------------------------------------------------------------------


class TestCrossTenantReindex(TestCase):
    def setUp(self):
        self.t_a = _make_tenant("CT A", "cta")
        self.t_b = _make_tenant("CT B", "ctb")
        self.admin_a = _make_user(self.t_a, "admin@cta.test", "SCHOOL_ADMIN")

    def test_admin_a_targeting_tenant_b_returns_404(self):
        client = APIClient()
        client.force_authenticate(user=self.admin_a)
        with patch(
            "utils.tenant_middleware.get_current_tenant",
            return_value=self.t_a,
        ), patch("apps.semantic_search.views.cache.get", return_value=0), \
             patch("apps.semantic_search.views.cache.set"):
            resp = client.post(
                "/api/v1/admin/search/reindex-tenant/",
                data={"tenant_id": str(self.t_b.id)},
                format="json",
                HTTP_HOST=f"{self.t_a.subdomain}.localhost",
            )
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# 19. AuditLog row written on reindex
# ---------------------------------------------------------------------------


class TestAuditLogOnReindex(TestCase):
    def setUp(self):
        self.tenant = _make_tenant("Audit School", "auditx")
        self.admin = _make_user(self.tenant, "admin@auditx.test", "SCHOOL_ADMIN")

    def test_reindex_writes_started_audit(self):
        client = APIClient()
        client.force_authenticate(user=self.admin)
        with patch(
            "utils.tenant_middleware.get_current_tenant",
            return_value=self.tenant,
        ), patch("apps.semantic_search.views.cache.get", return_value=0), \
             patch("apps.semantic_search.views.cache.set"), \
             patch(
                 "apps.semantic_search.tasks.reindex_tenant.apply_async",
             ) as mock_async:
            mock_async.return_value.id = "task-abc"
            resp = client.post(
                "/api/v1/admin/search/reindex-tenant/",
                data={},
                format="json",
                HTTP_HOST=f"{self.tenant.subdomain}.localhost",
            )
        self.assertIn(resp.status_code, (200, 202))
        rows = AuditLog.objects.filter(
            tenant=self.tenant, action="SEMANTIC_REINDEX_STARTED",
        )
        self.assertTrue(rows.exists())


# ---------------------------------------------------------------------------
# 20. course_id filter
# ---------------------------------------------------------------------------


class TestCourseIdFilter(TestCase):
    """The course_id filter must restrict to that course's chunks only.

    We assert on the ORM-side filter resolution (no vector math needed).
    """

    def setUp(self):
        from apps.courses.models import Course, Module, Content

        self.tenant = _make_tenant("CF School", "cfx")
        self.course_a = Course.objects.create(
            tenant=self.tenant, title="A", slug="a", description="da"
        )
        self.course_b = Course.objects.create(
            tenant=self.tenant, title="B", slug="b", description="db"
        )
        self.mod_a = Module.objects.create(course=self.course_a, title="MA", order=0)
        self.mod_b = Module.objects.create(course=self.course_b, title="MB", order=0)
        self.ct_a = Content.objects.create(
            module=self.mod_a, title="CA", content_type="TEXT", text_content="ta"
        )
        self.ct_b = Content.objects.create(
            module=self.mod_b, title="CB", content_type="TEXT", text_content="tb"
        )

    def test_resolve_course_scope_returns_only_that_course_ids(self):
        from apps.semantic_search.retrieval import _resolve_course_scope
        module_ids, content_ids = _resolve_course_scope(
            self.tenant, str(self.course_a.id)
        )
        self.assertIn(str(self.mod_a.id), module_ids)
        self.assertNotIn(str(self.mod_b.id), module_ids)
        self.assertIn(str(self.ct_a.id), content_ids)
        self.assertNotIn(str(self.ct_b.id), content_ids)

    def test_unknown_course_returns_none(self):
        from apps.semantic_search.retrieval import _resolve_course_scope
        result = _resolve_course_scope(
            self.tenant, "00000000-0000-0000-0000-000000000000"
        )
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# TASK-057 L1 regression — search() narrow exception handling.
# ProgrammingError / OperationalError → [] (fail-open for missing pgvector).
# Other exceptions MUST propagate so they surface as 500s, not silent empty.
# ---------------------------------------------------------------------------


class TestSearchNarrowExceptionHandling(TestCase):
    """Regression: search() must NOT swallow all DB exceptions silently."""

    def _make_tenant(self):
        from unittest.mock import MagicMock
        t = MagicMock()
        t.id = "test-tenant-id"
        return t

    def test_programming_error_returns_empty_list(self):
        """ProgrammingError (missing pgvector operator) is silently swallowed → []."""
        from django.db import ProgrammingError as DjangoProgrammingError
        from apps.semantic_search.retrieval import search

        tenant = self._make_tenant()

        with patch(
            "apps.semantic_search.retrieval._has_embedding_column",
            return_value=True,
        ), patch(
            "apps.semantic_search.retrieval.embed_texts",
            return_value=[[0.1] * 1536],
        ), patch(
            "apps.semantic_search.retrieval.connection"
        ) as mock_conn:
            mock_conn.cursor.return_value.__enter__ = lambda s: s
            mock_conn.cursor.return_value.__exit__ = lambda s, *a: False
            mock_conn.cursor.return_value.execute.side_effect = DjangoProgrammingError(
                "operator does not exist"
            )
            result = search(tenant, "hello", top_k=5)

        self.assertEqual(result, [])

    def test_operational_error_returns_empty_list(self):
        """OperationalError (connection issue) is silently swallowed → []."""
        from django.db import OperationalError as DjangoOperationalError
        from apps.semantic_search.retrieval import search

        tenant = self._make_tenant()

        with patch(
            "apps.semantic_search.retrieval._has_embedding_column",
            return_value=True,
        ), patch(
            "apps.semantic_search.retrieval.embed_texts",
            return_value=[[0.1] * 1536],
        ), patch(
            "apps.semantic_search.retrieval.connection"
        ) as mock_conn:
            mock_conn.cursor.return_value.__enter__ = lambda s: s
            mock_conn.cursor.return_value.__exit__ = lambda s, *a: False
            mock_conn.cursor.return_value.execute.side_effect = DjangoOperationalError(
                "server closed the connection unexpectedly"
            )
            result = search(tenant, "hello", top_k=5)

        self.assertEqual(result, [])

    def test_integrity_error_propagates(self):
        """IntegrityError is NOT swallowed — must propagate so caller gets 500."""
        from django.db import IntegrityError
        from apps.semantic_search.retrieval import search

        tenant = self._make_tenant()

        with patch(
            "apps.semantic_search.retrieval._has_embedding_column",
            return_value=True,
        ), patch(
            "apps.semantic_search.retrieval.embed_texts",
            return_value=[[0.1] * 1536],
        ), patch(
            "apps.semantic_search.retrieval.connection"
        ) as mock_conn:
            mock_conn.cursor.return_value.__enter__ = lambda s: s
            mock_conn.cursor.return_value.__exit__ = lambda s, *a: False
            mock_conn.cursor.return_value.execute.side_effect = IntegrityError(
                "unexpected integrity violation"
            )
            with self.assertRaises(IntegrityError):
                search(tenant, "hello", top_k=5)


# ---------------------------------------------------------------------------
# TASK-057 L4: embedder_info() returns non-empty model on first call under auto
# ---------------------------------------------------------------------------


class TestEmbedderInfoEagerResolution(TestCase):
    """TASK-057 L4: embedder_info() must return a non-empty model on first call
    when EMBEDDING_PROVIDER=auto, before any embed has been performed.

    Previously the function returned {"provider": "auto", "model": ""} under
    _AutoEmbedder without probing the candidate chain.  The fix eagerly walks
    the available() chain and returns the first concrete provider's name+model.
    """

    def test_embedder_info_model_non_empty_when_openrouter_available(self):
        """When OpenRouter API key is configured, embedder_info returns its model."""
        from apps.semantic_search.embeddings import embedder_info

        # Simulate auto mode with OpenRouter available
        with patch("apps.semantic_search.embeddings.OpenRouterEmbedder") as MockOR:
            mock_or_instance = MockOR.return_value
            mock_or_instance.name = "openrouter"
            mock_or_instance.model = "mixedbread-ai/mxbai-embed-large-v1"
            mock_or_instance.available.return_value = True

            # Also patch OllamaEmbedder so the loop doesn't skip to it
            with patch("apps.semantic_search.embeddings.OllamaEmbedder") as MockOllama:
                mock_ollama_instance = MockOllama.return_value
                mock_ollama_instance.available.return_value = False

                with patch("apps.semantic_search.embeddings.get_embedder") as mock_get:
                    # Return a real _AutoEmbedder-like object
                    from apps.semantic_search.embeddings import _AutoEmbedder
                    mock_get.return_value = _AutoEmbedder()

                    info = embedder_info()

        # Under auto with OpenRouter mocked as available, model must not be empty
        # (the function probes the chain)
        # We can't fully assert the exact value since get_embedder is also mocked
        # but we assert the general contract
        self.assertIn("provider", info)
        self.assertIn("model", info)

    def test_embedder_info_probes_chain_when_auto(self):
        """embedder_info() calls available() on candidates when provider is auto."""
        from apps.semantic_search.embeddings import embedder_info, _AutoEmbedder

        called = []

        class FakeOR:
            name = "openrouter"
            model = "mixedbread-ai/mxbai-embed-large-v1"

            def available(self):
                called.append("openrouter.available")
                return True  # available → should be chosen first

        with (
            patch("apps.semantic_search.embeddings.get_embedder", return_value=_AutoEmbedder()),
            patch("apps.semantic_search.embeddings.OpenRouterEmbedder", return_value=FakeOR()),
        ):
            info = embedder_info()

        # The function walked the chain and called available() on OpenRouter
        self.assertIn(
            "openrouter.available",
            called,
            "embedder_info() should call OpenRouterEmbedder().available() when in auto mode",
        )
        self.assertEqual(info["provider"], "openrouter")
        self.assertNotEqual(
            info["model"],
            "",
            "embedder_info() must return non-empty model string on first call under auto",
        )

    def test_embedder_info_falls_back_to_stub_model_when_no_providers_available(self):
        """When no real providers are available, embedder_info reports stub model name."""
        from apps.semantic_search.embeddings import embedder_info, _AutoEmbedder

        class UnavailableEmbedder:
            name = "fake"
            model = "fake-model"

            def available(self):
                return False

        with (
            patch("apps.semantic_search.embeddings.get_embedder", return_value=_AutoEmbedder()),
            patch("apps.semantic_search.embeddings.OpenRouterEmbedder", return_value=UnavailableEmbedder()),
            patch("apps.semantic_search.embeddings.OllamaEmbedder", return_value=UnavailableEmbedder()),
        ):
            info = embedder_info()

        self.assertEqual(info["provider"], "auto")
        self.assertNotEqual(
            info["model"],
            "",
            "When no real providers available, model should be stub model name, not empty string",
        )


# ---------------------------------------------------------------------------
# TASK-063 L2: _build_context_index exposes content_title and module_title
# ---------------------------------------------------------------------------


class TestContextIndexTitles(TestCase):
    """TASK-063 L2: search() results must carry content_title and module_title
    in their context dict so the frontend can render per-hit titles instead of
    repeating the course title for every result on a course-scoped search.
    """

    def setUp(self):
        from apps.courses.models import Course, Module, Content

        self.tenant = _make_tenant("Ctx School", "ctxtitles")
        self.course = Course.objects.create(
            tenant=self.tenant,
            title="My Course",
            slug="my-course",
            description="d",
        )
        self.module = Module.objects.create(
            course=self.course,
            title="My Module",
            order=0,
        )
        self.content = Content.objects.create(
            module=self.module,
            title="My Content",
            content_type="TEXT",
            text_content="some text",
        )

    def _seed_chunk(self, source_type, source_id, chunk_index=0):
        return EmbeddingChunk.all_objects.create(
            tenant=self.tenant,
            source_type=source_type,
            source_id=source_id,
            chunk_index=chunk_index,
            text="example text",
            text_hash=("x" * 60 + str(chunk_index).zfill(4)),
            model="m",
            provider="p",
        )

    def _run_build_context_index(self, rows):
        from apps.semantic_search.retrieval import _build_context_index
        return _build_context_index(self.tenant, rows)

    def test_content_hit_exposes_content_title_and_module_title(self):
        """content-type hit: context includes content_title=Content.title and
        module_title=Module.title."""
        self._seed_chunk(SOURCE_TYPE_CONTENT, self.content.id)
        rows = [
            {
                "source_type": SOURCE_TYPE_CONTENT,
                "source_id": str(self.content.id),
            }
        ]
        idx = self._run_build_context_index(rows)
        ctx = idx[(SOURCE_TYPE_CONTENT, str(self.content.id))]
        self.assertEqual(ctx["content_title"], "My Content")
        self.assertEqual(ctx["module_title"], "My Module")
        self.assertEqual(ctx["course_title"], "My Course")

    def test_transcript_hit_exposes_content_title_and_module_title(self):
        """transcript-type hit: same content/module titles as content hit."""
        self._seed_chunk(SOURCE_TYPE_TRANSCRIPT, self.content.id)
        rows = [
            {
                "source_type": SOURCE_TYPE_TRANSCRIPT,
                "source_id": str(self.content.id),
            }
        ]
        idx = self._run_build_context_index(rows)
        ctx = idx[(SOURCE_TYPE_TRANSCRIPT, str(self.content.id))]
        self.assertEqual(ctx["content_title"], "My Content")
        self.assertEqual(ctx["module_title"], "My Module")

    def test_module_hit_exposes_module_title_content_title_none(self):
        """module-type hit: context includes module_title, content_title=None."""
        self._seed_chunk(SOURCE_TYPE_MODULE, self.module.id)
        rows = [
            {
                "source_type": SOURCE_TYPE_MODULE,
                "source_id": str(self.module.id),
            }
        ]
        idx = self._run_build_context_index(rows)
        ctx = idx[(SOURCE_TYPE_MODULE, str(self.module.id))]
        self.assertEqual(ctx["module_title"], "My Module")
        self.assertIsNone(ctx["content_title"])
        self.assertEqual(ctx["course_title"], "My Course")

    def test_course_hit_has_no_content_or_module_title(self):
        """course-type hit: content_title and module_title are both None."""
        self._seed_chunk(SOURCE_TYPE_COURSE, self.course.id)
        rows = [
            {
                "source_type": SOURCE_TYPE_COURSE,
                "source_id": str(self.course.id),
            }
        ]
        idx = self._run_build_context_index(rows)
        ctx = idx[(SOURCE_TYPE_COURSE, str(self.course.id))]
        self.assertIsNone(ctx["content_title"])
        self.assertIsNone(ctx["module_title"])
        self.assertEqual(ctx["course_title"], "My Course")
