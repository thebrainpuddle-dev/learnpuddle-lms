from django.urls import path

from . import views


urlpatterns = [
    path("client-errors/ingest/", views.ops_client_error_ingest, name="ops_client_error_ingest_public"),
    path("proxy-errors/ingest/", views.ops_proxy_errors_ingest, name="ops_proxy_errors_ingest_public"),
]
