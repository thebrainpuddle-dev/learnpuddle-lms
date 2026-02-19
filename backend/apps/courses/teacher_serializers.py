from rest_framework import serializers
from django.conf import settings
from django.core.files.storage import default_storage

from apps.progress.models import TeacherProgress
from .models import Course, Module, Content


def _get_signed_file_url(file_field, expires_in=86400):
    """Generate a signed URL for S3/DO Spaces files, or return direct URL for local storage.
    
    Default expiry is 24 hours (86400 seconds) for thumbnails.
    """
    if not file_field:
        return None
    
    storage_backend = getattr(settings, 'STORAGE_BACKEND', 'local').lower()
    
    if storage_backend == 's3':
        try:
            storage = default_storage
            client = storage.connection.meta.client
            bucket_name = storage.bucket_name
            
            signed_url = client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': file_field.name},
                ExpiresIn=expires_in
            )
            return signed_url
        except Exception:
            return file_field.url
    
    return file_field.url


def _get_signed_url_from_path(url_or_path, expires_in=86400):
    """Generate a signed URL from a stored URL or S3 key path.
    
    Handles both:
    - Direct URLs: https://bucket.region.digitaloceanspaces.com/key/path
    - Relative paths: /media/key/path or key/path
    """
    if not url_or_path:
        return ""
    
    storage_backend = getattr(settings, 'STORAGE_BACKEND', 'local').lower()
    
    if storage_backend != 's3':
        return url_or_path
    
    try:
        storage = default_storage
        client = storage.connection.meta.client
        bucket_name = storage.bucket_name
        
        # Extract S3 key from URL
        key = url_or_path
        if url_or_path.startswith('http'):
            # Extract key from full URL
            # URL format: https://bucket.region.digitaloceanspaces.com/key/path
            # or: https://bucket.region.cdn.digitaloceanspaces.com/key/path
            from urllib.parse import urlparse
            parsed = urlparse(url_or_path)
            key = parsed.path.lstrip('/')
        elif url_or_path.startswith('/'):
            key = url_or_path.lstrip('/')
        
        signed_url = client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': key},
            ExpiresIn=expires_in
        )
        return signed_url
    except Exception:
        return url_or_path


class TeacherContentProgressSerializer(serializers.ModelSerializer):
    """
    Content serializer augmented with teacher progress.
    """

    status = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    video_progress_seconds = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    hls_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    has_transcript = serializers.SerializerMethodField()
    transcript_vtt_url = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = [
            "id",
            "title",
            "content_type",
            "order",
            "file_url",
            "hls_url",
            "thumbnail_url",
            "file_size",
            "duration",
            "text_content",
            "is_mandatory",
            "is_active",
            "status",
            "progress_percentage",
            "video_progress_seconds",
            "is_completed",
            "has_transcript",
            "transcript_vtt_url",
        ]

    def _progress_map(self):
        return self.context.get("progress_by_content_id", {})

    def _video_asset(self, obj):
        assets = self.context.get("video_assets_by_content_id", {}) or {}
        return assets.get(str(obj.id))

    def get_status(self, obj):
        p = self._progress_map().get(str(obj.id))
        return p.status if p else "NOT_STARTED"

    def get_progress_percentage(self, obj):
        p = self._progress_map().get(str(obj.id))
        return float(p.progress_percentage) if p else 0.0

    def get_video_progress_seconds(self, obj):
        p = self._progress_map().get(str(obj.id))
        return int(p.video_progress_seconds) if p else 0

    def get_is_completed(self, obj):
        p = self._progress_map().get(str(obj.id))
        return bool(p and p.status == "COMPLETED")

    def _abs(self, url: str) -> str:
        if not url:
            return ""
        if url.startswith("http://") or url.startswith("https://"):
            return url
        req = self.context.get("request")
        return req.build_absolute_uri(url) if req else url

    def get_hls_url(self, obj):
        if obj.content_type != "VIDEO":
            return ""
        asset = self._video_asset(obj)
        if not asset:
            return ""
        hls_url = getattr(asset, "hls_master_url", "") or ""
        if not hls_url:
            return ""
        # Generate signed URL for private S3/DO Spaces files (longer expiry for video playback)
        return _get_signed_url_from_path(hls_url, expires_in=14400)  # 4 hours for video streaming

    def get_thumbnail_url(self, obj):
        if obj.content_type != "VIDEO":
            return ""
        asset = self._video_asset(obj)
        if not asset:
            return ""
        thumb_url = getattr(asset, "thumbnail_url", "") or ""
        if not thumb_url:
            return ""
        # Generate signed URL for private S3/DO Spaces files
        return _get_signed_url_from_path(thumb_url)

    def get_has_transcript(self, obj):
        if obj.content_type != "VIDEO":
            return False
        asset = self._video_asset(obj)
        return bool(asset and getattr(asset, "transcript", None))

    def get_transcript_vtt_url(self, obj):
        if obj.content_type != "VIDEO":
            return ""
        asset = self._video_asset(obj)
        transcript = getattr(asset, "transcript", None) if asset else None
        if not transcript:
            return ""
        vtt_url = getattr(transcript, "vtt_url", "") or ""
        if not vtt_url:
            return ""
        # Generate signed URL for private S3/DO Spaces files
        return _get_signed_url_from_path(vtt_url)


class TeacherModuleSerializer(serializers.ModelSerializer):
    contents = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = ["id", "title", "description", "order", "is_active", "contents"]

    def get_contents(self, obj):
        contents = obj.contents.filter(is_active=True).order_by("order")
        return TeacherContentProgressSerializer(
            contents, many=True, context=self.context
        ).data


class TeacherCourseListSerializer(serializers.ModelSerializer):
    progress_percentage = serializers.SerializerMethodField()
    completed_content_count = serializers.SerializerMethodField()
    total_content_count = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "thumbnail",
            "thumbnail_url",
            "is_mandatory",
            "deadline",
            "estimated_hours",
            "is_published",
            "is_active",
            "created_at",
            "updated_at",
            "progress_percentage",
            "completed_content_count",
            "total_content_count",
        ]
    
    def get_thumbnail_url(self, obj):
        if not obj.thumbnail:
            return None
        return _get_signed_file_url(obj.thumbnail)

    def _get_teacher(self):
        return self.context["request"].user

    def get_total_content_count(self, obj):
        return Content.objects.filter(module__course=obj, is_active=True).count()

    def get_completed_content_count(self, obj):
        teacher = self._get_teacher()
        return TeacherProgress.objects.filter(
            teacher=teacher,
            course=obj,
            content__isnull=False,
            status="COMPLETED",
        ).count()

    def get_progress_percentage(self, obj):
        total = self.get_total_content_count(obj)
        if total == 0:
            return 0.0
        completed = self.get_completed_content_count(obj)
        return round((completed / total) * 100.0, 2)


class TeacherCourseDetailSerializer(serializers.ModelSerializer):
    modules = serializers.SerializerMethodField()
    progress = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "title",
            "slug",
            "description",
            "thumbnail",
            "thumbnail_url",
            "is_mandatory",
            "deadline",
            "estimated_hours",
            "is_published",
            "is_active",
            "created_at",
            "updated_at",
            "progress",
            "modules",
        ]
    
    def get_thumbnail_url(self, obj):
        if not obj.thumbnail:
            return None
        return _get_signed_file_url(obj.thumbnail)

    def get_modules(self, obj):
        modules = obj.modules.filter(is_active=True).order_by("order")
        return TeacherModuleSerializer(modules, many=True, context=self.context).data

    def get_progress(self, obj):
        teacher = self.context["request"].user
        total = Content.objects.filter(module__course=obj, is_active=True).count()
        completed = TeacherProgress.objects.filter(
            teacher=teacher,
            course=obj,
            content__isnull=False,
            status="COMPLETED",
        ).count()
        pct = round((completed / total) * 100.0, 2) if total else 0.0
        return {"completed_content_count": completed, "total_content_count": total, "percentage": pct}

