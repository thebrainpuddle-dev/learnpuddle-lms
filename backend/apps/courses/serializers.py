# apps/courses/serializers.py

from rest_framework import serializers
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.core.files.storage import default_storage
from .models import Course, Module, Content, TeacherGroup
from apps.users.models import User


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


def _get_signed_url_from_path(url_or_path, expires_in=14400):
    """Generate a signed URL from a stored URL or S3 key path.
    
    Handles both:
    - Direct URLs: https://bucket.region.digitaloceanspaces.com/key/path
    - Relative paths: /media/key/path or key/path
    
    Default expiry is 4 hours (14400 seconds) for content files.
    """
    if not url_or_path:
        return ""
    
    storage_backend = getattr(settings, 'STORAGE_BACKEND', 'local').lower()
    
    if storage_backend != 's3':
        return url_or_path
    
    try:
        from urllib.parse import urlparse
        storage = default_storage
        client = storage.connection.meta.client
        bucket_name = storage.bucket_name
        
        # Extract S3 key from URL
        key = url_or_path
        if url_or_path.startswith('http'):
            # Extract key from full URL
            # URL format: https://bucket.region.digitaloceanspaces.com/key/path
            # or: https://bucket.region.cdn.digitaloceanspaces.com/key/path
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


class ContentSerializer(serializers.ModelSerializer):
    """Serializer for course content."""
    video_status = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Content
        fields = [
            'id', 'title', 'content_type', 'order',
            'file_url', 'file_size', 'duration',
            'text_content', 'is_mandatory', 'is_active',
            'video_status',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_file_url(self, obj):
        """Return signed URL for S3/DO Spaces files."""
        raw_url = obj.file_url or ""
        if not raw_url:
            return ""
        return _get_signed_url_from_path(raw_url)

    def get_video_status(self, obj):
        if obj.content_type != "VIDEO":
            return None
        asset = getattr(obj, "video_asset", None)
        if asset is None:
            # Not prefetched; try DB lookup
            try:
                from .video_models import VideoAsset
                asset = VideoAsset.objects.filter(content=obj).first()
            except Exception:
                pass
        return asset.status if asset else None


class ModuleSerializer(serializers.ModelSerializer):
    """Serializer for course modules."""
    
    contents = ContentSerializer(many=True, read_only=True)
    content_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Module
        fields = [
            'id', 'title', 'description', 'order',
            'is_active', 'contents', 'content_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_content_count(self, obj):
        return obj.contents.filter(is_active=True).count()


class CourseListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for course listing."""
    
    module_count = serializers.SerializerMethodField()
    content_count = serializers.SerializerMethodField()
    assigned_teacher_count = serializers.SerializerMethodField()
    completion_rate = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'description', 'thumbnail', 'thumbnail_url',
            'is_mandatory', 'deadline', 'estimated_hours',
            'is_published', 'is_active', 'module_count', 'content_count',
            'assigned_teacher_count', 'completion_rate',
            'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_at', 'updated_at']
    
    def get_thumbnail_url(self, obj):
        if not obj.thumbnail:
            return None
        return _get_signed_file_url(obj.thumbnail)

    def get_content_count(self, obj):
        return Content.objects.filter(module__course=obj, is_active=True).count()
    
    def get_module_count(self, obj):
        return obj.modules.filter(is_active=True).count()
    
    def get_assigned_teacher_count(self, obj):
        if obj.assigned_to_all:
            # Count all teachers in tenant
            return User.objects.filter(
                tenant=obj.tenant,
                role='TEACHER',
                is_active=True
            ).count()
        
        # Count from groups + individual assignments (single queryset to avoid UNION pitfalls)
        group_ids = obj.assigned_groups.values_list("id", flat=True)
        individual_ids = obj.assigned_teachers.values_list("id", flat=True)

        return (
            User.objects.filter(
                tenant=obj.tenant,
                role="TEACHER",
                is_active=True,
            )
            .filter(Q(teacher_groups__in=group_ids) | Q(id__in=individual_ids))
            .distinct()
            .count()
        )
    
    def get_completion_rate(self, obj):
        # TODO: Calculate from TeacherProgress model
        return 0.0
    
    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name()
        return None


class CourseDetailSerializer(serializers.ModelSerializer):
    """Detailed course serializer with modules."""
    
    modules = ModuleSerializer(many=True, read_only=True)
    assigned_groups = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=TeacherGroup.objects.none(),
        required=False
    )
    assigned_teachers = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=User.objects.none(),
        required=False
    )
    stats = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        
        if request and hasattr(request, 'tenant') and request.tenant:
            groups_qs = TeacherGroup.objects.all_tenants().filter(
                tenant=request.tenant
            )
            teachers_qs = User.all_objects.filter(
                tenant=request.tenant,
                is_deleted=False,
            ).exclude(
                role__in=['SUPER_ADMIN', 'SCHOOL_ADMIN'],
            )
            # DRF many=True wraps field in ManyRelatedField.
            # Must set queryset on child_relation for validation to work.
            self.fields['assigned_groups'].child_relation.queryset = groups_qs
            self.fields['assigned_teachers'].child_relation.queryset = teachers_qs
        else:
            self.fields['assigned_groups'].child_relation.queryset = TeacherGroup.objects.none()
            self.fields['assigned_teachers'].child_relation.queryset = User.objects.none()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'description', 'thumbnail', 'thumbnail_url',
            'is_mandatory', 'deadline', 'estimated_hours',
            'assigned_to_all', 'assigned_groups', 'assigned_teachers',
            'is_published', 'is_active', 'modules', 'stats',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_by', 'created_at', 'updated_at']
    
    def get_thumbnail_url(self, obj):
        if not obj.thumbnail:
            return None
        return _get_signed_file_url(obj.thumbnail)
    
    def get_stats(self, obj):
        return {
            'total_modules': obj.modules.count(),
            'total_content': Content.objects.filter(module__course=obj).count(),
            'total_assignments': obj.assignments.count(),
        }
    
    def create(self, validated_data):
        assigned_groups = validated_data.pop('assigned_groups', [])
        assigned_teachers = validated_data.pop('assigned_teachers', [])
        
        # Get current user and tenant from context
        request = self.context['request']
        user = request.user
        tenant = request.tenant
        
        course = Course.objects.create(
            **validated_data,
            tenant=tenant,
            created_by=user
        )
        
        # Set assignments
        if assigned_groups:
            course.assigned_groups.set(assigned_groups)
        if assigned_teachers:
            course.assigned_teachers.set(assigned_teachers)
        
        # Notify newly assigned teachers (only if course is published)
        if course.is_published:
            self._notify_assigned_teachers(course, tenant, set(), assigned_groups, assigned_teachers)
        
        return course

    def update(self, instance, validated_data):
        assigned_groups = validated_data.pop('assigned_groups', None)
        assigned_teachers = validated_data.pop('assigned_teachers', None)
        assigned_to_all = validated_data.get('assigned_to_all', instance.assigned_to_all)
        was_published = instance.is_published
        
        # Track current assignments before update
        old_group_ids = set(instance.assigned_groups.values_list('id', flat=True))
        old_teacher_ids = set(instance.assigned_teachers.values_list('id', flat=True))
        old_assigned_to_all = instance.assigned_to_all
        
        with transaction.atomic():
            # Update regular fields
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()
            
            # Update assignments
            if assigned_groups is not None:
                instance.assigned_groups.set(assigned_groups)
            if assigned_teachers is not None:
                instance.assigned_teachers.set(assigned_teachers)
        
        # Notify outside the transaction (non-critical)
        if instance.is_published:
            request = self.context.get('request')
            tenant = request.tenant if request else instance.tenant
            
            new_group_ids = set(instance.assigned_groups.values_list('id', flat=True)) if assigned_groups is not None else old_group_ids
            new_teacher_ids = set(instance.assigned_teachers.values_list('id', flat=True)) if assigned_teachers is not None else old_teacher_ids
            
            self._notify_assigned_teachers(
                instance, tenant, 
                old_teacher_ids if not old_assigned_to_all else set(),
                list(instance.assigned_groups.all()) if assigned_groups is not None else [],
                list(instance.assigned_teachers.all()) if assigned_teachers is not None else [],
                old_group_ids if not old_assigned_to_all else set(),
            )
        
        return instance

    def _notify_assigned_teachers(self, course, tenant, old_teacher_ids, new_groups, new_teachers, old_group_ids=None):
        """
        Notify teachers who are newly assigned to a course.
        """
        from apps.notifications.services import notify_course_assigned
        
        # Get all teachers in new groups
        new_teachers_from_groups = set()
        if new_groups:
            for group in new_groups:
                new_teachers_from_groups.update(
                    group.members.filter(
                        tenant=tenant,
                        role__in=['TEACHER', 'HOD', 'IB_COORDINATOR'],
                        is_active=True
                    ).values_list('id', flat=True)
                )
        
        # Get individual teacher IDs
        new_teacher_ids = set(t.id if hasattr(t, 'id') else t for t in new_teachers)
        
        # Calculate teachers in old groups
        old_teachers_from_groups = set()
        if old_group_ids:
            from .models import TeacherGroup
            for group in TeacherGroup.objects.filter(id__in=old_group_ids):
                old_teachers_from_groups.update(
                    group.members.filter(
                        tenant=tenant,
                        role__in=['TEACHER', 'HOD', 'IB_COORDINATOR'],
                        is_active=True
                    ).values_list('id', flat=True)
                )
        
        # All old assignments
        all_old = old_teacher_ids | old_teachers_from_groups
        # All new assignments
        all_new = new_teacher_ids | new_teachers_from_groups
        
        # Only notify those who are newly assigned
        newly_assigned_ids = all_new - all_old
        
        if newly_assigned_ids:
            newly_assigned = User.objects.filter(id__in=newly_assigned_ids)
            notify_course_assigned(tenant, list(newly_assigned), course)


class CreateModuleSerializer(serializers.ModelSerializer):
    """Serializer for creating modules."""
    
    class Meta:
        model = Module
        fields = ['title', 'description', 'order', 'is_active']
    
    def create(self, validated_data):
        course_id = self.context.get('course_id')
        course = Course.objects.get(id=course_id)
        return Module.objects.create(course=course, **validated_data)


class CreateContentSerializer(serializers.ModelSerializer):
    """Serializer for creating content."""
    
    class Meta:
        model = Content
        fields = [
            'title', 'content_type', 'order',
            'file_url', 'file_size', 'duration',
            'text_content', 'is_mandatory', 'is_active'
        ]
    
    def create(self, validated_data):
        module_id = self.context.get('module_id')
        module = Module.objects.get(id=module_id)
        return Content.objects.create(module=module, **validated_data)
