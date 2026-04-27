"""
URL patterns for integrations_calendar.

Mounted in config/urls.py under both /api/v1/ and /api/:

  POST   admin/calendar/{provider}/connect/
  GET    calendar/{provider}/callback/
  POST   admin/calendar/{provider}/disconnect/
  GET    calendar/ical/{user_uuid}/{token}.ics
  POST   calendar/ical/revoke/
"""

from django.urls import path

from . import views

app_name = "integrations_calendar"

urlpatterns = [
    # Admin: initiate OAuth connection.
    path(
        "admin/calendar/<str:provider>/connect/",
        views.connect_calendar,
        name="connect",
    ),
    # Provider OAuth redirect callback (no admin restriction — provider redirects here).
    path(
        "calendar/<str:provider>/callback/",
        views.calendar_callback,
        name="callback",
    ),
    # Admin: disconnect / revoke.
    path(
        "admin/calendar/<str:provider>/disconnect/",
        views.disconnect_calendar,
        name="disconnect",
    ),
    # Public iCal feed (token-authenticated, rate-limited).
    path(
        "calendar/ical/<str:user_uuid>/<str:token>.ics",
        views.ical_feed,
        name="ical_feed",
    ),
    # Authenticated: rotate iCal token.
    path(
        "calendar/ical/revoke/",
        views.ical_revoke,
        name="ical_revoke",
    ),
]
