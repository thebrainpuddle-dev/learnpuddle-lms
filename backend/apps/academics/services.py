# apps/academics/services.py
"""
Core academic business logic:
- Auto-generated student/teacher IDs (atomic counter)
- Course auto-assignment based on section targeting
- Course cloning with deep content copy
- Academic year promotion workflow
"""

import logging
from django.db import transaction
from django.db.models import F

logger = logging.getLogger(__name__)


# ─── Auto-Generated User IDs ─────────────────────────────────────────────────

def generate_student_id(tenant) -> str:
    """
    Generate the next student ID atomically.
    Format: {prefix}-S-{zero_padded_counter}  e.g. KIS-S-0001

    Uses SELECT FOR UPDATE to prevent TOCTOU race conditions.
    Two concurrent requests will serialize via the row lock.
    """
    from apps.tenants.models import Tenant

    with transaction.atomic():
        t = Tenant.objects.select_for_update().get(pk=tenant.pk)
        counter = t.student_id_counter
        t.student_id_counter = counter + 1
        t.save(update_fields=['student_id_counter'])

    prefix = t.id_prefix or 'LP'
    return f"{prefix}-S-{counter:04d}"


def generate_teacher_id(tenant) -> str:
    """
    Generate the next teacher ID atomically.
    Format: {prefix}-T-{zero_padded_counter}  e.g. KIS-T-0001

    Uses SELECT FOR UPDATE to prevent TOCTOU race conditions.
    """
    from apps.tenants.models import Tenant

    with transaction.atomic():
        t = Tenant.objects.select_for_update().get(pk=tenant.pk)
        counter = t.teacher_id_counter
        t.teacher_id_counter = counter + 1
        t.save(update_fields=['teacher_id_counter'])

    prefix = t.id_prefix or 'LP'
    return f"{prefix}-T-{counter:04d}"


# ─── Course Auto-Assignment ──────────────────────────────────────────────────

def auto_assign_course_students(course):
    """
    Populate course.assigned_students based on target_sections / target_grades.

    Logic:
    1. If target_sections are set → students in those sections
    2. Else if target_grades are set → all students in those grades
    3. Else → no auto-assignment (manual only)

    Called on course publish and when new students join a section.
    """
    from apps.users.models import User

    if course.course_type != 'ACADEMIC':
        return 0

    target_sections = course.target_sections.all()
    if target_sections.exists():
        students = User.objects.filter(
            tenant=course.tenant,
            section_fk__in=target_sections,
            role='STUDENT',
            is_deleted=False,
            is_active=True,
        )
    else:
        target_grades = course.target_grades.all()
        if target_grades.exists():
            students = User.objects.filter(
                tenant=course.tenant,
                grade_fk__in=target_grades,
                role='STUDENT',
                is_deleted=False,
                is_active=True,
            )
        else:
            return 0

    student_ids = list(students.values_list('id', flat=True))
    if student_ids:
        course.assigned_students.add(*student_ids)
        logger.info(
            "Auto-assigned %d students to course %s (%s)",
            len(student_ids), course.title, course.id,
        )
    return len(student_ids)


def reassign_student_courses(student, old_section=None):
    """
    When a student changes section, update their course assignments.
    Remove courses from old section, add courses from new section.
    Preserve non-academic (manual) assignments.
    """
    from apps.courses.models import Course

    # Remove student from academic courses targeting the old section
    if old_section:
        old_courses = Course.objects.filter(
            tenant=student.tenant,
            target_sections=old_section,
            course_type='ACADEMIC',
            is_deleted=False,
        ).exclude(
            target_sections=student.section_fk,  # Keep if also targets new section
        )
        for course in old_courses:
            course.assigned_students.remove(student)

    if not student.section_fk:
        return

    # Add student to published academic courses targeting new section
    new_courses = Course.objects.filter(
        tenant=student.tenant,
        target_sections=student.section_fk,
        course_type='ACADEMIC',
        is_published=True,
        is_active=True,
    )

    for course in new_courses:
        course.assigned_students.add(student)


# ─── Course Cloning ──────────────────────────────────────────────────────────

@transaction.atomic
def clone_course(original_course, new_title=None, new_target_sections=None, cloned_by=None):
    """
    Deep-clone a course: copies modules + contents, resets progress/assignments.

    Args:
        original_course: Course instance to clone
        new_title: Optional title for the clone (defaults to "Original (Copy)")
        new_target_sections: Optional queryset/list of Section instances
        cloned_by: User who initiated the clone

    Returns:
        New Course instance (unpublished, no students assigned)
    """
    from apps.courses.models import Course, Module, Content

    # Create the new course
    new_course = Course(
        tenant=original_course.tenant,
        title=new_title or f"{original_course.title} (Copy)",
        slug='',  # Will be auto-generated by Course.save()
        description=original_course.description,
        thumbnail=original_course.thumbnail,
        is_mandatory=original_course.is_mandatory,
        estimated_hours=original_course.estimated_hours,
        course_type=original_course.course_type,
        subject=original_course.subject,
        is_published=False,  # Always start unpublished
        is_active=True,
        created_by=cloned_by,
    )
    new_course.save()  # Triggers slug generation

    # Copy M2M: target grades
    new_course.target_grades.set(original_course.target_grades.all())

    # Set target sections (new or copied)
    if new_target_sections is not None:
        new_course.target_sections.set(new_target_sections)
    else:
        new_course.target_sections.set(original_course.target_sections.all())

    # Deep-copy modules and their contents
    for module in original_course.modules.filter(is_deleted=False).order_by('order'):
        old_module_pk = module.pk
        module.pk = None  # Clear PK to create new instance
        module.course = new_course
        module.save()

        # Copy contents within this module
        from apps.courses.models import Content
        for content in Content.objects.filter(
            module_id=old_module_pk, is_deleted=False,
        ).order_by('order'):
            content.pk = None
            content.module = module
            content.save()

    logger.info(
        "Cloned course '%s' → '%s' (by %s)",
        original_course.title, new_course.title,
        cloned_by.get_full_name() if cloned_by else 'system',
    )
    return new_course


# ─── Academic Year Promotion ─────────────────────────────────────────────────

def get_promotion_preview(tenant):
    """
    Generate a preview of what the promotion workflow will do.
    Returns a list of grade-level promotion plans with student counts.
    """
    from apps.academics.models import Grade
    from apps.users.models import User

    grades = list(
        Grade.all_objects.filter(tenant=tenant).order_by('order')
    )

    if not grades:
        return []

    max_order = grades[-1].order
    preview = []

    for i, grade in enumerate(grades):
        student_count = User.objects.filter(
            tenant=tenant,
            grade_fk=grade,
            role='STUDENT',
            is_deleted=False,
            is_active=True,
        ).count()

        next_grade = grades[i + 1] if i + 1 < len(grades) else None

        preview.append({
            'grade_id': str(grade.id),
            'grade_name': grade.name,
            'grade_short_code': grade.short_code,
            'student_count': student_count,
            'next_grade_id': str(next_grade.id) if next_grade else None,
            'next_grade_name': next_grade.name if next_grade else 'GRADUATED',
            'is_final_grade': grade.order == max_order,
        })

    return preview


@transaction.atomic
def execute_promotion(tenant, excluded_student_ids=None, graduated_student_ids=None, new_academic_year=None):
    """
    Execute academic year promotion:
    1. Advance each student to the next grade in order
    2. Clear section assignments (admin re-assigns for new year)
    3. Handle exclusions (holdbacks) and graduations
    4. Update tenant's current_academic_year
    5. Clear assigned_students on academic courses

    Process in REVERSE grade order to avoid cascading conflicts.
    """
    from apps.academics.models import Grade
    from apps.users.models import User
    from apps.courses.models import Course

    excluded = set(excluded_student_ids or [])
    graduated = set(str(sid) for sid in (graduated_student_ids or []))

    grades = list(
        Grade.all_objects.filter(tenant=tenant).order_by('order')
    )

    if not grades:
        return {'promoted': 0, 'graduated': 0, 'new_academic_year': ''}

    promoted_count = 0
    graduated_count = 0

    # Build grade progression map
    grade_next = {}
    for i, grade in enumerate(grades):
        grade_next[grade.id] = grades[i + 1] if i + 1 < len(grades) else None

    # Process in reverse grade order to avoid cascading conflicts.
    # Uses bulk .update() for performance (no per-student save/signal).
    for grade in reversed(grades):
        next_grade = grade_next[grade.id]

        base_qs = User.objects.filter(
            tenant=tenant,
            grade_fk=grade,
            role='STUDENT',
            is_deleted=False,
            is_active=True,
        ).exclude(id__in=excluded)

        # Handle explicitly graduated students first
        if graduated:
            grad_qs = base_qs.filter(id__in=graduated)
            grad_count = grad_qs.update(section_fk=None)
            graduated_count += grad_count
            base_qs = base_qs.exclude(id__in=graduated)

        if next_grade:
            count = base_qs.update(grade_fk=next_grade, section_fk=None)
            promoted_count += count
        else:
            # Final grade — auto-graduate remaining
            count = base_qs.update(section_fk=None)
            graduated_count += count

    # Update academic year on tenant
    if new_academic_year:
        from apps.tenants.models import Tenant
        Tenant.objects.filter(pk=tenant.pk).update(
            current_academic_year=new_academic_year,
        )

    # Clear assigned_students on all academic courses (bulk via through table)
    academic_course_ids = list(
        Course.all_objects.filter(
            tenant=tenant, course_type='ACADEMIC',
        ).values_list('id', flat=True)
    )
    if academic_course_ids:
        Course.assigned_students.through.objects.filter(
            course_id__in=academic_course_ids,
        ).delete()

    logger.info(
        "Promotion complete for tenant %s: %d promoted, %d graduated → %s",
        tenant.name, promoted_count, graduated_count,
        new_academic_year or tenant.current_academic_year,
    )

    return {
        'promoted': promoted_count,
        'graduated': graduated_count,
        'new_academic_year': new_academic_year or tenant.current_academic_year,
    }
