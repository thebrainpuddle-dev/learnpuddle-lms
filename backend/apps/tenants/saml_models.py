# apps/tenants/saml_models.py
"""
Per-tenant SAML 2.0 SSO configuration.

Each tenant may configure exactly one TenantSAMLConfig which carries the
IdP metadata, SP entity ID, optional SP certificate/private key for
signing AuthnRequests, attribute mapping, and auto-provisioning flags.

Signature verification and assertion parsing live in
`apps.users.saml_service` — this module only persists configuration.
"""

from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import models


# Only these attribute-mapping keys are honored by the ACS flow.  The
# mapping is admin-editable JSON so we must sanitize input — never eval
# keys and never store unknown keys.
ALLOWED_ATTRIBUTE_KEYS = {"email", "first_name", "last_name", "groups", "role"}


def default_attribute_mapping() -> dict:
    """Reasonable starter mapping aligned with Azure AD / Okta defaults."""
    return {
        "email": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "first_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        "last_name": "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        "groups": "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
    }


class TenantSAMLConfig(models.Model):
    """SAML 2.0 SSO configuration for a single tenant."""

    ROLE_CHOICES = [
        ("TEACHER", "Teacher"),
        ("HOD", "Head of Department"),
        ("IB_COORDINATOR", "IB Coordinator"),
        ("SCHOOL_ADMIN", "School Admin"),
        ("STUDENT", "Student"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="saml_config",
    )

    enabled = models.BooleanField(default=False)

    # IdP metadata — admin pastes the IdP's metadata XML here.  Parsed
    # on-demand by `saml_service.load_idp_settings`.
    idp_metadata_xml = models.TextField(
        blank=True, default="",
        help_text="Full IdP SAML 2.0 metadata XML.",
    )
    idp_entity_id = models.CharField(max_length=500, blank=True, default="")
    idp_sso_url = models.URLField(blank=True, default="", max_length=500)
    idp_slo_url = models.URLField(blank=True, default="", max_length=500)
    # PEM-encoded X.509 certificate(s) — multiple allowed for rotation.
    idp_x509_certs = models.JSONField(
        default=list, blank=True,
        help_text="List of PEM-encoded X.509 certs extracted from IdP metadata.",
    )

    # SP-side settings
    sp_entity_id = models.CharField(
        max_length=500,
        help_text="This SP's entity ID (usually the tenant's ACS URL).",
    )
    sp_x509_cert = models.TextField(
        blank=True, default="",
        help_text="PEM-encoded SP certificate (optional, for signing AuthnRequests).",
    )
    # Stored Fernet-encrypted (via utils.encryption); use the
    # ``sp_private_key_pem`` property for the PEM plaintext.
    sp_private_key = models.TextField(
        blank=True, default="",
        help_text="PEM-encoded SP private key — persisted Fernet-encrypted at rest.",
    )

    # Attribute mapping (SAML attribute URI → User field)
    attribute_mapping = models.JSONField(
        default=default_attribute_mapping,
        blank=True,
        help_text="Keys restricted to: email, first_name, last_name, groups, role.",
    )

    # Provisioning
    auto_provision = models.BooleanField(
        default=False,
        help_text="If True, unknown users are created on successful SSO.",
    )
    default_role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default="TEACHER",
        help_text="Role assigned to auto-provisioned users.",
    )

    # Optional restriction: only allow auto-provisioning for specific email domains.
    allowed_email_domains = models.TextField(
        blank=True, default="",
        help_text="Comma-separated domains; empty = allow any.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_saml_configs"
        verbose_name = "Tenant SAML config"
        verbose_name_plural = "Tenant SAML configs"

    def __str__(self) -> str:  # pragma: no cover
        return f"SAMLConfig({self.tenant_id}, enabled={self.enabled})"

    def clean(self) -> None:
        super().clean()
        if self.attribute_mapping is None:
            self.attribute_mapping = {}
        if not isinstance(self.attribute_mapping, dict):
            raise ValidationError({"attribute_mapping": "Must be a JSON object."})
        unknown = set(self.attribute_mapping.keys()) - ALLOWED_ATTRIBUTE_KEYS
        if unknown:
            raise ValidationError(
                {"attribute_mapping": f"Unknown keys: {', '.join(sorted(unknown))}"}
            )
        for k, v in self.attribute_mapping.items():
            if not isinstance(v, str) or not v:
                raise ValidationError(
                    {"attribute_mapping": f"Value for '{k}' must be a non-empty string."}
                )
        if self.enabled and not (self.idp_sso_url and self.idp_x509_certs):
            raise ValidationError(
                "SAML cannot be enabled without an IdP SSO URL and at least one certificate."
            )

    # ---- Helpers -----------------------------------------------------

    # Ciphertext marker — legacy rows (prior to encryption-at-rest) store
    # the raw PEM and lack this prefix.  New writes always store a Fernet
    # token prefixed with this sentinel so the accessor can tell them
    # apart without guessing.
    _ENC_PREFIX = "enc:v1:"

    @property
    def sp_private_key_pem(self) -> str:
        """Return the decrypted PEM, or an empty string if none is configured."""
        raw = self.sp_private_key or ""
        if not raw:
            return ""
        if raw.startswith(self._ENC_PREFIX):
            from utils.encryption import decrypt_value
            return decrypt_value(raw[len(self._ENC_PREFIX):])
        # Legacy (pre-encryption-at-rest) plaintext — return as-is; the
        # next write will migrate the row to ciphertext.
        return raw

    def set_sp_private_key(self, pem: str) -> None:
        """Assign a new PEM private key, encrypted at rest."""
        if not pem:
            self.sp_private_key = ""
            return
        from utils.encryption import encrypt_value
        self.sp_private_key = f"{self._ENC_PREFIX}{encrypt_value(pem)}"

    def domain_allowed(self, email: str) -> bool:
        if not self.allowed_email_domains:
            return True
        allowed = {d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()}
        try:
            domain = email.split("@", 1)[1].lower()
        except IndexError:
            return False
        return domain in allowed
