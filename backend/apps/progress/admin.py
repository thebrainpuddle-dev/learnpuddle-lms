# apps/progress/admin.py

from django.contrib import admin
from .models import TeacherProgress, Assignment, AssignmentSubmission


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