# apps/courses/chatbot_auto_ingest.py
"""
Celery tasks for automatic ingestion of course content into AI chatbot
knowledge bases.

When a chatbot is assigned to sections, all published ACADEMIC course content
targeting those sections is automatically ingested.  When new content is added
to a published course, it is pushed to every matching chatbot.
"""
import hashlib
import logging
from typing import Optional

from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

from apps.courses.chatbot_models import AIChatbot, AIChatbotKnowledge
from apps.courses.chatbot_tasks import ingest_chatbot_knowledge
from apps.courses.models import Content, Course, Module
from apps.courses.video_models import VideoTranscript
from apps.progress.models import Assignment, Quiz, QuizQuestion
from utils.tenant_middleware import set_current_tenant, clear_current_tenant

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _content_hash(text: str) -> str:
    """Generate a SHA-256 hash of the given text for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_quiz_text(quiz: Quiz) -> str:
    """
    Format quiz questions into readable study-aid text.

    Includes the question prompt, answer options, and explanation.
    NEVER includes ``correct_answer`` — this is a learning aid, not a cheat
    sheet.
    """
    questions = QuizQuestion.all_objects.filter(quiz=quiz).order_by("order")
    if not questions.exists():
        return ""

    lines: list[str] = []
    for idx, q in enumerate(questions, start=1):
        lines.append(f"Question {idx}: {q.prompt}")

        # Options (MCQ / True-False)
        if q.options:
            for opt_idx, option in enumerate(q.options, start=1):
                # option may be a plain string or a dict with a "text" key
                opt_text = option if isinstance(option, str) else option.get("text", str(option))
                lines.append(f"  {opt_idx}. {opt_text}")

        if q.explanation:
            lines.append(f"  Explanation: {q.explanation}")

        lines.append("")  # blank separator between questions

    return "\n".join(lines).strip()


def _source_type_for_content(content: Content) -> Optional[str]:
    """Map a ``Content.content_type`` to an ``AIChatbotKnowledge.source_type``."""
    ct = content.content_type
    if ct == "DOCUMENT":
        file_url = content.file_url or ""
        if file_url.lower().endswith(".pdf"):
            return "pdf"
        return "document"
    if ct == "TEXT":
        return "text"
    if ct == "VIDEO":
        return "text"  # transcript text
    if ct == "LINK":
        return "url"
    return None  # AI_CLASSROOM, CHATBOT — skip


def _knowledge_exists(chatbot_id, content_id) -> bool:
    """Return True if an auto-ingested knowledge entry already exists."""
    return AIChatbotKnowledge.all_objects.filter(
        chatbot_id=chatbot_id,
        content_source_id=content_id,
    ).exists()


def _create_knowledge_for_content(
    chatbot: AIChatbot,
    content: Content,
) -> Optional[AIChatbotKnowledge]:
    """
    Create an ``AIChatbotKnowledge`` record for a single Content item and
    return it, or ``None`` if the content should be skipped.
    """
    if _knowledge_exists(chatbot.id, content.id):
        return None

    source_type = _source_type_for_content(content)
    if source_type is None:
        return None

    title = content.title or str(content.id)
    raw_text = ""
    file_url = ""
    c_hash = ""

    if content.content_type == "TEXT":
        raw_text = (content.text_content or "").strip()
        if not raw_text:
            logger.debug(
                "Skipping TEXT content %s for chatbot %s — empty text",
                content.id, chatbot.id,
            )
            return None
        c_hash = _content_hash(raw_text)

    elif content.content_type == "VIDEO":
        # Try to get transcript via VideoAsset -> VideoTranscript
        transcript_text = ""
        try:
            video_asset = content.video_asset
            transcript = video_asset.transcript
            transcript_text = (transcript.full_text or "").strip()
        except (AttributeError, ObjectDoesNotExist):
            pass
        if not transcript_text:
            logger.debug(
                "Skipping VIDEO content %s for chatbot %s — no transcript",
                content.id, chatbot.id,
            )
            return None
        raw_text = transcript_text
        c_hash = _content_hash(raw_text)

    elif content.content_type == "DOCUMENT":
        file_url = content.file_url or ""
        if not file_url:
            logger.debug(
                "Skipping DOCUMENT content %s for chatbot %s — no file_url",
                content.id, chatbot.id,
            )
            return None
        c_hash = _content_hash(file_url)

    elif content.content_type == "LINK":
        file_url = content.file_url or ""
        if not file_url:
            logger.debug(
                "Skipping LINK content %s for chatbot %s — no file_url",
                content.id, chatbot.id,
            )
            return None
        c_hash = _content_hash(file_url)

    knowledge = AIChatbotKnowledge.all_objects.create(
        chatbot=chatbot,
        tenant=chatbot.tenant,
        content_source=content,
        is_auto=True,
        source_type=source_type,
        title=title,
        raw_text=raw_text,
        file_url=file_url,
        content_hash=c_hash,
        embedding_status="pending",
    )
    return knowledge


def _create_knowledge_for_assignment(
    chatbot: AIChatbot,
    assignment: Assignment,
) -> Optional[AIChatbotKnowledge]:
    """
    Create a knowledge record for an Assignment's description + instructions.
    Uses ``content_source`` linked to the assignment's content FK when
    available, otherwise uses a title-based dedup via content_hash.
    """
    parts: list[str] = []
    if assignment.description:
        parts.append(assignment.description.strip())
    if assignment.instructions:
        parts.append(assignment.instructions.strip())
    raw_text = "\n\n".join(parts).strip()
    if not raw_text:
        return None

    c_hash = _content_hash(f"assignment:{assignment.id}")

    # Dedup: check by hash + chatbot
    if AIChatbotKnowledge.all_objects.filter(
        chatbot=chatbot,
        content_hash=c_hash,
    ).exists():
        return None

    knowledge = AIChatbotKnowledge.all_objects.create(
        chatbot=chatbot,
        tenant=chatbot.tenant,
        content_source=assignment.content,  # may be None
        is_auto=True,
        source_type="text",
        title=f"Assignment: {assignment.title}",
        raw_text=raw_text,
        content_hash=c_hash,
        embedding_status="pending",
    )
    return knowledge


def _create_knowledge_for_quiz(
    chatbot: AIChatbot,
    quiz: Quiz,
) -> Optional[AIChatbotKnowledge]:
    """
    Create a knowledge record for a Quiz (formatted questions, no answers).
    """
    raw_text = _build_quiz_text(quiz)
    if not raw_text:
        return None

    c_hash = _content_hash(f"quiz:{quiz.id}")

    if AIChatbotKnowledge.all_objects.filter(
        chatbot=chatbot,
        content_hash=c_hash,
    ).exists():
        return None

    knowledge = AIChatbotKnowledge.all_objects.create(
        chatbot=chatbot,
        tenant=chatbot.tenant,
        content_source=quiz.assignment.content if quiz.assignment else None,
        is_auto=True,
        source_type="text",
        title=f"Quiz: {quiz.assignment.title}" if quiz.assignment else "Quiz",
        raw_text=raw_text,
        content_hash=c_hash,
        embedding_status="pending",
    )
    return knowledge


# ---------------------------------------------------------------------------
# Celery Tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, soft_time_limit=600, time_limit=660)
def auto_ingest_course_content(self, chatbot_id: str):
    """
    Ingest all published ACADEMIC course content into a chatbot's knowledge
    base.

    Finds every published ACADEMIC course whose ``target_sections`` overlap
    with the chatbot's ``sections``, then creates ``AIChatbotKnowledge``
    entries for each piece of active content, each assignment, and each quiz.
    Already-existing entries (by ``content_source`` or ``content_hash``) are
    skipped.
    """
    try:
        chatbot = AIChatbot.all_objects.select_related("tenant").get(pk=chatbot_id)
    except AIChatbot.DoesNotExist:
        logger.error("auto_ingest_course_content: chatbot %s not found", chatbot_id)
        return

    tenant = chatbot.tenant
    set_current_tenant(tenant)

    try:
        section_ids = list(
            chatbot.sections.values_list("id", flat=True)
        )
        if not section_ids:
            logger.info(
                "auto_ingest_course_content: chatbot %s has no sections — nothing to ingest",
                chatbot_id,
            )
            return

        # Find published ACADEMIC courses targeting any of the chatbot's sections
        courses = Course.all_objects.filter(
            tenant=tenant,
            is_published=True,
            course_type="ACADEMIC",
            target_sections__id__in=section_ids,
        ).distinct()

        created_count = 0

        for course in courses:
            # --- Content items ---
            modules = Module.all_objects.filter(
                course=course, is_active=True,
            ).exclude(is_deleted=True)
            contents = Content.all_objects.filter(
                module__in=modules,
                is_active=True,
            ).exclude(is_deleted=True).select_related("module")

            for content in contents:
                if content.content_type in ("AI_CLASSROOM", "CHATBOT"):
                    continue
                knowledge = _create_knowledge_for_content(chatbot, content)
                if knowledge:
                    ingest_chatbot_knowledge.delay(str(knowledge.id))
                    created_count += 1

            # --- Assignments ---
            assignments = Assignment.all_objects.filter(
                course=course,
                is_active=True,
            ).exclude(is_deleted=True)

            for assignment in assignments:
                knowledge = _create_knowledge_for_assignment(chatbot, assignment)
                if knowledge:
                    ingest_chatbot_knowledge.delay(str(knowledge.id))
                    created_count += 1

                # --- Quizzes ---
                try:
                    quiz = assignment.quiz
                    knowledge = _create_knowledge_for_quiz(chatbot, quiz)
                    if knowledge:
                        ingest_chatbot_knowledge.delay(str(knowledge.id))
                        created_count += 1
                except Quiz.DoesNotExist:
                    pass

        logger.info(
            "auto_ingest_course_content: chatbot %s — created %d knowledge entries",
            chatbot_id, created_count,
        )

    except Exception as exc:
        logger.exception(
            "auto_ingest_course_content failed for chatbot %s", chatbot_id
        )
        raise self.retry(exc=exc, countdown=120)
    finally:
        clear_current_tenant()


@shared_task(bind=True, max_retries=2, soft_time_limit=300, time_limit=360)
def auto_ingest_single_content(self, content_id: str):
    """
    Ingest a single Content item into every chatbot whose sections overlap
    with the content's course ``target_sections``.

    Called when new content is created or updated in a published ACADEMIC
    course.
    """
    try:
        content = Content.all_objects.select_related(
            "module__course",
        ).get(pk=content_id)
    except Content.DoesNotExist:
        logger.error("auto_ingest_single_content: content %s not found", content_id)
        return

    course = content.module.course
    if not course.is_published or course.course_type != "ACADEMIC":
        logger.debug(
            "auto_ingest_single_content: course %s is not published/ACADEMIC — skipping",
            course.id,
        )
        return

    if not content.is_active:
        logger.debug(
            "auto_ingest_single_content: content %s is not active — skipping",
            content.id,
        )
        return

    if content.content_type in ("AI_CLASSROOM", "CHATBOT"):
        return

    tenant = course.tenant
    set_current_tenant(tenant)

    try:
        section_ids = list(
            course.target_sections.values_list("id", flat=True)
        )
        if not section_ids:
            return

        # Find chatbots that share at least one section with this course
        chatbots = AIChatbot.all_objects.filter(
            tenant=tenant,
            is_active=True,
            sections__id__in=section_ids,
        ).distinct().select_related("tenant")

        created_count = 0
        for chatbot in chatbots:
            knowledge = _create_knowledge_for_content(chatbot, content)
            if knowledge:
                ingest_chatbot_knowledge.delay(str(knowledge.id))
                created_count += 1

        if created_count:
            logger.info(
                "auto_ingest_single_content: content %s — created %d knowledge entries across chatbots",
                content_id, created_count,
            )

    except Exception as exc:
        logger.exception(
            "auto_ingest_single_content failed for content %s", content_id
        )
        raise self.retry(exc=exc, countdown=120)
    finally:
        clear_current_tenant()
