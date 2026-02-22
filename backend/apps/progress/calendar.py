from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Dict, Iterable, List

from django.utils import timezone

from apps.notifications.models import Notification
from apps.progress.models import Assignment


def _to_date(raw: str | None, default_date: date) -> date:
    if not raw:
        return default_date
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default_date


def _to_time_label(dt: datetime | None, fallback_hour: int = 9) -> str:
    if dt is None:
        return f"{fallback_hour:02d}:00"
    return timezone.localtime(dt).strftime("%H:%M")


def _end_time_label(start_label: str, duration_minutes: int = 45) -> str:
    start = datetime.strptime(start_label, "%H:%M")
    end = start + timedelta(minutes=duration_minutes)
    return end.strftime("%H:%M")


def build_teacher_calendar_window(
    user,
    courses_qs,
    start_date_raw: str | None = None,
    days: int = 5,
) -> Dict:
    days = min(7, max(3, int(days)))
    today = timezone.localdate()
    start_date = _to_date(start_date_raw, today)
    end_date = start_date + timedelta(days=days - 1)
    course_ids = list(courses_qs.values_list("id", flat=True))

    events: List[Dict] = []

    course_deadlines = (
        courses_qs.exclude(deadline__isnull=True)
        .filter(deadline__gte=start_date, deadline__lte=end_date)
        .order_by("deadline")
    )
    for idx, course in enumerate(course_deadlines):
        start_time = f"{9 + (idx % 5):02d}:00"
        events.append(
            {
                "id": f"course-{course.id}",
                "type": "course_deadline",
                "title": course.title,
                "subtitle": "Course deadline",
                "date": course.deadline.isoformat(),
                "start_time": start_time,
                "end_time": _end_time_label(start_time, 60),
                "color": "amber",
                "route": f"/teacher/courses/{course.id}",
            }
        )

    assignment_deadlines = (
        Assignment.objects.filter(
            course_id__in=course_ids,
            is_active=True,
            due_date__isnull=False,
            due_date__date__gte=start_date,
            due_date__date__lte=end_date,
        )
        .select_related("course")
        .order_by("due_date")
    )
    for assignment in assignment_deadlines:
        local_due = timezone.localtime(assignment.due_date)
        start_time = _to_time_label(local_due, fallback_hour=11)
        events.append(
            {
                "id": f"assignment-{assignment.id}",
                "type": "assignment_due",
                "title": assignment.title,
                "subtitle": assignment.course.title,
                "date": local_due.date().isoformat(),
                "start_time": start_time,
                "end_time": _end_time_label(start_time, 45),
                "color": "rose",
                "route": "/teacher/assignments",
            }
        )

    reminder_events = Notification.objects.filter(
        teacher=user,
        notification_type__in=["REMINDER", "ASSIGNMENT_DUE"],
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
    ).order_by("created_at")[:20]
    for idx, notification in enumerate(reminder_events):
        local_created = timezone.localtime(notification.created_at)
        start_time = local_created.strftime("%H:%M") if notification.notification_type == "ASSIGNMENT_DUE" else f"{15 + (idx % 3):02d}:00"
        events.append(
            {
                "id": f"notification-{notification.id}",
                "type": "reminder",
                "title": notification.title,
                "subtitle": "Reminder",
                "date": local_created.date().isoformat(),
                "start_time": start_time,
                "end_time": _end_time_label(start_time, 30),
                "color": "sky",
                "route": "/teacher/reminders",
            }
        )

    events.sort(key=lambda item: (item["date"], item["start_time"], item["title"]))

    day_rows = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        day_events = [event for event in events if event["date"] == day.isoformat()]
        total_minutes = 0
        for event in day_events:
            try:
                start_dt = datetime.strptime(event["start_time"], "%H:%M")
                end_dt = datetime.strptime(event["end_time"], "%H:%M")
                total_minutes += int((end_dt - start_dt).total_seconds() / 60)
            except ValueError:
                total_minutes += 45

        day_rows.append(
            {
                "date": day.isoformat(),
                "weekday": day.strftime("%A"),
                "short_weekday": day.strftime("%a"),
                "day": day.day,
                "month": day.strftime("%b"),
                "is_today": day == today,
                "task_count": len(day_events),
                "total_minutes": total_minutes,
            }
        )

    return {
        "window": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "days": days,
        },
        "days": day_rows,
        "events": events,
    }
