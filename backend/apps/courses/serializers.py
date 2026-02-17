# apps/courses/serializers.py

from rest_framework import serializers
from django.db.models import Q
from django.core.exceptions import ObjectDoesNotExist
from .models import Course, Module, Content, TeacherGroup
from apps.users.models import User
import logging

_ser_log = logging.getLogger('debug.course_serializers')


class SafePrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """
    Custom PrimaryKeyRelatedField that properly handles querysets from
    custom managers without triggering unexpected filtering.
    
    The issue: DRF's get_queryset() calls self.queryset.all() which can
    sometimes trigger manager behaviors. This field stores and uses
    the queryset directly without the .all() call.
    """
    
    def __init__(self, **kwargs):
        self._explicit_queryset = None
        super().__init__(**kwargs)
    
    def set_queryset(self, queryset):
        """Set queryset explicitly, bypassing potential manager issues."""
        self._explicit_queryset = queryset
        self.queryset = queryset
    
    def get_queryset(self):
        """Return the explicitly set queryset without calling .all()."""
        if self._explicit_queryset is not None:
            return self._explicit_queryset
        return super().get_queryset()
    
    def to_internal_value(self, data):
        """Override to add debugging and handle lookup properly."""
        queryset = self.get_queryset()
        try:
            # Log for debugging
            _ser_log.warning('[SPKRF] to_internal_value: data=%s type=%s qs_count=%s',
                data, type(data).__name__, queryset.count())
            
            if self.pk_field is not None:
                data = self.pk_field.to_internal_value(data)
            
            # Try direct get
            result = queryset.get(pk=data)
            _ser_log.warning('[SPKRF] found: %s', result)
            return result
        except ObjectDoesNotExist:
            _ser_log.warning('[SPKRF] ObjectDoesNotExist for pk=%s, qs_sql=%s', 
                data, str(queryset.query)[:500])
            self.fail('does_not_exist', pk_value=data)
        except (TypeError, ValueError) as e:
            _ser_log.warning('[SPKRF] TypeError/ValueError: %s', e)
            self.fail('incorrect_type', data_type=type(data).__name__)


class ContentSerializer(serializers.ModelSerializer):
    """Serializer for course content."""
    video_status = serializers.SerializerMethodField()

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
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.thumbnail.url)
        return obj.thumbnail.url

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
        queryset=TeacherGroup.objects.none(),  # overridden in __init__
        required=False
    )
    # Use custom field to bypass DRF's queryset.all() behavior
    assigned_teachers = SafePrimaryKeyRelatedField(
        many=True,
        queryset=User.objects.none(),  # overridden in __init__
        required=False
    )
    stats = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        
        if request and hasattr(request, 'tenant') and request.tenant:
            # Use all_tenants() to bypass TenantManager's automatic filtering
            # and apply explicit tenant filter to avoid double-filtering issues
            self.fields['assigned_groups'].queryset = TeacherGroup.objects.all_tenants().filter(
                tenant=request.tenant
            )
            # Match /teachers/ endpoint: all non-admin users from tenant
            # Use all_objects to bypass UserSoftDeleteManager's automatic filtering
            # which can cause issues with DRF's PrimaryKeyRelatedField lookup
            teachers_qs = User.all_objects.filter(
                tenant=request.tenant,
                is_deleted=False,  # Explicit soft-delete filter
            ).exclude(
                role__in=['SUPER_ADMIN', 'SCHOOL_ADMIN'],
            )
            # Use set_queryset for SafePrimaryKeyRelatedField
            if hasattr(self.fields['assigned_teachers'], 'set_queryset'):
                self.fields['assigned_teachers'].set_queryset(teachers_qs)
            else:
                self.fields['assigned_teachers'].queryset = teachers_qs
        else:
            # If no tenant in context, make fields optional to avoid validation errors
            # The view decorator @tenant_required will catch missing tenant before serializer
            self.fields['assigned_groups'].queryset = TeacherGroup.objects.none()
            self.fields['assigned_teachers'].queryset = User.objects.none()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'slug', 'description', 'thumbnail',
            'is_mandatory', 'deadline', 'estimated_hours',
            'assigned_to_all', 'assigned_groups', 'assigned_teachers',
            'is_published', 'is_active', 'modules', 'stats',
            'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'slug', 'created_by', 'created_at', 'updated_at']
    
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
        
        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update assignments
        if assigned_groups is not None:
            instance.assigned_groups.set(assigned_groups)
        if assigned_teachers is not None:
            instance.assigned_teachers.set(assigned_teachers)
        
        # Only notify if course is published
        if instance.is_published:
            request = self.context.get('request')
            tenant = request.tenant if request else instance.tenant
            
            # Get new assignments
            new_group_ids = set(instance.assigned_groups.values_list('id', flat=True)) if assigned_groups is not None else old_group_ids
            new_teacher_ids = set(instance.assigned_teachers.values_list('id', flat=True)) if assigned_teachers is not None else old_teacher_ids
            
            # Notify newly assigned teachers
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
