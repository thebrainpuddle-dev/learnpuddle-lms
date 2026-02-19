from rest_framework import serializers

from apps.progress.models import TeacherProgress
from .models import Course, Module, Content
from utils.s3_utils import sign_file_field, sign_url


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
        # Return backend proxy URL that serves m3u8 with signed segment URLs
        # URL ends with .m3u8 so HLS.js recognizes it as an HLS source
        req = self.context.get("request")
        if req:
            return req.build_absolute_uri(f"/api/courses/hls/{obj.id}/master.m3u8")
        return f"/api/courses/hls/{obj.id}/master.m3u8"

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
        return sign_url(thumb_url)

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
        return sign_url(vtt_url)


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
        return sign_file_field(obj.thumbnail)

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
        return sign_file_field(obj.thumbnail)

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

