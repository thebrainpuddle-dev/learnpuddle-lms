# utils/media_xframe_middleware.py

from django.conf import settings


class MediaXFrameExemptMiddleware:
    """
    Remove X-Frame-Options for media file responses so they can be
    embedded in iframes (e.g. PDF preview, video preview).
    Must be placed *after* XFrameOptionsMiddleware in MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        media_url = getattr(settings, "MEDIA_URL", "/media/")
        if request.path.startswith(media_url):
            response.headers.pop("X-Frame-Options", None)
        return response
