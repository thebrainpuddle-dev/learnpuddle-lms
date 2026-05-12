"""HTTP routes for MAIC v2.

Mounted into the project URL config under /api/maic/v2/.
"""
from django.urls import path

from .views import MaicQuizGradeView, MaicSessionCreateView
from .views_generation import MaicGenerationCreateView, MaicGenerationDetailView

app_name = "maic_v2"

urlpatterns = [
    path("sessions/", MaicSessionCreateView.as_view(), name="session-create"),
    path("generate/", MaicGenerationCreateView.as_view(), name="generate-create"),
    path("generate/<str:job_id>/", MaicGenerationDetailView.as_view(), name="generate-detail"),
    path("quiz-grade/", MaicQuizGradeView.as_view(), name="quiz-grade"),
    path("quiz/grade/", MaicQuizGradeView.as_view(), name="quiz-grade-canonical"),
]
