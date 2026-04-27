"""
Platform-level Course Templates (TASK-049).

A ``CourseTemplate`` is a tenant-independent blueprint that SUPER_ADMIN curators
build. Any tenant's SCHOOL_ADMIN can clone a published template into their own
tenant to get a starter course. Templates themselves never belong to a tenant.

Blueprint shape (``blueprint_json``) is deliberately simple + forward-compatible
with whatever TASK-048 ``ContentRevision.snapshot_json`` ends up using:

    {
        "schema_version": 1,
        "course": {
            "title": "...",
            "description": "...",
            "estimated_hours": 12,
            "is_mandatory": false
        },
        "modules": [
            {
                "title": "Module 1",
                "description": "...",
                "order": 1,
                "contents": [
                    {
                        "title": "Welcome video",
                        "content_type": "VIDEO",
                        "order": 1,
                        "text_content": "",
                        "file_url": "",
                        "duration": null,
                        "is_mandatory": true,
                        "meta_json": {}
                    }
                ]
            }
        ]
    }
"""

import uuid

from django.db import models


CATEGORY_CHOICES = [
    ("TEACHING_SKILLS", "Teaching Skills"),
    ("IB_PYP", "IB PYP"),
    ("IB_MYP", "IB MYP"),
    ("IB_DP", "IB DP"),
    ("LEADERSHIP", "Leadership"),
    ("WELLBEING", "Wellbeing"),
    ("OTHER", "Other"),
]

LEVEL_CHOICES = [
    ("BEGINNER", "Beginner"),
    ("INTERMEDIATE", "Intermediate"),
    ("ADVANCED", "Advanced"),
]


class CourseTemplate(models.Model):
    """
    A platform-level course blueprint. NOT tenant-scoped.

    Only SUPER_ADMIN users may CRUD these rows. SCHOOL_ADMIN users of any
    tenant may list/preview published templates and clone them into their
    own tenant.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    slug = models.SlugField(max_length=200, unique=True)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    category = models.CharField(
        max_length=32, choices=CATEGORY_CHOICES, default="OTHER"
    )
    language = models.CharField(max_length=10, default="en")
    estimated_hours = models.PositiveIntegerField(default=0)
    level = models.CharField(
        max_length=16, choices=LEVEL_CHOICES, default="BEGINNER"
    )
    thumbnail_url = models.URLField(blank=True, default="")

    # Serialized course + modules + contents tree. See module-level docstring
    # for the expected shape.
    blueprint_json = models.JSONField(default=dict, blank=True)

    is_published = models.BooleanField(default=False)

    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authored_course_templates",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "course_templates"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["category", "is_published"]),
            models.Index(fields=["language", "is_published"]),
            models.Index(fields=["level", "is_published"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"CourseTemplate({self.slug})"
