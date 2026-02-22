from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from apps.courses.models import Content, Course
from apps.progress.models import TeacherProgress


@dataclass
class ModuleSequenceState:
    completed_content_count: int
    total_content_count: int
    completion_percentage: float
    is_completed: bool
    is_locked: bool
    lock_reason: str


@dataclass
class ContentSequenceState:
    is_locked: bool
    lock_reason: str


def _content_progress_status_map(teacher_id, course: Course) -> Dict[str, str]:
    progress_rows = TeacherProgress.objects.filter(
        teacher_id=teacher_id,
        course=course,
        content__isnull=False,
    ).values("content_id", "status")
    return {str(row["content_id"]): row["status"] for row in progress_rows}


def compute_course_sequence_state(
    course: Course,
    teacher_id,
) -> Tuple[Dict[str, ModuleSequenceState], Dict[str, ContentSequenceState]]:
    """
    Compute module/content lock state for a course.

    Locking rules:
    1) Module N+1 is locked until module N is completed.
    2) Within an unlocked module, lesson K+1 is locked until lesson K is completed.
    """
    status_map = _content_progress_status_map(teacher_id, course)
    modules = (
        course.modules.filter(is_active=True)
        .prefetch_related("contents")
        .order_by("order", "created_at")
    )

    module_state_by_id: Dict[str, ModuleSequenceState] = {}
    content_state_by_id: Dict[str, ContentSequenceState] = {}
    previous_module_completed = True

    for module in modules:
        contents: List[Content] = list(module.contents.filter(is_active=True).order_by("order", "created_at"))
        total_count = len(contents)
        completed_count = sum(1 for item in contents if status_map.get(str(item.id)) == "COMPLETED")
        completion_percentage = round((completed_count / total_count) * 100.0, 2) if total_count else 100.0
        is_module_completed = total_count == 0 or completed_count >= total_count

        is_module_locked = not previous_module_completed
        module_lock_reason = (
            "Finish the previous module to unlock this one."
            if is_module_locked
            else ""
        )

        module_state_by_id[str(module.id)] = ModuleSequenceState(
            completed_content_count=completed_count,
            total_content_count=total_count,
            completion_percentage=completion_percentage,
            is_completed=is_module_completed,
            is_locked=is_module_locked,
            lock_reason=module_lock_reason,
        )

        previous_content_completed = True
        for index, item in enumerate(contents):
            content_locked = False
            lock_reason = ""
            if is_module_locked:
                content_locked = True
                lock_reason = module_lock_reason
            elif index > 0 and not previous_content_completed:
                content_locked = True
                lock_reason = "Complete the previous lesson to continue."

            content_state_by_id[str(item.id)] = ContentSequenceState(
                is_locked=content_locked,
                lock_reason=lock_reason,
            )

            item_completed = status_map.get(str(item.id)) == "COMPLETED"
            previous_content_completed = previous_content_completed and item_completed

        previous_module_completed = is_module_completed

    return module_state_by_id, content_state_by_id


def get_content_lock_state(
    course: Course,
    content_id: str,
    teacher_id,
) -> ContentSequenceState:
    _module_state, content_state = compute_course_sequence_state(course, teacher_id)
    return content_state.get(str(content_id), ContentSequenceState(is_locked=False, lock_reason=""))
