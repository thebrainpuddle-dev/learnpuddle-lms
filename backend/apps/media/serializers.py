# apps/media/serializers.py

from rest_framework import serializers
from .models import MediaAsset


class MediaAssetSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            'id', 'title', 'media_type',
            'file_url', 'file_name', 'file_size', 'mime_type',
            'duration', 'thumbnail_url',
            'tags', 'is_active',
            'uploaded_by', 'uploaded_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by:
            return obj.uploaded_by.get_full_name()
        return ''

    def get_file_url(self, obj):
        """
        Return the file URL. For S3 storage, generates a signed URL that
        the browser can access directly without auth headers.
        """
        from django.conf import settings
        from django.core.files.storage import default_storage
        
        # For LINK type, return the external URL as-is
        if obj.media_type == 'LINK' and obj.file_url:
            return obj.file_url
        
        # For uploaded files, generate appropriate URL
        if obj.file:
            file_path = obj.file.name
            storage_backend = getattr(settings, 'STORAGE_BACKEND', 'local').lower()
            
            if storage_backend == 's3':
                # Generate signed URL for S3/Spaces (1 hour expiry)
                try:
                    storage = default_storage
                    client = storage.connection.meta.client
                    bucket_name = storage.bucket_name
                    
                    signed_url = client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': bucket_name, 'Key': file_path},
                        ExpiresIn=3600  # 1 hour
                    )
                    return signed_url
                except Exception:
                    # Fallback to direct URL if signing fails
                    return obj.file.url
            else:
                # Local storage: use Django media URL
                request = self.context.get('request')
                if request:
                    return request.build_absolute_uri(obj.file.url)
                return obj.file.url
        
        # Fallback to stored file_url if no file object
        url = obj.file_url or ''
        if url and not url.startswith('http'):
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(url)
        return url


class MediaAssetCreateSerializer(serializers.ModelSerializer):
    file = serializers.FileField(required=False, allow_null=True)
    is_active = serializers.BooleanField(default=True, required=False)

    class Meta:
        model = MediaAsset
        fields = ['title', 'media_type', 'file', 'file_url', 'tags', 'is_active']

    def create(self, validated_data):
        request = self.context['request']
        tenant = request.tenant
        user = request.user

        file_obj = validated_data.pop('file', None)
        file_url = validated_data.get('file_url', '') or ''
        media_type = validated_data['media_type']

        if media_type == 'LINK':
            if not file_url:
                raise serializers.ValidationError({'file_url': 'URL is required for link type.'})
        elif file_obj:
            validated_data['file'] = file_obj
            validated_data['file_name'] = getattr(file_obj, 'name', '') or ''
            validated_data['file_size'] = getattr(file_obj, 'size', None)
            validated_data['mime_type'] = getattr(file_obj, 'content_type', '') or ''
        elif file_url:
            # Allow creating a DOCUMENT/VIDEO asset from an existing URL
            # (e.g. file already uploaded via /uploads/content-file/).
            # Extract filename from the URL path for searchability.
            from urllib.parse import urlparse
            path = urlparse(file_url).path
            validated_data['file_name'] = path.rsplit('/', 1)[-1] if '/' in path else ''
        else:
            raise serializers.ValidationError(
                {'file': 'File upload or file_url is required for video or document type.'}
            )

        # Don't store file_url for uploaded files - it's generated dynamically
        # by the serializer to ensure proper auth routing
        if file_obj and 'file_url' in validated_data:
            del validated_data['file_url']
        
        asset = MediaAsset.objects.create(
            tenant=tenant,
            uploaded_by=user,
            **validated_data,
        )

        return asset
