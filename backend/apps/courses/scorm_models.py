"""
SCORM 1.2 models.

SCORMPackage — represents an imported SCORM 1.2 content package, uploaded as a
.zip, extracted to a tenant-isolated media path, and linked 1:1 to a Content
row of type SCORM.

SCORMTrackingData — per-teacher SCORM runtime state (cmi.* data) stored as JSON.
"""

import uuid

from django.db import models

from utils.tenant_manager import TenantManager


class SCORMPackage(models.Model):
    """
    One SCORM 1.2 / 2004 package linked to exactly one Content.

    package_path stores a tenant-relative directory (e.g.
    ``tenant/<tenant_id>/scorm/<package_uuid>``) under ``MEDIA_ROOT``.
    ``launch_url`` is the manifest-declared launch resource, relative to
    ``package_path``.
    """

    VERSION_CHOICES = [
        ("1.2", "SCORM 1.2"),
        ("2004", "SCORM 2004"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="scorm_packages",
    )
    content = models.OneToOneField(
        "courses.Content",
        on_delete=models.CASCADE,
        related_name="scorm_package",
    )

    manifest_path = models.CharField(max_length=500, help_text="Relative path to imsmanifest.xml")
    launch_url = models.CharField(max_length=500, help_text="Relative launch URL inside the package")
    version = models.CharField(max_length=8, choices=VERSION_CHOICES, default="1.2")
    package_path = models.CharField(max_length=500, help_text="Relative package root under MEDIA_ROOT")
    package_size = models.BigIntegerField(default=0, help_text="Extracted size in bytes")

    uploaded_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_scorm_packages",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "scorm_packages"
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
        ]

    def __str__(self):
        return f"SCORMPackage({self.id}) -> Content({self.content_id})"


class SCORMTrackingData(models.Model):
    """
    Per-teacher SCORM tracking state. One row per (package, user).

    ``cmi`` stores the raw flat SCORM 1.2 CMI data model as submitted by the
    runtime (keys like ``cmi.core.lesson_status``, ``cmi.core.score.raw``).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="scorm_tracking_rows",
    )
    package = models.ForeignKey(
        SCORMPackage,
        on_delete=models.CASCADE,
        related_name="tracking_rows",
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="scorm_tracking_rows",
    )

    lesson_status = models.CharField(max_length=32, blank=True, default="")
    score_raw = models.FloatField(null=True, blank=True)
    session_time = models.CharField(max_length=32, blank=True, default="")
    total_time = models.CharField(max_length=32, blank=True, default="")

    cmi = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "scorm_tracking_data"
        unique_together = [("package", "user")]
        indexes = [
            models.Index(fields=["tenant", "user"]),
            models.Index(fields=["package", "user"]),
        ]

    def __str__(self):
        return f"SCORMTracking(pkg={self.package_id}, user={self.user_id})"
