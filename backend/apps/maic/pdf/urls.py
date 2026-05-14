"""HTTP routes for MAIC v2 PDF parsing."""
from django.urls import path

from apps.maic.pdf.views import ParsePDFView


app_name = "maic_pdf"

urlpatterns = [
    path("parse/", ParsePDFView.as_view(), name="parse"),
]
