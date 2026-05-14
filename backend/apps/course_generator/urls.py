"""URL patterns for TASK-060 — AI Course Generator.

Mounted at /api/v1/admin/course-generator/ (and /api/ mirror) via config/urls.py.
"""

from django.urls import path

from .views import (
    create_generation_job_api_view,
    delete_generation_job_api_view,
    get_generation_job_api_view,
    list_generation_jobs_api_view,
    materialise_job_api_view,
)

urlpatterns = [
    # POST /admin/course-generator/  — enqueue job
    path("", create_generation_job_api_view, name="course_generator_create"),
    # GET  /admin/course-generator/jobs/  — list jobs
    path("jobs/", list_generation_jobs_api_view, name="course_generator_list"),
    # GET + DELETE /admin/course-generator/jobs/{job_id}/  — poll status / purge job
    # get_generation_job now accepts both GET and DELETE (TASK-060 L1 spec fix).
    path("jobs/<uuid:job_id>/", get_generation_job_api_view, name="course_generator_detail"),
    # POST /admin/course-generator/jobs/{job_id}/materialise/  — create draft
    path("jobs/<uuid:job_id>/materialise/", materialise_job_api_view, name="course_generator_materialise"),
    # DELETE /admin/course-generator/jobs/{job_id}/delete/  — legacy URL (backward compat)
    # Frontend aiCourseGeneratorService.ts may still hit this; keep it alive.
    path("jobs/<uuid:job_id>/delete/", delete_generation_job_api_view, name="course_generator_delete_legacy"),
]
