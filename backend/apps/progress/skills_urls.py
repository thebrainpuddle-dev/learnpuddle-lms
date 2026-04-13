# apps/progress/skills_urls.py

from django.urls import path

from . import skills_views

app_name = "skills"

urlpatterns = [
    # Skill CRUD
    path("", skills_views.skill_list, name="skill_list"),
    path("create/", skills_views.skill_create, name="skill_create"),
    path("categories/", skills_views.skill_categories, name="skill_categories"),
    path("<uuid:skill_id>/", skills_views.skill_detail, name="skill_detail"),
    path("<uuid:skill_id>/update/", skills_views.skill_update, name="skill_update"),
    path("<uuid:skill_id>/delete/", skills_views.skill_delete, name="skill_delete"),

    # Course-skill mappings
    path("course-mappings/", skills_views.course_skill_list, name="course_skill_list"),
    path("course-mappings/create/", skills_views.course_skill_create, name="course_skill_create"),
    path("course-mappings/<uuid:mapping_id>/delete/", skills_views.course_skill_delete, name="course_skill_delete"),

    # Teacher skill matrix
    path("matrix/", skills_views.teacher_skill_matrix, name="teacher_skill_matrix"),
    path("assign/", skills_views.teacher_skill_assign, name="teacher_skill_assign"),
    path("teacher/<uuid:teacher_skill_id>/update/", skills_views.teacher_skill_update, name="teacher_skill_update"),
    path("teacher/<uuid:teacher_skill_id>/delete/", skills_views.teacher_skill_delete, name="teacher_skill_delete"),
    path("bulk-update/", skills_views.teacher_skill_bulk_update, name="teacher_skill_bulk_update"),

    # Gap analysis
    path("gap-analysis/", skills_views.skill_gap_analysis, name="skill_gap_analysis"),
]
