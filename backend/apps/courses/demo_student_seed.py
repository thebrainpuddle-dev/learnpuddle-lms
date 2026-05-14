"""Demo data for the student portal live harness.

The records created here are ordinary production models: academic structure,
published course content, shared study summaries, discussions, and AI tutors.
They exist so local/demo smoke tests can click through real student-facing
detail pages instead of stopping at empty states.
"""

from __future__ import annotations

import hashlib

from django.utils import timezone

from apps.academics.models import Grade, GradeBand, Section, Subject, TeachingAssignment
from apps.courses.chatbot_models import AIChatbot, AIChatbotConversation, AIChatbotKnowledge
from apps.courses.models import Content, Course, Module
from apps.courses.study_summary_models import StudySummary
from apps.discussions.models import DiscussionReply, DiscussionThread
from apps.tenants.models import Tenant
from apps.users.models import User


DEMO_COURSE_TITLE = "Student Demo: Study Skills Lab"
DEMO_COURSE_SLUG = "student-demo-study-skills-lab"
DEMO_MODULE_TITLE = "Learning How to Learn"
DEMO_CONTENT_TITLE = "How to Build Durable Study Notes"
DEMO_CHATBOT_NAME = "Demo Study Coach"
DEMO_THREAD_TITLE = "How should I revise from the demo study notes?"


def ensure_demo_student_portal_content(tenant: Tenant) -> dict[str, str]:
    """Ensure demo student routes have real data to render and navigate."""
    teacher = User.objects.get(email="teacher@demo.learnpuddle.com")
    student = User.objects.get(email="student@demo.learnpuddle.com")

    section = _ensure_academic_structure(tenant, teacher, student)
    course, content = _ensure_course_content(tenant, teacher, student, section)
    _ensure_study_summary(tenant, teacher, content)
    chatbot = _ensure_chatbot(tenant, teacher, student, section, content)
    thread = _ensure_discussion(tenant, teacher, student, section, course, content)
    _finalize_course_as_academic(course)

    return {
        "section_id": str(section.id),
        "course_id": str(course.id),
        "content_id": str(content.id),
        "chatbot_id": str(chatbot.id),
        "thread_id": str(thread.id),
    }


def _ensure_academic_structure(
    tenant: Tenant,
    teacher: User,
    student: User,
) -> Section:
    band, _ = GradeBand.objects.get_or_create(
        tenant=tenant,
        name="Demo Middle School",
        defaults={
            "short_code": "DMS",
            "order": 1,
            "curriculum_framework": "CUSTOM",
        },
    )
    grade, _ = Grade.objects.get_or_create(
        tenant=tenant,
        short_code="G8",
        defaults={
            "grade_band": band,
            "name": "Grade 8",
            "order": 8,
        },
    )
    if grade.grade_band_id != band.id or grade.name != "Grade 8":
        grade.grade_band = band
        grade.name = "Grade 8"
        grade.order = 8
        grade.save(update_fields=["grade_band", "name", "order", "updated_at"])

    section, _ = Section.objects.get_or_create(
        tenant=tenant,
        grade=grade,
        name="A",
        academic_year="2026-27",
        defaults={"class_teacher": teacher},
    )
    if section.class_teacher_id != teacher.id:
        section.class_teacher = teacher
        section.save(update_fields=["class_teacher", "updated_at"])

    subject, _ = Subject.objects.get_or_create(
        tenant=tenant,
        code="STUDY",
        defaults={
            "name": "Study Skills",
            "department": "Learning Support",
        },
    )
    subject.applicable_grades.add(grade)

    assignment, _ = TeachingAssignment.objects.get_or_create(
        tenant=tenant,
        teacher=teacher,
        subject=subject,
        academic_year="2026-27",
        defaults={"is_class_teacher": True},
    )
    assignment.sections.add(section)

    student.grade_fk = grade
    student.section_fk = section
    student.grade_level = grade.name
    student.section = section.name
    student.student_id = student.student_id or "DEMO-STUDENT-001"
    student.enrollment_date = student.enrollment_date or timezone.localdate()
    student.save(
        update_fields=[
            "grade_fk",
            "section_fk",
            "grade_level",
            "section",
            "student_id",
            "enrollment_date",
            "updated_at",
        ],
    )

    teacher.subjects = sorted(set([*(teacher.subjects or []), "Study Skills"]))
    teacher.grades = sorted(set([*(teacher.grades or []), grade.name]))
    teacher.department = teacher.department or "Learning Support"
    teacher.save(update_fields=["subjects", "grades", "department", "updated_at"])

    return section


def _ensure_course_content(
    tenant: Tenant,
    teacher: User,
    student: User,
    section: Section,
) -> tuple[Course, Content]:
    course = Course.objects.filter(tenant=tenant, slug=DEMO_COURSE_SLUG).first()
    if not course:
        course = Course.objects.create(
            tenant=tenant,
            title=DEMO_COURSE_TITLE,
            slug=DEMO_COURSE_SLUG,
            description=(
                "A short production-style course used by the student portal "
                "smoke test to exercise course detail, study-note rendering, "
                "discussion context, and AI tutor access."
            ),
            estimated_hours=1,
            is_published=True,
            is_active=True,
            # Keep the course non-academic while demo content and chatbot
            # sections are being wired. The chatbot auto-ingest signal only
            # targets ACADEMIC courses, and this seed installs its own ready
            # knowledge source below without requiring embedding credentials.
            course_type="PD",
            created_by=teacher,
            assigned_to_all_students=False,
        )
    else:
        course.title = DEMO_COURSE_TITLE
        course.description = (
            "A short production-style course used by the student portal smoke "
            "test to exercise course detail, study-note rendering, discussion "
            "context, and AI tutor access."
        )
        course.estimated_hours = 1
        course.is_published = True
        course.is_active = True
        course.course_type = "PD"
        course.created_by = teacher
        course.assigned_to_all_students = False
        course.save()

    course.assigned_students.add(student)
    course.target_grades.add(section.grade)
    course.target_sections.add(section)

    module, _ = Module.objects.get_or_create(
        course=course,
        title=DEMO_MODULE_TITLE,
        defaults={
            "description": "Practical routines for turning lessons into durable memory.",
            "order": 1,
            "is_active": True,
        },
    )
    module.description = "Practical routines for turning lessons into durable memory."
    module.order = 1
    module.is_active = True
    module.save(update_fields=["description", "order", "is_active", "updated_at"])

    content, _ = Content.all_objects.get_or_create(
        module=module,
        title=DEMO_CONTENT_TITLE,
        defaults={
            "content_type": "TEXT",
            "order": 1,
            "is_active": True,
            "is_mandatory": True,
            "text_content": _demo_content_html(),
        },
    )
    content.content_type = "TEXT"
    content.order = 1
    content.is_active = True
    content.is_mandatory = True
    content.text_content = _demo_content_html()
    content.save(
        update_fields=[
            "content_type",
            "order",
            "is_active",
            "is_mandatory",
            "text_content",
            "updated_at",
        ],
    )

    return course, content


def _finalize_course_as_academic(course: Course) -> None:
    if course.course_type != "ACADEMIC":
        course.course_type = "ACADEMIC"
        course.save(update_fields=["course_type", "updated_at"])


def _ensure_study_summary(
    tenant: Tenant,
    teacher: User,
    content: Content,
) -> StudySummary:
    source_hash = hashlib.sha256(content.text_content.encode("utf-8")).hexdigest()
    summary = (
        StudySummary.all_objects.filter(
            tenant=tenant,
            content=content,
            generated_by=teacher,
            student__isnull=True,
        )
        .order_by("created_at")
        .first()
    )
    if not summary:
        summary = StudySummary.all_objects.create(
            tenant=tenant,
            content=content,
            generated_by=teacher,
            is_shared=True,
            status="READY",
            source_text_hash=source_hash,
            summary_data=_demo_summary_data(),
        )
    else:
        summary.is_shared = True
        summary.status = "READY"
        summary.source_text_hash = source_hash
        summary.summary_data = _demo_summary_data()
        summary.save(
            update_fields=[
                "is_shared",
                "status",
                "source_text_hash",
                "summary_data",
                "updated_at",
            ],
        )
    return summary


def _ensure_chatbot(
    tenant: Tenant,
    teacher: User,
    student: User,
    section: Section,
    content: Content,
) -> AIChatbot:
    chatbot, _ = AIChatbot.objects.get_or_create(
        tenant=tenant,
        creator=teacher,
        name=DEMO_CHATBOT_NAME,
        defaults={
            "persona_preset": "study_buddy",
            "persona_description": (
                "A concise study coach who helps students turn notes into "
                "retrieval practice and spaced revision plans."
            ),
            "welcome_message": (
                "Hi! I can help you turn the demo study notes into flashcards, "
                "retrieval questions, and a revision plan."
            ),
            "block_off_topic": True,
            "is_active": True,
        },
    )
    chatbot.persona_preset = "study_buddy"
    chatbot.persona_description = (
        "A concise study coach who helps students turn notes into retrieval "
        "practice and spaced revision plans."
    )
    chatbot.welcome_message = (
        "Hi! I can help you turn the demo study notes into flashcards, "
        "retrieval questions, and a revision plan."
    )
    chatbot.block_off_topic = True
    chatbot.is_active = True
    chatbot.save(
        update_fields=[
            "persona_preset",
            "persona_description",
            "welcome_message",
            "block_off_topic",
            "is_active",
            "updated_at",
        ],
    )
    _ensure_chatbot_section(chatbot, section)

    raw_text = (
        "Durable study notes combine retrieval practice, spaced repetition, "
        "dual coding, and short reflection loops. Students should close the "
        "source, recall the idea, check gaps, and revisit it over several days."
    )
    knowledge_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    knowledge, _ = AIChatbotKnowledge.all_objects.get_or_create(
        tenant=tenant,
        chatbot=chatbot,
        title="Durable Study Notes Guide",
        defaults={
            "content_source": content,
            "is_auto": True,
            "source_type": "text",
            "raw_text": raw_text,
            "content_hash": knowledge_hash,
            "chunk_count": 1,
            "total_token_count": 64,
            "embedding_status": "ready",
        },
    )
    knowledge.content_source = content
    knowledge.is_auto = True
    knowledge.source_type = "text"
    knowledge.raw_text = raw_text
    knowledge.content_hash = knowledge_hash
    knowledge.chunk_count = 1
    knowledge.total_token_count = 64
    knowledge.embedding_status = "ready"
    knowledge.error_message = ""
    knowledge.save(
        update_fields=[
            "content_source",
            "is_auto",
            "source_type",
            "raw_text",
            "content_hash",
            "chunk_count",
            "total_token_count",
            "embedding_status",
            "error_message",
            "updated_at",
        ],
    )

    AIChatbotConversation.objects.get_or_create(
        tenant=tenant,
        chatbot=chatbot,
        student=student,
        title="How do I revise these notes?",
        defaults={"message_count": 1},
    )
    return chatbot


def _ensure_chatbot_section(chatbot: AIChatbot, section: Section) -> None:
    """Link the demo tutor to a section without queueing auto-ingest.

    The demo seed installs a ready knowledge source below. Calling
    ``chatbot.sections.add`` would fire the generic auto-ingest signal, which
    can require embedding credentials unrelated to this smoke fixture.
    """
    through = AIChatbot.sections.through
    chatbot_field = next(
        field
        for field in through._meta.fields
        if getattr(field.remote_field, "model", None) is AIChatbot
    )
    section_field = next(
        field
        for field in through._meta.fields
        if getattr(field.remote_field, "model", None) is Section
    )
    through.objects.get_or_create(
        **{
            f"{chatbot_field.name}_id": chatbot.id,
            f"{section_field.name}_id": section.id,
        }
    )


def _ensure_discussion(
    tenant: Tenant,
    teacher: User,
    student: User,
    section: Section,
    course: Course,
    content: Content,
) -> DiscussionThread:
    thread, _ = DiscussionThread.objects.get_or_create(
        tenant=tenant,
        section=section,
        title=DEMO_THREAD_TITLE,
        defaults={
            "course": course,
            "content": content,
            "body": (
                "I made Cornell notes from the demo lesson, but I am not sure "
                "how to revise them without just rereading. What should I do next?"
            ),
            "author": student,
            "status": "open",
            "is_pinned": True,
            "view_count": 7,
        },
    )
    thread.course = course
    thread.content = content
    thread.body = (
        "I made Cornell notes from the demo lesson, but I am not sure how to "
        "revise them without just rereading. What should I do next?"
    )
    thread.author = student
    thread.status = "open"
    thread.is_pinned = True
    thread.view_count = max(thread.view_count, 7)
    thread.save(
        update_fields=[
            "course",
            "content",
            "body",
            "author",
            "status",
            "is_pinned",
            "view_count",
            "updated_at",
        ],
    )

    DiscussionReply.objects.get_or_create(
        thread=thread,
        author=teacher,
        body=(
            "Use the notes as prompts: cover the right column, answer from "
            "memory, then check and mark one gap to revisit tomorrow."
        ),
    )
    thread.update_reply_stats()
    return thread


def _demo_content_html() -> str:
    return """
<h2>Build notes for recall, not storage</h2>
<p><strong>Durable notes</strong> are short, searchable, and easy to test from memory.</p>
<ul>
  <li>Write one key idea per section.</li>
  <li>Add a question that forces recall.</li>
  <li>Review once today, once tomorrow, and once next week.</li>
</ul>
<p>End every lesson with a two-minute reflection: what changed in my understanding?</p>
""".strip()


def _demo_summary_data() -> dict:
    return {
        "summary": (
            "**Durable study notes** are designed for active recall rather than "
            "passive storage.\n\nThe strongest routine is simple: write a key "
            "idea, turn it into a question, answer from memory, then schedule "
            "a short revisit."
        ),
        "flashcards": [
            {
                "front": "What makes study notes durable?",
                "back": "They are organized around recall prompts, not copied paragraphs.",
            },
            {
                "front": "Why should students revisit notes tomorrow?",
                "back": "Spacing the review strengthens memory and exposes gaps early.",
            },
        ],
        "key_terms": [
            {
                "term": "Active recall",
                "definition": "Trying to retrieve an idea before checking the source.",
            },
            {
                "term": "Spaced repetition",
                "definition": "Reviewing learning over widening time intervals.",
            },
        ],
        "quiz_prep": [
            {
                "type": "short_answer",
                "question": "Describe a three-step note review routine.",
                "answer": "Cover the notes, recall the idea, check and mark gaps.",
                "options": [],
            }
        ],
        "mind_map": {
            "nodes": [
                {
                    "id": "core",
                    "label": "Durable Notes",
                    "type": "core",
                    "description": "Notes built for later retrieval.",
                },
                {
                    "id": "recall",
                    "label": "Active Recall",
                    "type": "process",
                    "description": "Answer before checking.",
                },
                {
                    "id": "spacing",
                    "label": "Spaced Review",
                    "type": "process",
                    "description": "Revisit over time.",
                },
            ],
            "edges": [
                {"source": "core", "target": "recall", "label": "uses"},
                {"source": "core", "target": "spacing", "label": "strengthened by"},
            ],
        },
    }
