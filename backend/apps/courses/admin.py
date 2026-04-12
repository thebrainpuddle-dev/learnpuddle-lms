# apps/courses/admin.py

from django.contrib import admin
from .models import TeacherGroup, Course, Module, Content
from .maic_models import TenantAIConfig, MAICClassroom


class TenantFilteredAdmin(admin.ModelAdmin):
    """
    Base admin class that filters querysets by tenant.
    """
    
    def get_queryset(self, request):
        """
        Filter by tenant for non-superusers.
        """
        qs = super().get_queryset(request)
        
        if request.user.is_superuser:
            return qs
        
        # Filter by user's tenant
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(tenant=request.user.tenant)
        
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """
        Auto-set tenant on save.
        """
        if hasattr(obj, 'tenant_id') and not obj.tenant_id:
            if hasattr(request.user, 'tenant') and request.user.tenant:
                obj.tenant = request.user.tenant
        
        super().save_model(request, obj, form, change)


@admin.register(TeacherGroup)
class TeacherGroupAdmin(TenantFilteredAdmin):
    list_display = ['name', 'tenant', 'group_type', 'created_at']
    list_filter = ['group_type', 'tenant']
    search_fields = ['name']


@admin.register(Course)
class CourseAdmin(TenantFilteredAdmin):
    list_display = ['title', 'tenant', 'is_mandatory', 'is_published', 'deadline', 'created_at']
    list_filter = ['is_mandatory', 'is_published', 'tenant']
    search_fields = ['title', 'description']
    readonly_fields = ['slug', 'created_at', 'updated_at']
    
    def save_model(self, request, obj, form, change):
        """
        Auto-set tenant and created_by.
        """
        if not obj.tenant_id:
            if hasattr(request.user, 'tenant') and request.user.tenant:
                obj.tenant = request.user.tenant
        
        if not obj.created_by_id:
            obj.created_by = request.user
        
        super().save_model(request, obj, form, change)


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'order', 'created_at']
    list_filter = ['course']
    ordering = ['course', 'order']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(course__tenant=request.user.tenant)
        return qs.none()


@admin.register(Content)
class ContentAdmin(admin.ModelAdmin):
    list_display = ['title', 'module', 'content_type', 'order']
    list_filter = ['content_type']
    ordering = ['module', 'order']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(module__course__tenant=request.user.tenant)
        return qs.none()


# --- MAIC Admin -----------------------------------------------------------

@admin.register(TenantAIConfig)
class TenantAIConfigAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'llm_provider', 'llm_model', 'tts_provider', 'maic_enabled', 'updated_at']
    list_filter = ['llm_provider', 'tts_provider', 'maic_enabled']
    readonly_fields = ['id', 'created_at', 'updated_at']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(tenant=request.user.tenant)
        return qs.none()


@admin.register(MAICClassroom)
class MAICClassroomAdmin(TenantFilteredAdmin):
    list_display = ['title', 'tenant', 'creator', 'status', 'is_public', 'scene_count', 'created_at']
    list_filter = ['status', 'is_public', 'tenant']
    search_fields = ['title', 'topic']
    readonly_fields = ['id', 'config', 'created_at', 'updated_at']