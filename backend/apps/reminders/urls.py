from django.urls import path

from . import views

app_name = "reminders"

urlpatterns = [
    path("preview/", views.reminder_preview, name="reminder_preview"),
    path("send/", views.reminder_send, name="reminder_send"),
    path("history/", views.reminder_history, name="reminder_history"),
    path("automation-status/", views.reminder_automation_status, name="reminder_automation_status"),
]
