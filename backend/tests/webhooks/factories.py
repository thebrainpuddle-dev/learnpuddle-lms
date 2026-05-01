# tests/webhooks/factories.py
"""
Shared test-data factories for the webhooks test suite.

These helpers avoid near-verbatim duplication across:
    - tests/webhooks/test_webhook_services.py
    - tests/webhooks/test_webhook_tasks.py
    - tests/webhooks/test_webhook_views.py

Usage example::

    from tests.webhooks.factories import make_tenant, make_user, make_endpoint, make_delivery

    tenant = make_tenant("My School", "myschool")
    admin  = make_user("admin@myschool.com", tenant)
    ep     = make_endpoint(tenant, admin)
    dlv    = make_delivery(ep)

All helpers require an active DB transaction (``@pytest.mark.django_db``
or ``django.test.TestCase``).

Reviewer note (N2, 2026-04-30): helpers in task/service/views test files
were near-verbatim duplicates. Central factory module replaces duplication
— existing test files import from here, keeping the public helper names
unchanged.
"""

import uuid
from django.utils import timezone


# ---------------------------------------------------------------------------
# Internal uid helper
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------

def make_tenant(name: str = "", subdomain: str = ""):
    """Create and return a Tenant suitable for webhook tests.

    Args:
        name:      Human-readable school name (default: auto-generated).
        subdomain: Unique subdomain slug (default: auto-generated).
    """
    from apps.tenants.models import Tenant

    uid = _uid()
    name      = name      or f"Webhook School {uid}"
    subdomain = subdomain or f"webhook{uid}"
    return Tenant.objects.create(
        name=name,
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.example.com",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

def make_user(email: str = "", tenant=None, role: str = "SCHOOL_ADMIN"):
    """Create and return a User belonging to *tenant*.

    Args:
        email:  User email (default: auto-generated from role + uid).
        tenant: Tenant the user belongs to.  Required.
        role:   Django role string (default: ``SCHOOL_ADMIN``).
    """
    from apps.users.models import User

    if tenant is None:
        raise ValueError("make_user() requires a Tenant instance")

    uid  = _uid()
    role_slug = role.lower().replace("_", "")
    email = email or f"{role_slug}_{uid}@webhook.example.com"

    return User.objects.create_user(
        email=email,
        password="Pass!123",
        first_name="Test",
        last_name="User",
        tenant=tenant,
        role=role,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# WebhookEndpoint
# ---------------------------------------------------------------------------

def make_endpoint(
    tenant,
    user,
    *,
    name: str = "Test Hook",
    url:  str = "https://hooks.example.com/test",
    events=None,
    is_active: bool = True,
    secret: str = "",
):
    """Create and return a WebhookEndpoint.

    Args:
        tenant:    Owner tenant.
        user:      ``created_by`` user.
        name:      Human-readable name (default: ``"Test Hook"``).
        url:       Delivery URL (default: a safe external URL for mocking).
        events:    List of event type strings (default: ``["course.created"]``).
        is_active: Whether the endpoint is active (default: ``True``).
        secret:    HMAC secret for signature verification (default: auto-assigned
                   by the model if left blank).
    """
    from apps.webhooks.models import WebhookEndpoint

    kwargs = dict(
        tenant=tenant,
        name=name,
        url=url,
        events=events or ["course.created"],
        created_by=user,
        is_active=is_active,
    )
    if secret:
        kwargs["secret"] = secret

    return WebhookEndpoint.objects.create(**kwargs)


# ---------------------------------------------------------------------------
# WebhookDelivery
# ---------------------------------------------------------------------------

def make_delivery(
    endpoint,
    *,
    status: str = "pending",
    event_type: str = "course.created",
    payload: dict | None = None,
    next_retry_at=None,
):
    """Create and return a WebhookDelivery for *endpoint*.

    Args:
        endpoint:     The ``WebhookEndpoint`` this delivery targets.
        status:       Delivery status string (default: ``"pending"``).
        event_type:   Event type (default: ``"course.created"``).
        payload:      JSON payload dict (default: ``{"test": True}``).
        next_retry_at: Optional datetime for the next retry attempt.
    """
    from apps.webhooks.models import WebhookDelivery

    return WebhookDelivery.objects.create(
        endpoint=endpoint,
        event_type=event_type,
        payload=payload or {"test": True},
        status=status,
        next_retry_at=next_retry_at,
    )
