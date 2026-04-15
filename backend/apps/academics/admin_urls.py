# apps/academics/admin_urls.py
from django.urls import path
from . import admin_views
from .attendance_urls import admin_urlpatterns as attendance_patterns

app_name = "admin_academics"

urlpatterns = [
    # ─── GradeBands ───────────────────────────────────────────────
    path("grade-bands/", admin_views.grade_band_list_create, name="grade_band_list"),
    path("grade-bands/<uuid:band_id>/", admin_views.grade_band_detail, name="grade_band_detail"),

    # ─── Grades ───────────────────────────────────────────────────
    path("grades/", admin_views.grade_list_create, name="grade_list"),
    path("grades/<uuid:grade_id>/", admin_views.grade_detail, name="grade_detail"),

    # ─── Sections ─────────────────────────────────────────────────
    path("sections/", admin_views.section_list_create, name="section_list"),
    path("sections/<uuid:section_id>/", admin_views.section_detail, name="section_detail"),

    # ─── Section Detail Views (students, teachers, courses) ──────
    path("sections/<uuid:section_id>/students/", admin_views.section_students, name="section_students"),
    path("sections/<uuid:section_id>/teachers/", admin_views.section_teachers, name="section_teachers"),
    path("sections/<uuid:section_id>/courses/", admin_views.section_courses, name="section_courses"),

    # ─── Section Actions (import, add student) ───────────────────
    path("sections/<uuid:section_id>/import-students/", admin_views.section_import_students, name="section_import_students"),
    path("sections/<uuid:section_id>/add-student/", admin_views.section_add_student, name="section_add_student"),

    # ─── Subjects ─────────────────────────────────────────────────
    path("subjects/", admin_views.subject_list_create, name="subject_list"),
    path("subjects/<uuid:subject_id>/", admin_views.subject_detail, name="subject_detail"),

    # ─── Teaching Assignments ─────────────────────────────────────
    path("teaching-assignments/", admin_views.teaching_assignment_list_create, name="ta_list"),
    path("teaching-assignments/<uuid:assignment_id>/", admin_views.teaching_assignment_detail, name="ta_detail"),

    # ─── Student Transfer ─────────────────────────────────────────
    path("students/<uuid:student_id>/transfer/", admin_views.transfer_student, name="transfer_student"),

    # ─── Course Cloning ───────────────────────────────────────────
    path("courses/<uuid:course_id>/clone/", admin_views.clone_course_view, name="clone_course"),

    # ─── School Overview ──────────────────────────────────────────
    path("school-overview/", admin_views.school_overview, name="school_overview"),

    # ─── Academic Year Promotion ──────────────────────────────────
    path("promotion/preview/", admin_views.promotion_preview, name="promotion_preview"),
    path("promotion/execute/", admin_views.promotion_execute, name="promotion_execute"),

    # ─── Attendance ─────────────────────────────────────────────────
] + attendance_patterns
