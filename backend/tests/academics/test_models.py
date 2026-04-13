# tests/academics/test_models.py
"""
Comprehensive model tests for the academics app.

Covers:
- CRUD operations for all five models
- unique_together constraint enforcement
- Model __str__ representations
- Meta ordering
- ManyToMany relationships (applicable_grades, sections)
- ForeignKey CASCADE / SET_NULL behavior
- TenantManager auto-filtering via context-var
- all_objects manager bypass
"""

import pytest
from django.db import IntegrityError

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.academics.models import GradeBand, Grade, Section, Subject, TeachingAssignment
from utils.tenant_middleware import set_current_tenant, clear_current_tenant


# ===========================================================================
# GradeBand
# ===========================================================================

@pytest.mark.django_db
class TestGradeBand:

    def test_create_grade_band(self, tenant):
        band = GradeBand.objects.create(
            tenant=tenant,
            name="High School",
            short_code="HS",
            order=4,
            curriculum_framework="IGCSE",
        )
        assert band.id is not None
        assert band.name == "High School"
        assert band.curriculum_framework == "IGCSE"

    def test_str_representation(self, grade_band):
        result = str(grade_band)
        assert "Primary" in result
        assert "PRI" in result

    def test_unique_together_tenant_name(self, tenant, grade_band):
        """Duplicate (tenant, name) should raise IntegrityError."""
        with pytest.raises(IntegrityError):
            GradeBand.objects.create(
                tenant=tenant,
                name=grade_band.name,  # "Primary" — already exists
                short_code="DUP",
                order=99,
            )

    def test_ordering_by_order(self, tenant):
        GradeBand.objects.create(tenant=tenant, name="Middle", short_code="MID", order=3)
        GradeBand.objects.create(tenant=tenant, name="Early Years", short_code="EY", order=0)
        GradeBand.objects.create(tenant=tenant, name="High School", short_code="HS", order=4)

        bands = list(GradeBand.all_objects.filter(tenant=tenant).order_by("order"))
        orders = [b.order for b in bands]
        assert orders == sorted(orders), "GradeBands should be ordered by the 'order' field"

    def test_default_curriculum_framework(self, tenant):
        band = GradeBand.objects.create(
            tenant=tenant, name="Custom Band", short_code="CB", order=10,
        )
        assert band.curriculum_framework == "CUSTOM"

    def test_theme_config_json_field(self, tenant):
        theme = {"accent_color": "#FF5733", "bg_image": "https://example.com/bg.jpg"}
        band = GradeBand.objects.create(
            tenant=tenant, name="Themed Band", short_code="TB", order=5,
            theme_config=theme,
        )
        band.refresh_from_db()
        assert band.theme_config == theme

    def test_theme_config_default_none(self, tenant):
        band = GradeBand.objects.create(
            tenant=tenant, name="No Theme", short_code="NT", order=6,
        )
        assert band.theme_config is None

    def test_timestamps_auto_set(self, grade_band):
        assert grade_band.created_at is not None
        assert grade_band.updated_at is not None

    def test_cascade_delete_with_tenant(self, tenant, grade_band):
        """Deleting the tenant should CASCADE-delete its grade bands."""
        band_id = grade_band.id
        tenant.delete()
        assert not GradeBand.all_objects.filter(id=band_id).exists()


# ===========================================================================
# Grade
# ===========================================================================

@pytest.mark.django_db
class TestGrade:

    def test_create_grade(self, tenant, grade_band):
        grade = Grade.objects.create(
            tenant=tenant,
            grade_band=grade_band,
            name="Grade 1",
            short_code="G1",
            order=1,
        )
        assert grade.id is not None
        assert grade.grade_band == grade_band

    def test_str_representation(self, grade):
        result = str(grade)
        assert "Grade 5" in result
        assert "G5" in result

    def test_unique_together_tenant_shortcode(self, tenant, grade_band, grade):
        """Duplicate (tenant, short_code) should raise IntegrityError."""
        with pytest.raises(IntegrityError):
            Grade.objects.create(
                tenant=tenant,
                grade_band=grade_band,
                name="Another Grade",
                short_code=grade.short_code,  # "G5" — already exists
                order=99,
            )

    def test_ordering_by_order(self, tenant, grade_band):
        Grade.objects.create(tenant=tenant, grade_band=grade_band, name="G3", short_code="G3", order=3)
        Grade.objects.create(tenant=tenant, grade_band=grade_band, name="G1", short_code="G1", order=1)

        grades = list(Grade.all_objects.filter(tenant=tenant).order_by("order"))
        orders = [g.order for g in grades]
        assert orders == sorted(orders)

    def test_cascade_delete_with_grade_band(self, tenant, grade_band, grade):
        """Deleting a GradeBand should CASCADE-delete its Grades."""
        grade_id = grade.id
        grade_band.delete()
        assert not Grade.all_objects.filter(id=grade_id).exists()

    def test_cascade_delete_with_tenant(self, tenant, grade_band, grade):
        """Deleting the tenant should CASCADE-delete Grades."""
        grade_id = grade.id
        tenant.delete()
        assert not Grade.all_objects.filter(id=grade_id).exists()


# ===========================================================================
# Section
# ===========================================================================

@pytest.mark.django_db
class TestSection:

    def test_create_section(self, tenant, grade):
        section = Section.objects.create(
            tenant=tenant,
            grade=grade,
            name="B",
            academic_year="2026-27",
        )
        assert section.id is not None

    def test_str_representation(self, section):
        result = str(section)
        assert "Grade 5" in result
        assert "A" in result
        assert "2026-27" in result

    def test_class_teacher_assignment(self, tenant, grade, teacher_user):
        section = Section.objects.create(
            tenant=tenant,
            grade=grade,
            name="C",
            academic_year="2026-27",
            class_teacher=teacher_user,
        )
        assert section.class_teacher == teacher_user

    def test_class_teacher_set_null_on_delete(self, tenant, grade, teacher_user):
        """Deleting the teacher should SET_NULL on class_teacher, not delete the section."""
        section = Section.objects.create(
            tenant=tenant,
            grade=grade,
            name="D",
            academic_year="2026-27",
            class_teacher=teacher_user,
        )
        section_id = section.id
        teacher_user.hard_delete()
        section.refresh_from_db()
        assert section.class_teacher is None
        assert Section.all_objects.filter(id=section_id).exists()

    def test_unique_together_tenant_grade_name_year(self, tenant, grade, section):
        """Duplicate (tenant, grade, name, academic_year) should raise IntegrityError."""
        with pytest.raises(IntegrityError):
            Section.objects.create(
                tenant=tenant,
                grade=grade,
                name=section.name,  # "A"
                academic_year=section.academic_year,  # "2026-27"
            )

    def test_same_name_different_year_allowed(self, tenant, grade):
        """Same section name in a different academic year is allowed."""
        Section.objects.create(tenant=tenant, grade=grade, name="A", academic_year="2025-26")
        Section.objects.create(tenant=tenant, grade=grade, name="A", academic_year="2026-27")
        count = Section.all_objects.filter(tenant=tenant, grade=grade, name="A").count()
        assert count == 2

    def test_cascade_delete_with_grade(self, tenant, grade, section):
        """Deleting a Grade should CASCADE-delete its Sections."""
        section_id = section.id
        grade.delete()
        assert not Section.all_objects.filter(id=section_id).exists()


# ===========================================================================
# Subject
# ===========================================================================

@pytest.mark.django_db
class TestSubject:

    def test_create_subject(self, tenant):
        subject = Subject.objects.create(
            tenant=tenant,
            name="English",
            code="ENG",
            department="Languages",
        )
        assert subject.id is not None

    def test_str_representation(self, subject):
        result = str(subject)
        assert "Mathematics" in result
        assert "MATH" in result

    def test_unique_together_tenant_code(self, tenant, subject):
        """Duplicate (tenant, code) should raise IntegrityError."""
        with pytest.raises(IntegrityError):
            Subject.objects.create(
                tenant=tenant,
                name="Different Name",
                code=subject.code,  # "MATH" — already exists
                department="Other",
            )

    def test_applicable_grades_m2m(self, tenant, grade, subject):
        subject.applicable_grades.add(grade)
        assert grade in subject.applicable_grades.all()

    def test_applicable_grades_multiple(self, tenant, grade_band, subject):
        g1 = Grade.objects.create(tenant=tenant, grade_band=grade_band, name="G1", short_code="G1", order=1)
        g2 = Grade.objects.create(tenant=tenant, grade_band=grade_band, name="G2", short_code="G2", order=2)
        subject.applicable_grades.add(g1, g2)
        assert subject.applicable_grades.count() == 2

    def test_is_elective_default_false(self, subject):
        assert subject.is_elective is False

    def test_is_elective_set_true(self, tenant):
        elective = Subject.objects.create(
            tenant=tenant, name="Art", code="ART", is_elective=True,
        )
        assert elective.is_elective is True

    def test_department_blank_default(self, tenant):
        sub = Subject.objects.create(tenant=tenant, name="PE", code="PE")
        assert sub.department == ""

    def test_ordering_by_department_then_name(self, tenant):
        Subject.objects.create(tenant=tenant, name="Zoology", code="ZOO", department="Sciences")
        Subject.objects.create(tenant=tenant, name="Art", code="ART", department="Arts")
        Subject.objects.create(tenant=tenant, name="Biology", code="BIO", department="Sciences")

        subjects = list(Subject.all_objects.filter(tenant=tenant).order_by("department", "name"))
        departments_names = [(s.department, s.name) for s in subjects]
        assert departments_names == sorted(departments_names)

    def test_cascade_delete_with_tenant(self, tenant, subject):
        """Deleting the tenant should CASCADE-delete its Subjects."""
        subject_id = subject.id
        tenant.delete()
        assert not Subject.all_objects.filter(id=subject_id).exists()


# ===========================================================================
# TeachingAssignment
# ===========================================================================

@pytest.mark.django_db
class TestTeachingAssignment:

    def test_create_assignment(self, tenant, teacher_user, subject, section):
        ta = TeachingAssignment.objects.create(
            tenant=tenant,
            teacher=teacher_user,
            subject=subject,
            academic_year="2026-27",
        )
        ta.sections.add(section)
        assert ta.id is not None
        assert section in ta.sections.all()

    def test_str_representation(self, teaching_assignment):
        result = str(teaching_assignment)
        assert "Teacher Academics" in result  # teacher full name
        assert "Mathematics" in result
        assert "2026-27" in result

    def test_is_class_teacher_default_false(self, teaching_assignment):
        assert teaching_assignment.is_class_teacher is False

    def test_is_class_teacher_set_true(self, tenant, teacher_user, subject):
        ta = TeachingAssignment.objects.create(
            tenant=tenant,
            teacher=teacher_user,
            subject=subject,
            academic_year="2025-26",
            is_class_teacher=True,
        )
        assert ta.is_class_teacher is True

    def test_unique_together_teacher_subject_year(self, tenant, teacher_user, subject, teaching_assignment):
        """Duplicate (tenant, teacher, subject, academic_year) should raise IntegrityError."""
        with pytest.raises(IntegrityError):
            TeachingAssignment.objects.create(
                tenant=tenant,
                teacher=teacher_user,
                subject=subject,
                academic_year="2026-27",  # same year as fixture
            )

    def test_same_teacher_different_year_allowed(self, tenant, teacher_user, subject):
        TeachingAssignment.objects.create(
            tenant=tenant, teacher=teacher_user, subject=subject, academic_year="2025-26",
        )
        TeachingAssignment.objects.create(
            tenant=tenant, teacher=teacher_user, subject=subject, academic_year="2026-27",
        )
        count = TeachingAssignment.all_objects.filter(
            tenant=tenant, teacher=teacher_user, subject=subject,
        ).count()
        assert count == 2

    def test_same_teacher_different_subject_same_year(self, tenant, teacher_user, subject, section):
        """A teacher can teach multiple subjects in the same year."""
        other_subject = Subject.objects.create(
            tenant=tenant, name="Science", code="SCI", department="Sciences",
        )
        ta1 = TeachingAssignment.objects.create(
            tenant=tenant, teacher=teacher_user, subject=subject, academic_year="2026-27",
        )
        ta2 = TeachingAssignment.objects.create(
            tenant=tenant, teacher=teacher_user, subject=other_subject, academic_year="2026-27",
        )
        assert ta1.id != ta2.id

    def test_multiple_sections_on_assignment(self, tenant, grade, teacher_user, subject):
        """A single TeachingAssignment can span multiple sections."""
        sec_a = Section.objects.create(tenant=tenant, grade=grade, name="X", academic_year="2026-27")
        sec_b = Section.objects.create(tenant=tenant, grade=grade, name="Y", academic_year="2026-27")
        ta = TeachingAssignment.objects.create(
            tenant=tenant, teacher=teacher_user, subject=subject, academic_year="2026-27",
        )
        ta.sections.add(sec_a, sec_b)
        assert ta.sections.count() == 2

    def test_cascade_delete_with_teacher(self, teaching_assignment, teacher_user):
        """Deleting the teacher should CASCADE-delete their TeachingAssignments."""
        ta_id = teaching_assignment.id
        teacher_user.hard_delete()
        assert not TeachingAssignment.all_objects.filter(id=ta_id).exists()

    def test_cascade_delete_with_subject(self, teaching_assignment, subject):
        """Deleting the subject should CASCADE-delete TeachingAssignments for it."""
        ta_id = teaching_assignment.id
        subject.delete()
        assert not TeachingAssignment.all_objects.filter(id=ta_id).exists()

    def test_cascade_delete_with_tenant(self, teaching_assignment, tenant):
        """Deleting the tenant should CASCADE-delete TeachingAssignments."""
        ta_id = teaching_assignment.id
        tenant.delete()
        assert not TeachingAssignment.all_objects.filter(id=ta_id).exists()


# ===========================================================================
# TenantManager filtering
# ===========================================================================

@pytest.mark.django_db
class TestTenantManagerFiltering:
    """
    Verify that TenantManager auto-filters queries by the current tenant
    set in context-var storage, and that all_objects bypasses filtering.
    """

    @pytest.fixture
    def tenant_b(self, db):
        return Tenant.objects.create(
            name="Other School",
            slug="other-school-academics",
            subdomain="other",
            email="other@school.com",
            is_active=True,
        )

    @pytest.fixture
    def setup_cross_tenant_data(self, tenant, tenant_b):
        """Create identical-looking data in two tenants."""
        band_a = GradeBand.objects.create(
            tenant=tenant, name="Primary", short_code="PRI", order=1,
        )
        band_b = GradeBand.objects.create(
            tenant=tenant_b, name="Primary", short_code="PRI", order=1,
        )
        return band_a, band_b

    def test_tenant_context_filters_grade_bands(self, tenant, tenant_b, setup_cross_tenant_data):
        band_a, band_b = setup_cross_tenant_data

        set_current_tenant(tenant)
        bands = list(GradeBand.objects.all())
        band_ids = [b.id for b in bands]
        assert band_a.id in band_ids
        assert band_b.id not in band_ids
        clear_current_tenant()

    def test_other_tenant_context(self, tenant, tenant_b, setup_cross_tenant_data):
        band_a, band_b = setup_cross_tenant_data

        set_current_tenant(tenant_b)
        bands = list(GradeBand.objects.all())
        band_ids = [b.id for b in bands]
        assert band_b.id in band_ids
        assert band_a.id not in band_ids
        clear_current_tenant()

    def test_no_tenant_context_returns_all(self, tenant, tenant_b, setup_cross_tenant_data):
        band_a, band_b = setup_cross_tenant_data

        clear_current_tenant()
        bands = list(GradeBand.objects.all())
        band_ids = [b.id for b in bands]
        assert band_a.id in band_ids
        assert band_b.id in band_ids

    def test_all_objects_bypasses_filtering(self, tenant, tenant_b, setup_cross_tenant_data):
        band_a, band_b = setup_cross_tenant_data

        set_current_tenant(tenant)
        all_bands = list(GradeBand.all_objects.all())
        all_ids = [b.id for b in all_bands]
        assert band_a.id in all_ids
        assert band_b.id in all_ids
        clear_current_tenant()

    def test_all_tenants_bypass_method(self, tenant, tenant_b, setup_cross_tenant_data):
        band_a, band_b = setup_cross_tenant_data

        set_current_tenant(tenant)
        bypass_bands = list(GradeBand.objects.all_tenants().all())
        bypass_ids = [b.id for b in bypass_bands]
        assert band_a.id in bypass_ids
        assert band_b.id in bypass_ids
        clear_current_tenant()

    def test_tenant_filtering_applies_to_grades(self, tenant, tenant_b):
        """Verify TenantManager filtering works on Grade model too."""
        band_a = GradeBand.objects.create(tenant=tenant, name="BA", short_code="BA", order=1)
        band_b = GradeBand.objects.create(tenant=tenant_b, name="BB", short_code="BB", order=1)
        grade_a = Grade.objects.create(tenant=tenant, grade_band=band_a, name="GA", short_code="GA", order=1)
        grade_b = Grade.objects.create(tenant=tenant_b, grade_band=band_b, name="GB", short_code="GB", order=1)

        set_current_tenant(tenant)
        grade_ids = [g.id for g in Grade.objects.all()]
        assert grade_a.id in grade_ids
        assert grade_b.id not in grade_ids
        clear_current_tenant()

    def test_tenant_filtering_applies_to_subjects(self, tenant, tenant_b):
        """Verify TenantManager filtering works on Subject model."""
        sub_a = Subject.objects.create(tenant=tenant, name="Math", code="MA")
        sub_b = Subject.objects.create(tenant=tenant_b, name="Math", code="MA")

        set_current_tenant(tenant_b)
        sub_ids = [s.id for s in Subject.objects.all()]
        assert sub_b.id in sub_ids
        assert sub_a.id not in sub_ids
        clear_current_tenant()

    def test_tenant_filtering_applies_to_sections(self, tenant, tenant_b):
        """Verify TenantManager filtering works on Section model."""
        band = GradeBand.objects.create(tenant=tenant, name="B1", short_code="B1", order=1)
        grade = Grade.objects.create(tenant=tenant, grade_band=band, name="G1", short_code="G1X", order=1)
        sec_a = Section.objects.create(tenant=tenant, grade=grade, name="A", academic_year="2026-27")

        band_b = GradeBand.objects.create(tenant=tenant_b, name="B2", short_code="B2", order=1)
        grade_b = Grade.objects.create(tenant=tenant_b, grade_band=band_b, name="G1", short_code="G1Y", order=1)
        sec_b = Section.objects.create(tenant=tenant_b, grade=grade_b, name="A", academic_year="2026-27")

        set_current_tenant(tenant)
        sec_ids = [s.id for s in Section.objects.all()]
        assert sec_a.id in sec_ids
        assert sec_b.id not in sec_ids
        clear_current_tenant()


# ===========================================================================
# Reverse relation and related_name checks
# ===========================================================================

@pytest.mark.django_db
class TestReverseRelations:

    def test_tenant_grade_bands_reverse(self, tenant, grade_band):
        assert grade_band in tenant.grade_bands.all()

    def test_tenant_grades_reverse(self, tenant, grade):
        assert grade in tenant.grades.all()

    def test_tenant_sections_reverse(self, tenant, section):
        assert section in tenant.sections.all()

    def test_tenant_subjects_reverse(self, tenant, subject):
        assert subject in tenant.subjects.all()

    def test_tenant_teaching_assignments_reverse(self, tenant, teaching_assignment):
        assert teaching_assignment in tenant.teaching_assignments.all()

    def test_grade_band_grades_reverse(self, grade_band, grade):
        assert grade in grade_band.grades.all()

    def test_grade_sections_reverse(self, grade, section):
        assert section in grade.sections.all()

    def test_subject_teaching_assignments_reverse(self, subject, teaching_assignment):
        assert teaching_assignment in subject.teaching_assignments.all()

    def test_teacher_teaching_assignments_reverse(self, teacher_user, teaching_assignment):
        assert teaching_assignment in teacher_user.teaching_assignments.all()

    def test_section_teaching_assignments_reverse(self, section, teaching_assignment):
        assert teaching_assignment in section.teaching_assignments.all()

    def test_teacher_class_teacher_sections_reverse(self, tenant, grade, teacher_user):
        sec = Section.objects.create(
            tenant=tenant, grade=grade, name="CT", academic_year="2026-27",
            class_teacher=teacher_user,
        )
        assert sec in teacher_user.class_teacher_sections.all()
