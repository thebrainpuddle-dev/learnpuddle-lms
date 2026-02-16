# apps/tenants/onboarding_urls.py
"""
Public onboarding URLs (no authentication required).
"""

from django.urls import path
from . import onboarding_views

urlpatterns = [
    path('signup/', onboarding_views.tenant_signup, name='tenant_signup'),
    path('check-subdomain/', onboarding_views.check_subdomain, name='check_subdomain'),
    path('plans/', onboarding_views.available_plans, name='available_plans'),
]
