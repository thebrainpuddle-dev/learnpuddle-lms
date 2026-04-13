# apps/progress/certification_urls.py

from django.urls import path

from . import certification_views

app_name = "certifications"

urlpatterns = [
    # CertificationType CRUD
    path("types/", certification_views.certification_type_list, name="type_list"),
    path("types/create/", certification_views.certification_type_create, name="type_create"),
    path("types/<uuid:cert_type_id>/", certification_views.certification_type_detail, name="type_detail"),
    path("types/<uuid:cert_type_id>/update/", certification_views.certification_type_update, name="type_update"),
    path("types/<uuid:cert_type_id>/delete/", certification_views.certification_type_delete, name="type_delete"),

    # TeacherCertification management
    path("", certification_views.certification_list, name="certification_list"),
    path("issue/", certification_views.certification_issue, name="certification_issue"),
    path("<uuid:cert_id>/", certification_views.certification_detail, name="certification_detail"),
    path("<uuid:cert_id>/revoke/", certification_views.certification_revoke, name="certification_revoke"),
    path("<uuid:cert_id>/renew/", certification_views.certification_renew, name="certification_renew"),

    # Expiry check
    path("expiry-check/", certification_views.certification_expiry_check, name="expiry_check"),
]
