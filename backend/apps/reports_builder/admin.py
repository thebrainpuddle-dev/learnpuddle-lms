from django.contrib import admin

from .models import ReportDefinition, ReportRun, ReportSchedule


@admin.register(ReportDefinition)
class ReportDefinitionAdmin(admin.ModelAdmin):
    list_display = ["name", "data_source", "tenant", "created_by", "created_at", "is_soft_deleted"]
    list_filter = ["data_source", "is_soft_deleted", "tenant"]
    search_fields = ["name", "description"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(ReportSchedule)
class ReportScheduleAdmin(admin.ModelAdmin):
    list_display = ["definition", "cadence", "run_at_hour", "enabled", "last_run_status", "last_run_at"]
    list_filter = ["cadence", "enabled", "last_run_status"]
    readonly_fields = ["id", "last_run_at", "last_run_status", "created_at", "updated_at"]


@admin.register(ReportRun)
class ReportRunAdmin(admin.ModelAdmin):
    list_display = ["id", "definition", "run_by", "status", "row_count", "started_at", "finished_at"]
    list_filter = ["status", "tenant"]
    readonly_fields = ["id", "started_at", "finished_at", "artifact_sha256"]
    search_fields = ["id", "error"]
