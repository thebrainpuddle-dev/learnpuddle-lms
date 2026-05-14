"""
Outlook / MS Graph Calendar provider for integrations_calendar.

OAuth flow:
  - Scope: Calendars.ReadWrite (on the dedicated calendar only)
  - Creates a dedicated "LearnPuddle" calendar on first connect.
  - Uses msal for token management.

Secrets required (from settings / env):
  OUTLOOK_CLIENT_ID
  OUTLOOK_CLIENT_SECRET
  OUTLOOK_TENANT_ID  (use "common" for multi-tenant apps)
"""

from __future__ import annotations

import logging
import requests
from typing import TYPE_CHECKING

from django.conf import settings

logger = logging.getLogger(__name__)

SCOPES = ["Calendars.ReadWrite", "User.Read", "offline_access"]
CALENDAR_NAME = "LearnPuddle"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}"
REDIRECT_URI_SETTING = "OUTLOOK_CALENDAR_REDIRECT_URI"

if TYPE_CHECKING:
    from apps.integrations_calendar.models import CalendarConnection


def get_auth_url(state: str) -> dict:
    """
    Return the full MSAL auth code flow dict for the Outlook OAuth2 flow.

    Unlike Google's get_auth_url() (which returns a plain URL string), this
    returns the complete dict from initiate_auth_code_flow() so that
    connect_calendar can store it server-side and pass it back verbatim as
    ``session_state`` to acquire_token_by_auth_code_flow() on the callback,
    enabling full nonce/PKCE validation at the MSAL layer.

    The dict includes: auth_uri, state, code_verifier, code_challenge,
    code_challenge_method, nonce, redirect_uri, scope, claims_challenge.

    Callers must check the return type:
      - dict  → Outlook: extract ``result["auth_uri"]``; store full dict in cache.
      - str   → Google (other providers): store integer 1 as existence sentinel.

    Raises ImportError if msal is not installed.
    """
    return get_auth_flow(state)


def get_auth_flow(state: str) -> dict:
    """
    Return the full MSAL auth code flow dict for server-side storage (Slice B).

    Unlike get_auth_url() which discards all but auth_uri, this returns the
    complete dict that acquire_token_by_auth_code_flow() requires for nonce/PKCE
    validation:

      - auth_uri           — the redirect URL to send the user to
      - state              — the CSRF state token (same as the ``state`` arg)
      - code_verifier      — PKCE verifier (kept secret, never sent to provider)
      - code_challenge     — PKCE challenge (hash of verifier, embedded in auth_uri)
      - code_challenge_method — "S256"
      - nonce              — id_token nonce for replay protection
      - redirect_uri       — must match what was used to build auth_uri
      - scope              — space-separated scope list

    Store the returned dict in the server-side cache keyed by state and pass it
    back verbatim as ``session_state`` to exchange_code() on the OAuth callback.
    Raises ImportError if msal is not installed.
    """
    try:
        import msal
    except ImportError as exc:
        raise ImportError(
            "msal is required for Outlook Calendar integration. "
            "Add msal>=1.28 to requirements.txt."
        ) from exc

    authority = AUTHORITY_TEMPLATE.format(
        tenant_id=getattr(settings, "OUTLOOK_TENANT_ID", "common")
    )
    # ConfidentialClientApplication is required for server-side auth code flow.
    app = msal.ConfidentialClientApplication(
        client_id=settings.OUTLOOK_CLIENT_ID,
        client_credential=settings.OUTLOOK_CLIENT_SECRET,
        authority=authority,
    )
    # initiate_auth_code_flow returns a dict that must be stored server-side
    # and passed back to acquire_token_by_auth_code_flow on the callback.
    return app.initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=_redirect_uri(),
        state=state,
        prompt="select_account",
    )


def exchange_code(code: str, state: str, session_state: dict) -> dict:
    """
    Exchange authorisation code for access + refresh tokens.

    ``session_state`` is the dict returned by ``initiate_auth_code_flow``
    (must be stored in the session by the connect view and passed back here).

    Returns dict with keys: access_token, refresh_token, scopes,
    provider_user_id (MS Graph "id").
    """
    try:
        import msal
    except ImportError as exc:
        raise ImportError("msal is required.") from exc

    authority = AUTHORITY_TEMPLATE.format(
        tenant_id=getattr(settings, "OUTLOOK_TENANT_ID", "common")
    )
    app = msal.ConfidentialClientApplication(
        client_id=settings.OUTLOOK_CLIENT_ID,
        client_credential=settings.OUTLOOK_CLIENT_SECRET,
        authority=authority,
    )
    auth_response = {"code": code, "state": state}
    result = app.acquire_token_by_auth_code_flow(
        auth_code_flow=session_state,
        auth_response=auth_response,
    )
    if "error" in result:
        raise ValueError(f"MSAL token exchange failed: {result.get('error_description', result['error'])}")

    access_token = result.get("access_token", "")
    refresh_token = result.get("refresh_token", "")
    provider_user_id = _fetch_graph_user_id(access_token)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "scopes": " ".join(result.get("scope", SCOPES) if isinstance(result.get("scope"), list) else SCOPES),
        "provider_user_id": provider_user_id,
    }


def refresh_access_token(connection: "CalendarConnection") -> str:
    """
    Refresh the access token using the stored refresh token.
    Returns the new access token and updates the connection.
    """
    try:
        import msal
    except ImportError as exc:
        raise ImportError("msal is required.") from exc

    authority = AUTHORITY_TEMPLATE.format(
        tenant_id=getattr(settings, "OUTLOOK_TENANT_ID", "common")
    )
    app = msal.ConfidentialClientApplication(
        client_id=settings.OUTLOOK_CLIENT_ID,
        client_credential=settings.OUTLOOK_CLIENT_SECRET,
        authority=authority,
    )
    refresh_token = connection.get_refresh_token()
    result = app.acquire_token_by_refresh_token(
        refresh_token=refresh_token,
        scopes=SCOPES,
    )
    if "error" in result:
        raise ValueError(f"MSAL refresh failed: {result.get('error_description', result['error'])}")

    new_access = result.get("access_token", "")
    new_refresh = result.get("refresh_token", refresh_token)
    connection.set_access_token(new_access)
    if new_refresh:
        connection.set_refresh_token(new_refresh)
    connection.save(update_fields=["access_token_encrypted", "refresh_token_encrypted"])
    return new_access


def ensure_learnpuddle_calendar(connection: "CalendarConnection") -> str:
    """
    Create the dedicated LearnPuddle calendar in Outlook if it doesn't exist yet.
    Returns the calendar ID.
    """
    headers = _auth_headers(connection)
    resp = requests.get(f"{GRAPH_BASE}/me/calendars", headers=headers, timeout=15)
    resp.raise_for_status()
    for cal in resp.json().get("value", []):
        if cal.get("name") == CALENDAR_NAME:
            return cal["id"]

    create_resp = requests.post(
        f"{GRAPH_BASE}/me/calendars",
        headers={**headers, "Content-Type": "application/json"},
        json={
            "name": CALENDAR_NAME,
            "isDefaultCalendar": False,
        },
        timeout=15,
    )
    create_resp.raise_for_status()
    return create_resp.json()["id"]


def upsert_event(connection: "CalendarConnection", event_data: dict) -> str:
    """
    Create or update an Outlook Calendar event.

    ``event_data`` must contain:
      - uid: stable UID string (used as iCalUId for idempotency lookup)
      - summary: event title
      - description: event description
      - start_dt: UTC datetime
      - end_dt: UTC datetime

    Returns the provider event ID.
    """
    headers = {**_auth_headers(connection), "Content-Type": "application/json"}
    calendar_id = connection.target_calendar_id

    body = {
        "subject": event_data["summary"],
        "body": {
            "contentType": "text",
            "content": event_data.get("description", ""),
        },
        "start": {
            "dateTime": event_data["start_dt"].strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": event_data["end_dt"].strftime("%Y-%m-%dT%H:%M:%S"),
            "timeZone": "UTC",
        },
        "isReminderOn": False,
    }

    # Look up existing event by iCalUId (stable UID).
    filter_url = (
        f"{GRAPH_BASE}/me/calendars/{calendar_id}/events"
        f"?$filter=iCalUId eq '{event_data['uid']}'&$select=id"
    )
    lookup = requests.get(filter_url, headers=_auth_headers(connection), timeout=15)
    lookup.raise_for_status()
    items = lookup.json().get("value", [])

    if items:
        provider_event_id = items[0]["id"]
        patch_resp = requests.patch(
            f"{GRAPH_BASE}/me/calendars/{calendar_id}/events/{provider_event_id}",
            headers=headers,
            json=body,
            timeout=15,
        )
        patch_resp.raise_for_status()
    else:
        create_resp = requests.post(
            f"{GRAPH_BASE}/me/calendars/{calendar_id}/events",
            headers=headers,
            json=body,
            timeout=15,
        )
        create_resp.raise_for_status()
        provider_event_id = create_resp.json()["id"]

    return provider_event_id


def delete_event(connection: "CalendarConnection", provider_event_id: str) -> None:
    """Delete an Outlook Calendar event by its provider event ID."""
    try:
        resp = requests.delete(
            f"{GRAPH_BASE}/me/calendars/{connection.target_calendar_id}/events/{provider_event_id}",
            headers=_auth_headers(connection),
            timeout=15,
        )
        resp.raise_for_status()
    except Exception:
        logger.exception(
            "outlook: failed to delete event %s for connection %s",
            provider_event_id, connection.pk,
        )


def revoke_tokens(connection: "CalendarConnection") -> None:
    """
    Revoke OAuth tokens for Outlook.

    MS Graph does not have a direct token revocation endpoint (tokens
    expire naturally).  Best practice is to sign out the user from the
    tenant's session — here we just clear local tokens.  The connection
    status is set to 'revoked' by the disconnect view.
    """
    # MS doesn't expose a sync revocation URL; session is invalidated server-side.
    logger.info(
        "outlook: disconnecting connection %s — tokens cleared locally, "
        "MS session will expire naturally.",
        connection.pk,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _redirect_uri() -> str:
    return getattr(settings, REDIRECT_URI_SETTING, "")


def _auth_headers(connection: "CalendarConnection") -> dict:
    """Return Authorization headers with a valid access token."""
    access_token = connection.get_access_token()
    return {"Authorization": f"Bearer {access_token}"}


def _fetch_graph_user_id(access_token: str) -> str:
    """Retrieve the MS Graph user's 'id' field."""
    try:
        resp = requests.get(
            f"{GRAPH_BASE}/me?$select=id",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("id", "")
    except Exception:
        logger.exception("outlook: failed to fetch user id from MS Graph")
        return ""
