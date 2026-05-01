# apps/courses/tests_chatbot_auto_ingest.py
"""
Unit tests for apps/courses/chatbot_auto_ingest.py.

Focus areas:
  1. _source_type_for_content — mapping content_type to source_type
  2. _create_knowledge_for_content — per-content-type skip/create logic
     * TASK-043: QUIZ content_type must be skipped (no knowledge record created)
     * TEXT, DOCUMENT, LINK, VIDEO, AI_CLASSROOM, CHATBOT — correct handling
  3. _content_hash — determinism + uniqueness

These tests use real DB rows (pytest.mark.django_db).  Heavy Celery tasks
(auto_ingest_course_content, auto_ingest_single_content) are NOT exercised
here — they require live Redis/Celery infrastructure.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from apps.courses.chatbot_auto_ingest import (
    _content_hash,
    _create_knowledge_for_content,
    _source_type_for_content,
)
from apps.courses.chatbot_models import AIChatbot, AIChatbotKnowledge
from apps.courses.models import Content, Course, Module
from apps.tenants.models import Tenant
from apps.users.models import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name="AI Ingest School", subdomain=None):
    subdomain = subdomain or f"aiingest-{uuid.uuid4().hex[:6]}"
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.example.com",
        is_active=True,
    )


def _make_user(tenant, email=None, role="SCHOOL_ADMIN"):
    email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
    return User.objects.create_user(
        email=email,
        password="Pass!1234",
        first_name="Test",
        last_name="User",
        tenant=tenant,
        role=role,
        is_active=True,
    )


def _make_course(tenant, creator):
    slug = f"course-{uuid.uuid4().hex[:8]}"
    return Course.objects.create(
        tenant=tenant,
        title="AI Ingest Test Course",
        slug=slug,
        description="For auto-ingest tests",
        created_by=creator,
        is_published=True,
        is_active=True,
    )


def _make_module(course):
    return Module.objects.create(
        course=course,
        title="Test Module",
        description="Module for auto-ingest tests",
        order=1,
        is_active=True,
    )


def _make_content(module, content_type="TEXT", **kwargs):
    defaults = {
        "title": f"Content-{content_type}-{uuid.uuid4().hex[:6]}",
        "content_type": content_type,
        "order": 1,
        "text_content": "<p>Some text</p>" if content_type == "TEXT" else "",
        "file_url": "",
        "is_active": True,
    }
    defaults.update(kwargs)
    return Content.objects.create(module=module, **defaults)


def _make_chatbot(tenant, creator):
    return AIChatbot.all_objects.create(
        tenant=tenant,
        creator=creator,
        name="Test Chatbot",
        persona_preset="study_buddy",
        is_active=True,
    )


# ===========================================================================
# 1. _content_hash
# ===========================================================================

class ContentHashTestCase(TestCase):
    """_content_hash must be deterministic and produce unique digests."""

    def test_returns_hex_string(self):
        result = _content_hash("hello")
        self.assertIsInstance(result, str)
        # SHA-256 hex is always 64 chars
        self.assertEqual(len(result), 64)
        int(result, 16)  # should not raise

    def test_same_input_same_hash(self):
        self.assertEqual(_content_hash("same"), _content_hash("same"))

    def test_different_inputs_different_hashes(self):
        self.assertNotEqual(_content_hash("foo"), _content_hash("bar"))

    def test_empty_string_is_valid_input(self):
        h = _content_hash("")
        self.assertEqual(len(h), 64)


# ===========================================================================
# 2. _source_type_for_content
# ===========================================================================

class SourceTypeForContentTestCase(TestCase):
    """_source_type_for_content must map content_type to the correct source_type."""

    def _content(self, content_type, file_url=""):
        """Build a minimal MagicMock that acts like a Content instance."""
        m = MagicMock()
        m.content_type = content_type
        m.file_url = file_url
        return m

    def test_text_returns_text(self):
        self.assertEqual(_source_type_for_content(self._content("TEXT")), "text")

    def test_video_returns_text_for_transcript(self):
        self.assertEqual(_source_type_for_content(self._content("VIDEO")), "text")

    def test_document_pdf_returns_pdf(self):
        self.assertEqual(
            _source_type_for_content(self._content("DOCUMENT", file_url="https://s3.example.com/doc.pdf")),
            "pdf",
        )

    def test_document_docx_returns_document(self):
        self.assertEqual(
            _source_type_for_content(self._content("DOCUMENT", file_url="https://s3.example.com/doc.docx")),
            "document",
        )

    def test_link_returns_url(self):
        self.assertEqual(
            _source_type_for_content(self._content("LINK", file_url="https://example.com")),
            "url",
        )

    def test_ai_classroom_returns_none(self):
        """AI_CLASSROOM should be skipped — not suitable for text retrieval."""
        self.assertIsNone(_source_type_for_content(self._content("AI_CLASSROOM")))

    def test_chatbot_returns_none(self):
        """CHATBOT should be skipped — meta content, not course material."""
        self.assertIsNone(_source_type_for_content(self._content("CHATBOT")))

    def test_quiz_returns_none(self):
        """
        TASK-043: QUIZ content_type has no entry in _source_type_for_content.
        The function falls through to return None.  Combined with the explicit
        elif branch in _create_knowledge_for_content, QUIZ is doubly-skipped.
        """
        self.assertIsNone(_source_type_for_content(self._content("QUIZ")))


# ===========================================================================
# 3. _create_knowledge_for_content
# ===========================================================================

class CreateKnowledgeForContentTestCase(TestCase):
    """
    Tests for _create_knowledge_for_content — the per-content-type dispatcher.
    All tests use real DB rows (no mocks for the knowledge creation path).

    Note: @pytest.mark.django_db is NOT needed here — django.test.TestCase already
    wraps every test in a transaction and handles DB isolation natively.
    """

    def setUp(self):
        self.tenant = _make_tenant()
        self.admin = _make_user(self.tenant)
        self.course = _make_course(self.tenant, self.admin)
        self.module = _make_module(self.course)
        self.chatbot = _make_chatbot(self.tenant, self.admin)

    # ── TASK-043: QUIZ skip ────────────────────────────────────────────────

    def test_quiz_content_type_returns_none(self):
        """
        TASK-043: _create_knowledge_for_content must return None for QUIZ content.

        The QUIZ content_type was introduced in TASK-043.  Unlike TEXT / VIDEO /
        DOCUMENT / LINK, QUIZ content is NOT suitable for free-text RAG indexing
        (quiz questions are configured separately via QuizConfig / QuestionBank).
        An explicit elif branch in _create_knowledge_for_content enforces this.
        """
        content = _make_content(self.module, content_type="QUIZ")
        result = _create_knowledge_for_content(self.chatbot, content)
        self.assertIsNone(result)

    def test_quiz_content_creates_no_knowledge_record(self):
        """
        TASK-043: no AIChatbotKnowledge row must be created for QUIZ content.

        Verifies the DB-level invariant — not just the return value.
        """
        content = _make_content(self.module, content_type="QUIZ")
        before_count = AIChatbotKnowledge.all_objects.filter(chatbot=self.chatbot).count()
        _create_knowledge_for_content(self.chatbot, content)
        after_count = AIChatbotKnowledge.all_objects.filter(chatbot=self.chatbot).count()
        self.assertEqual(after_count, before_count,
                         "No AIChatbotKnowledge must be created for QUIZ content")

    # ── Other skipped content types ────────────────────────────────────────

    def test_ai_classroom_content_type_returns_none(self):
        """AI_CLASSROOM content is skipped — _source_type_for_content returns None."""
        content = _make_content(self.module, content_type="AI_CLASSROOM")
        self.assertIsNone(_create_knowledge_for_content(self.chatbot, content))

    def test_chatbot_content_type_returns_none(self):
        """CHATBOT content is skipped — not indexable course material."""
        content = _make_content(self.module, content_type="CHATBOT")
        self.assertIsNone(_create_knowledge_for_content(self.chatbot, content))

    def test_empty_text_content_returns_none(self):
        """TEXT content with no text is skipped to avoid empty knowledge entries."""
        content = _make_content(self.module, content_type="TEXT", text_content="")
        self.assertIsNone(_create_knowledge_for_content(self.chatbot, content))

    def test_whitespace_only_text_content_returns_none(self):
        """Whitespace-only TEXT content is stripped and treated as empty."""
        content = _make_content(self.module, content_type="TEXT", text_content="   \n  \t  ")
        self.assertIsNone(_create_knowledge_for_content(self.chatbot, content))

    def test_document_without_file_url_returns_none(self):
        """DOCUMENT content with no file_url is skipped (nothing to index)."""
        content = _make_content(self.module, content_type="DOCUMENT", file_url="")
        self.assertIsNone(_create_knowledge_for_content(self.chatbot, content))

    def test_link_without_file_url_returns_none(self):
        """LINK content with no file_url is skipped."""
        content = _make_content(self.module, content_type="LINK", file_url="")
        self.assertIsNone(_create_knowledge_for_content(self.chatbot, content))

    # ── Successful creation ────────────────────────────────────────────────

    def test_text_content_creates_knowledge_record(self):
        """TEXT content with non-empty text creates an AIChatbotKnowledge row."""
        content = _make_content(
            self.module, content_type="TEXT",
            text_content="Photosynthesis converts CO2 + H2O → glucose + O2.",
        )
        result = _create_knowledge_for_content(self.chatbot, content)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, AIChatbotKnowledge)
        self.assertEqual(result.source_type, "text")
        self.assertEqual(result.embedding_status, "pending")

    def test_document_with_file_url_creates_knowledge_record(self):
        """DOCUMENT content with a file_url creates an AIChatbotKnowledge row."""
        content = _make_content(
            self.module, content_type="DOCUMENT",
            file_url="https://s3.example.com/lesson.docx",
        )
        result = _create_knowledge_for_content(self.chatbot, content)
        self.assertIsNotNone(result)
        self.assertEqual(result.file_url, "https://s3.example.com/lesson.docx")

    def test_link_with_file_url_creates_knowledge_record(self):
        """LINK content with a file_url creates an AIChatbotKnowledge row."""
        content = _make_content(
            self.module, content_type="LINK",
            file_url="https://www.khanacademy.org/lesson/1",
        )
        result = _create_knowledge_for_content(self.chatbot, content)
        self.assertIsNotNone(result)
        self.assertEqual(result.source_type, "url")

    def test_idempotent_text_content_returns_none_on_second_call(self):
        """
        Calling _create_knowledge_for_content twice for the same TEXT content
        returns the knowledge record the first time and None the second time
        (dedup via _knowledge_exists check on chatbot + content).
        """
        content = _make_content(
            self.module, content_type="TEXT",
            text_content="Idempotency check — this text only appears once.",
        )
        first = _create_knowledge_for_content(self.chatbot, content)
        self.assertIsNotNone(first)

        second = _create_knowledge_for_content(self.chatbot, content)
        self.assertIsNone(second, "Duplicate call must return None (dedup guard)")

    def test_knowledge_record_is_linked_to_correct_content(self):
        """Created knowledge record must have content_source pointing to the content."""
        content = _make_content(
            self.module, content_type="TEXT",
            text_content="The mitochondria is the powerhouse of the cell.",
        )
        result = _create_knowledge_for_content(self.chatbot, content)
        self.assertIsNotNone(result)
        self.assertEqual(result.content_source_id, content.id)

    def test_knowledge_record_belongs_to_correct_tenant(self):
        """Knowledge record tenant must match the chatbot's tenant."""
        content = _make_content(
            self.module, content_type="TEXT",
            text_content="Tenant isolation check.",
        )
        result = _create_knowledge_for_content(self.chatbot, content)
        self.assertIsNotNone(result)
        self.assertEqual(result.tenant_id, self.tenant.id)

    def test_video_without_transcript_returns_none(self):
        """
        VIDEO content with no VideoTranscript is skipped.

        The real code tries to access content.video_asset.transcript.full_text
        and falls back to empty string on AttributeError / DoesNotExist.
        A video content without a VideoAsset → no transcript → skip.
        """
        # Create a VIDEO content with no VideoAsset (file_url only, no asset row)
        content = _make_content(
            self.module, content_type="VIDEO",
            file_url="https://cdn.example.com/video.mp4",
        )
        # No VideoAsset / VideoTranscript rows → accessing content.video_asset raises AttributeError
        result = _create_knowledge_for_content(self.chatbot, content)
        self.assertIsNone(result, "VIDEO without transcript must be skipped")
