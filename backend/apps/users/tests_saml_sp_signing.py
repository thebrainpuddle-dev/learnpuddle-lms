"""Tests for SP-side signing of AuthnRequest and LogoutResponse.

PHASE3-9: When the tenant's SAML config has ``sp_private_key`` (Fernet
encrypted) and ``sp_x509_cert`` set, AuthnRequest emission and
LogoutResponse construction must produce XMLDSig-signed XML so that
strict-mode IdPs (Microsoft Entra/AzureAD strict, ADFS) accept the
artifacts.  When the SP key is absent we must continue to emit unsigned
artifacts (backwards compatibility — many IdPs accept unsigned).

Round-trip tests use ``signxml.XMLVerifier`` to confirm the produced
signatures verify against the matching SP public certificate.

Canonicalization: ``http://www.w3.org/2001/10/xml-exc-c14n#``
Signature alg:    ``rsa-sha256``
Digest alg:       ``sha256``
"""

from __future__ import annotations

import base64
import datetime as _dt

import pytest
from django.test import Client

from apps.tenants.models import Tenant
from apps.tenants.saml_models import TenantSAMLConfig
from apps.users.saml_service import (
    NS,
    SP_SIG_ALG,
    SP_SIG_C14N,
    SP_DIGEST_ALG,
    build_logout_response,
    sign_saml_xml,
)


pytestmark = pytest.mark.django_db


# ----------------------------------------------------------------------
# Self-signed RSA keypair used as the SP credentials in these tests.
# Generated once per test session — keys never leave the test process.
# ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def sp_keypair():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "test-sp.learnpuddle.test")]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_dt.datetime.utcnow() - _dt.timedelta(days=1))
        .not_valid_after(_dt.datetime.utcnow() + _dt.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
    return {"key_pem": key_pem, "cert_pem": cert_pem}


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="SAML Signing Test School",
        slug="saml-sign-test",
        subdomain="saml-sign-test",
        email="admin@saml-sign-test.edu",
        feature_saml=True,
    )


@pytest.fixture
def saml_config_unsigned(tenant):
    """Config with no SP key — unsigned AuthnRequest / LogoutResponse path."""
    return TenantSAMLConfig.objects.create(
        tenant=tenant,
        enabled=True,
        sp_entity_id="https://saml-sign-test.test/sp",
        idp_entity_id="idp-issuer",
        idp_sso_url="https://idp.example.org/sso",
        idp_slo_url="https://idp.example.org/slo",
        idp_x509_certs=["-----BEGIN CERTIFICATE-----\nDUMMY\n-----END CERTIFICATE-----"],
        attribute_mapping={},
        auto_provision=False,
    )


@pytest.fixture
def saml_config_signed(tenant, sp_keypair):
    """Config with SP keypair — signed AuthnRequest / LogoutResponse path."""
    cfg = TenantSAMLConfig.objects.create(
        tenant=tenant,
        enabled=True,
        sp_entity_id="https://saml-sign-test.test/sp",
        idp_entity_id="idp-issuer",
        idp_sso_url="https://idp.example.org/sso",
        idp_slo_url="https://idp.example.org/slo",
        idp_x509_certs=["-----BEGIN CERTIFICATE-----\nDUMMY\n-----END CERTIFICATE-----"],
        sp_x509_cert=sp_keypair["cert_pem"],
        attribute_mapping={},
        auto_provision=False,
    )
    cfg.set_sp_private_key(sp_keypair["key_pem"])
    cfg.save()
    return cfg


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _parse(xml: str):
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    return etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml, parser)


def _decode_authn_request_from_form(html: str) -> str:
    """Extract the SAMLRequest value from the auto-post form HTML."""
    import re

    m = re.search(r'name="SAMLRequest"\s+value="([^"]+)"', html)
    assert m, f"SAMLRequest not found in form HTML: {html[:300]}"
    decoded = base64.b64decode(m.group(1)).decode("utf-8")
    return decoded


# ----------------------------------------------------------------------
# AuthnRequest tests
# ----------------------------------------------------------------------

def test_authn_request_signed_when_sp_key_configured(
    client: Client, tenant, saml_config_signed
):
    """When SP key is configured, AuthnRequest is XML-signed and POSTed."""
    resp = client.get(f"/api/v1/auth/saml/{tenant.subdomain}/login/")
    assert resp.status_code == 200
    assert resp["Content-Type"].startswith("text/html")

    body = resp.content.decode("utf-8")
    assert "<form" in body and "method=\"post\"" in body
    xml = _decode_authn_request_from_form(body)

    root = _parse(xml)
    assert root.tag.endswith("}AuthnRequest")
    sig = root.find("ds:Signature", NS)
    assert sig is not None, "AuthnRequest is missing <ds:Signature>"
    # SAML §5.4.1: Signature must be the first child of the signed element.
    assert root[0] is sig, "Signature must be the first child of AuthnRequest"


def test_authn_request_unsigned_when_sp_key_absent(
    client: Client, tenant, saml_config_unsigned
):
    """No SP key configured -> unsigned AuthnRequest via HTTP-Redirect."""
    resp = client.get(f"/api/v1/auth/saml/{tenant.subdomain}/login/")
    # HTTP-Redirect binding: 302 to IdP SSO URL with SAMLRequest in query.
    assert resp.status_code == 302
    location = resp["Location"]
    assert "SAMLRequest=" in location

    # Decode + inflate the SAMLRequest and assert no <ds:Signature>.
    import urllib.parse, zlib

    qs = urllib.parse.urlparse(location).query
    saml_request = urllib.parse.parse_qs(qs)["SAMLRequest"][0]
    deflated = base64.b64decode(saml_request)
    xml = zlib.decompress(deflated, -15).decode("utf-8")
    root = _parse(xml)
    assert root.find("ds:Signature", NS) is None, "Unexpected signature on unsigned path"


def test_authn_request_signature_verifies_with_sp_cert(tenant, saml_config_signed, sp_keypair):
    """Round-trip: the signed AuthnRequest verifies with the matching SP cert.

    Catches any private-key/cert mismatch — if these were swapped or the
    cert was wrong we'd produce technically-valid XML that no IdP can
    verify.
    """
    client = Client()
    resp = client.get(f"/api/v1/auth/saml/{tenant.subdomain}/login/")
    assert resp.status_code == 200
    xml = _decode_authn_request_from_form(resp.content.decode("utf-8"))

    from signxml import XMLVerifier

    root = _parse(xml)
    # Should not raise.
    XMLVerifier().verify(
        root,
        x509_cert=sp_keypair["cert_pem"],
        expect_references=1,
        require_x509=True,
        ignore_ambiguous_key_info=True,
    )


def test_authn_request_uses_exclusive_c14n_and_rsa_sha256(tenant, saml_config_signed):
    """The signature must use exclusive XML canonicalization + rsa-sha256.

    Prevents accidental drift to a weaker algorithm — strict-mode IdPs
    will reject anything weaker than SHA-256.
    """
    client = Client()
    resp = client.get(f"/api/v1/auth/saml/{tenant.subdomain}/login/")
    xml = _decode_authn_request_from_form(resp.content.decode("utf-8"))
    root = _parse(xml)

    sig = root.find("ds:Signature", NS)
    assert sig is not None
    c14n = sig.find("ds:SignedInfo/ds:CanonicalizationMethod", NS)
    sig_method = sig.find("ds:SignedInfo/ds:SignatureMethod", NS)
    digest = sig.find("ds:SignedInfo/ds:Reference/ds:DigestMethod", NS)
    assert c14n is not None and c14n.get("Algorithm") == SP_SIG_C14N
    assert sig_method is not None and sig_method.get("Algorithm") == SP_SIG_ALG
    assert digest is not None and digest.get("Algorithm") == SP_DIGEST_ALG


# ----------------------------------------------------------------------
# LogoutResponse tests
# ----------------------------------------------------------------------

def test_logout_response_signed_when_sp_key_configured(sp_keypair):
    xml = build_logout_response(
        in_response_to="id-original-logout-request",
        issuer="https://sp.example.test",
        destination="https://idp.example.test/slo",
        sp_private_key_pem=sp_keypair["key_pem"],
        sp_x509_cert_pem=sp_keypair["cert_pem"],
    )
    root = _parse(xml)
    assert root.tag.endswith("}LogoutResponse")
    sig = root.find("ds:Signature", NS)
    assert sig is not None, "LogoutResponse missing <ds:Signature>"
    assert root[0] is sig


def test_logout_response_unsigned_when_sp_key_absent():
    xml = build_logout_response(
        in_response_to="id-original",
        issuer="https://sp.example.test",
        destination="https://idp.example.test/slo",
    )
    root = _parse(xml)
    assert root.find("ds:Signature", NS) is None


def test_logout_response_signature_verifies_with_sp_cert(sp_keypair):
    """Round-trip on the LogoutResponse path."""
    xml = build_logout_response(
        in_response_to="id-original",
        issuer="https://sp.example.test",
        destination="https://idp.example.test/slo",
        sp_private_key_pem=sp_keypair["key_pem"],
        sp_x509_cert_pem=sp_keypair["cert_pem"],
    )
    from signxml import XMLVerifier

    XMLVerifier().verify(
        _parse(xml),
        x509_cert=sp_keypair["cert_pem"],
        expect_references=1,
        require_x509=True,
        ignore_ambiguous_key_info=True,
    )


def test_logout_response_uses_exclusive_c14n_and_rsa_sha256(sp_keypair):
    xml = build_logout_response(
        in_response_to="id-original",
        issuer="https://sp.example.test",
        destination="https://idp.example.test/slo",
        sp_private_key_pem=sp_keypair["key_pem"],
        sp_x509_cert_pem=sp_keypair["cert_pem"],
    )
    root = _parse(xml)
    sig = root.find("ds:Signature", NS)
    assert sig is not None
    assert (
        sig.find("ds:SignedInfo/ds:CanonicalizationMethod", NS).get("Algorithm")
        == SP_SIG_C14N
    )
    assert (
        sig.find("ds:SignedInfo/ds:SignatureMethod", NS).get("Algorithm")
        == SP_SIG_ALG
    )
    assert (
        sig.find("ds:SignedInfo/ds:Reference/ds:DigestMethod", NS).get("Algorithm")
        == SP_DIGEST_ALG
    )


# ----------------------------------------------------------------------
# Direct sign_saml_xml unit tests
# ----------------------------------------------------------------------

def test_sign_saml_xml_inserts_signature_as_first_child(sp_keypair):
    """SAML §5.4.1 mandates Signature as first child of the signed element."""
    xml = (
        '<?xml version="1.0"?>'
        '<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        'ID="id-test" Version="2.0" IssueInstant="2026-04-27T00:00:00Z">'
        '<saml:Issuer>https://sp.test</saml:Issuer>'
        '</samlp:AuthnRequest>'
    )
    signed = sign_saml_xml(
        xml,
        sp_private_key_pem=sp_keypair["key_pem"],
        sp_x509_cert_pem=sp_keypair["cert_pem"],
    )
    root = _parse(signed)
    assert root[0].tag.endswith("}Signature")
    # And there's still an Issuer somewhere after it.
    assert any(child.tag.endswith("}Issuer") for child in root)
