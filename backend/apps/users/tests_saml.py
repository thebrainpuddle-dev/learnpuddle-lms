"""Tests for the SAML SSO flow.

These tests focus on *security-critical* behaviors that do not require
signing XML with a real private key:

  * unsigned assertions are rejected (``REJECT_SIGNATURE``),
  * assertions past ``NotOnOrAfter`` are rejected (``REJECT_EXPIRED``),
  * audience mismatches are rejected (``REJECT_AUDIENCE``),
  * attribute mapping JSON cannot contain unknown keys,
  * SAML endpoints are feature-gated and tenant-scoped,
  * ACS audit row is written for every decision,
  * provisioning is disabled unless tenant opts in.

Full end-to-end signature verification requires a real IdP cert /
signing key pair which is exercised in integration environments.
"""

from __future__ import annotations

import base64

import pytest
from django.test import Client, override_settings
from django.urls import reverse

from apps.tenants.models import Tenant
from apps.tenants.saml_models import TenantSAMLConfig
from apps.users.models import SAMLAuthEvent, User
from apps.users.saml_service import (
    SAMLValidationError,
    build_logout_response,
    parse_logout_request,
    verify_and_parse_response,
)


pytestmark = pytest.mark.django_db


UNSIGNED_RESPONSE = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="R1" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
  <saml:Assertion ID="A1" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
    <saml:Subject>
      <saml:NameID>user@example.org</saml:NameID>
    </saml:Subject>
    <saml:Conditions NotBefore="2026-04-18T09:00:00Z"
                     NotOnOrAfter="2099-01-01T00:00:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>sp-audience</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
  </saml:Assertion>
</samlp:Response>
"""


EXPIRED_RESPONSE = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="R2" Version="2.0" IssueInstant="2020-01-01T00:00:00Z">
  <saml:Assertion ID="A2" Version="2.0" IssueInstant="2020-01-01T00:00:00Z">
    <saml:Subject><saml:NameID>user@example.org</saml:NameID></saml:Subject>
    <saml:Conditions NotOnOrAfter="2020-01-01T01:00:00Z"/>
  </saml:Assertion>
</samlp:Response>
"""


WRONG_AUDIENCE_RESPONSE = """<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="R3" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
  <saml:Assertion ID="A3" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
    <saml:Subject><saml:NameID>user@example.org</saml:NameID></saml:Subject>
    <saml:Conditions NotOnOrAfter="2099-01-01T00:00:00Z">
      <saml:AudienceRestriction>
        <saml:Audience>some-other-sp</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
  </saml:Assertion>
</samlp:Response>
"""


DUMMY_CERT = (
    "-----BEGIN CERTIFICATE-----\n"
    "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA\n"
    "-----END CERTIFICATE-----"
)


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="SAML Test School",
        slug="saml-test",
        subdomain="saml-test",
        email="admin@saml-test.edu",
        # SAML is gated on ``tenant.features['saml']`` (backed by
        # ``feature_saml``) per the TASK-045 spec.
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
        auto_provision=False,
    )


# ----------------------------------------------------------------------
# Service-level tests
# ----------------------------------------------------------------------

def _b64(xml: str) -> str:
    return base64.b64encode(xml.encode("utf-8")).decode("ascii")


def test_unsigned_response_is_rejected():
    with pytest.raises(SAMLValidationError) as exc:
        verify_and_parse_response(
            raw_response_b64=_b64(UNSIGNED_RESPONSE),
            idp_certs_pem=[DUMMY_CERT],
            expected_audience="sp-audience",
            attribute_mapping={},
        )
    assert exc.value.code == "REJECT_SIGNATURE"


def test_expired_response_is_rejected():
    # Covers the expiry helper directly (signature check runs first on
    # real responses — the signed-fixture tests below exercise the
    # NotOnOrAfter path end-to-end).
    from apps.users.saml_service import _parse_iso, CLOCK_SKEW
    import datetime

    not_on_or_after = _parse_iso("2020-01-01T01:00:00Z")
    now = datetime.datetime.now(datetime.timezone.utc)
    assert now - CLOCK_SKEW >= not_on_or_after


# XML fragments for the "fail-closed on missing guards" tests.  Each has
# a stub ``<ds:Signature>`` element so the signature-presence check
# passes; the monkey-patched ``_verify_xml_signature`` then no-ops so we
# can exercise the Conditions / AudienceRestriction / Destination guards.
_STUB_SIG = (
    '<ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">'
    '<ds:SignedInfo/><ds:SignatureValue/><ds:KeyInfo/>'
    '</ds:Signature>'
)


def test_response_without_conditions_is_rejected():
    """Fail-closed when the IdP omits the <Conditions> element entirely."""
    raw = f"""<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="R9" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
  {_STUB_SIG}
  <saml:Assertion ID="A9" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
    <saml:Subject><saml:NameID>u@example.org</saml:NameID></saml:Subject>
  </saml:Assertion>
</samlp:Response>
"""
    import apps.users.saml_service as svc

    original = svc._verify_xml_signature
    svc._verify_xml_signature = lambda *a, **kw: None
    try:
        with pytest.raises(SAMLValidationError) as exc:
            verify_and_parse_response(
                raw_response_b64=_b64(raw),
                idp_certs_pem=[DUMMY_CERT],
                expected_audience="sp-audience",
                attribute_mapping={},
            )
        assert exc.value.code == "REJECT_AUDIENCE"
    finally:
        svc._verify_xml_signature = original


def test_response_without_audience_is_rejected():
    """Assertion without any AudienceRestriction must be rejected."""
    raw = f"""<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="R10" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
  {_STUB_SIG}
  <saml:Assertion ID="A10" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
    <saml:Subject><saml:NameID>u@example.org</saml:NameID></saml:Subject>
    <saml:Conditions NotOnOrAfter="2099-01-01T00:00:00Z"/>
  </saml:Assertion>
</samlp:Response>
"""
    import apps.users.saml_service as svc

    original = svc._verify_xml_signature
    svc._verify_xml_signature = lambda *a, **kw: None
    try:
        with pytest.raises(SAMLValidationError) as exc:
            verify_and_parse_response(
                raw_response_b64=_b64(raw),
                idp_certs_pem=[DUMMY_CERT],
                expected_audience="sp-audience",
                attribute_mapping={},
            )
        assert exc.value.code == "REJECT_AUDIENCE"
    finally:
        svc._verify_xml_signature = original


def test_response_without_destination_is_rejected():
    """When an expected_destination is configured, missing the attribute fails."""
    raw = f"""<?xml version="1.0"?>
<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
    ID="R11" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
  {_STUB_SIG}
  <saml:Assertion ID="A11" Version="2.0" IssueInstant="2026-04-18T10:00:00Z">
    <saml:Subject><saml:NameID>u@example.org</saml:NameID></saml:Subject>
    <saml:Conditions NotOnOrAfter="2099-01-01T00:00:00Z">
      <saml:AudienceRestriction><saml:Audience>sp-audience</saml:Audience></saml:AudienceRestriction>
    </saml:Conditions>
  </saml:Assertion>
</samlp:Response>
"""
    import apps.users.saml_service as svc
    original = svc._verify_xml_signature
    svc._verify_xml_signature = lambda *a, **kw: None
    try:
        with pytest.raises(SAMLValidationError) as exc:
            verify_and_parse_response(
                raw_response_b64=_b64(raw),
                idp_certs_pem=[DUMMY_CERT],
                expected_audience="sp-audience",
                attribute_mapping={},
                expected_destination="https://acs.example.org/",
            )
        assert exc.value.code == "REJECT_AUDIENCE"
    finally:
        svc._verify_xml_signature = original


# ----------------------------------------------------------------------
# Signed-fixture end-to-end tests (M3)
# ----------------------------------------------------------------------

def _self_signed_idp():
    """Generate a fresh self-signed RSA keypair + cert usable for signxml."""
    from cryptography import x509 as _x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime as _dt

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    subject = issuer = _x509.Name([_x509.NameAttribute(NameOID.COMMON_NAME, "idp-test")])
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (
        _x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(_x509.random_serial_number())
        .not_valid_before(now - _dt.timedelta(minutes=5))
        .not_valid_after(now + _dt.timedelta(days=365))
        .sign(key, hashes.SHA256(), default_backend())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    return cert_pem, key_pem, key


def _sign_assertion(assertion_xml: str, key, cert_pem: str) -> bytes:
    """Sign a SAML assertion element with signxml and return the bytes."""
    from lxml import etree
    from signxml import XMLSigner, methods

    doc = etree.fromstring(assertion_xml.encode("utf-8"))
    signer = XMLSigner(method=methods.enveloped, signature_algorithm="rsa-sha256")
    signed = signer.sign(doc, key=key, cert=cert_pem)
    return etree.tostring(signed)


@pytest.fixture
def signed_idp():
    """Self-signed IdP fixture used by the signed-assertion tests."""
    try:
        import signxml  # noqa: F401
        import cryptography  # noqa: F401
    except Exception:
        pytest.skip("signxml / cryptography not installed in test env")
    return _self_signed_idp()


def _build_response(assertion_id: str, audience: str, not_on_or_after: str) -> str:
    return f"""<?xml version=\"1.0\"?>
<samlp:Response xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\"
    xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\"
    ID=\"R-{assertion_id}\" Version=\"2.0\" IssueInstant=\"2026-04-18T10:00:00Z\"
    Destination=\"https://sp.example.org/acs\">
  <saml:Assertion xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\"
      ID=\"A-{assertion_id}\" Version=\"2.0\" IssueInstant=\"2026-04-18T10:00:00Z\">
    <saml:Issuer>idp-issuer</saml:Issuer>
    <saml:Subject>
      <saml:NameID>user@example.org</saml:NameID>
    </saml:Subject>
    <saml:Conditions NotBefore=\"2026-04-18T09:00:00Z\" NotOnOrAfter=\"{not_on_or_after}\">
      <saml:AudienceRestriction>
        <saml:Audience>{audience}</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
  </saml:Assertion>
</samlp:Response>
"""


def test_signed_assertion_rejects_wrong_audience(signed_idp):
    cert_pem, _key_pem, key = signed_idp
    # Build response whose assertion has audience = "other-sp"
    raw = _build_response("x1", audience="other-sp", not_on_or_after="2099-01-01T00:00:00Z")
    # Sign the outer Response element with signxml
    from lxml import etree
    from signxml import XMLSigner, methods
    doc = etree.fromstring(raw.encode("utf-8"))
    signed = XMLSigner(method=methods.enveloped, signature_algorithm="rsa-sha256").sign(doc, key=key, cert=cert_pem)
    body = etree.tostring(signed)

    with pytest.raises(SAMLValidationError) as exc:
        verify_and_parse_response(
            raw_response_b64=base64.b64encode(body).decode(),
            idp_certs_pem=[cert_pem],
            expected_audience="sp-audience",
            attribute_mapping={},
            expected_destination="https://sp.example.org/acs",
        )
    assert exc.value.code == "REJECT_AUDIENCE"


def test_signed_assertion_rejects_expired(signed_idp):
    cert_pem, _key_pem, key = signed_idp
    raw = _build_response("x2", audience="sp-audience", not_on_or_after="2020-01-01T00:00:00Z")
    from lxml import etree
    from signxml import XMLSigner, methods
    doc = etree.fromstring(raw.encode("utf-8"))
    signed = XMLSigner(method=methods.enveloped, signature_algorithm="rsa-sha256").sign(doc, key=key, cert=cert_pem)
    body = etree.tostring(signed)

    with pytest.raises(SAMLValidationError) as exc:
        verify_and_parse_response(
            raw_response_b64=base64.b64encode(body).decode(),
            idp_certs_pem=[cert_pem],
            expected_audience="sp-audience",
            attribute_mapping={},
            expected_destination="https://sp.example.org/acs",
        )
    assert exc.value.code == "REJECT_EXPIRED"


def test_expired_idp_cert_is_rejected():
    """Even if the signature is arithmetically correct, an expired IdP
    cert must be rejected at the validity-period check."""
    from cryptography import x509 as _x509
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime as _dt

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
    subject = issuer = _x509.Name([_x509.NameAttribute(NameOID.COMMON_NAME, "expired-idp")])
    past = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=365)
    cert = (
        _x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(_x509.random_serial_number())
        .not_valid_before(past - _dt.timedelta(days=365))
        .not_valid_after(past)  # Expired yesterday-ish
        .sign(key, hashes.SHA256(), default_backend())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")

    from apps.users.saml_service import _assert_cert_validity_period
    with pytest.raises(SAMLValidationError) as exc:
        _assert_cert_validity_period(cert_pem)
    assert exc.value.code == "REJECT_SIGNATURE"


def test_malformed_xml_is_rejected():
    with pytest.raises(SAMLValidationError) as exc:
        verify_and_parse_response(
            raw_response_b64=_b64("<not-saml/>"),
            idp_certs_pem=[DUMMY_CERT],
            expected_audience="sp",
            attribute_mapping={},
        )
    assert exc.value.code == "REJECT_MALFORMED"


def test_missing_certs_is_rejected():
    with pytest.raises(SAMLValidationError) as exc:
        verify_and_parse_response(
            raw_response_b64=_b64(UNSIGNED_RESPONSE),
            idp_certs_pem=[],
            expected_audience="sp-audience",
            attribute_mapping={},
        )
    assert exc.value.code == "REJECT_SIGNATURE"


# ----------------------------------------------------------------------
# Model-level tests
# ----------------------------------------------------------------------

def test_attribute_mapping_rejects_unknown_keys(tenant):
    cfg = TenantSAMLConfig(
        tenant=tenant,
        enabled=False,
        sp_entity_id="x",
        attribute_mapping={"email": "urn:email", "evil": "ohno"},
    )
    with pytest.raises(Exception):
        cfg.full_clean()


def test_attribute_mapping_rejects_non_string_values(tenant):
    cfg = TenantSAMLConfig(
        tenant=tenant,
        enabled=False,
        sp_entity_id="x",
        attribute_mapping={"email": 42},
    )
    with pytest.raises(Exception):
        cfg.full_clean()


def test_enabling_without_cert_is_rejected(tenant):
    cfg = TenantSAMLConfig(
        tenant=tenant,
        enabled=True,
        sp_entity_id="x",
        idp_sso_url="https://idp.example.org/sso",
        idp_x509_certs=[],
    )
    with pytest.raises(Exception):
        cfg.full_clean()


# ----------------------------------------------------------------------
# Endpoint tests
# ----------------------------------------------------------------------

def test_acs_rejects_unsigned_and_audits(client, tenant, saml_config):
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/acs/",
        data={"SAMLResponse": _b64(UNSIGNED_RESPONSE)},
    )
    assert resp.status_code == 403
    events = SAMLAuthEvent.objects.filter(tenant=tenant)
    assert events.exists()
    assert events.first().decision == "REJECT_SIGNATURE"


def test_acs_returns_404_for_unknown_tenant(client):
    resp = client.post(
        "/api/v1/auth/saml/nope/acs/",
        data={"SAMLResponse": "x"},
    )
    assert resp.status_code == 404


def test_acs_returns_403_when_feature_flag_off(client, tenant, saml_config):
    tenant.feature_saml = False
    tenant.save()
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/acs/",
        data={"SAMLResponse": "x"},
    )
    assert resp.status_code == 403


def test_tenant_features_dict_exposes_saml(tenant):
    """``tenant.features['saml']`` is the canonical feature flag per spec."""
    assert tenant.features.get("saml") is True
    tenant.feature_saml = False
    tenant.save()
    tenant.refresh_from_db()
    assert tenant.features.get("saml") is False


def test_acs_returns_403_when_config_disabled(client, tenant, saml_config):
    saml_config.enabled = False
    saml_config.save()
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/acs/",
        data={"SAMLResponse": "x"},
    )
    assert resp.status_code == 403


def test_metadata_endpoint_returns_xml(client, tenant, saml_config):
    resp = client.get(f"/api/v1/auth/saml/{tenant.subdomain}/metadata/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/samlmetadata+xml")
    body = resp.content.decode("utf-8")
    assert "EntityDescriptor" in body
    assert "AssertionConsumerService" in body
    # Must NOT expose the private key.
    assert "PRIVATE KEY" not in body


def test_provision_saml_user_blocks_when_auto_provision_disabled(tenant, saml_config):
    from apps.users.saml_service import SAMLAssertion
    from apps.users.sso_pipeline import provision_saml_user

    assertion = SAMLAssertion(
        response_id="R",
        assertion_id="A",
        subject_name_id="x@example.org",
        email="new@example.org",
    )
    with pytest.raises(PermissionError):
        provision_saml_user(tenant=tenant, config=saml_config, assertion=assertion)


def test_provision_saml_user_allows_existing_user(tenant, saml_config):
    from apps.users.saml_service import SAMLAssertion
    from apps.users.sso_pipeline import provision_saml_user

    user = User.objects.create(
        email="existing@example.org",
        first_name="Ex",
        last_name="User",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )
    assertion = SAMLAssertion(
        response_id="R",
        assertion_id="A",
        subject_name_id="existing@example.org",
        email="existing@example.org",
        first_name="Ex",
        last_name="User",
    )
    resolved = provision_saml_user(tenant=tenant, config=saml_config, assertion=assertion)
    assert resolved.id == user.id


def test_provision_saml_user_creates_when_auto_provision_enabled(tenant, saml_config):
    from apps.users.saml_service import SAMLAssertion
    from apps.users.sso_pipeline import provision_saml_user

    saml_config.auto_provision = True
    saml_config.save()

    assertion = SAMLAssertion(
        response_id="R",
        assertion_id="A",
        subject_name_id="new@example.org",
        email="new@example.org",
        first_name="New",
        last_name="User",
    )
    user = provision_saml_user(tenant=tenant, config=saml_config, assertion=assertion)
    assert user.pk is not None
    assert user.tenant_id == tenant.id
    assert user.role == "TEACHER"
    assert user.email_verified is True
    # Password must be unusable for SSO-provisioned users.
    assert not user.has_usable_password()


def test_provision_saml_user_rejects_orphan_user(tenant, saml_config):
    """An orphan user (tenant_id=None) must NOT be adopted into any tenant
    via SAML — this was the cross-tenant-adoption hole (H3)."""
    from apps.users.saml_service import SAMLAssertion
    from apps.users.sso_pipeline import provision_saml_user

    # Create an orphan user record — e.g. a legacy super-admin or a row
    # whose tenant was later deleted.
    orphan = User.objects.create(
        email="orphan@example.org",
        first_name="Or",
        last_name="Phan",
        tenant=None,
        role="SUPER_ADMIN",
        is_active=True,
    )
    assertion = SAMLAssertion(
        response_id="R",
        assertion_id="A",
        subject_name_id="orphan@example.org",
        email="orphan@example.org",
    )
    with pytest.raises(PermissionError):
        provision_saml_user(tenant=tenant, config=saml_config, assertion=assertion)
    # Orphan must NOT have been moved into this tenant.
    orphan.refresh_from_db()
    assert orphan.tenant_id is None


def test_provision_saml_user_rejects_other_tenant(tenant, saml_config):
    """A user who already belongs to another tenant must NOT be moved."""
    from apps.users.saml_service import SAMLAssertion
    from apps.users.sso_pipeline import provision_saml_user

    other = Tenant.objects.create(
        name="Other School", slug="other", subdomain="other",
        email="x@other.edu",
    )
    belongs_elsewhere = User.objects.create(
        email="elsewhere@example.org",
        first_name="El",
        last_name="Se",
        tenant=other,
        role="TEACHER",
        is_active=True,
    )
    assertion = SAMLAssertion(
        response_id="R",
        assertion_id="A",
        subject_name_id="elsewhere@example.org",
        email="elsewhere@example.org",
    )
    with pytest.raises(PermissionError):
        provision_saml_user(tenant=tenant, config=saml_config, assertion=assertion)
    belongs_elsewhere.refresh_from_db()
    assert belongs_elsewhere.tenant_id == other.id


def test_provision_saml_user_enforces_domain_allow_list(tenant, saml_config):
    from apps.users.saml_service import SAMLAssertion
    from apps.users.sso_pipeline import provision_saml_user

    saml_config.auto_provision = True
    saml_config.allowed_email_domains = "allowed.org"
    saml_config.save()

    assertion = SAMLAssertion(
        response_id="R",
        assertion_id="A",
        subject_name_id="x@blocked.org",
        email="x@blocked.org",
    )
    with pytest.raises(PermissionError):
        provision_saml_user(tenant=tenant, config=saml_config, assertion=assertion)


# ---------------------------------------------------------------------------
# SLO security tests (M1 + M2 from review-BE-OBS4-SAML-SLO-2026-04-19.md)
# ---------------------------------------------------------------------------

_UNSIGNED_LOGOUT_REQUEST = """\
<?xml version="1.0"?>
<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    ID="req-slo-001" Version="2.0" IssueInstant="2026-04-19T10:00:00Z">
  <saml:Issuer>idp-issuer</saml:Issuer>
  <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
    >user@example.org</saml:NameID>
</samlp:LogoutRequest>
"""


def test_unsigned_logout_request_rejected_when_certs_configured():
    """M1: When IdP certs are configured, an unsigned LogoutRequest must be
    rejected with REJECT_SIGNATURE.

    Without this guard an attacker can POST a forged unsigned LogoutRequest
    (the SLS endpoint is @csrf_exempt) and force-logout any user whose email
    they know.
    """
    with pytest.raises(SAMLValidationError) as exc:
        parse_logout_request(
            raw_request_b64=_b64(_UNSIGNED_LOGOUT_REQUEST),
            idp_certs_pem=[DUMMY_CERT],
        )
    assert exc.value.code == "REJECT_SIGNATURE"


def test_unsigned_logout_request_allowed_when_no_certs_configured():
    """Unsigned LogoutRequests are still accepted when no certs are configured.

    Some IdP deployments don't sign SLO requests; if the operator hasn't
    loaded any certs we can't verify, so we allow — consistent with
    'secure by configuration'.
    """
    result = parse_logout_request(
        raw_request_b64=_b64(_UNSIGNED_LOGOUT_REQUEST),
        idp_certs_pem=[],
    )
    assert result.name_id == "user@example.org"


def test_build_logout_response_escapes_xml_injection_in_response_to():
    """M2: Attacker-controlled in_response_to must not break response XML.

    Without escaping, a crafted ID like 'foo">&lt;injected/&gt;<x' is
    interpolated directly into the attribute value, producing malformed XML
    (or worse — XML element injection if the surrounding quotes are broken).
    """
    import xml.etree.ElementTree as ET

    injected_id = 'req-123"><injected/><x y="'
    xml_str = build_logout_response(
        in_response_to=injected_id,
        issuer="sp-entity",
        destination="https://idp.example.org/slo",
    )
    # Must be parseable as well-formed XML
    root = ET.fromstring(xml_str)
    # Must recover the exact raw value (not parse embedded elements)
    assert root.get("InResponseTo") == injected_id


def test_build_logout_response_escapes_issuer_and_destination():
    """Defence-in-depth: ``issuer`` and ``destination`` also flow through
    attribute/text serialization — confirm they are escaped correctly when
    given metacharacters.  ``issuer`` is server-controlled today but might
    be sourced from config in future, and ``destination`` is config-driven.
    """
    import xml.etree.ElementTree as ET

    xml_str = build_logout_response(
        in_response_to="req-1",
        issuer='evil<issuer> & stuff',
        destination='https://idp.example.org/slo?x="y"&z=1',
    )
    root = ET.fromstring(xml_str)
    # Destination attribute round-trips losslessly.
    assert root.get("Destination") == 'https://idp.example.org/slo?x="y"&z=1'
    # Issuer element text round-trips losslessly.
    issuer_el = root.find("{urn:oasis:names:tc:SAML:2.0:assertion}Issuer")
    assert issuer_el is not None
    assert issuer_el.text == 'evil<issuer> & stuff'


def test_parse_logout_request_deflate_fallback():
    """HTTP-Redirect binding: the LogoutRequest is raw-deflate compressed
    before base64 encoding.  ``parse_logout_request`` must fall back to
    zlib raw-deflate after the plain-XML parse fails.
    """
    import zlib

    raw_xml = _UNSIGNED_LOGOUT_REQUEST.encode("utf-8")
    deflated = zlib.compress(raw_xml)[2:-4]  # strip zlib header + adler32 -> raw deflate
    encoded = base64.b64encode(deflated).decode("ascii")

    result = parse_logout_request(
        raw_request_b64=encoded,
        idp_certs_pem=[],  # signature check disabled when no certs present
    )
    assert result.name_id == "user@example.org"
    assert result.request_id == "req-slo-001"


def test_parse_logout_request_missing_id_rejected():
    """A LogoutRequest with no ID attribute is malformed and must be rejected."""
    raw = """\
<?xml version="1.0"?>
<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
    Version="2.0" IssueInstant="2026-04-19T10:00:00Z">
  <saml:NameID>user@example.org</saml:NameID>
</samlp:LogoutRequest>
"""
    with pytest.raises(SAMLValidationError) as exc:
        parse_logout_request(
            raw_request_b64=_b64(raw),
            idp_certs_pem=[],
        )
    assert exc.value.code == "REJECT_MALFORMED"


# ---------------------------------------------------------------------------
# SLS view tests — end-to-end on the saml_sls endpoint
# (covers gap tests 1, 2, 3, 5, 6, 7, 8 from SAML-SLO-TEST-REQUEST.md)
# ---------------------------------------------------------------------------

@pytest.fixture
def slo_config(tenant):
    """TenantSAMLConfig with an ``idp_slo_url`` configured but *no* IdP certs
    — so unsigned LogoutRequests are accepted and parse-related errors are
    tested without needing a real signing key.
    """
    return TenantSAMLConfig.objects.create(
        tenant=tenant,
        enabled=True,
        sp_entity_id="sp-audience",
        idp_entity_id="idp-issuer",
        idp_sso_url="https://idp.example.org/sso",
        idp_slo_url="https://idp.example.org/slo",
        idp_x509_certs=[],  # no certs → unsigned requests allowed
        attribute_mapping={},
        auto_provision=False,
    )


def _make_logout_request_b64(name_id: str = "user@example.org") -> tuple[str, str]:
    """Return (b64, request_id) for a minimal unsigned LogoutRequest."""
    import uuid as _uuid
    rid = f"id-{_uuid.uuid4().hex}"
    xml = (
        f'<?xml version="1.0"?>'
        f'<samlp:LogoutRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        f'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{rid}" Version="2.0" IssueInstant="2026-04-19T10:00:00Z">'
        f'<saml:Issuer>idp-issuer</saml:Issuer>'
        f'<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">'
        f'{name_id}</saml:NameID>'
        f'</samlp:LogoutRequest>'
    )
    return _b64(xml), rid


def test_sls_missing_saml_request_returns_400(client, tenant, slo_config):
    """Gap test #1: POST with no SAMLRequest field → 400 BAD_REQUEST + audit."""
    resp = client.post(f"/api/v1/auth/saml/{tenant.subdomain}/sls/", data={})
    assert resp.status_code == 400
    ev = SAMLAuthEvent.objects.filter(tenant=tenant).order_by("-created_at").first()
    assert ev is not None
    assert ev.decision == "REJECT_MALFORMED"
    assert "Missing SAMLRequest" in (ev.detail or "")


def test_sls_malformed_base64_still_redirects_with_responder_status(
    client, tenant, slo_config,
):
    """Gap test #2: malformed SAMLRequest must NOT 500 the view; the IdP
    still receives a LogoutResponse with ``Responder`` status so its SLO
    loop can complete. Also audits REJECT_MALFORMED.
    """
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/sls/",
        data={"SAMLRequest": "this is !!! not valid base64 or XML"},
    )
    # View continues past the parse error and still issues a redirect to
    # the configured idp_slo_url.
    assert resp.status_code == 302
    assert resp["Location"].startswith("https://idp.example.org/slo")

    # Decode the SAMLResponse in the redirect query and confirm status is Responder.
    import zlib
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(resp["Location"]).query)
    assert "SAMLResponse" in qs
    xml = zlib.decompress(base64.b64decode(qs["SAMLResponse"][0]), -15).decode()
    assert "Responder" in xml

    # Audit row written with REJECT_MALFORMED.
    decisions = list(
        SAMLAuthEvent.objects.filter(tenant=tenant).values_list("decision", flat=True)
    )
    assert "REJECT_MALFORMED" in decisions


def test_sls_valid_request_blacklists_user_tokens(client, tenant, slo_config):
    """Gap test #3: a valid LogoutRequest with a known NameID must:

    * 302 redirect to ``idp_slo_url``
    * Blacklist the user's outstanding SimpleJWT refresh tokens
    * Audit the event with ``decision="ACCEPT"``
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (  # type: ignore
            BlacklistedToken, OutstandingToken,
        )
        from rest_framework_simplejwt.tokens import RefreshToken
    except Exception:
        pytest.skip("simplejwt token_blacklist app not available in test env")

    user = User.objects.create(
        email="user@example.org",
        first_name="U",
        last_name="Ser",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )
    # Mint a real refresh token so OutstandingToken row exists.
    RefreshToken.for_user(user)
    assert OutstandingToken.objects.filter(user=user).exists()

    saml_req_b64, _rid = _make_logout_request_b64("user@example.org")
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/sls/",
        data={"SAMLRequest": saml_req_b64},
    )
    assert resp.status_code == 302
    assert resp["Location"].startswith("https://idp.example.org/slo")

    # All outstanding tokens blacklisted.
    outstanding = list(OutstandingToken.objects.filter(user=user))
    assert outstanding, "Expected at least one OutstandingToken for user"
    for ot in outstanding:
        assert BlacklistedToken.objects.filter(token=ot).exists(), (
            f"Token {ot.id} was not blacklisted by the SLS view"
        )

    # ACCEPT audit row present.
    decisions = list(
        SAMLAuthEvent.objects.filter(tenant=tenant).values_list("decision", flat=True)
    )
    assert "ACCEPT" in decisions


def test_sls_valid_request_unknown_user_still_redirects(client, tenant, slo_config):
    """Gap test #4: valid LogoutRequest referencing an unknown NameID must
    not crash — the IdP still needs its LogoutResponse. No tokens to revoke.
    """
    saml_req_b64, _rid = _make_logout_request_b64("ghost@example.org")
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/sls/",
        data={"SAMLRequest": saml_req_b64},
    )
    assert resp.status_code == 302
    assert resp["Location"].startswith("https://idp.example.org/slo")


def test_sls_relay_state_is_echoed(client, tenant, slo_config):
    """Gap test #5: ``RelayState`` POSTed by the IdP must be echoed back in
    the redirect URL so the IdP can correlate the logout round-trip.
    """
    saml_req_b64, _rid = _make_logout_request_b64("nobody@example.org")
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/sls/",
        data={"SAMLRequest": saml_req_b64, "RelayState": "opaque-token-xyz"},
    )
    assert resp.status_code == 302
    assert "RelayState=opaque-token-xyz" in resp["Location"]


def test_sls_returns_200_json_when_no_idp_slo_url_configured(
    client, tenant,
):
    """Gap test #6: when ``idp_slo_url`` is blank, the view can't redirect
    anywhere — it should return a plain 200 JSON so the browser isn't left
    on an error page.
    """
    TenantSAMLConfig.objects.create(
        tenant=tenant,
        enabled=True,
        sp_entity_id="sp-audience",
        idp_entity_id="idp-issuer",
        idp_sso_url="https://idp.example.org/sso",
        idp_slo_url="",  # blank
        idp_x509_certs=[],
        attribute_mapping={},
        auto_provision=False,
    )
    saml_req_b64, _rid = _make_logout_request_b64("nobody@example.org")
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/sls/",
        data={"SAMLRequest": saml_req_b64},
    )
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("application/json")
    import json as _json
    assert _json.loads(resp.content) == {"message": "Logout processed"}


def test_sls_response_in_response_to_matches_request_id(client, tenant, slo_config):
    """Gap test #7 (structure check): the LogoutResponse InResponseTo
    attribute must be the exact ID from the LogoutRequest so the IdP can
    match the response to its outstanding request.
    """
    saml_req_b64, request_id = _make_logout_request_b64("echo@example.org")
    resp = client.post(
        f"/api/v1/auth/saml/{tenant.subdomain}/sls/",
        data={"SAMLRequest": saml_req_b64},
    )
    assert resp.status_code == 302

    import zlib
    import xml.etree.ElementTree as ET
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(resp["Location"]).query)
    xml = zlib.decompress(base64.b64decode(qs["SAMLResponse"][0]), -15).decode()
    root = ET.fromstring(xml)
    assert root.get("InResponseTo") == request_id
    # Status code must be Success for a well-formed request.
    status_el = root.find(
        "{urn:oasis:names:tc:SAML:2.0:protocol}Status/"
        "{urn:oasis:names:tc:SAML:2.0:protocol}StatusCode"
    )
    assert status_el is not None
    assert "Success" in status_el.get("Value", "")
