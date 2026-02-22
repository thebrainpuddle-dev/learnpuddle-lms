from __future__ import annotations

from datetime import timedelta
from typing import Dict, Iterable, List, Set

from django.db.models import Sum
from django.db import IntegrityError
from django.utils import timezone

from apps.courses.models import Content
from apps.progress.models import AssignmentSubmission, QuizSubmission, TeacherProgress, TeacherQuestClaim

BADGE_LEVELS: List[Dict] = [
    {
        "level": 1,
        "key": "associate_educator",
        "name": "Associate Educator",
        "ripple_range": "0–200 RP",
        "min_points": 0,
        "max_points": 199,
        "color": "#4ECDC4",
    },
    {
        "level": 2,
        "key": "certified_teacher",
        "name": "Certified Teacher",
        "ripple_range": "200–600 RP",
        "min_points": 200,
        "max_points": 599,
        "color": "#45B7D1",
    },
    {
        "level": 3,
        "key": "senior_educator",
        "name": "Senior Educator",
        "ripple_range": "600–1,200 RP",
        "min_points": 600,
        "max_points": 1199,
        "color": "#6C63FF",
    },
    {
        "level": 4,
        "key": "lead_academic_mentor",
        "name": "Lead Academic Mentor",
        "ripple_range": "1,200–2,500 RP",
        "min_points": 1200,
        "max_points": 2499,
        "color": "#F7B731",
    },
    {
        "level": 5,
        "key": "master_faculty",
        "name": "Master Faculty",
        "ripple_range": "2,500+ RP",
        "min_points": 2500,
        "max_points": None,
        "color": "#FF6B6B",
    },
]

QUEST_KEY_STREAK_5 = "streak_5_days"
QUEST_REWARD_STREAK_5 = 5

# Points rules kept intentionally simple for the first gamified MVP.
POINTS_CONTENT_COMPLETION = 10
POINTS_COURSE_COMPLETION = 40
POINTS_ASSIGNMENT_SUBMIT = 15
POINTS_STREAK_DAY = 2


def _compute_current_streak(activity_days: Set) -> int:
    if not activity_days:
        return 0
    today = timezone.localdate()
    streak = 0
    cursor = today
    while cursor in activity_days:
        streak += 1
        cursor = cursor - timedelta(days=1)
    return streak


def _collect_activity_days(user_id, course_ids: Iterable[str]) -> Set:
    progress_days = TeacherProgress.objects.filter(
        teacher_id=user_id,
        course_id__in=course_ids,
    ).values_list("last_accessed", flat=True)
    regular_submission_days = AssignmentSubmission.objects.filter(
        teacher_id=user_id,
        assignment__course_id__in=course_ids,
    ).values_list("submitted_at", flat=True)
    quiz_submission_days = QuizSubmission.objects.filter(
        teacher_id=user_id,
        quiz__assignment__course_id__in=course_ids,
    ).values_list("submitted_at", flat=True)

    days = set()
    for dt in list(progress_days) + list(regular_submission_days) + list(quiz_submission_days):
        if dt is None:
            continue
        days.add(timezone.localtime(dt).date())

    # Logging in to dashboard counts as activity today for streak continuity.
    days.add(timezone.localdate())
    return days


def _find_current_badge(total_points: int) -> Dict:
    current = BADGE_LEVELS[0]
    for badge in BADGE_LEVELS:
        max_points = badge["max_points"]
        if max_points is None and total_points >= badge["min_points"]:
            current = badge
        elif max_points is not None and badge["min_points"] <= total_points <= max_points:
            current = badge
    return current


def _build_badge_progress(total_points: int) -> List[Dict]:
    badges = []
    for badge in BADGE_LEVELS:
        max_points = badge["max_points"]
        unlocked = total_points >= badge["min_points"]
        if max_points is None:
            progress_pct = 100 if unlocked else 0
        else:
            span = max(1, max_points - badge["min_points"] + 1)
            progress_pct = int(min(100, max(0, ((total_points - badge["min_points"] + 1) / span) * 100)))
        badges.append(
            {
                **badge,
                "unlocked": unlocked,
                "progress_percentage": progress_pct,
                "style": "glass_3d",
            }
        )
    return badges


def build_teacher_gamification_summary(user, courses_qs) -> Dict:
    courses = list(courses_qs)
    course_ids = [str(course.id) for course in courses]
    if not course_ids:
        return {
            "points_total": 0,
            "points_breakdown": {
                "content_completion": 0,
                "course_completion": 0,
                "assignment_submission": 0,
                "streak_bonus": 0,
                "quest_bonus": 0,
            },
            "streak": {"current_days": 1, "target_days": 5},
            "quest": {
                "key": QUEST_KEY_STREAK_5,
                "title": "Log in 5 days straight",
                "description": "Build consistency by showing up for five consecutive days.",
                "reward_points": QUEST_REWARD_STREAK_5,
                "progress_current": 1,
                "progress_target": 5,
                "completed": False,
                "claimable": False,
                "claimed_today": False,
            },
            "badge_current": {**BADGE_LEVELS[0], "style": "glass_3d"},
            "badges": _build_badge_progress(0),
        }

    completed_contents = TeacherProgress.objects.filter(
        teacher=user,
        course_id__in=course_ids,
        content__isnull=False,
        status="COMPLETED",
    ).count()

    completed_courses = 0
    for course in courses:
        total = Content.objects.filter(module__course=course, is_active=True).count()
        if total == 0:
            continue
        completed = TeacherProgress.objects.filter(
            teacher=user,
            course=course,
            content__isnull=False,
            status="COMPLETED",
        ).count()
        if completed >= total:
            completed_courses += 1

    assignment_submissions = AssignmentSubmission.objects.filter(
        teacher=user,
        assignment__course_id__in=course_ids,
        status__in=["SUBMITTED", "GRADED"],
    ).count()
    quiz_submissions = QuizSubmission.objects.filter(
        teacher=user,
        quiz__assignment__course_id__in=course_ids,
    ).count()

    activity_days = _collect_activity_days(user.id, course_ids)
    current_streak = _compute_current_streak(activity_days)
    today = timezone.localdate()
    claimed_today = TeacherQuestClaim.objects.filter(
        teacher=user,
        quest_key=QUEST_KEY_STREAK_5,
        claim_date=today,
    ).exists()
    quest_bonus_points = (
        TeacherQuestClaim.objects.filter(
            teacher=user,
            quest_key=QUEST_KEY_STREAK_5,
        ).aggregate(total=Sum("points_awarded"))["total"]
        or 0
    )

    points_from_content = completed_contents * POINTS_CONTENT_COMPLETION
    points_from_courses = completed_courses * POINTS_COURSE_COMPLETION
    points_from_assignments = (assignment_submissions + quiz_submissions) * POINTS_ASSIGNMENT_SUBMIT
    points_from_streak = current_streak * POINTS_STREAK_DAY

    points_total = (
        points_from_content
        + points_from_courses
        + points_from_assignments
        + points_from_streak
        + quest_bonus_points
    )

    quest_completed = current_streak >= 5
    quest_claimable = quest_completed and not claimed_today
    current_badge = _find_current_badge(points_total)

    return {
        "points_total": points_total,
        "points_breakdown": {
            "content_completion": points_from_content,
            "course_completion": points_from_courses,
            "assignment_submission": points_from_assignments,
            "streak_bonus": points_from_streak,
            "quest_bonus": quest_bonus_points,
        },
        "streak": {"current_days": current_streak, "target_days": 5},
        "quest": {
            "key": QUEST_KEY_STREAK_5,
            "title": "Log in 5 days straight",
            "description": "Build consistency by showing up for five consecutive days.",
            "reward_points": QUEST_REWARD_STREAK_5,
            "progress_current": min(5, current_streak),
            "progress_target": 5,
            "completed": quest_completed,
            "claimable": quest_claimable,
            "claimed_today": claimed_today,
        },
        "badge_current": {**current_badge, "style": "glass_3d"},
        "badges": _build_badge_progress(points_total),
    }


def claim_quest_reward(user, courses_qs, quest_key: str) -> Dict:
    if quest_key != QUEST_KEY_STREAK_5:
        raise ValueError("Unsupported quest key.")

    summary = build_teacher_gamification_summary(user, courses_qs)
    quest = summary["quest"]
    if not quest["claimable"]:
        raise PermissionError("Quest is not claimable yet.")

    today = timezone.localdate()
    try:
        TeacherQuestClaim.objects.create(
            teacher=user,
            quest_key=quest_key,
            claim_date=today,
            points_awarded=QUEST_REWARD_STREAK_5,
        )
    except IntegrityError as exc:
        raise PermissionError("Quest reward already claimed for today.") from exc

    return build_teacher_gamification_summary(user, courses_qs)
