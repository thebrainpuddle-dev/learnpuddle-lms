# utils/cdn.py
"""
CDN utilities for serving media assets efficiently.

Provides helpers for:
- Generating CDN URLs for media files
- Image transformation/resizing URLs (e.g., Cloudflare Images, Imgix)
- Video streaming URLs with signed tokens
"""

import hashlib
import time
from typing import Optional
from urllib.parse import urljoin, urlparse
from django.conf import settings


def get_cdn_url(path: str) -> str:
    """
    Get CDN URL for a media path.
    
    If CDN is not configured, returns the standard media URL.
    
    Args:
        path: Relative path to the media file (e.g., 'videos/abc123/manifest.m3u8')
    
    Returns:
        Full URL to the media file (via CDN if configured)
    """
    if not path:
        return ''
    
    # Remove leading slash if present
    path = path.lstrip('/')
    
    if settings.CDN_ENABLED:
        return f"https://{settings.CDN_DOMAIN}/media/{path}"
    
    return urljoin(settings.MEDIA_URL, path)


def get_image_url(
    path: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    quality: int = 80,
    format: str = 'auto',
) -> str:
    """
    Get optimized image URL with optional transformations.
    
    Supports Cloudflare Images URL format. For other CDNs, adjust the
    query parameters accordingly.
    
    Args:
        path: Path to the original image
        width: Desired width in pixels
        height: Desired height in pixels
        quality: JPEG quality (1-100)
        format: Output format (auto, webp, avif, jpeg, png)
    
    Returns:
        URL with transformation parameters
    """
    base_url = get_cdn_url(path)
    
    if not settings.CDN_ENABLED:
        return base_url
    
    # Build transformation parameters
    # Format for Cloudflare Images: /cdn-cgi/image/width=X,height=Y,quality=Q,format=F/path
    params = []
    if width:
        params.append(f"width={width}")
    if height:
        params.append(f"height={height}")
    if quality != 80:
        params.append(f"quality={quality}")
    if format != 'auto':
        params.append(f"format={format}")
    
    if params:
        # Cloudflare Images format
        transform = ','.join(params)
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}/cdn-cgi/image/{transform}{parsed.path}"
    
    return base_url


def get_video_streaming_url(
    video_id: str,
    manifest_name: str = 'manifest.m3u8',
    expires_in: int = 3600,
) -> str:
    """
    Get HLS streaming URL for a video.
    
    For production with CloudFront, this would include a signed URL.
    
    Args:
        video_id: UUID of the video
        manifest_name: HLS manifest filename
        expires_in: URL expiration time in seconds
    
    Returns:
        Streaming URL (signed if using CloudFront signed URLs)
    """
    path = f"videos/{video_id}/{manifest_name}"
    base_url = get_cdn_url(path)
    
    # For CloudFront signed URLs, you would add signature here
    # This is a placeholder for the signing logic
    if settings.CDN_ENABLED and hasattr(settings, 'CLOUDFRONT_KEY_ID'):
        return sign_cloudfront_url(base_url, expires_in)
    
    return base_url


def sign_cloudfront_url(url: str, expires_in: int = 3600) -> str:
    """
    Sign a CloudFront URL for secure access.
    
    Note: This is a simplified implementation. For production,
    use the boto3 CloudFront signer or django-cloudfront.
    
    Args:
        url: URL to sign
        expires_in: Expiration time in seconds
    
    Returns:
        Signed URL with policy and signature
    """
    # Placeholder - implement actual CloudFront signing
    # For now, return URL with expiration timestamp
    expires = int(time.time()) + expires_in
    return f"{url}?Expires={expires}"


def get_thumbnail_sizes() -> dict:
    """
    Get standard thumbnail size configurations.
    
    Returns dictionary of size name to dimensions.
    """
    return {
        'xs': {'width': 64, 'height': 64},
        'sm': {'width': 150, 'height': 150},
        'md': {'width': 300, 'height': 200},
        'lg': {'width': 600, 'height': 400},
        'xl': {'width': 1200, 'height': 800},
    }


def get_responsive_image_srcset(
    path: str,
    sizes: list[int] = [320, 640, 960, 1280, 1920],
) -> str:
    """
    Generate srcset attribute for responsive images.
    
    Args:
        path: Path to the original image
        sizes: List of widths to generate
    
    Returns:
        srcset string for use in <img> tag
    """
    srcset_parts = []
    for size in sizes:
        url = get_image_url(path, width=size)
        srcset_parts.append(f"{url} {size}w")
    
    return ', '.join(srcset_parts)
