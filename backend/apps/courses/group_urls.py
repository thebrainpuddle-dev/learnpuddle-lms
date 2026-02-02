from django.urls import path

from . import group_views
from . import group_membership_views

app_name = "teacher_groups"

urlpatterns = [
    path("teacher-groups/", group_views.teacher_group_list_create, name="teacher_group_list_create"),
    path("teacher-groups/<uuid:group_id>/", group_views.teacher_group_detail, name="teacher_group_detail"),
    path(
        "teacher-groups/<uuid:group_id>/members/",
        group_membership_views.teacher_group_members,
        name="teacher_group_members",
    ),
    path(
        "teacher-groups/<uuid:group_id>/members/<uuid:teacher_id>/",
        group_membership_views.teacher_group_member_remove,
        name="teacher_group_member_remove",
    ),
]

