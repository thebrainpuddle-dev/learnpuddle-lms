# apps/users/urls.py

from django.urls import path
from . import views

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
]
