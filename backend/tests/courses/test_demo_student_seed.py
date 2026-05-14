"""Regression tests for production-shaped student demo seed data."""

import pytest

from apps.courses.chatbot_models import AIChatbot
from apps.courses.demo_student_seed import (
    DEMO_CHATBOT_NAME,
    DEMO_COURSE_SLUG,
    DEMO_THREAD_TITLE,
    ensure_demo_student_portal_content,
)
from apps.courses.models import Content, Course
from apps.courses.study_summary_models import StudySummary
from apps.discussions.models import DiscussionThread
from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db


def _make_demo_users():
    tenant = Tenant.objects.create(
        name="Demo School",
        slug="demo-school",
        subdomain="demo",
        email="demo@example.com",
        is_active=True,
        feature_maic=True,
        feature_students=True,
    )
    teacher = User.objects.create_user(
        email="teacher@demo.learnpuddle.com",
        password="Teacher@123",
        first_name="Demo",
        last_name="Teacher",
        tenant=tenant,
        role="TEACHER",
    )
    student = User.objects.create_user(
        email="student@demo.learnpuddle.com",
        password="Student@123",
        first_name="Demo",
        last_name="Student",
        tenant=tenant,
        role="STUDENT",
    )
    return tenant, teacher, student


def test_demo_student_seed_creates_real_portal_content():
    tenant, teacher, student = _make_demo_users()

    seeded = ensure_demo_student_portal_content(tenant)

    student.refresh_from_db()
    assert str(student.section_fk_id) == seeded["section_id"]
    assert student.grade_fk_id is not None

    course = Course.objects.get(tenant=tenant, slug=DEMO_COURSE_SLUG)
    assert course.is_published is True
    assert course.is_active is True
    assert course.assigned_students.filter(pk=student.pk).exists()
    assert course.target_sections.filter(pk=student.section_fk_id).exists()

    content = Content.all_objects.get(pk=seeded["content_id"])
    assert content.content_type == "TEXT"
    assert content.module.course_id == course.id
    assert "Durable" in content.text_content

    summary = StudySummary.all_objects.get(content=content, generated_by=teacher)
    assert summary.status == "READY"
    assert summary.is_shared is True
    assert summary.summary_data["flashcards"]

    chatbot = AIChatbot.objects.get(tenant=tenant, name=DEMO_CHATBOT_NAME)
    assert chatbot.is_active is True
    assert chatbot.sections.filter(pk=student.section_fk_id).exists()
    assert chatbot.knowledge_sources.filter(embedding_status="ready").exists()

    thread = DiscussionThread.objects.get(tenant=tenant, title=DEMO_THREAD_TITLE)
    assert thread.section_id == student.section_fk_id
    assert thread.course_id == course.id
    assert thread.content_id == content.id
    assert thread.reply_count >= 1


def test_demo_student_seed_is_idempotent():
    tenant, _, _ = _make_demo_users()

    first = ensure_demo_student_portal_content(tenant)
    second = ensure_demo_student_portal_content(tenant)

    assert first == second
    assert Course.objects.filter(tenant=tenant, slug=DEMO_COURSE_SLUG).count() == 1
    assert AIChatbot.objects.filter(tenant=tenant, name=DEMO_CHATBOT_NAME).count() == 1
    assert DiscussionThread.objects.filter(tenant=tenant, title=DEMO_THREAD_TITLE).count() == 1
