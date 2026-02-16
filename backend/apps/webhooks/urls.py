# apps/webhooks/urls.py
from django.urls import path
from . import views

app_name = 'webhooks'

urlpatterns = [
    path('', views.webhook_list_create, name='list_create'),
    path('events/', views.webhook_events, name='events'),
    path('<uuid:webhook_id>/', views.webhook_detail, name='detail'),
    path('<uuid:webhook_id>/secret/', views.webhook_regenerate_secret, name='regenerate_secret'),
    path('<uuid:webhook_id>/test/', views.webhook_test, name='test'),
    path('<uuid:webhook_id>/deliveries/', views.webhook_deliveries, name='deliveries'),
]
