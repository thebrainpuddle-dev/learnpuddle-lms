"""HTTP routes for media generation (Phase 9, MAIC-914).

Mounted into config/urls.py at /api/maic/v2/media/ (parallel to
/api/maic/v2/pbl/ from Phase 7).
"""
from django.urls import path

from apps.maic.media.views import GenerateImageView, GenerateVideoView


app_name = "maic_media"

urlpatterns = [
    path(
        "generate-image/",
        GenerateImageView.as_view(),
        name="generate-image",
    ),
    path(
        "generate-video/",
        GenerateVideoView.as_view(),
        name="generate-video",
    ),
]
