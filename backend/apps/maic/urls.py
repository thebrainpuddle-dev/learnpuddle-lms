"""HTTP routes for MAIC v2.

Mounted into the project URL config under /api/maic/v2/.
"""
from django.urls import path

from .views import MaicSessionCreateView
from .views_generation import MaicGenerationCreateView

app_name = "maic_v2"

urlpatterns = [
    path("sessions/", MaicSessionCreateView.as_view(), name="session-create"),
    path("generate/", MaicGenerationCreateView.as_view(), name="generate-create"),
]
