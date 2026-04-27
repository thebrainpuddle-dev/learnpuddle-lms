# apps/users/saml_urls.py
"""URL routes for per-tenant SAML endpoints.

Included from the root URL conf so the subdomain in the path is the
authoritative tenant identifier for the SAML flow (not the Host
header).  This avoids coupling the IdP's ACS URL to a specific
subdomain host.
"""

from django.urls import path

from . import saml_views

app_name = "saml"

urlpatterns = [
    path(
        "auth/saml/<str:tenant_subdomain>/metadata/",
        saml_views.saml_metadata,
        name="metadata",
    ),
    path(
        "auth/saml/<str:tenant_subdomain>/login/",
        saml_views.saml_login,
        name="login",
    ),
    path(
        "auth/saml/<str:tenant_subdomain>/acs/",
        saml_views.saml_acs,
        name="acs",
    ),
    path(
        "auth/saml/<str:tenant_subdomain>/sls/",
        saml_views.saml_sls,
        name="sls",
    ),
]
