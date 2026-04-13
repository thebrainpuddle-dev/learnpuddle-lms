# tests/academics/test_services.py
"""
Comprehensive tests for apps.academics.services:

- generate_student_id / generate_teacher_id  (atomic counter, prefix, formatting)
- auto_assign_course_students               (section targeting, grade fallback, PD skip)
- reassign_student_courses                  (student section change re-assignment)
- clone_course                              (deep copy, modules+contents, unpublished)
- get_promotion_preview                     (grade plan, final-grade flag, counts)
- execute_promotion                         (advance, graduate, exclude, clear courses)
"""

import pytest

from apps.academics.models import Grade, GradeBand, Section
from apps.academics.services import (
    auto_assign_course_students,
    clone_course,
    execute_promotion,
    generate_student_id,
    generate_teacher_id,
    get_promotion_preview,
    reassign_student_courses,
)
from apps.courses.models import Content, Course, Module
from apps.tenants.models import Tenant
from apps.users.models import User


# ═══════════════════════════════════════════════════════════════════════════════
# generate_student_id
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGenerateStudentId:
    """Tests for generate_student_id(tenant)."""

    def test_first_id_is_0001(self, tenant):
        sid = generate_student_id(tenant)
        assert sid == "TST-S-0001"

    def test_sequential_ids(self, tenant):
        s1 = generate_student_id(tenant)
        tenant.refresh_from_db()
        s2 = generate_student_id(tenant)
        assert s1 == "TST-S-0001"
        assert s2 == "TST-S-0002"

    def test_uses_tenant_prefix(self, tenant):
        tenant.id_prefix = "KIS"
        tenant.save(update_fields=["id_prefix"])
        sid = generate_student_id(tenant)
        assert sid.startswith("KIS-S-")

    def test_counter_incremented_in_db(self, tenant):
        generate_student_id(tenant)
        tenant.refresh_from_db()
        assert tenant.student_id_counter == 2

    def test_falls_back_to_lp_prefix_when_empty(self, tenant):
        tenant.id_prefix = ""
        tenant.save(update_fields=["id_prefix"])
        sid = generate_student_id(tenant)
        assert sid.startswith("LP-S-")

    def test_zero_padding_up_to_9999(self, tenant):
        tenant.student_id_counter = 42
        tenant.save(update_fields=["student_id_counter"])
        tenant.refresh_from_db()
        sid = generate_student_id(tenant)
        assert sid == "TST-S-0042"

    def test_counter_beyond_9999(self, tenant):
        """Counters above 9999 still work (no truncation, just wider)."""
        tenant.student_id_counter = 10001
        tenant.save(update_fields=["student_id_counter"])
        tenant.refresh_from_db()
        sid = generate_student_id(tenant)
        assert sid == "TST-S-10001"

    def test_does_not_increment_teacher_counter(self, tenant):
        generate_student_id(tenant)
        tenant.refresh_from_db()
        assert tenant.teacher_id_counter == 1  # unchanged

    def test_multiple_calls_give_unique_ids(self, tenant):
        ids = set()
        for _ in range(5):
            tenant.refresh_from_db()
            ids.add(generate_student_id(tenant))
        assert len(ids) == 5


# ═══════════════════════════════════════════════════════════════════════════════
# generate_teacher_id
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGenerateTeacherId:
    """Tests for generate_teacher_id(tenant)."""

    def test_first_id(self, tenant):
        tid = generate_teacher_id(tenant)
        assert tid == "TST-T-0001"

    def test_sequential_ids(self, tenant):
        t1 = generate_teacher_id(tenant)
        tenant.refresh_from_db()
        t2 = generate_teacher_id(tenant)
        assert t1 == "TST-T-0001"
        assert t2 == "TST-T-0002"

    def test_counter_incremented_in_db(self, tenant):
        generate_teacher_id(tenant)
        tenant.refresh_from_db()
        assert tenant.teacher_id_counter == 2

    def test_does_not_increment_student_counter(self, tenant):
        generate_teacher_id(tenant)
        tenant.refresh_from_db()
        assert tenant.student_id_counter == 1  # unchanged

    def test_falls_back_to_lp_prefix_when_empty(self, tenant):
        tenant.id_prefix = ""
        tenant.save(update_fields=["id_prefix"])
        tid = generate_teacher_id(tenant)
        assert tid.startswith("LP-T-")

    def test_uses_tenant_prefix(self, tenant):
        tenant.id_prefix = "ABC"
        tenant.save(update_fields=["id_prefix"])
        tid = generate_teacher_id(tenant)
        assert tid.startswith("ABC-T-")

    def test_student_and_teacher_counters_independent(self, tenant):
        """Student and teacher counters track independently."""
        generate_student_id(tenant)
        tenant.refresh_from_db()
        generate_student_id(tenant)
        tenant.refresh_from_db()
        # student_id_counter is now 3
        tid = generate_teacher_id(tenant)
        assert tid == "TST-T-0001"  # teacher counter still at 1


# ═══════════════════════════════════════════════════════════════════════════════
# auto_assign_course_students
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAutoAssignCourseStudents:
    """Tests for auto_assign_course_students(course)."""

    def test_assigns_students_in_target_sections(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        course = Course.objects.create(
            tenant=tenant,
            title="Physics",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        course.target_sections.add(section)

        count = auto_assign_course_students(course)
        assert count == 1
        assert student_user in course.assigned_students.all()

    def test_skips_pd_courses(self, tenant):
        course = Course.objects.create(
            tenant=tenant,
            title="PD Course",
            description="",
            course_type="PD",
        )
        count = auto_assign_course_students(course)
        assert count == 0

    def test_assigns_by_target_grades_when_no_sections(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        course = Course.objects.create(
            tenant=tenant,
            title="Math",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        course.target_grades.add(grade)
        count = auto_assign_course_students(course)
        assert count == 1
        assert student_user in course.assigned_students.all()

    def test_idempotent(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        course = Course.objects.create(
            tenant=tenant,
            title="Chem",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        course.target_sections.add(section)
        auto_assign_course_students(course)
        auto_assign_course_students(course)
        assert course.assigned_students.count() == 1

    def test_returns_zero_when_no_targets(self, tenant):
        course = Course.objects.create(
            tenant=tenant,
            title="No Targets",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        # No target_sections or target_grades set
        count = auto_assign_course_students(course)
        assert count == 0

    def test_excludes_deleted_students(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.is_deleted = True
        student_user.save(update_fields=["section_fk", "grade_fk", "is_deleted"])

        course = Course.objects.create(
            tenant=tenant,
            title="Bio",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        course.target_sections.add(section)
        count = auto_assign_course_students(course)
        assert count == 0

    def test_excludes_inactive_students(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.is_active = False
        student_user.save(update_fields=["section_fk", "grade_fk", "is_active"])

        course = Course.objects.create(
            tenant=tenant,
            title="History",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        course.target_sections.add(section)
        count = auto_assign_course_students(course)
        assert count == 0

    def test_only_assigns_students_not_teachers(self, tenant, grade, section, teacher_user):
        """Teachers in the section should not be assigned as students."""
        teacher_user.section_fk = section
        teacher_user.grade_fk = grade
        teacher_user.save(update_fields=["section_fk", "grade_fk"])

        course = Course.objects.create(
            tenant=tenant,
            title="English",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        course.target_sections.add(section)
        count = auto_assign_course_students(course)
        assert count == 0

    def test_multiple_students_in_section(self, tenant, grade, section):
        """All active students in the section should be assigned."""
        students = []
        for i in range(3):
            s = User.objects.create_user(
                email=f"multi-student-{i}@test.com",
                password="pass",
                tenant=tenant,
                role="STUDENT",
                section_fk=section,
                grade_fk=grade,
            )
            students.append(s)

        course = Course.objects.create(
            tenant=tenant,
            title="Multi",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        course.target_sections.add(section)
        count = auto_assign_course_students(course)
        assert count == 3
        for s in students:
            assert s in course.assigned_students.all()

    def test_section_target_takes_precedence_over_grade(
        self, tenant, grade, section, grade_band
    ):
        """When both sections and grades are set, sections are used."""
        # Create a second section in the same grade
        section_b = Section.objects.create(
            tenant=tenant, grade=grade, name="B", academic_year="2026-27"
        )
        s_a = User.objects.create_user(
            email="sec-a@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
            section_fk=section,
            grade_fk=grade,
        )
        s_b = User.objects.create_user(
            email="sec-b@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
            section_fk=section_b,
            grade_fk=grade,
        )

        course = Course.objects.create(
            tenant=tenant,
            title="Precedence",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        # Target only section A, but also add the grade
        course.target_sections.add(section)
        course.target_grades.add(grade)

        count = auto_assign_course_students(course)
        # Only student in section A should be assigned (sections take precedence)
        assert count == 1
        assert s_a in course.assigned_students.all()
        assert s_b not in course.assigned_students.all()


# ═══════════════════════════════════════════════════════════════════════════════
# reassign_student_courses
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReassignStudentCourses:
    """Tests for reassign_student_courses(student)."""

    def test_assigns_courses_targeting_student_section(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        course = Course.objects.create(
            tenant=tenant,
            title="Targeted Course",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        course.target_sections.add(section)

        reassign_student_courses(student_user)
        assert student_user in course.assigned_students.all()

    def test_does_nothing_if_student_has_no_section(self, student_user):
        student_user.section_fk = None
        student_user.save(update_fields=["section_fk"])

        reassign_student_courses(student_user)
        # No error raised; just a no-op

    def test_ignores_unpublished_courses(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        course = Course.objects.create(
            tenant=tenant,
            title="Draft Course",
            description="",
            course_type="ACADEMIC",
            is_published=False,
            is_active=True,
        )
        course.target_sections.add(section)

        reassign_student_courses(student_user)
        assert student_user not in course.assigned_students.all()

    def test_ignores_pd_courses(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        course = Course.objects.create(
            tenant=tenant,
            title="PD Only",
            description="",
            course_type="PD",
            is_published=True,
            is_active=True,
        )
        course.target_sections.add(section)

        reassign_student_courses(student_user)
        assert student_user not in course.assigned_students.all()

    def test_ignores_inactive_courses(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        course = Course.objects.create(
            tenant=tenant,
            title="Inactive",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=False,
        )
        course.target_sections.add(section)

        reassign_student_courses(student_user)
        assert student_user not in course.assigned_students.all()

    def test_assigns_multiple_courses(self, tenant, grade, section, student_user):
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        courses = []
        for i in range(3):
            c = Course.objects.create(
                tenant=tenant,
                title=f"Course {i}",
                description="",
                course_type="ACADEMIC",
                is_published=True,
                is_active=True,
            )
            c.target_sections.add(section)
            courses.append(c)

        reassign_student_courses(student_user)
        for c in courses:
            assert student_user in c.assigned_students.all()

    def test_preserves_existing_assignments(self, tenant, grade, section, student_user):
        """Existing manual assignments are preserved when reassigning."""
        student_user.section_fk = section
        student_user.grade_fk = grade
        student_user.save(update_fields=["section_fk", "grade_fk"])

        manual_course = Course.objects.create(
            tenant=tenant,
            title="Manual",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            is_active=True,
        )
        # Manually assigned, no target_sections pointing to student's section
        manual_course.assigned_students.add(student_user)

        reassign_student_courses(student_user)
        # Manual assignment still present
        assert student_user in manual_course.assigned_students.all()


# ═══════════════════════════════════════════════════════════════════════════════
# clone_course
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCloneCourse:
    """Tests for clone_course(original_course, ...)."""

    def test_clones_with_new_title(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Original",
            description="Desc",
            course_type="ACADEMIC",
            is_published=True,
            created_by=admin_user,
        )
        module = Module.objects.create(course=original, title="Module 1", order=1)
        Content.objects.create(
            module=module, title="Lesson 1", order=1, content_type="TEXT"
        )

        clone = clone_course(original, new_title="Clone", cloned_by=admin_user)

        assert clone.id != original.id
        assert clone.title == "Clone"
        assert clone.is_published is False
        assert clone.modules.count() == 1
        cloned_module = clone.modules.first()
        assert cloned_module.id != module.id
        assert cloned_module.contents.count() == 1

    def test_default_title_appends_copy(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant, title="Bio", description="", created_by=admin_user
        )
        clone = clone_course(original, cloned_by=admin_user)
        assert clone.title == "Bio (Copy)"

    def test_clone_is_unpublished(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Published",
            description="",
            is_published=True,
            created_by=admin_user,
        )
        clone = clone_course(original, cloned_by=admin_user)
        assert clone.is_published is False

    def test_clone_has_no_assigned_students(self, tenant, admin_user, student_user):
        original = Course.objects.create(
            tenant=tenant,
            title="With Students",
            description="",
            is_published=True,
            created_by=admin_user,
        )
        original.assigned_students.add(student_user)

        clone = clone_course(original, cloned_by=admin_user)
        assert clone.assigned_students.count() == 0

    def test_clone_copies_target_grades(self, tenant, admin_user, grade):
        original = Course.objects.create(
            tenant=tenant,
            title="Graded",
            description="",
            course_type="ACADEMIC",
            created_by=admin_user,
        )
        original.target_grades.add(grade)

        clone = clone_course(original, cloned_by=admin_user)
        assert grade in clone.target_grades.all()

    def test_clone_copies_target_sections_by_default(self, tenant, admin_user, section):
        original = Course.objects.create(
            tenant=tenant,
            title="Sectioned",
            description="",
            course_type="ACADEMIC",
            created_by=admin_user,
        )
        original.target_sections.add(section)

        clone = clone_course(original, cloned_by=admin_user)
        assert section in clone.target_sections.all()

    def test_clone_with_new_target_sections(self, tenant, admin_user, grade, section):
        """Passing new_target_sections overrides the original."""
        section_b = Section.objects.create(
            tenant=tenant, grade=grade, name="B", academic_year="2026-27"
        )
        original = Course.objects.create(
            tenant=tenant,
            title="Override",
            description="",
            course_type="ACADEMIC",
            created_by=admin_user,
        )
        original.target_sections.add(section)

        clone = clone_course(
            original,
            new_target_sections=[section_b],
            cloned_by=admin_user,
        )
        assert section not in clone.target_sections.all()
        assert section_b in clone.target_sections.all()

    def test_deep_copies_multiple_modules_and_contents(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Deep",
            description="",
            created_by=admin_user,
        )
        for m_idx in range(2):
            mod = Module.objects.create(
                course=original, title=f"Module {m_idx}", order=m_idx
            )
            for c_idx in range(3):
                Content.objects.create(
                    module=mod,
                    title=f"Content {m_idx}-{c_idx}",
                    order=c_idx,
                    content_type="TEXT",
                )

        clone = clone_course(original, cloned_by=admin_user)
        assert clone.modules.count() == 2
        for mod in clone.modules.all():
            assert mod.contents.count() == 3

    def test_clone_preserves_course_type(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Academic",
            description="",
            course_type="ACADEMIC",
            created_by=admin_user,
        )
        clone = clone_course(original, cloned_by=admin_user)
        assert clone.course_type == "ACADEMIC"

    def test_clone_preserves_is_mandatory(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Mandatory",
            description="",
            is_mandatory=True,
            created_by=admin_user,
        )
        clone = clone_course(original, cloned_by=admin_user)
        assert clone.is_mandatory is True

    def test_clone_preserves_estimated_hours(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Timed",
            description="",
            estimated_hours=10,
            created_by=admin_user,
        )
        clone = clone_course(original, cloned_by=admin_user)
        assert clone.estimated_hours == 10

    def test_clone_sets_created_by_to_cloner(self, tenant, admin_user, teacher_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Creator Test",
            description="",
            created_by=admin_user,
        )
        clone = clone_course(original, cloned_by=teacher_user)
        assert clone.created_by == teacher_user

    def test_clone_skips_soft_deleted_modules(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Soft Del Mod",
            description="",
            created_by=admin_user,
        )
        Module.objects.create(
            course=original, title="Active Module", order=1, is_deleted=False
        )
        Module.objects.create(
            course=original, title="Deleted Module", order=2, is_deleted=True
        )

        clone = clone_course(original, cloned_by=admin_user)
        assert clone.modules.count() == 1
        assert clone.modules.first().title == "Active Module"

    def test_clone_skips_soft_deleted_contents(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Soft Del Content",
            description="",
            created_by=admin_user,
        )
        mod = Module.objects.create(course=original, title="Mod", order=1)
        Content.objects.create(
            module=mod, title="Active", order=1, content_type="TEXT", is_deleted=False
        )
        Content.objects.create(
            module=mod, title="Deleted", order=2, content_type="TEXT", is_deleted=True
        )

        clone = clone_course(original, cloned_by=admin_user)
        cloned_mod = clone.modules.first()
        assert cloned_mod.contents.count() == 1
        assert cloned_mod.contents.first().title == "Active"

    def test_clone_generates_unique_slug(self, tenant, admin_user):
        original = Course.objects.create(
            tenant=tenant,
            title="Slug Test",
            description="",
            created_by=admin_user,
        )
        clone = clone_course(original, new_title="Slug Test", cloned_by=admin_user)
        assert clone.slug != ""
        assert clone.slug != original.slug

    def test_clone_without_cloned_by(self, tenant):
        """cloned_by=None is allowed."""
        original = Course.objects.create(
            tenant=tenant, title="No Cloner", description=""
        )
        clone = clone_course(original)
        assert clone.created_by is None
        assert clone.title == "No Cloner (Copy)"

    def test_content_order_preserved(self, tenant, admin_user):
        """Content order within modules should be preserved."""
        original = Course.objects.create(
            tenant=tenant,
            title="Order Test",
            description="",
            created_by=admin_user,
        )
        mod = Module.objects.create(course=original, title="M1", order=1)
        Content.objects.create(
            module=mod, title="Third", order=3, content_type="TEXT"
        )
        Content.objects.create(
            module=mod, title="First", order=1, content_type="TEXT"
        )
        Content.objects.create(
            module=mod, title="Second", order=2, content_type="VIDEO"
        )

        clone = clone_course(original, cloned_by=admin_user)
        cloned_contents = list(
            clone.modules.first().contents.order_by("order").values_list("title", flat=True)
        )
        assert cloned_contents == ["First", "Second", "Third"]


# ═══════════════════════════════════════════════════════════════════════════════
# get_promotion_preview
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGetPromotionPreview:
    """Tests for get_promotion_preview(tenant)."""

    def test_preview_returns_grade_plan(self, tenant, grade_band, grade):
        preview = get_promotion_preview(tenant)
        assert len(preview) == 1
        assert preview[0]["grade_id"] == str(grade.id)
        assert preview[0]["is_final_grade"] is True

    def test_empty_when_no_grades(self, tenant):
        preview = get_promotion_preview(tenant)
        assert preview == []

    def test_final_grade_flag_only_on_last(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="G1x", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="G2x", order=2
        )

        preview = get_promotion_preview(tenant)
        assert len(preview) == 2
        assert preview[0]["is_final_grade"] is False
        assert preview[1]["is_final_grade"] is True

    def test_next_grade_mapping(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="G1a", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="G2a", order=2
        )

        preview = get_promotion_preview(tenant)
        assert preview[0]["next_grade_id"] == str(g2.id)
        assert preview[0]["next_grade_name"] == "G2"
        assert preview[1]["next_grade_id"] is None
        assert preview[1]["next_grade_name"] == "GRADUATED"

    def test_student_count_per_grade(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="G1b", order=1
        )
        for i in range(3):
            User.objects.create_user(
                email=f"preview-s{i}@test.com",
                password="pass",
                tenant=tenant,
                role="STUDENT",
                grade_fk=g1,
            )

        preview = get_promotion_preview(tenant)
        assert preview[0]["student_count"] == 3

    def test_excludes_deleted_students_from_count(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="G1c", order=1
        )
        User.objects.create_user(
            email="active-prev@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
            grade_fk=g1,
        )
        deleted = User.objects.create_user(
            email="deleted-prev@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
            grade_fk=g1,
        )
        deleted.is_deleted = True
        deleted.save(update_fields=["is_deleted"])

        preview = get_promotion_preview(tenant)
        assert preview[0]["student_count"] == 1

    def test_excludes_non_student_roles_from_count(self, tenant, grade_band, teacher_user):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="G1d", order=1
        )
        teacher_user.grade_fk = g1
        teacher_user.save(update_fields=["grade_fk"])

        preview = get_promotion_preview(tenant)
        assert preview[0]["student_count"] == 0

    def test_preview_includes_grade_metadata(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="Grade 1", short_code="G1e", order=1
        )
        preview = get_promotion_preview(tenant)
        assert preview[0]["grade_name"] == "Grade 1"
        assert preview[0]["grade_short_code"] == "G1e"


# ═══════════════════════════════════════════════════════════════════════════════
# execute_promotion
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExecutePromotion:
    """Tests for execute_promotion(tenant, ...)."""

    def test_promotes_students_to_next_grade(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="EP1", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="EP2", order=2
        )
        student = User.objects.create_user(
            email="promote@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        student.grade_fk = g1
        student.save(update_fields=["grade_fk"])

        result = execute_promotion(tenant, new_academic_year="2027-28")
        student.refresh_from_db()
        assert student.grade_fk == g2
        assert student.section_fk is None
        assert result["promoted"] == 1

    def test_graduates_final_grade_students(self, tenant, grade_band):
        g12 = Grade.objects.create(
            tenant=tenant,
            grade_band=grade_band,
            name="G12",
            short_code="EP12",
            order=12,
        )
        student = User.objects.create_user(
            email="grad@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        student.grade_fk = g12
        student.save(update_fields=["grade_fk"])

        result = execute_promotion(tenant, new_academic_year="2027-28")
        assert result["graduated"] == 1

    def test_clears_sections_on_promotion(self, tenant, grade_band, section):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="EPC1", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="EPC2", order=2
        )
        student = User.objects.create_user(
            email="clear-section@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        student.grade_fk = g1
        student.section_fk = section
        student.save(update_fields=["grade_fk", "section_fk"])

        execute_promotion(tenant, new_academic_year="2027-28")
        student.refresh_from_db()
        assert student.section_fk is None

    def test_excludes_students_by_id(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="EPX1", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="EPX2", order=2
        )
        held_back = User.objects.create_user(
            email="held@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        held_back.grade_fk = g1
        held_back.save(update_fields=["grade_fk"])

        promoted = User.objects.create_user(
            email="goes-up@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        promoted.grade_fk = g1
        promoted.save(update_fields=["grade_fk"])

        result = execute_promotion(
            tenant,
            excluded_student_ids=[held_back.id],
            new_academic_year="2027-28",
        )
        held_back.refresh_from_db()
        promoted.refresh_from_db()
        assert held_back.grade_fk == g1  # stayed
        assert promoted.grade_fk == g2  # promoted
        assert result["promoted"] == 1

    def test_explicitly_graduated_students(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="EPG1", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="EPG2", order=2
        )
        student = User.objects.create_user(
            email="early-grad@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        student.grade_fk = g1
        student.save(update_fields=["grade_fk"])

        result = execute_promotion(
            tenant,
            graduated_student_ids=[student.id],
            new_academic_year="2027-28",
        )
        student.refresh_from_db()
        # Explicitly graduated: grade unchanged, section cleared
        assert student.grade_fk == g1
        assert student.section_fk is None
        assert result["graduated"] == 1

    def test_updates_tenant_academic_year(self, tenant, grade_band):
        Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="EPY1", order=1
        )
        execute_promotion(tenant, new_academic_year="2027-28")
        tenant.refresh_from_db()
        assert tenant.current_academic_year == "2027-28"

    def test_does_not_update_year_when_not_provided(self, tenant, grade_band):
        Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="EPYN", order=1
        )
        execute_promotion(tenant)
        tenant.refresh_from_db()
        assert tenant.current_academic_year == "2026-27"  # unchanged

    def test_clears_academic_course_assignments(self, tenant, grade_band, admin_user, student_user):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="ECA1", order=1
        )
        student_user.grade_fk = g1
        student_user.save(update_fields=["grade_fk"])

        course = Course.objects.create(
            tenant=tenant,
            title="Academic Course",
            description="",
            course_type="ACADEMIC",
            is_published=True,
            created_by=admin_user,
        )
        course.assigned_students.add(student_user)

        execute_promotion(tenant, new_academic_year="2027-28")
        assert course.assigned_students.count() == 0

    def test_does_not_clear_pd_course_assignments(
        self, tenant, grade_band, admin_user, teacher_user
    ):
        Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="ECPD", order=1
        )

        pd_course = Course.objects.create(
            tenant=tenant,
            title="PD Course",
            description="",
            course_type="PD",
            is_published=True,
            created_by=admin_user,
        )
        pd_course.assigned_students.add(teacher_user)

        execute_promotion(tenant, new_academic_year="2027-28")
        # PD course assignments are NOT cleared
        assert pd_course.assigned_students.count() == 1

    def test_empty_grades_returns_zeros(self, tenant):
        result = execute_promotion(tenant, new_academic_year="2027-28")
        assert result["promoted"] == 0
        assert result["graduated"] == 0
        assert result["new_academic_year"] == ""

    def test_skips_deleted_students(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="ESD1", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="ESD2", order=2
        )
        student = User.objects.create_user(
            email="deleted-promo@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        student.grade_fk = g1
        student.is_deleted = True
        student.save(update_fields=["grade_fk", "is_deleted"])

        result = execute_promotion(tenant, new_academic_year="2027-28")
        assert result["promoted"] == 0

    def test_skips_inactive_students(self, tenant, grade_band):
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="ESI1", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="ESI2", order=2
        )
        student = User.objects.create_user(
            email="inactive-promo@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        student.grade_fk = g1
        student.is_active = False
        student.save(update_fields=["grade_fk", "is_active"])

        result = execute_promotion(tenant, new_academic_year="2027-28")
        assert result["promoted"] == 0

    def test_multi_grade_chain_promotion(self, tenant, grade_band):
        """Students in G1->G2, G2->G3 all promoted correctly."""
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="MC1", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="MC2", order=2
        )
        g3 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G3", short_code="MC3", order=3
        )

        s1 = User.objects.create_user(
            email="chain-s1@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        s1.grade_fk = g1
        s1.save(update_fields=["grade_fk"])

        s2 = User.objects.create_user(
            email="chain-s2@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        s2.grade_fk = g2
        s2.save(update_fields=["grade_fk"])

        s3 = User.objects.create_user(
            email="chain-s3@test.com",
            password="pass",
            tenant=tenant,
            role="STUDENT",
        )
        s3.grade_fk = g3
        s3.save(update_fields=["grade_fk"])

        result = execute_promotion(tenant, new_academic_year="2027-28")

        s1.refresh_from_db()
        s2.refresh_from_db()
        s3.refresh_from_db()

        assert s1.grade_fk == g2  # G1 -> G2
        assert s2.grade_fk == g3  # G2 -> G3
        assert s3.grade_fk == g3  # G3 is final grade, stays
        assert result["promoted"] == 2
        assert result["graduated"] == 1

    def test_return_contains_new_academic_year(self, tenant, grade_band):
        Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="RAY1", order=1
        )
        result = execute_promotion(tenant, new_academic_year="2028-29")
        assert result["new_academic_year"] == "2028-29"

    def test_return_academic_year_fallback(self, tenant, grade_band):
        """When new_academic_year is not provided, returns the tenant's current value."""
        Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="RAF1", order=1
        )
        result = execute_promotion(tenant)
        assert result["new_academic_year"] == "2026-27"

    def test_does_not_promote_non_student_roles(self, tenant, grade_band, teacher_user):
        """Teachers in a grade are not promoted."""
        g1 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G1", short_code="NP1", order=1
        )
        g2 = Grade.objects.create(
            tenant=tenant, grade_band=grade_band, name="G2", short_code="NP2", order=2
        )
        teacher_user.grade_fk = g1
        teacher_user.save(update_fields=["grade_fk"])

        result = execute_promotion(tenant, new_academic_year="2027-28")
        teacher_user.refresh_from_db()
        assert teacher_user.grade_fk == g1  # unchanged
        assert result["promoted"] == 0
