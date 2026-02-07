import uuid

from django.db import models
from django.utils import timezone


class VideoAsset(models.Model):
    """
    Video processing metadata and derived artifacts for a `courses.Content` row where
    `content_type='VIDEO'`.
    """

    STATUS_CHOICES = [
        ("UPLOADED", "Uploaded"),
        ("PROCESSING", "Processing"),
        ("READY", "Ready"),
        ("FAILED", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    content = models.OneToOneField(
        "courses.Content",
        on_delete=models.CASCADE,
        related_name="video_asset",
    )

    # Source (original) upload reference. `source_file` is a storage key/path.
    source_file = models.CharField(max_length=512, blank=True, default="")
    source_url = models.URLField(blank=True, default="")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="UPLOADED")
    error_message = models.TextField(blank=True, default="")

    # Technical metadata (best-effort; filled by ffprobe)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    codec = models.CharField(max_length=64, blank=True, default="")

    # Derived artifacts
    hls_master_url = models.URLField(blank=True, default="")
    thumbnail_url = models.URLField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "video_assets"
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["content"]),
        ]

    def __str__(self) -> str:
        return f"VideoAsset({self.content_id}) {self.status}"


class VideoTranscript(models.Model):
    """
    Transcript + captions metadata for a processed video.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video_asset = models.OneToOneField(
        VideoAsset,
        on_delete=models.CASCADE,
        related_name="transcript",
    )

    language = models.CharField(max_length=20, default="en")
    full_text = models.TextField(blank=True, default="")
    segments = models.JSONField(blank=True, default=list)  # [{"start":..,"end":..,"text":..}, ...]
    vtt_url = models.URLField(blank=True, default="")

    generated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "video_transcripts"

    def mark_generated_now(self):
        self.generated_at = timezone.now()
        self.save(update_fields=["generated_at", "updated_at"])

    def __str__(self) -> str:
        return f"VideoTranscript({self.video_asset_id})"

