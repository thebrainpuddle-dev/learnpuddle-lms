# apps/progress/admin.py

from django.contrib import admin
from .models import TeacherProgress, Assignment, AssignmentSubmission
from .skills_models import Skill, CourseSkill, TeacherSkill
from .certification_models import CertificationType, TeacherCertification


@admin.register(TeacherProgress)
class TeacherProgressAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'course', 'status', 'progress_percentage', 'last_accessed']
    list_filter = ['status', 'course']
    search_fields = ['teacher__email', 'course__title']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(course__tenant=request.user.tenant)
        return qs.none()


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'due_date', 'max_score']
    list_filter = ['course', 'is_mandatory']
    search_fields = ['title']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(course__tenant=request.user.tenant)
        return qs.none()


@admin.register(AssignmentSubmission)
class AssignmentSubmissionAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'assignment', 'status', 'score', 'submitted_at']
    list_filter = ['status', 'assignment']
    search_fields = ['teacher__email', 'assignment__title']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(assignment__course__tenant=request.user.tenant)
        return qs.none()


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'level_required', 'tenant', 'created_at']
    list_filter = ['category', 'level_required']
    search_fields = ['name', 'description']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(tenant=request.user.tenant)
        return qs.none()


@admin.register(CourseSkill)
class CourseSkillAdmin(admin.ModelAdmin):
    list_display = ['course', 'skill', 'level_taught', 'created_at']
    list_filter = ['level_taught']
    search_fields = ['course__title', 'skill__name']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(course__tenant=request.user.tenant)
        return qs.none()


@admin.register(TeacherSkill)
class TeacherSkillAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'skill', 'current_level', 'target_level', 'last_assessed']
    list_filter = ['current_level', 'target_level']
    search_fields = ['teacher__email', 'skill__name']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(tenant=request.user.tenant)
        return qs.none()


@admin.register(CertificationType)
class CertificationTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'validity_months', 'auto_renew', 'tenant', 'created_at']
    list_filter = ['auto_renew', 'validity_months']
    search_fields = ['name', 'description']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(tenant=request.user.tenant)
        return qs.none()


@admin.register(TeacherCertification)
class TeacherCertificationAdmin(admin.ModelAdmin):
    list_display = ['teacher', 'certification_type', 'status', 'issued_at', 'expires_at']
    list_filter = ['status', 'certification_type']
    search_fields = ['teacher__email', 'certification_type__name']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        if hasattr(request.user, 'tenant') and request.user.tenant:
            return qs.filter(tenant=request.user.tenant)
        return qs.none()