"""
tests/factories.py — Lightweight test data factories for the LearnPuddle LMS test suite.

These are plain Python helper functions (not factory_boy) that create model instances
with sensible defaults. They mirror the factory_boy API style for easy migration later.

Usage:
    from tests.factories import TenantFactory, UserFactory, CourseFactory, AssignmentFactory

    tenant = TenantFactory.create()
    admin = UserFactory.create(tenant=tenant, role='SCHOOL_ADMIN')
    course = CourseFactory.create(tenant=tenant, created_by=admin)
    assignment = AssignmentFactory.create(tenant=tenant, course=course)

All factories require an active database transaction (use with @pytest.mark.django_db).
"""

import uuid
from django.utils import timezone


# ─────────────────────────────────────────────────────────────
# Base helper
# ─────────────────────────────────────────────────────────────

def _uid() -> str:
    """Return a short unique suffix to avoid collisions in tests."""
    return uuid.uuid4().hex[:8]


# ─────────────────────────────────────────────────────────────
# TenantFactory
# ─────────────────────────────────────────────────────────────

class TenantFactory:
    @staticmethod
    def create(**kwargs) -> "Tenant":  # type: ignore[name-defined]
        from apps.tenants.models import Tenant
        uid = _uid()
        defaults = {
            "name": f"Test School {uid}",
            "slug": f"test-school-{uid}",
            "subdomain": f"school{uid}",
            "email": f"admin@school{uid}.com",
            "is_active": True,
        }
        defaults.update(kwargs)
        return Tenant.objects.create(**defaults)

    @staticmethod
    def create_pair() -> tuple:
        """Create two tenants for cross-tenant isolation tests."""
        tenant_a = TenantFactory.create()
        tenant_b = TenantFactory.create()
        return tenant_a, tenant_b


# ─────────────────────────────────────────────────────────────
# UserFactory
# ─────────────────────────────────────────────────────────────

class UserFactory:
    @staticmethod
    def create(tenant, role="TEACHER", **kwargs) -> "User":  # type: ignore[name-defined]
        from apps.users.models import User
        uid = _uid()
        role_lower = role.lower().replace("_", "")
        defaults = {
            "email": f"{role_lower}_{uid}@testschool.com",
            "password": f"TestPass!{uid}123",
            "first_name": role.title(),
            "last_name": "User",
            "tenant": tenant,
            "role": role,
            "is_active": True,
        }
        defaults.update(kwargs)
        password = defaults.pop("password")
        user = User(**defaults)
        user.set_password(password)
        user.save()
        return user

    @staticmethod
    def create_admin(tenant, **kwargs):
        return UserFactory.create(tenant, role="SCHOOL_ADMIN", **kwargs)

    @staticmethod
    def create_teacher(tenant, **kwargs):
        return UserFactory.create(tenant, role="TEACHER", **kwargs)

    @staticmethod
    def create_super_admin(tenant, **kwargs):
        return UserFactory.create(tenant, role="SUPER_ADMIN", **kwargs)


# ─────────────────────────────────────────────────────────────
# CourseFactory
# ─────────────────────────────────────────────────────────────

class CourseFactory:
    @staticmethod
    def create(tenant, created_by, **kwargs) -> "Course":  # type: ignore[name-defined]
        from apps.courses.models import Course
        uid = _uid()
        defaults = {
            "tenant": tenant,
            "title": f"Test Course {uid}",
            "slug": f"test-course-{uid}",
            "description": "Auto-created by CourseFactory for testing.",
            "created_by": created_by,
            "is_published": True,
            "is_active": True,
        }
        defaults.update(kwargs)
        return Course.objects.create(**defaults)


# ─────────────────────────────────────────────────────────────
# ModuleFactory
# ─────────────────────────────────────────────────────────────

class ModuleFactory:
    @staticmethod
    def create(course, **kwargs) -> "Module":  # type: ignore[name-defined]
        from apps.courses.models import Module
        uid = _uid()
        defaults = {
            "course": course,
            "title": f"Test Module {uid}",
            "description": "Auto-created by ModuleFactory.",
            "order": 1,
            "is_active": True,
        }
        defaults.update(kwargs)
        return Module.objects.create(**defaults)


# ─────────────────────────────────────────────────────────────
# ContentFactory
# ─────────────────────────────────────────────────────────────

class ContentFactory:
    @staticmethod
    def create_text(module, **kwargs) -> "Content":  # type: ignore[name-defined]
        from apps.courses.models import Content
        uid = _uid()
        defaults = {
            "module": module,
            "title": f"Text Content {uid}",
            "content_type": "TEXT",
            "order": 1,
            "text_content": f"<p>Test content {uid}</p>",
            "is_mandatory": True,
            "is_active": True,
        }
        defaults.update(kwargs)
        return Content.objects.create(**defaults)

    @staticmethod
    def create_video(module, **kwargs) -> "Content":  # type: ignore[name-defined]
        from apps.courses.models import Content
        uid = _uid()
        defaults = {
            "module": module,
            "title": f"Video Content {uid}",
            "content_type": "VIDEO",
            "order": 2,
            "file_url": "",
            "file_size": 0,
            "duration": 600,
            "text_content": "",
            "is_mandatory": True,
            "is_active": True,
        }
        defaults.update(kwargs)
        return Content.objects.create(**defaults)


# ─────────────────────────────────────────────────────────────
# VideoAssetFactory
# ─────────────────────────────────────────────────────────────

class VideoAssetFactory:
    @staticmethod
    def create(content, status="UPLOADED", **kwargs) -> "VideoAsset":  # type: ignore[name-defined]
        from apps.courses.video_models import VideoAsset
        uid = _uid()
        defaults = {
            "content": content,
            "source_file": f"tenant/test/videos/{uid}/source.mp4",
            "status": status,
            "error_message": "",
        }
        defaults.update(kwargs)
        return VideoAsset.objects.create(**defaults)

    @staticmethod
    def create_ready(content, **kwargs) -> "VideoAsset":  # type: ignore[name-defined]
        return VideoAssetFactory.create(
            content,
            status="READY",
            hls_master_url=f"https://cdn.example.com/hls/master.m3u8",
            thumbnail_url=f"https://cdn.example.com/thumb.jpg",
            duration_seconds=600,
            width=1920,
            height=1080,
            codec="h264",
            **kwargs,
        )


# ─────────────────────────────────────────────────────────────
# AssignmentFactory
# ─────────────────────────────────────────────────────────────

class AssignmentFactory:
    @staticmethod
    def create(tenant, course, module=None, **kwargs) -> "Assignment":  # type: ignore[name-defined]
        from apps.progress.models import Assignment
        uid = _uid()
        defaults = {
            "tenant": tenant,
            "course": course,
            "module": module,
            "title": f"Test Assignment {uid}",
            "description": f"Auto-created assignment {uid} for testing.",
            "instructions": "Complete this assignment.",
            "max_score": 100,
            "passing_score": 70,
            "generation_source": "MANUAL",
            "is_mandatory": True,
            "is_active": True,
        }
        defaults.update(kwargs)
        return Assignment.objects.create(**defaults)

    @staticmethod
    def create_video_auto(tenant, course, module, content, **kwargs) -> "Assignment":  # type: ignore[name-defined]
        return AssignmentFactory.create(
            tenant, course, module,
            content=content,
            generation_source="VIDEO_AUTO",
            generation_metadata={"type": "quiz", "video_asset_id": str(uuid.uuid4())},
            **kwargs,
        )


# ─────────────────────────────────────────────────────────────
# QuizFactory
# ─────────────────────────────────────────────────────────────

class QuizFactory:
    @staticmethod
    def create(tenant, assignment, **kwargs) -> "Quiz":  # type: ignore[name-defined]
        from apps.progress.models import Quiz
        defaults = {
            "tenant": tenant,
            "assignment": assignment,
            "schema_version": 1,
            "is_auto_generated": False,
            "max_attempts": 3,
        }
        defaults.update(kwargs)
        return Quiz.objects.create(**defaults)

    @staticmethod
    def create_auto(tenant, assignment, **kwargs) -> "Quiz":  # type: ignore[name-defined]
        return QuizFactory.create(
            tenant, assignment,
            is_auto_generated=True,
            generation_model="gpt-4o-mini",
            **kwargs,
        )


# ─────────────────────────────────────────────────────────────
# QuizQuestionFactory
# ─────────────────────────────────────────────────────────────

class QuizQuestionFactory:
    @staticmethod
    def create_mcq(tenant, quiz, order=1, **kwargs) -> "QuizQuestion":  # type: ignore[name-defined]
        from apps.progress.models import QuizQuestion
        defaults = {
            "tenant": tenant,
            "quiz": quiz,
            "order": order,
            "question_type": "MCQ",
            "selection_mode": "SINGLE",
            "prompt": f"Question {order}: What is the correct answer?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": {"answer": "Option A"},
            "explanation": "Option A is correct.",
            "points": 1,
        }
        defaults.update(kwargs)
        return QuizQuestion.objects.create(**defaults)

    @staticmethod
    def create_true_false(tenant, quiz, order=1, **kwargs) -> "QuizQuestion":  # type: ignore[name-defined]
        from apps.progress.models import QuizQuestion
        defaults = {
            "tenant": tenant,
            "quiz": quiz,
            "order": order,
            "question_type": "TRUE_FALSE",
            "selection_mode": "SINGLE",
            "prompt": f"True or False (Q{order})?",
            "options": ["True", "False"],
            "correct_answer": {"answer": "True"},
            "explanation": "The statement is true.",
            "points": 1,
        }
        defaults.update(kwargs)
        return QuizQuestion.objects.create(**defaults)

    @staticmethod
    def create_batch(tenant, quiz, count=6, question_type="MCQ") -> list:
        """Create `count` questions on the given quiz."""
        method = {
            "MCQ": QuizQuestionFactory.create_mcq,
            "TRUE_FALSE": QuizQuestionFactory.create_true_false,
        }.get(question_type, QuizQuestionFactory.create_mcq)
        return [method(tenant, quiz, order=i + 1) for i in range(count)]


# ─────────────────────────────────────────────────────────────
# TeacherProgressFactory
# ─────────────────────────────────────────────────────────────

class TeacherProgressFactory:
    @staticmethod
    def create(tenant, teacher, course, content=None, **kwargs) -> "TeacherProgress":  # type: ignore[name-defined]
        from apps.progress.models import TeacherProgress
        defaults = {
            "tenant": tenant,
            "teacher": teacher,
            "course": course,
            "content": content,
            "status": "NOT_STARTED",
            "progress_percentage": 0,
            "video_progress_seconds": 0,
        }
        defaults.update(kwargs)
        return TeacherProgress.all_objects.create(**defaults)

    @staticmethod
    def create_completed(tenant, teacher, course, **kwargs) -> "TeacherProgress":  # type: ignore[name-defined]
        return TeacherProgressFactory.create(
            tenant, teacher, course,
            status="COMPLETED",
            progress_percentage=100,
            started_at=timezone.now(),
            completed_at=timezone.now(),
            **kwargs,
        )


# ─────────────────────────────────────────────────────────────
# QuizSubmissionFactory
# ─────────────────────────────────────────────────────────────

class QuizSubmissionFactory:
    @staticmethod
    def create(tenant, quiz, teacher, attempt_number=1, **kwargs) -> "QuizSubmission":  # type: ignore[name-defined]
        from apps.progress.models import QuizSubmission
        defaults = {
            "tenant": tenant,
            "quiz": quiz,
            "teacher": teacher,
            "attempt_number": attempt_number,
            "answers": {},
            "score": None,
            "time_expired": False,
        }
        defaults.update(kwargs)
        return QuizSubmission.objects.create(**defaults)

    @staticmethod
    def create_graded(tenant, quiz, teacher, score=85, **kwargs) -> "QuizSubmission":  # type: ignore[name-defined]
        return QuizSubmissionFactory.create(
            tenant, quiz, teacher,
            answers={"q1": "Option A", "q2": "True"},
            score=score,
            graded_at=timezone.now(),
            **kwargs,
        )


# ─────────────────────────────────────────────────────────────
# AssignmentSubmissionFactory
# ─────────────────────────────────────────────────────────────

class AssignmentSubmissionFactory:
    @staticmethod
    def create(tenant, assignment, teacher, **kwargs) -> "AssignmentSubmission":  # type: ignore[name-defined]
        from apps.progress.models import AssignmentSubmission
        defaults = {
            "tenant": tenant,
            "assignment": assignment,
            "teacher": teacher,
            "submission_text": "My submission text here.",
            "status": "SUBMITTED",
        }
        defaults.update(kwargs)
        return AssignmentSubmission.all_objects.create(**defaults)

    @staticmethod
    def create_graded(tenant, assignment, teacher, graded_by, score=88, **kwargs) -> "AssignmentSubmission":  # type: ignore[name-defined]
        return AssignmentSubmissionFactory.create(
            tenant, assignment, teacher,
            score=score,
            feedback="Good work!",
            graded_by=graded_by,
            graded_at=timezone.now(),
            status="GRADED",
            **kwargs,
        )


# ─────────────────────────────────────────────────────────────
# Convenience builder: full stack
# ─────────────────────────────────────────────────────────────

def build_full_stack(tenant=None) -> dict:
    """
    Create a complete test stack (tenant → admin → course → module → content).
    Returns a dict with all created objects.

    Usage:
        stack = build_full_stack()
        admin = stack['admin']
        course = stack['course']
    """
    t = tenant or TenantFactory.create()
    admin = UserFactory.create_admin(t)
    teacher = UserFactory.create_teacher(t)
    course = CourseFactory.create(t, created_by=admin)
    module = ModuleFactory.create(course)
    text_content = ContentFactory.create_text(module)
    video_content = ContentFactory.create_video(module, order=2)
    return {
        "tenant": t,
        "admin": admin,
        "teacher": teacher,
        "course": course,
        "module": module,
        "text_content": text_content,
        "video_content": video_content,
    }
