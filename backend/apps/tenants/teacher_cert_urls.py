# apps/tenants/teacher_cert_urls.py

from django.urls import path
from . import teacher_cert_views

app_name = "teacher_certifications"

urlpatterns = [
    path('certifications/', teacher_cert_views.my_certifications, name='my_certifications'),
]
