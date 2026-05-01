# apps/users/saml_service.py
"""
Minimal SAML 2.0 assertion parser + signature verifier.

Design goals
------------
1. **Never accept unsigned assertions.**  Every successful call through
   :func:`verify_and_parse_response` has cryptographically validated the
   ``<ds:Signature>`` on either the ``<samlp:Response>`` or the
   ``<saml:Assertion>`` using the configured IdP X.509 certificate(s).
2. **Enforce replay and expiry windows.**  ``NotBefore`` / ``NotOnOrAfter``
   are checked against wall-clock time with a small clock-skew tolerance.
3. **Contain the XML attack surface.**  Parsing happens with
   ``lxml.etree.XMLParser(resolve_entities=False, no_network=True)`` so
   external entities, DTD loading and network retrieval are disabled.
4. **Fail closed.**  Any parsing / verification error returns a
   structured ``SAMLValidationError`` that the ACS view turns into a
   403 with an audit log row.

We use :mod:`signxml` (a pure-python XMLDSig implementation on top of
``cryptography`` and ``lxml``) for the actual signature check.  These
libraries are listed in ``requirements.txt`` but imported lazily so that
simply loading this module never crashes the rest of Django in an
environment where SAML isn't needed.
"""

from __future__ import annotations

import base64
import datetime as _dt
import logging
from dataclasses import dataclass, field
from typing import Iterable, List, Optional
from xml.sax.saxutils import escape as _xml_escape, quoteattr as _xml_quoteattr

logger = logging.getLogger(__name__)

NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "md": "urn:oasis:names:tc:SAML:2.0:metadata",
}

# Maximum clock skew we'll tolerate when comparing NotBefore /
# NotOnOrAfter with server wall-clock time.
CLOCK_SKEW = _dt.timedelta(minutes=3)


class SAMLValidationError(Exception):
    """Raised when a SAML Response fails any validation step.

    The ``code`` field is intended to map onto
    ``SAMLAuthEvent.DECISION_CHOICES`` so the ACS view can write one row
    per decision without string parsing.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class SAMLAssertion:
    """Parsed attributes from a verified assertion."""

    response_id: str
    assertion_id: str
    subject_name_id: str
    email: str = ""
    first_name: str = ""
    last_name: str = ""
    groups: List[str] = field(default_factory=list)
    raw_attributes: dict = field(default_factory=dict)


@dataclass
class SAMLLogoutRequest:
    """Parsed attributes extracted from a SAML LogoutRequest."""

    request_id: str
    name_id: str
    issuer: str = ""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _parse_xml(raw: bytes):
    """Safely parse a bytes buffer into an lxml element.

    Raises :class:`SAMLValidationError` on any parsing error.  External
    entities, DTD loading and network access are disabled.
    """
    try:
        from lxml import etree  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SAMLValidationError("REJECT_MALFORMED", f"lxml unavailable: {exc}")

    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
    )
    try:
        return etree.fromstring(raw, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise SAMLValidationError("REJECT_MALFORMED", f"Invalid XML: {exc}")


def _parse_iso(value: str) -> _dt.datetime:
    """Parse a SAML timestamp (always UTC, ISO-8601 with trailing 'Z')."""
    if not value:
        raise SAMLValidationError("REJECT_MALFORMED", "Missing timestamp")
    # strip trailing Z and fractional seconds handling
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = _dt.datetime.fromisoformat(cleaned)
    except ValueError:
        raise SAMLValidationError("REJECT_MALFORMED", f"Bad timestamp: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _cert_to_der(pem_or_b64: str) -> bytes:
    """Convert either a PEM cert or a bare base64 blob into DER bytes."""
    value = (pem_or_b64 or "").strip()
    if not value:
        raise SAMLValidationError("REJECT_SIGNATURE", "Empty certificate configured")
    if "-----BEGIN" in value:
        # Already PEM — extract the base64 payload.
        lines = [l.strip() for l in value.splitlines() if l.strip()]
        body = "".join(l for l in lines if not l.startswith("-----"))
    else:
        body = "".join(value.split())
    try:
        return base64.b64decode(body)
    except Exception as exc:
        raise SAMLValidationError("REJECT_SIGNATURE", f"Bad certificate encoding: {exc}")


def _ensure_pem(pem_or_b64: str) -> str:
    """Normalize a cert to PEM form so :mod:`signxml` is happy."""
    value = (pem_or_b64 or "").strip()
    if not value:
        raise SAMLValidationError("REJECT_SIGNATURE", "Empty certificate configured")
    if "-----BEGIN" in value:
        return value
    body = "".join(value.split())
    # Re-wrap at 64 chars per PEM convention.
    wrapped = "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN CERTIFICATE-----\n{wrapped}\n-----END CERTIFICATE-----\n"


# ----------------------------------------------------------------------
# IdP metadata parsing
# ----------------------------------------------------------------------

def parse_idp_metadata(metadata_xml: str) -> dict:
    """Extract IdP entity ID, SSO/SLO URLs and signing certs from metadata.

    Returns a dict with keys: ``entity_id``, ``sso_url``, ``slo_url``,
    ``certs`` (list of PEM strings).
    """
    root = _parse_xml(metadata_xml.encode("utf-8"))

    entity_id = root.get("entityID", "")

    sso_url = ""
    slo_url = ""
    for sso in root.findall(".//md:IDPSSODescriptor/md:SingleSignOnService", NS):
        binding = sso.get("Binding", "")
        # Prefer HTTP-Redirect, fall back to HTTP-POST.
        if not sso_url or "HTTP-Redirect" in binding:
            sso_url = sso.get("Location", "") or sso_url
    for slo in root.findall(".//md:IDPSSODescriptor/md:SingleLogoutService", NS):
        if not slo_url:
            slo_url = slo.get("Location", "")

    certs: List[str] = []
    for cert_el in root.findall(".//md:IDPSSODescriptor//ds:X509Certificate", NS):
        text = (cert_el.text or "").strip()
        if text:
            certs.append(_ensure_pem(text))

    if not certs:
        raise SAMLValidationError(
            "REJECT_MALFORMED", "IdP metadata contained no X509Certificate"
        )
    if not sso_url:
        raise SAMLValidationError(
            "REJECT_MALFORMED", "IdP metadata contained no SingleSignOnService URL"
        )

    return {
        "entity_id": entity_id,
        "sso_url": sso_url,
        "slo_url": slo_url,
        "certs": certs,
    }


# ----------------------------------------------------------------------
# Signature verification
# ----------------------------------------------------------------------

def _assert_cert_validity_period(pem: str) -> None:
    """Reject PEM certs that are expired or not-yet-valid.

    Raises :class:`SAMLValidationError` with code ``REJECT_SIGNATURE`` if
    the cert's ``NotBefore`` / ``NotAfter`` window does not include now.
    We intentionally do NOT walk a trust chain — the IdP cert is a
    tenant-configured trust anchor — we only enforce the validity period.
    """
    try:
        from cryptography import x509  # type: ignore
        from cryptography.hazmat.backends import default_backend  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            f"cryptography unavailable — cannot check cert validity: {exc}",
        )

    try:
        cert = x509.load_pem_x509_certificate(pem.encode("ascii"), default_backend())
    except Exception as exc:
        raise SAMLValidationError(
            "REJECT_SIGNATURE", f"Unparseable IdP certificate: {exc}"
        )

    # cryptography >= 42 exposes ``not_valid_before_utc`` / ``not_valid_after_utc``.
    # Fall back to the naive attrs for older versions and coerce to UTC.
    not_before = (
        getattr(cert, "not_valid_before_utc", None)
        or cert.not_valid_before.replace(tzinfo=_dt.timezone.utc)
    )
    not_after = (
        getattr(cert, "not_valid_after_utc", None)
        or cert.not_valid_after.replace(tzinfo=_dt.timezone.utc)
    )
    now = _now()
    if now < not_before - CLOCK_SKEW:
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            f"IdP certificate is not yet valid (NotBefore={not_before.isoformat()})",
        )
    if now > not_after + CLOCK_SKEW:
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            f"IdP certificate expired at {not_after.isoformat()}",
        )


# SAML best-practice canonicalization + signing algorithms (matching what
# Microsoft Entra/ADFS strict mode expects for SP-signed AuthnRequest /
# LogoutResponse).
SP_SIG_C14N = "http://www.w3.org/2001/10/xml-exc-c14n#"
SP_SIG_ALG = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
SP_DIGEST_ALG = "http://www.w3.org/2001/04/xmlenc#sha256"


def sign_saml_xml(xml_string: str, *, sp_private_key_pem: str, sp_x509_cert_pem: str) -> str:
    """Embed an enveloped XMLDSig over the root element of ``xml_string``.

    Produces an enveloped signature with exclusive XML canonicalization
    (``http://www.w3.org/2001/10/xml-exc-c14n#``) and ``rsa-sha256`` /
    ``sha256`` digest — current SAML best-practice and what strict-mode
    IdPs (Microsoft Entra/AzureAD strict, ADFS) require.

    The ``ID`` attribute of the root element is referenced as the signed
    fragment.  Returns a UTF-8 XML string with a ``<ds:Signature>`` child
    inserted as the first element child of the root (per SAML §5).
    """
    if not sp_private_key_pem or not sp_x509_cert_pem:
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            "sign_saml_xml called without both private key and certificate",
        )
    try:
        from lxml import etree  # type: ignore
        from signxml import XMLSigner, methods  # type: ignore
        from signxml.algorithms import (  # type: ignore
            CanonicalizationMethod,
            DigestAlgorithm,
            SignatureMethod,
        )
    except Exception as exc:  # pragma: no cover
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            f"signxml unavailable — cannot sign SAML XML: {exc}",
        )

    raw = xml_string.encode("utf-8") if isinstance(xml_string, str) else xml_string
    root = _parse_xml(raw)
    root_id = root.get("ID")
    if not root_id:
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            "Cannot sign SAML XML: root element has no ID attribute",
        )

    signer = XMLSigner(
        method=methods.enveloped,
        signature_algorithm=SignatureMethod.RSA_SHA256,
        digest_algorithm=DigestAlgorithm.SHA256,
        c14n_algorithm=CanonicalizationMethod.EXCLUSIVE_XML_CANONICALIZATION_1_0,
    )
    # SAML §5.4.1: the Signature element MUST be the first child of the
    # signed element.  signxml inserts the Signature as the last child by
    # default; we relocate after signing.  We also pin the reference URI
    # to the root ID so the signature covers exactly this AuthnRequest /
    # LogoutResponse and verifiers don't have to guess.
    try:
        signed_root = signer.sign(
            root,
            key=sp_private_key_pem.encode("utf-8") if isinstance(sp_private_key_pem, str) else sp_private_key_pem,
            cert=sp_x509_cert_pem,
            reference_uri=f"#{root_id}",
        )
    except Exception as exc:
        raise SAMLValidationError(
            "REJECT_SIGNATURE", f"Failed to sign SAML XML: {exc}"
        )

    # Move the Signature element to the front (SAML positional requirement).
    sig = signed_root.find("ds:Signature", NS)
    if sig is not None and len(signed_root) and signed_root[0] is not sig:
        signed_root.remove(sig)
        signed_root.insert(0, sig)

    return etree.tostring(signed_root, xml_declaration=True, encoding="utf-8").decode(
        "utf-8"
    )


def _verify_xml_signature(signed_element, pem_certs: Iterable[str]) -> None:
    """Verify XMLDSig on ``signed_element`` against any of ``pem_certs``.

    Raises :class:`SAMLValidationError` with code ``REJECT_SIGNATURE`` if
    none of the supplied certs validate the signature, or if every
    candidate cert is outside its validity window.
    """
    try:
        from signxml import XMLVerifier  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            f"signxml unavailable — cannot verify SAML signature: {exc}",
        )

    last_error: Optional[Exception] = None
    for pem in pem_certs:
        # Validity window check first — an expired IdP cert must never pass
        # even if the signature is otherwise correct.
        _assert_cert_validity_period(pem)
        try:
            XMLVerifier().verify(
                signed_element,
                x509_cert=pem,
                expect_references=1,
                require_x509=True,
                ignore_ambiguous_key_info=True,
            )
            return
        except Exception as exc:  # pragma: no cover
            last_error = exc
            continue
    raise SAMLValidationError(
        "REJECT_SIGNATURE",
        f"No configured IdP certificate validated the signature: {last_error}",
    )


# ----------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------

def verify_and_parse_response(
    *,
    raw_response_b64: str,
    idp_certs_pem: Iterable[str],
    expected_audience: str,
    attribute_mapping: dict,
    expected_destination: Optional[str] = None,
) -> SAMLAssertion:
    """Parse, verify and validate a SAML Response.

    Args:
        raw_response_b64: The base64-encoded SAMLResponse form field.
        idp_certs_pem: Iterable of PEM-encoded IdP signing certs.
        expected_audience: SP entity ID that should appear in
            ``<AudienceRestriction>``.
        attribute_mapping: Dict mapping our internal user-field names
            (``email``, ``first_name``, ``last_name``, ``groups``) to
            SAML attribute names.
        expected_destination: If provided, the Response's
            ``Destination`` attribute must match (prevents token reuse
            against the wrong ACS URL).

    Returns: a populated :class:`SAMLAssertion` on success.

    Raises: :class:`SAMLValidationError` on any verification failure.
    """
    try:
        raw_bytes = base64.b64decode(raw_response_b64, validate=False)
    except Exception as exc:
        raise SAMLValidationError("REJECT_MALFORMED", f"Bad base64: {exc}")

    root = _parse_xml(raw_bytes)

    if not root.tag.endswith("}Response"):
        raise SAMLValidationError(
            "REJECT_MALFORMED", f"Root element is {root.tag!r}, expected samlp:Response"
        )

    response_id = root.get("ID", "")
    if not response_id:
        raise SAMLValidationError("REJECT_MALFORMED", "Response missing ID")

    # Find the assertion element (support both encrypted & plain).
    # We need the assertion BEFORE the signature check because the
    # signature can be on either the Response or the Assertion.
    assertion = root.find("saml:Assertion", NS)
    if assertion is None:
        # EncryptedAssertion is unsupported in this minimal implementation.
        if root.find("saml:EncryptedAssertion", NS) is not None:
            raise SAMLValidationError(
                "REJECT_MALFORMED",
                "EncryptedAssertion is not supported in this build",
            )
        raise SAMLValidationError("REJECT_MALFORMED", "Response contained no Assertion")

    assertion_id = assertion.get("ID", "")
    if not assertion_id:
        raise SAMLValidationError("REJECT_MALFORMED", "Assertion missing ID")

    # ------------------------------------------------------------------
    # Signature verification — require signature on the Response *or* on
    # the Assertion (ideally both).  Unsigned messages are rejected.
    #
    # SECURITY (AUDIT-2026-04-26-PHASE3-3): the signature check MUST run
    # before the Destination / AudienceRestriction / Conditions checks.
    # Signature is the cryptographic gate; everything else is contextual.
    # If we let Destination fire first, an unsigned response is logged as
    # ``REJECT_AUDIENCE`` instead of ``REJECT_SIGNATURE`` — which silently
    # under-counts failed-signature attempts on SOC dashboards and points
    # admins triaging "broken IdP cert" alerts at the wrong subsystem.
    # ------------------------------------------------------------------
    normalized_certs = [_ensure_pem(c) for c in idp_certs_pem if c]
    if not normalized_certs:
        raise SAMLValidationError(
            "REJECT_SIGNATURE", "No IdP certificates configured"
        )

    response_sig = root.find("ds:Signature", NS)
    assertion_sig = assertion.find("ds:Signature", NS)
    if response_sig is None and assertion_sig is None:
        raise SAMLValidationError(
            "REJECT_SIGNATURE",
            "Neither Response nor Assertion is signed — unsigned SAML is rejected",
        )

    # Verify whichever signature we find.  If both are present, verify both.
    if response_sig is not None:
        _verify_xml_signature(root, normalized_certs)
    if assertion_sig is not None:
        _verify_xml_signature(assertion, normalized_certs)

    # ------------------------------------------------------------------
    # Destination check — runs AFTER signature verification so that an
    # unsigned response is correctly classified as REJECT_SIGNATURE.
    # ------------------------------------------------------------------
    if expected_destination:
        destination = root.get("Destination", "")
        # SECURITY: missing Destination is not acceptable — a response
        # harvested from another SP could otherwise be replayed here.
        if not destination:
            raise SAMLValidationError(
                "REJECT_AUDIENCE",
                "SAML Response missing required Destination attribute",
            )
        if destination != expected_destination:
            raise SAMLValidationError(
                "REJECT_AUDIENCE",
                f"Destination mismatch: {destination!r} != {expected_destination!r}",
            )

    # ------------------------------------------------------------------
    # Conditions: NotBefore / NotOnOrAfter + AudienceRestriction
    # ------------------------------------------------------------------
    conditions = assertion.find("saml:Conditions", NS)
    now = _now()
    # SECURITY: missing <Conditions> means we have no AudienceRestriction
    # and no expiry window — an unbound assertion would otherwise be
    # accepted forever by any SP.  Fail closed.
    if conditions is None:
        raise SAMLValidationError(
            "REJECT_AUDIENCE",
            "Assertion missing required <Conditions> element",
        )

    nb = conditions.get("NotBefore")
    na = conditions.get("NotOnOrAfter")
    if nb:
        not_before = _parse_iso(nb)
        if now + CLOCK_SKEW < not_before:
            raise SAMLValidationError(
                "REJECT_NOT_YET_VALID",
                f"Assertion NotBefore={not_before.isoformat()} is in the future",
            )
    if na:
        not_on_or_after = _parse_iso(na)
        if now - CLOCK_SKEW >= not_on_or_after:
            raise SAMLValidationError(
                "REJECT_EXPIRED",
                f"Assertion expired at {not_on_or_after.isoformat()}",
            )

    # Audience restriction — must contain our SP entity ID.  A missing
    # AudienceRestriction is rejected: an IdP that omits it has issued a
    # bearer assertion that any SP could replay.
    audiences = [
        (a.text or "").strip()
        for a in conditions.findall(
            "saml:AudienceRestriction/saml:Audience", NS
        )
    ]
    if expected_audience:
        if not audiences:
            raise SAMLValidationError(
                "REJECT_AUDIENCE",
                "Assertion missing required AudienceRestriction",
            )
        if expected_audience not in audiences:
            raise SAMLValidationError(
                "REJECT_AUDIENCE",
                f"Audience {expected_audience!r} not in {audiences!r}",
            )

    # ------------------------------------------------------------------
    # Subject confirmation — also enforces a NotOnOrAfter window.
    # ------------------------------------------------------------------
    subject = assertion.find("saml:Subject", NS)
    name_id_el = subject.find("saml:NameID", NS) if subject is not None else None
    name_id = (name_id_el.text or "").strip() if name_id_el is not None else ""

    if subject is not None:
        for sc_data in subject.findall(
            "saml:SubjectConfirmation/saml:SubjectConfirmationData", NS
        ):
            na = sc_data.get("NotOnOrAfter")
            if na:
                not_on_or_after = _parse_iso(na)
                if now - CLOCK_SKEW >= not_on_or_after:
                    raise SAMLValidationError(
                        "REJECT_EXPIRED",
                        f"SubjectConfirmation expired at {not_on_or_after.isoformat()}",
                    )
            if expected_destination:
                recipient = sc_data.get("Recipient", "")
                if recipient and recipient != expected_destination:
                    raise SAMLValidationError(
                        "REJECT_AUDIENCE",
                        f"Recipient mismatch: {recipient!r} != {expected_destination!r}",
                    )

    # ------------------------------------------------------------------
    # Attribute extraction
    # ------------------------------------------------------------------
    raw_attrs: dict = {}
    for attr in assertion.findall("saml:AttributeStatement/saml:Attribute", NS):
        name = attr.get("Name", "")
        friendly = attr.get("FriendlyName", "")
        values = [
            (v.text or "").strip()
            for v in attr.findall("saml:AttributeValue", NS)
        ]
        if name:
            raw_attrs[name] = values
        if friendly and friendly not in raw_attrs:
            raw_attrs[friendly] = values

    def _first(key: str) -> str:
        attr_name = attribute_mapping.get(key)
        if not attr_name:
            return ""
        values = raw_attrs.get(attr_name, [])
        return values[0] if values else ""

    email = (_first("email") or name_id or "").strip().lower()
    first_name = _first("first_name")
    last_name = _first("last_name")
    groups_attr = attribute_mapping.get("groups")
    groups = raw_attrs.get(groups_attr, []) if groups_attr else []

    return SAMLAssertion(
        response_id=response_id,
        assertion_id=assertion_id,
        subject_name_id=name_id,
        email=email,
        first_name=first_name,
        last_name=last_name,
        groups=list(groups),
        raw_attributes=raw_attrs,
    )


# ----------------------------------------------------------------------
# SLO helpers
# ----------------------------------------------------------------------

def parse_logout_request(
    *,
    raw_request_b64: str,
    idp_certs_pem: Iterable[str] = (),
) -> SAMLLogoutRequest:
    """Parse and verify a base64-encoded SAML LogoutRequest.

    **Signature enforcement**: when at least one IdP certificate is supplied,
    a missing ``<ds:Signature>`` element raises
    ``SAMLValidationError("REJECT_SIGNATURE", ...)``.  This prevents an
    attacker from posting a forged unsigned LogoutRequest to the
    ``@csrf_exempt`` SLS endpoint and force-logging-out arbitrary users.
    When *no* certificates are configured, unsigned requests are still
    accepted (trust-on-first-use / IdPs that don't sign SLO requests).

    Supports both HTTP-POST binding (raw base64 XML) and HTTP-Redirect
    binding (raw-deflate-compressed base64) by trying plain base64 first
    and falling back to deflate decompression.

    Raises :class:`SAMLValidationError` on malformed input or signature
    failure.
    """
    try:
        raw_bytes = base64.b64decode(raw_request_b64, validate=False)
    except Exception as exc:
        raise SAMLValidationError("REJECT_MALFORMED", f"Bad base64: {exc}")

    # Try plain XML first (HTTP-POST binding); fall back to raw-deflate
    # (HTTP-Redirect binding — RFC 7616 §3.4.4.1).
    try:
        root = _parse_xml(raw_bytes)
    except SAMLValidationError:
        import zlib
        try:
            raw_bytes = zlib.decompress(raw_bytes, -15)  # raw deflate (no header)
        except Exception as exc:
            raise SAMLValidationError(
                "REJECT_MALFORMED",
                f"LogoutRequest is neither plain XML nor deflate-compressed: {exc}",
            )
        root = _parse_xml(raw_bytes)

    if not root.tag.endswith("}LogoutRequest"):
        raise SAMLValidationError(
            "REJECT_MALFORMED",
            f"Root element is {root.tag!r}, expected samlp:LogoutRequest",
        )

    request_id = root.get("ID", "")
    if not request_id:
        raise SAMLValidationError("REJECT_MALFORMED", "LogoutRequest missing ID attribute")

    # Signature enforcement — when certs are configured a missing signature
    # is a hard rejection, not a fallback.  Allowing unsigned requests through
    # when we hold the IdP's public key would let any third-party site
    # force-logout users by cross-posting a forged LogoutRequest (the SLS
    # endpoint is @csrf_exempt; signature verification is the only gate).
    sig = root.find("ds:Signature", NS)
    normalized_certs = [_ensure_pem(c) for c in idp_certs_pem if c]
    if normalized_certs:
        if sig is None:
            raise SAMLValidationError(
                "REJECT_SIGNATURE",
                "LogoutRequest is unsigned but IdP certificates are configured; "
                "unsigned requests are rejected when a trust anchor is present",
            )
        _verify_xml_signature(root, normalized_certs)

    name_id_el = root.find("saml:NameID", NS)
    name_id = (name_id_el.text or "").strip() if name_id_el is not None else ""

    issuer_el = root.find("saml:Issuer", NS)
    issuer = (issuer_el.text or "").strip() if issuer_el is not None else ""

    return SAMLLogoutRequest(
        request_id=request_id,
        name_id=name_id,
        issuer=issuer,
    )


def build_logout_response(
    *,
    in_response_to: str,
    issuer: str,
    destination: str,
    status_code: str = "urn:oasis:names:tc:SAML:2.0:status:Success",
    sp_private_key_pem: str = "",
    sp_x509_cert_pem: str = "",
) -> str:
    """Build a SAML LogoutResponse XML string, optionally SP-signed.

    Args:
        in_response_to: The ID of the LogoutRequest this is responding to.
        issuer: SP entity ID (``<saml:Issuer>``).
        destination: IdP SLO URL that will receive the response.
        status_code: SAML status code URI (default: Success).
        sp_private_key_pem: PEM private key.  When supplied with
            ``sp_x509_cert_pem`` the response is enveloped-signed using
            exclusive XML canonicalization + ``rsa-sha256``.  When empty
            the response is emitted unsigned (backwards-compatible
            behaviour for IdPs that don't require a signed LogoutResponse).
        sp_x509_cert_pem: PEM SP certificate matching the private key.

    Returns:
        UTF-8 XML string.
    """
    import uuid

    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    response_id = f"id-{uuid.uuid4().hex}"
    # Use quoteattr() for attribute values (adds surrounding quotes + escapes
    # embedded quotes/ampersands) and escape() for text content.
    # ``in_response_to`` originates from the parsed LogoutRequest ID attribute
    # and is attacker-controlled when the request is forged; the other values
    # are server-controlled but are escaped for defence-in-depth.
    xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<samlp:LogoutResponse"
        " xmlns:samlp=\"urn:oasis:names:tc:SAML:2.0:protocol\""
        " xmlns:saml=\"urn:oasis:names:tc:SAML:2.0:assertion\""
        f" ID={_xml_quoteattr(response_id)}"
        " Version=\"2.0\""
        f" IssueInstant={_xml_quoteattr(now)}"
        f" Destination={_xml_quoteattr(destination)}"
        f" InResponseTo={_xml_quoteattr(in_response_to)}>"
        f"<saml:Issuer>{_xml_escape(issuer)}</saml:Issuer>"
        "<samlp:Status>"
        f"<samlp:StatusCode Value={_xml_quoteattr(status_code)}/>"
        "</samlp:Status>"
        "</samlp:LogoutResponse>"
    )
    if sp_private_key_pem and sp_x509_cert_pem:
        xml = sign_saml_xml(
            xml,
            sp_private_key_pem=sp_private_key_pem,
            sp_x509_cert_pem=sp_x509_cert_pem,
        )
    return xml


# ----------------------------------------------------------------------
# Simple SP metadata generator
# ----------------------------------------------------------------------

def generate_sp_metadata(*, entity_id: str, acs_url: str, slo_url: str, sp_cert: str = "") -> str:
    """Generate a minimal SP metadata XML document.

    This is served unauthenticated from the metadata endpoint and must
    only expose public information (entity ID, ACS URL, optional public
    cert).  Never include ``sp_private_key`` here.
    """
    cert_block = ""
    if sp_cert:
        stripped = (
            sp_cert.replace("-----BEGIN CERTIFICATE-----", "")
            .replace("-----END CERTIFICATE-----", "")
            .strip()
        )
        stripped = "".join(stripped.split())
        cert_block = (
            "<md:KeyDescriptor use=\"signing\">"
            "<ds:KeyInfo xmlns:ds=\"http://www.w3.org/2000/09/xmldsig#\">"
            f"<ds:X509Data><ds:X509Certificate>{stripped}</ds:X509Certificate></ds:X509Data>"
            "</ds:KeyInfo></md:KeyDescriptor>"
        )
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
        "<md:EntityDescriptor xmlns:md=\"urn:oasis:names:tc:SAML:2.0:metadata\" "
        f"entityID=\"{entity_id}\">"
        "<md:SPSSODescriptor AuthnRequestsSigned=\"false\" WantAssertionsSigned=\"true\" "
        "protocolSupportEnumeration=\"urn:oasis:names:tc:SAML:2.0:protocol\">"
        f"{cert_block}"
        f"<md:SingleLogoutService Binding=\"urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST\" Location=\"{slo_url}\"/>"
        "<md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>"
        "<md:AssertionConsumerService "
        "Binding=\"urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST\" "
        f"Location=\"{acs_url}\" index=\"1\"/>"
        "</md:SPSSODescriptor>"
        "</md:EntityDescriptor>"
    )
