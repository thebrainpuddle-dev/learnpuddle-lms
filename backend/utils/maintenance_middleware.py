from django.http import JsonResponse


class MaintenanceModeWriteBlockMiddleware:
    """
    Blocks tenant write requests during tenant maintenance windows.
    Super-admin requests are always allowed.
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
    EXEMPT_PATH_PREFIXES = (
        "/health/",
        "/admin/",
        "/api/super-admin/",
        "/api/v1/super-admin/",
        "/api/users/auth/",
        "/api/v1/users/auth/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in self.SAFE_METHODS:
            return self.get_response(request)

        if any(request.path.startswith(prefix) for prefix in self.EXEMPT_PATH_PREFIXES):
            return self.get_response(request)

        user = getattr(request, "user", None)
        if user and user.is_authenticated and getattr(user, "role", "") == "SUPER_ADMIN":
            return self.get_response(request)

        tenant = getattr(request, "tenant", None)
        if tenant and getattr(tenant, "maintenance_mode_enabled", False):
            return JsonResponse(
                {
                    "error": "Tenant is in maintenance mode. Writes are temporarily disabled.",
                    "maintenance_mode": True,
                    "maintenance_ends_at": tenant.maintenance_mode_ends_at.isoformat()
                    if tenant.maintenance_mode_ends_at
                    else None,
                },
                status=503,
            )

        return self.get_response(request)
