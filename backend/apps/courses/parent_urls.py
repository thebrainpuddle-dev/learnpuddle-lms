from django.urls import path
from . import parent_views

app_name = "parent"

urlpatterns = [
    # Auth (public)
    path("auth/request-link/", parent_views.parent_request_magic_link, name="request_link"),
    path("auth/verify/", parent_views.parent_verify_token, name="verify"),
    path("auth/refresh/", parent_views.parent_refresh_session, name="refresh"),
    path("auth/logout/", parent_views.parent_logout, name="logout"),
    path("auth/demo-login/", parent_views.parent_demo_login, name="demo_login"),

    # Protected
    path("children/", parent_views.parent_children_list, name="children_list"),
    path("children/<uuid:child_id>/overview/", parent_views.parent_child_overview, name="child_overview"),
]
