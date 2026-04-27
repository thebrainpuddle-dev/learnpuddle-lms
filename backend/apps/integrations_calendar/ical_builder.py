"""
iCalendar feed builder.

Generates a VCALENDAR with VEVENTs for a user's LMS deadlines,
assignments, and quiz due dates.

Requires: icalendar>=5.0 (added to requirements.txt by TASK-054).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone as dt_timezone
from typing import TYPE_CHECKING

from django.conf import settings
from django.utils import timezone

try:
    from icalendar import Calendar, Event, vText, vDatetime
    ICALENDAR_AVAILABLE = True
except ImportError:
    ICALENDAR_AVAILABLE = False

if TYPE_CHECKING:
    from apps.users.models import User

logger = logging.getLogger(__name__)

PLATFORM_DOMAIN = getattr(settings, "PLATFORM_DOMAIN", "learnpuddle.com")


def _uid(source_type: str, source_id: str, tenant_subdomain: str) -> str:
    """
    Stable RFC 5545 UID for a calendar event.
    Pattern: lp-{source_type}-{source_id}@{subdomain}.{domain}
    """
    return f"lp-{source_type}-{source_id}@{tenant_subdomain}.{PLATFORM_DOMAIN}"


def _to_dt(value) -> datetime:
    """Normalise a date or datetime to a UTC-aware datetime."""
    if value is None:
        return timezone.now()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt_timezone.utc)
        return value.astimezone(dt_timezone.utc)
    # date object — treat as midnight UTC
    return datetime(value.year, value.month, value.day, tzinfo=dt_timezone.utc)


def build_ical_feed(user: "User") -> bytes:
    """
    Build and return an RFC 5545 iCalendar feed (bytes) for *user*.

    Includes:
    - Assignment due dates
    - Quiz deadlines (via assignment)
    - Enrollment deadlines (course enrollment_end_date)

    All events are DTSTART / DTEND / UID / SUMMARY / DESCRIPTION only.
    """
    if not ICALENDAR_AVAILABLE:
        raise RuntimeError(
            "icalendar package is not installed. "
            "Add icalendar>=5.0 to requirements.txt."
        )

    tenant = getattr(user, "tenant", None)
    subdomain = tenant.subdomain if tenant else "learnpuddle"

    cal = Calendar()
    cal.add("prodid", f"-//LearnPuddle LMS//{PLATFORM_DOMAIN}//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", "LearnPuddle — My Deadlines")
    cal.add("x-wr-caldesc", "Course deadlines and assignments from LearnPuddle LMS")

    events_added = 0

    # --- Assignment due dates ---
    try:
        from apps.progress.models import Assignment

        assignments = Assignment.objects.all_objects.filter(
            course__in=_user_course_ids(user),
            due_date__isnull=False,
            is_active=True,
        ).select_related("course")

        for assignment in assignments:
            due = _to_dt(assignment.due_date)
            event = Event()
            event.add("uid", _uid("assignment", str(assignment.id), subdomain))
            event.add("summary", f"[LearnPuddle] {assignment.title} — Due")
            event.add("description", assignment.description[:500] if assignment.description else "")
            event.add("dtstart", due)
            event.add("dtend", due)
            event.add("dtstamp", timezone.now())
            cal.add_component(event)
            events_added += 1
    except Exception:
        logger.exception("ical_builder: error collecting assignment events for user=%s", user.pk)

    # --- Enrollment deadlines ---
    try:
        from apps.courses.models import Enrollment

        enrollments = Enrollment.objects.filter(
            user=user,
            enrollment_end_date__isnull=False,
        ).select_related("course")

        for enrollment in enrollments:
            due = _to_dt(enrollment.enrollment_end_date)
            event = Event()
            event.add("uid", _uid("deadline", str(enrollment.id), subdomain))
            event.add("summary", f"[LearnPuddle] {enrollment.course.title} — Enrollment Ends")
            event.add("description", f"Course enrollment ends on {enrollment.enrollment_end_date}.")
            event.add("dtstart", due)
            event.add("dtend", due)
            event.add("dtstamp", timezone.now())
            cal.add_component(event)
            events_added += 1
    except Exception:
        logger.exception("ical_builder: error collecting enrollment events for user=%s", user.pk)

    logger.debug("ical_builder: built feed for user=%s events=%d", user.pk, events_added)
    return cal.to_ical()


def _user_course_ids(user):
    """Return queryset / list of course PKs the user is enrolled in or assigned to."""
    try:
        from apps.courses.models import Enrollment
        return Enrollment.objects.filter(user=user).values_list("course_id", flat=True)
    except Exception:
        return []
