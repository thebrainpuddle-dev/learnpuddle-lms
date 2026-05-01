"""Tests for AUDIT-2026-04-26-PHASE3-10: one-time SSO code exchange for SAML.

Before this fix, ``saml_acs`` redirected the browser to
``host{relay_state}#access=<JWT>&refresh=<JWT>`` — exposing the JWT pair in
the URL fragment.  Fragments are not transmitted in HTTP request bodies but
they ARE captured by browser history, JS-based error trackers (Sentry,
Datadog RUM), and the address bar.

The fix mirrors the OAuth callback (``apps/users/sso_views.py``):

  1. ACS mints a short-lived, opaque, single-use code with
     ``secrets.token_urlsafe(48)``.
  2. The JWT pair + ``user_id`` are cached under ``sso_code:{code}`` for
     ~120 seconds.
  3. The ACS redirect now uses ``?code=<code>`` (a query string param —
     consumed and stripped by the frontend, never persisted in browser
     history through fragments).
  4. The frontend POSTs ``{"code": ...}`` to ``/users/auth/sso/token-exchange/``,
     which pops the cache key (single use) and returns the tokens.

These tests confirm:

  * ACS redirect now uses ``?code=`` and contains NO ``#access=`` /
    ``#refresh=`` fragment.
  * The minted code is opaque (≥32 chars, URL-safe character set, not a
    JWT).
  * The token-exchange endpoint returns the JWT pair on first call and
    deletes the cache key.
  * A second exchange of the same code returns 400 (single-use).
  * An expired/missing code returns 400.
  * The OAuth ``sso_token_exchange`` flow still works (regression).
"""

from __future__ import annotations

import re
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from django.core.cache import cache
from django.test import Client

from apps.tenants.models import Tenant
from apps.tenants.saml_models import TenantSAMLConfig
from apps.users.models import User
from apps.users.saml_service import SAMLAssertion


pytestmark = pytest.mark.django_db


DUMMY_CERT = (
    "-----BEGIN CERTIFICATE-----\n"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\n"
    "-----END CERTIFICATE-----"
)


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="Code-Exchange Test School",
        slug="sso-code-test",
        subdomain="sso-code-test",
        email="admin@sso-code-test.edu",
        feature_saml=True,
    )


@pytest.fixture
def saml_config(tenant):
    return TenantSAMLConfig.objects.create(
        tenant=tenant,
        enabled=True,
        sp_entity_id="sp-audience",
        idp_entity_id="idp-issuer",
        idp_sso_url="https://idp.example.org/sso",
        idp_x509_certs=[DUMMY_CERT],
        attribute_mapping={
            "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        },
        auto_provision=True,
    )


@pytest.fixture
def existing_user(tenant):
    return User.objects.create(
        email="alice@example.org",
        first_name="Alice",
        last_name="Example",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture(autouse=True)
def _clear_cache():
    """Tests must start from a clean cache so codes don't leak between cases."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def patched_acs(monkeypatch, existing_user):
    """Bypass the SAML XMLDSig pipeline so we can drive ``saml_acs`` end-to-end.

    Patches ``saml_views.verify_and_parse_response`` to return a synthetic
    ``SAMLAssertion`` for ``existing_user.email``.  Replay-cache and
    domain-allow checks remain real (we run against a clean cache and the
    test config has no ``sso_domains`` allow-list).
    """
    import apps.users.saml_views as saml_views

    def _fake_parse(*_args, **_kwargs):
        return SAMLAssertion(
            response_id="test-response-id",
            assertion_id="test-assertion-id-unique-{}".format(id(existing_user)),
            subject_name_id=existing_user.email,
            email=existing_user.email,
            raw_attributes={},
        )

    monkeypatch.setattr(saml_views, "verify_and_parse_response", _fake_parse)
    return saml_views


def _post_acs(client: Client, tenant, saml_config, *, relay_state="/dashboard"):
    return client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/acs/",
        data={"SAMLResponse": "fake-base64-payload", "RelayState": relay_state},
    )


# ----------------------------------------------------------------------
# RED tests — describe the post-fix contract.
# ----------------------------------------------------------------------

def test_acs_redirect_uses_one_time_code_not_fragment(
    client, tenant, saml_config, patched_acs, existing_user
):
    """ACS redirect must use ``?code=<token>`` and never expose tokens in
    a ``#access=...&refresh=...`` fragment.
    """
    resp = _post_acs(client, tenant, saml_config, relay_state="/dashboard")

    assert resp.status_code == 302, resp.content
    location = resp["Location"]

    # No JWT-bearing fragment.
    assert "#access=" not in location, f"JWT leaked in fragment: {location}"
    assert "#refresh=" not in location, f"JWT leaked in fragment: {location}"
    assert "access=" not in location.split("?")[-1].split("&", 1)[0:1] + [], None
    # And no `access`/`refresh` keys at all in the URL — only `code`.
    parsed = urlparse(location)
    qs = parse_qs(parsed.query)
    assert "access" not in qs
    assert "refresh" not in qs
    assert "code" in qs, f"Expected ?code= in redirect, got {location}"
    assert parsed.path == "/dashboard"


def test_minted_code_is_opaque_and_url_safe(
    client, tenant, saml_config, patched_acs
):
    """Code must be ≥32 chars, URL-safe, and clearly not a JWT (no dots)."""
    resp = _post_acs(client, tenant, saml_config)
    assert resp.status_code == 302
    qs = parse_qs(urlparse(resp["Location"]).query)
    code = qs["code"][0]

    assert len(code) >= 32, f"code too short: {len(code)}"
    # token_urlsafe alphabet: A-Z a-z 0-9 - _
    assert re.fullmatch(r"[A-Za-z0-9_\-]+", code), f"non-urlsafe chars: {code!r}"
    # JWTs have two `.` separators — codes must not.
    assert "." not in code, "code must not look like a JWT"


def test_token_exchange_returns_jwt_pair_and_consumes_code(
    client, tenant, saml_config, patched_acs, existing_user
):
    """First exchange returns the JWT pair; cache entry is deleted afterwards."""
    resp = _post_acs(client, tenant, saml_config)
    code = parse_qs(urlparse(resp["Location"]).query)["code"][0]

    # Cache should hold the tokens prior to exchange.
    assert cache.get(f"sso_code:{code}") is not None

    exch = client.post(
        "/api/v1/users/auth/sso/token-exchange/",
        data={"code": code},
        content_type="application/json",
    )
    assert exch.status_code == 200, exch.content
    body = exch.json()

    # Exchange returns the JWT pair.  We accept either the OAuth-legacy keys
    # (``access_token`` / ``refresh_token``) or the spec keys
    # (``access`` / ``refresh``) — but at least one must be populated and
    # the values must look like JWTs (three dot-separated parts).
    access = body.get("access") or body.get("access_token")
    refresh = body.get("refresh") or body.get("refresh_token")
    assert access, body
    assert refresh, body
    assert access.count(".") == 2, f"access not a JWT: {access[:30]}…"
    assert refresh.count(".") == 2, f"refresh not a JWT: {refresh[:30]}…"

    # Single-use: cache key was popped.
    assert cache.get(f"sso_code:{code}") is None


def test_token_exchange_second_call_with_same_code_fails(
    client, tenant, saml_config, patched_acs
):
    """Replaying the same code returns 400."""
    resp = _post_acs(client, tenant, saml_config)
    code = parse_qs(urlparse(resp["Location"]).query)["code"][0]

    first = client.post(
        "/api/v1/users/auth/sso/token-exchange/",
        data={"code": code},
        content_type="application/json",
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/users/auth/sso/token-exchange/",
        data={"code": code},
        content_type="application/json",
    )
    assert second.status_code == 400, second.content


def test_token_exchange_with_unknown_or_expired_code_fails(client):
    """An unknown / TTL-expired code must be rejected with 400."""
    # Unknown code (never minted).
    resp = client.post(
        "/api/v1/users/auth/sso/token-exchange/",
        data={"code": "this-code-was-never-minted"},
        content_type="application/json",
    )
    assert resp.status_code == 400

    # Simulated expiry: write then delete (mimics TTL eviction).
    cache.set("sso_code:transient", {"access_token": "x", "refresh_token": "y", "user_id": "z"}, timeout=120)
    cache.delete("sso_code:transient")
    resp2 = client.post(
        "/api/v1/users/auth/sso/token-exchange/",
        data={"code": "transient"},
        content_type="application/json",
    )
    assert resp2.status_code == 400


def test_token_exchange_rejects_missing_code(client):
    resp = client.post(
        "/api/v1/users/auth/sso/token-exchange/",
        data={},
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_oauth_sso_token_exchange_regression(client, existing_user):
    """The OAuth callback writes ``sso_code:<code>`` cache entries; the
    exchange endpoint must continue to consume them transparently — i.e.
    SAML reuses the same namespace, no behaviour change for OAuth callers.
    """
    # Mimic what ``sso_callback`` does after Google OAuth succeeds.
    cache.set(
        "sso_code:oauth-test-code-xyz",
        {
            "access_token": "header.payload.sig",
            "refresh_token": "header.payload.sig",
            "user_id": str(existing_user.id),
        },
        timeout=60,
    )
    resp = client.post(
        "/api/v1/users/auth/sso/token-exchange/",
        data={"code": "oauth-test-code-xyz"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    # OAuth-legacy keys must remain present so the existing frontend
    # ``SSOCallbackPage.tsx`` keeps working.
    assert body.get("access_token") == "header.payload.sig"
    assert body.get("refresh_token") == "header.payload.sig"


def test_acs_relay_state_external_url_returns_json_not_redirect(
    client, tenant, saml_config, patched_acs
):
    """RelayState that does not start with ``/`` must NOT cause a redirect
    (defence-in-depth: don't let an attacker-controlled RelayState steer
    the browser anywhere).  The view falls back to a JSON response — and
    in that path no JWT-fragment leak is possible.
    """
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/acs/",
        data={
            "SAMLResponse": "fake-base64-payload",
            "RelayState": "https://evil.example.com/steal",
        },
    )
    # JSON path: tokens are returned in the body, not in a URL.
    assert resp.status_code == 200
    body = resp.json()
    assert "tokens" in body
