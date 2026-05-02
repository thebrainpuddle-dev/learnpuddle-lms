"""HTTP routes for MAIC v2.

Mounted into the project URL config under /api/maic/v2/.
"""
from django.urls import path

from .views import MaicSessionCreateView

app_name = "maic_v2"

urlpatterns = [
    path("sessions/", MaicSessionCreateView.as_view(), name="session-create"),
]
