"""HTTP routes for the PBL subsystem (Phase 7, MAIC-704).

Mounted into config/urls.py at `/api/maic/v2/pbl/` (parallel to
`/api/maic/v2/sessions/` and `/api/maic/v2/generate/` from
apps.maic.urls).
"""
from django.urls import path

from apps.maic_pbl.views import PBLProjectCreateView


app_name = "maic_pbl"

urlpatterns = [
    path(
        "projects/",
        PBLProjectCreateView.as_view(),
        name="project-create",
    ),
]
