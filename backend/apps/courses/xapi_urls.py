"""URL routes for the minimal xAPI LRS.

POST /api/v1/xapi/statements/        -> create (any authed tenant user)
GET  /api/v1/xapi/statements/        -> list (admin-only)
"""

from django.urls import path

from . import xapi_views

app_name = "xapi"

urlpatterns = [
    path(
        "xapi/statements/",
        xapi_views.xapi_statements,
        name="xapi_statements",
    ),
]
