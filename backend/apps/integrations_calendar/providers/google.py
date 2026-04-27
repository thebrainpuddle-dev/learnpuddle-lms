"""
Google Calendar provider for integrations_calendar.

OAuth flow:
  - Scope: https://www.googleapis.com/auth/calendar.app.created
    (app-only calendar access — cannot read/write calendars not created by this app)
  - Creates a dedicated "LearnPuddle" calendar on first connect.
  - Uses google-auth-oauthlib + google-api-python-client.

Secrets required (from settings / env):
  GOOGLE_CALENDAR_CLIENT_ID
  GOOGLE_CALENDAR_CLIENT_SECRET
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.conf import settings

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar.app.created"]
CALENDAR_NAME = "LearnPuddle"
REDIRECT_URI_SETTING = "GOOGLE_CALENDAR_REDIRECT_URI"

if TYPE_CHECKING:
    from apps.integrations_calendar.models import CalendarConnection


def get_auth_url(state: str) -> str:
    """
    Return the Google OAuth2 authorisation URL.
    Raises ImportError if google-auth-oauthlib is not installed.
    """
    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError as exc:
        raise ImportError(
            "google-auth-oauthlib is required for Google Calendar integration. "
            "Add google-auth-oauthlib>=1.2 to requirements.txt."
        ) from exc

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
            "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_redirect_uri()],
        }
    }

    flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state)
    flow.redirect_uri = _redirect_uri()

    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="false",
    )
    return auth_url


def exchange_code(code: str, state: str) -> dict:
    """
    Exchange authorisation code for access + refresh tokens.

    Returns dict with keys: access_token, refresh_token, scopes,
    provider_user_id (Google sub claim from tokeninfo).
    """
    try:
        from google_auth_oauthlib.flow import Flow
        import google.oauth2.credentials
        import googleapiclient.discovery
    except ImportError as exc:
        raise ImportError("google-auth-oauthlib and google-api-python-client are required.") from exc

    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CALENDAR_CLIENT_ID,
            "client_secret": settings.GOOGLE_CALENDAR_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_redirect_uri()],
        }
    }

    flow = Flow.from_client_config(client_config, scopes=SCOPES, state=state)
    flow.redirect_uri = _redirect_uri()
    flow.fetch_token(code=code)

    credentials = flow.credentials
    # Fetch the Google user sub to store as provider_user_id.
    provider_user_id = _fetch_google_sub(credentials)

    return {
        "access_token": credentials.token,
        "refresh_token": credentials.refresh_token or "",
        "scopes": " ".join(credentials.scopes or SCOPES),
        "provider_user_id": provider_user_id,
    }


def ensure_learnpuddle_calendar(connection: "CalendarConnection") -> str:
    """
    Create the dedicated LearnPuddle calendar if it doesn't exist yet.
    Returns the calendar ID.
    """
    service = _build_service(connection)
    calendar_list = service.calendarList().list().execute()
    for cal in calendar_list.get("items", []):
        if cal.get("summary") == CALENDAR_NAME:
            return cal["id"]

    new_cal = service.calendars().insert(body={
        "summary": CALENDAR_NAME,
        "description": "Course deadlines from LearnPuddle LMS",
        "timeZone": "UTC",
    }).execute()
    return new_cal["id"]


def upsert_event(connection: "CalendarConnection", event_data: dict) -> str:
    """
    Create or update a Google Calendar event.

    ``event_data`` must contain:
      - uid: stable UID string
      - summary: event title
      - description: event description
      - start_dt: UTC datetime
      - end_dt: UTC datetime

    Returns the provider event ID.
    """
    from apps.integrations_calendar.models import CalendarSyncedEvent

    service = _build_service(connection)
    calendar_id = connection.target_calendar_id

    body = {
        "summary": event_data["summary"],
        "description": event_data.get("description", ""),
        "start": {"dateTime": event_data["start_dt"].isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": event_data["end_dt"].isoformat(), "timeZone": "UTC"},
        "iCalUID": event_data["uid"],
    }

    # Check for existing event by UID.
    existing = service.events().list(
        calendarId=calendar_id,
        iCalUID=event_data["uid"],
    ).execute()

    items = existing.get("items", [])
    if items:
        provider_event_id = items[0]["id"]
        service.events().update(
            calendarId=calendar_id,
            eventId=provider_event_id,
            body=body,
        ).execute()
    else:
        result = service.events().insert(calendarId=calendar_id, body=body).execute()
        provider_event_id = result["id"]

    return provider_event_id


def delete_event(connection: "CalendarConnection", provider_event_id: str) -> None:
    """Delete a Google Calendar event by its provider event ID."""
    service = _build_service(connection)
    try:
        service.events().delete(
            calendarId=connection.target_calendar_id,
            eventId=provider_event_id,
        ).execute()
    except Exception:
        logger.exception(
            "google: failed to delete event %s for connection %s",
            provider_event_id, connection.pk,
        )


def revoke_tokens(connection: "CalendarConnection") -> None:
    """Revoke OAuth tokens at Google."""
    import requests as req_lib

    access_token = connection.get_access_token()
    if access_token:
        try:
            req_lib.post(
                "https://oauth2.googleapis.com/revoke",
                params={"token": access_token},
                timeout=10,
            )
        except Exception:
            logger.exception("google: token revocation failed for connection %s", connection.pk)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _redirect_uri() -> str:
    return getattr(settings, REDIRECT_URI_SETTING, "")


def _build_service(connection: "CalendarConnection"):
    """Build an authenticated Google Calendar API service client."""
    try:
        import google.oauth2.credentials
        import googleapiclient.discovery
    except ImportError as exc:
        raise ImportError("google-api-python-client is required.") from exc

    creds = google.oauth2.credentials.Credentials(
        token=connection.get_access_token(),
        refresh_token=connection.get_refresh_token(),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CALENDAR_CLIENT_ID,
        client_secret=settings.GOOGLE_CALENDAR_CLIENT_SECRET,
    )
    return googleapiclient.discovery.build("calendar", "v3", credentials=creds, cache_discovery=False)


def _fetch_google_sub(credentials) -> str:
    """Retrieve the Google user's 'sub' (subject) claim."""
    try:
        import googleapiclient.discovery
        oauth2_service = googleapiclient.discovery.build(
            "oauth2", "v2", credentials=credentials, cache_discovery=False,
        )
        info = oauth2_service.userinfo().get().execute()
        return info.get("id", "")
    except Exception:
        logger.exception("google: failed to fetch user sub")
        return ""
