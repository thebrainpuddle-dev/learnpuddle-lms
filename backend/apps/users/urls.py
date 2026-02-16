# apps/users/urls.py

from django.urls import path
from . import views, sso_views, twofa_views

app_name = 'users'

urlpatterns = [
    # Authentication
    path('auth/login/', views.login_view, name='login'),
    path('auth/logout/', views.logout_view, name='logout'),
    path('auth/refresh/', views.refresh_token_view, name='refresh'),
    path('auth/me/', views.me_view, name='me'),
    
    # User management
    path('auth/register-teacher/', views.register_teacher_view, name='register_teacher'),
    path('auth/change-password/', views.change_password_view, name='change_password'),
    path('auth/request-password-reset/', views.request_password_reset_view, name='request_password_reset'),
    path('auth/confirm-password-reset/', views.confirm_password_reset_view, name='confirm_password_reset'),
    path('auth/preferences/', views.preferences_view, name='preferences'),
    path('auth/verify-email/', views.verify_email_view, name='verify_email'),
    path('auth/resend-verification/', views.resend_verification_view, name='resend_verification'),
    
    # SSO (Single Sign-On)
    path('auth/sso/providers/', sso_views.sso_providers, name='sso_providers'),
    path('auth/sso/callback/<str:backend>/', sso_views.sso_callback, name='sso_callback'),
    path('auth/sso/token-exchange/', sso_views.sso_token_exchange, name='sso_token_exchange'),
    path('auth/sso/status/', sso_views.sso_status, name='sso_status'),
    path('auth/sso/unlink/', sso_views.sso_unlink, name='sso_unlink'),
    
    # 2FA (Two-Factor Authentication)
    path('auth/2fa/status/', twofa_views.twofa_status, name='twofa_status'),
    path('auth/2fa/setup/', twofa_views.twofa_setup_start, name='twofa_setup_start'),
    path('auth/2fa/confirm/', twofa_views.twofa_setup_confirm, name='twofa_setup_confirm'),
    path('auth/2fa/disable/', twofa_views.twofa_disable, name='twofa_disable'),
    path('auth/2fa/backup-codes/', twofa_views.twofa_regenerate_backup_codes, name='twofa_backup_codes'),
    path('auth/2fa/verify/', twofa_views.twofa_verify, name='twofa_verify'),
]
