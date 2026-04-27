# apps/progress/rubric_urls.py
#
# TASK-044 — Rubric URL routes. Included from config/urls.py at the root
# of `_api_patterns` so the full paths match the TASK spec:
#   - /api/v1/admin/rubrics/
#   - /api/v1/admin/assignments/{id}/attach-rubric/
#   - /api/v1/admin/submissions/{id}/evaluate/
#   - /api/v1/teacher/submissions/{id}/evaluation/

from django.urls import path

from . import rubric_views

app_name = "rubrics"

urlpatterns = [
    # Admin: rubric CRUD
    path(
        "admin/rubrics/",
        rubric_views.rubric_list_create,
        name="rubric_list_create",
    ),
    path(
        "admin/rubrics/<uuid:rubric_id>/",
        rubric_views.rubric_detail,
        name="rubric_detail",
    ),
    path(
        "admin/rubrics/<uuid:rubric_id>/clone/",
        rubric_views.rubric_clone,
        name="rubric_clone",
    ),

    # Admin: attach / detach rubric on an assignment
    path(
        "admin/assignments/<uuid:assignment_id>/attach-rubric/",
        rubric_views.assignment_attach_rubric,
        name="assignment_attach_rubric",
    ),

    # Admin / evaluator: evaluate a submission with a rubric
    path(
        "admin/submissions/<uuid:submission_id>/evaluate/",
        rubric_views.submission_evaluate,
        name="submission_evaluate",
    ),

    # Teacher: view own evaluation
    path(
        "teacher/submissions/<uuid:submission_id>/evaluation/",
        rubric_views.submission_evaluation_view,
        name="submission_evaluation_view",
    ),
]
