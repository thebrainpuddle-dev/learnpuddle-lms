"""
Tests for the Stripe webhook endpoint (OBS-4 fix: exception granularity).

Before the fix, ALL exceptions from ``construct_webhook_event`` were caught
and returned as 400. This meant:
- ``stripe.error.SignatureVerificationError`` (tampered request) → 400
- Unexpected ``Exception`` (runtime bug) → 400

After the fix the three cases are distinguished:
- ``ValueError`` (malformed payload / config error) → 400 (no retry)
- ``stripe.error.SignatureVerificationError`` → 401 (clear auth failure)
- ``Exception`` (unexpected) → 500 (triggers Stripe auto-retry)

These tests also cover:
- Missing ``Stripe-Signature`` header → 400
- Valid event dispatched to registered handler → 200
- Unknown event type (no handler) → 200 (logged but not retried)

The endpoint URL is ``/api/webhooks/stripe/`` (see config/urls.py).
No authentication is required (Stripe signs the payload).
"""
from __future__ import annotations

import json
from unittest import mock

import pytest
import stripe
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


STRIPE_WEBHOOK_URL = "/api/webhooks/stripe/"

# Minimal valid-looking event payload for tests that need to get past
# signature verification (construct_webhook_event is mocked in those tests).
_MINIMAL_EVENT_PAYLOAD = json.dumps({
    "id": "evt_test_123",
    "type": "checkout.session.completed",
    "object": "event",
    "data": {"object": {}},
}).encode("utf-8")


@pytest.fixture
def anon_client():
    """APIClient with no auth.

    Throttling is bypassed by mocking the throttle's allow_request method
    so individual tests do not need to worry about rate limits.
    """
    return APIClient()


@pytest.fixture(autouse=True)
def bypass_stripe_throttle():
    """Auto-use fixture: bypass StripeWebhookThrottle for all tests in this
    module so rate-limit 429s don't interfere with exception-handling assertions.
    """
    with mock.patch(
        "apps.billing.webhook_views.StripeWebhookThrottle.allow_request",
        return_value=True,
    ):
        yield


# ---------------------------------------------------------------------------
# 1. Missing Stripe-Signature header
# ---------------------------------------------------------------------------


def test_missing_signature_returns_400(anon_client):
    """Stripe-Signature header is required. Missing → 400 (no retry)."""
    resp = anon_client.post(
        STRIPE_WEBHOOK_URL,
        data=_MINIMAL_EVENT_PAYLOAD,
        content_type="application/json",
        # Deliberately no HTTP_STRIPE_SIGNATURE header
    )
    assert resp.status_code == 400
    assert "signature" in resp.data.get("error", "").lower()


# ---------------------------------------------------------------------------
# 2. ValueError (malformed payload / config error) → 400
# ---------------------------------------------------------------------------


def test_value_error_returns_400(anon_client):
    """A ValueError from construct_webhook_event → 400 (Stripe won't retry).

    Typical causes: malformed JSON, missing STRIPE_WEBHOOK_SECRET.
    Stripe should not retry these — the payload itself is bad.
    """
    with mock.patch(
        "apps.billing.stripe_service.construct_webhook_event",
        side_effect=ValueError("Malformed payload"),
    ):
        resp = anon_client.post(
            STRIPE_WEBHOOK_URL,
            data=_MINIMAL_EVENT_PAYLOAD,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1234,v1=abc",
        )
    assert resp.status_code == 400
    assert "payload" in resp.data.get("error", "").lower()


# ---------------------------------------------------------------------------
# 3. SignatureVerificationError → 401 (OBS-4 regression guard)
# ---------------------------------------------------------------------------


def test_signature_verification_error_returns_401(anon_client):
    """HMAC mismatch → 401. Key OBS-4 regression: pre-fix this was 400.

    401 surfaces distinctly in Stripe's delivery dashboard vs application
    errors (500) — easier on-call triage.
    """
    with mock.patch(
        "apps.billing.stripe_service.construct_webhook_event",
        side_effect=stripe.error.SignatureVerificationError(
            "Signature mismatch", "t=1234,v1=bad"
        ),
    ):
        resp = anon_client.post(
            STRIPE_WEBHOOK_URL,
            data=_MINIMAL_EVENT_PAYLOAD,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1234,v1=bad",
        )
    assert resp.status_code == 401, (
        f"Expected 401 for SignatureVerificationError, got {resp.status_code}. "
        "OBS-4 regression: exception granularity not applied?"
    )
    assert "signature" in resp.data.get("error", "").lower()


# ---------------------------------------------------------------------------
# 4. Unexpected Exception → 500 (OBS-4 regression guard)
# ---------------------------------------------------------------------------


def test_unexpected_exception_returns_500(anon_client):
    """An unexpected runtime error during event construction → 500.

    Key OBS-4 regression: pre-fix this was 400. 500 triggers Stripe's
    automatic delivery retry, so transient errors self-heal.
    """
    with mock.patch(
        "apps.billing.stripe_service.construct_webhook_event",
        side_effect=RuntimeError("Unexpected database error"),
    ):
        resp = anon_client.post(
            STRIPE_WEBHOOK_URL,
            data=_MINIMAL_EVENT_PAYLOAD,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1234,v1=xyz",
        )
    assert resp.status_code == 500, (
        f"Expected 500 for unexpected Exception, got {resp.status_code}. "
        "OBS-4 regression: exception granularity not applied?"
    )
    assert "error" in resp.data


# ---------------------------------------------------------------------------
# 5. Valid event dispatched to registered handler → 200
# ---------------------------------------------------------------------------


def _make_mock_event(event_type="checkout.session.completed"):
    """Build a minimal mock Stripe event object."""
    event = mock.MagicMock()
    event.id = "evt_test_ok"
    event.type = event_type
    return event


def test_valid_event_with_registered_handler_returns_200(anon_client):
    """A valid event whose type has a registered handler → 200 with
    {"received": True}. Handler is invoked once."""
    mock_event = _make_mock_event("checkout.session.completed")
    mock_handler = mock.MagicMock()

    with (
        mock.patch(
            "apps.billing.stripe_service.construct_webhook_event",
            return_value=mock_event,
        ),
        mock.patch(
            "apps.billing.webhook_handlers.handle_checkout_session_completed",
            mock_handler,
        ),
    ):
        resp = anon_client.post(
            STRIPE_WEBHOOK_URL,
            data=_MINIMAL_EVENT_PAYLOAD,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1234,v1=valid",
        )

    assert resp.status_code == 200
    assert resp.data.get("received") is True
    mock_handler.assert_called_once_with(mock_event)


# ---------------------------------------------------------------------------
# 6. Valid event with no registered handler → 200 (logged only)
# ---------------------------------------------------------------------------


def test_valid_event_with_unknown_type_returns_200(anon_client):
    """Unknown event type (no handler) → 200. Stripe should not retry;
    this is expected behaviour (we only process specific events)."""
    mock_event = _make_mock_event("some.unknown.event")

    with mock.patch(
        "apps.billing.stripe_service.construct_webhook_event",
        return_value=mock_event,
    ):
        resp = anon_client.post(
            STRIPE_WEBHOOK_URL,
            data=_MINIMAL_EVENT_PAYLOAD,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1234,v1=valid",
        )

    assert resp.status_code == 200
    assert resp.data.get("received") is True


# ---------------------------------------------------------------------------
# 7. Handler raises an exception → still returns 200 (Stripe won't retry)
# ---------------------------------------------------------------------------


def test_handler_exception_still_returns_200(anon_client):
    """If the handler raises an exception the view catches it, logs it,
    and returns 200 — preventing pointless Stripe retries for application-
    side errors that are logged for investigation."""
    mock_event = _make_mock_event("checkout.session.completed")

    with (
        mock.patch(
            "apps.billing.stripe_service.construct_webhook_event",
            return_value=mock_event,
        ),
        mock.patch(
            "apps.billing.webhook_handlers.handle_checkout_session_completed",
            side_effect=Exception("Handler crash"),
        ),
    ):
        resp = anon_client.post(
            STRIPE_WEBHOOK_URL,
            data=_MINIMAL_EVENT_PAYLOAD,
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="t=1234,v1=valid",
        )

    assert resp.status_code == 200
