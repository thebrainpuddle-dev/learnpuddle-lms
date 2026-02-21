import logging

from celery import shared_task

from .services import run_automated_course_deadline_reminders

logger = logging.getLogger(__name__)


@shared_task(name="reminders.send_automated_course_deadline_reminders")
def send_automated_course_deadline_reminders():
    summary = run_automated_course_deadline_reminders()
    logger.info("automated course reminders summary=%s", summary)
    return summary
