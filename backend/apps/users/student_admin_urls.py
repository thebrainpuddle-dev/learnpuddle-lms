from django.urls import path

from . import student_admin_views

app_name = "admin_students"

urlpatterns = [
    path("", student_admin_views.students_list_view, name="students_list"),
    path("deleted/", student_admin_views.deleted_students_list_view, name="deleted_students_list"),
    path("register/", student_admin_views.register_student_view, name="register_student"),
    path("bulk-import/", student_admin_views.students_bulk_import_view, name="students_bulk_import"),
    path("bulk-action/", student_admin_views.students_bulk_action, name="students_bulk_action"),
    path("<uuid:student_id>/", student_admin_views.student_detail_view, name="student_detail"),
    path("<uuid:student_id>/restore/", student_admin_views.restore_student_view, name="restore_student"),
    path("invitations/", student_admin_views.student_invitations_view, name="student_invitations"),
    path("bulk-invite/", student_admin_views.student_bulk_invite_view, name="student_bulk_invite"),
]
