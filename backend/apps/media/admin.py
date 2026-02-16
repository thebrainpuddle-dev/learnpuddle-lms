# apps/media/admin.py

from django.contrib import admin
from .models import MediaAsset


@admin.register(MediaAsset)
class MediaAssetAdmin(admin.ModelAdmin):
    list_display = ['title', 'media_type', 'tenant', 'is_active', 'created_at']
    list_filter = ['media_type', 'is_active', 'tenant']
    search_fields = ['title', 'file_name']
