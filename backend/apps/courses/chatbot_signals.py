# apps/courses/chatbot_signals.py
"""
Django signal handlers for automatic chatbot knowledge ingestion.

Connected in ``apps.courses.apps.CoursesConfig.ready()``.
"""
import logging

logger = logging.getLogger(__name__)


def on_content_created_or_updated(sender, instance, **kwargs):
    """
    ``post_save`` handler for ``Content``.

    When an active content item is saved inside a published ACADEMIC course,
    queue it for ingestion into every chatbot whose sections overlap with the
    course's ``target_sections``.
    """
    content = instance

    if not content.is_active:
        return

    # Skip content types that are never ingested
    if content.content_type in ("AI_CLASSROOM", "CHATBOT"):
        return

    # Walk up to the course (Content -> Module -> Course)
    try:
        module = content.module
        course = module.course
    except Exception:
        logger.debug(
            "on_content_created_or_updated: could not resolve course for content %s",
            content.pk,
        )
        return

    if not course.is_published or course.course_type != "ACADEMIC":
        return

    # Delay import to avoid circular imports at module load time
    from apps.courses.chatbot_auto_ingest import auto_ingest_single_content

    auto_ingest_single_content.delay(str(content.id))


def on_chatbot_sections_changed(sender, instance, action, **kwargs):
    """
    ``m2m_changed`` handler for ``AIChatbot.sections``.

    When sections are added to or removed from a chatbot, re-sync all
    course content so the knowledge base reflects the new section scope.

    ``instance`` is the ``AIChatbot`` when sections are changed via
    ``chatbot.sections.add(...)`` / ``chatbot.sections.remove(...)``.
    """
    if action not in ("post_add", "post_remove"):
        return

    chatbot = instance

    # Delay import to avoid circular imports at module load time
    from apps.courses.chatbot_auto_ingest import auto_ingest_course_content

    auto_ingest_course_content.delay(str(chatbot.id))
    logger.info(
        "on_chatbot_sections_changed: queued auto_ingest_course_content for chatbot %s (action=%s)",
        chatbot.id, action,
    )
