"""
Models for the integrations_calendar app.

CalendarConnection  — one OAuth connection per provider per user.
CalendarSyncedEvent — tracks what has been pushed to which provider calendar.
ICalToken           — per-user iCal feed token (stored as SHA-256 hash only).
"""

import hashlib
import secrets
import uuid

from django.db import models
from django.utils import timezone

from utils.tenant_manager import TenantManager

from .crypto import decrypt_calendar_token, encrypt_calendar_token


class CalendarConnection(models.Model):
    """
    One row per (user, provider) pair.

    Access and refresh tokens are stored encrypted at rest using Fernet
    key-derived from SECRET_KEY (via apps.integrations_calendar.crypto).
    They are NEVER stored in plaintext and NEVER logged.
    """

    PROVIDER_GOOGLE = "google"
    PROVIDER_OUTLOOK = "outlook"
    PROVIDER_CHOICES = [
        (PROVIDER_GOOGLE, "Google Calendar"),
        (PROVIDER_OUTLOOK, "Outlook Calendar"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_EXPIRED = "expired"
    STATUS_REVOKED = "revoked"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_EXPIRED, "Expired (token needs refresh)"),
        (STATUS_REVOKED, "Revoked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="calendar_connections",
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="calendar_connections",
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)

    # Provider's identifier for the authenticated user (e.g. Google sub / MS oid).
    provider_user_id = models.CharField(max_length=255, blank=True, default="")

    # OAuth tokens — stored encrypted; never plaintext in DB or logs.
    access_token_encrypted = models.TextField(
        blank=True,
        default="",
        help_text="Fernet-encrypted access token. Never log or return in full.",
    )
    refresh_token_encrypted = models.TextField(
        blank=True,
        default="",
        help_text="Fernet-encrypted refresh token. Never log or return in full.",
    )

    # Space-separated list of granted OAuth scopes.
    scopes = models.TextField(blank=True, default="")

    # Provider calendar ID for the dedicated "LearnPuddle" calendar.
    target_calendar_id = models.CharField(max_length=500, blank=True, default="")

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )
    # Last error message (truncated); cleared on successful sync.
    error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()

    class Meta:
        db_table = "integrations_calendar_connection"
        unique_together = [("user", "provider")]
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"], name="cal_conn_tenant_status_idx"),
            models.Index(fields=["user", "provider"], name="cal_conn_user_provider_idx"),
        ]

    def __str__(self):
        return f"{self.user} — {self.get_provider_display()} [{self.status}]"

    # ------------------------------------------------------------------
    # Token helpers — callers SHOULD use these, not touch the _encrypted
    # fields directly.
    # ------------------------------------------------------------------

    def set_access_token(self, plaintext: str) -> None:
        self.access_token_encrypted = encrypt_calendar_token(plaintext)

    def get_access_token(self) -> str:
        return decrypt_calendar_token(self.access_token_encrypted)

    def set_refresh_token(self, plaintext: str) -> None:
        self.refresh_token_encrypted = encrypt_calendar_token(plaintext)

    def get_refresh_token(self) -> str:
        return decrypt_calendar_token(self.refresh_token_encrypted)


class CalendarSyncedEvent(models.Model):
    """
    One row per (connection, source_type, source_id) triple.

    Allows idempotent updates: when re-syncing, we look up the existing
    provider_event_id and PATCH/PUT rather than creating a duplicate.
    """

    SOURCE_DEADLINE = "deadline"
    SOURCE_ASSIGNMENT = "assignment"
    SOURCE_QUIZ = "quiz"
    SOURCE_CERTIFICATION = "certification"
    SOURCE_CHOICES = [
        (SOURCE_DEADLINE, "Enrollment Deadline"),
        (SOURCE_ASSIGNMENT, "Assignment Due Date"),
        (SOURCE_QUIZ, "Quiz Deadline"),
        (SOURCE_CERTIFICATION, "Certification Expiry"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connection = models.ForeignKey(
        CalendarConnection,
        on_delete=models.CASCADE,
        related_name="synced_events",
    )
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    # UUID or integer PK of the LMS object (Assignment.id, etc.).
    source_id = models.CharField(max_length=255)
    # Provider's event ID returned after creation (used for updates/deletes).
    provider_event_id = models.CharField(max_length=500, blank=True, default="")
    # SHA-256 of the event title — used to detect if a re-push is needed.
    title_hash = models.CharField(max_length=64, blank=True, default="")
    last_pushed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "integrations_calendar_synced_event"
        unique_together = [("connection", "source_type", "source_id")]
        indexes = [
            models.Index(
                fields=["connection", "source_type"],
                name="cal_event_conn_type_idx",
            ),
        ]

    def __str__(self):
        return f"{self.source_type}:{self.source_id} → {self.connection}"


class ICalToken(models.Model):
    """
    Per-user signed token that authenticates the public iCal feed URL.

    Only the SHA-256 hash is stored.  The plaintext token is generated
    once and embedded in the feed URL; it is never retrievable after that.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="ical_tokens",
    )
    # SHA-256 hex digest of the raw token — never the token itself.
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "integrations_calendar_ical_token"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="ical_token_user_revoked_idx"),
        ]

    def __str__(self):
        return f"ICalToken(user={self.user_id}, revoked={self.revoked_at is not None})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    # ------------------------------------------------------------------
    # Class-level helpers
    # ------------------------------------------------------------------

    @classmethod
    def generate(cls, user) -> tuple["ICalToken", str]:
        """
        Create a new active ICalToken for *user*.

        Returns ``(token_instance, raw_token)`` where *raw_token* is the
        URL-safe random string that MUST be embedded in the feed URL.
        The raw token is NOT stored — only its hash is persisted.
        """
        raw = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        instance = cls.objects.create(user=user, token_hash=token_hash)
        return instance, raw

    @classmethod
    def verify(cls, user, raw_token: str) -> "ICalToken | None":
        """
        Return the active ICalToken for *user* matching *raw_token*, or
        ``None`` if no match is found (including revoked tokens).
        """
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        try:
            return cls.objects.get(user=user, token_hash=token_hash, revoked_at__isnull=True)
        except cls.DoesNotExist:
            return None
