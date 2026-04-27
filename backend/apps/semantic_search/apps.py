from django.apps import AppConfig


class SemanticSearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.semantic_search"
    verbose_name = "Semantic Search (pgvector)"

    def ready(self):
        # Import signal handlers to connect them.
        from . import signals  # noqa: F401

        # Connect soft_deleted signal receivers (TASK-057b).
        # These are connected here (not via @receiver decorator) because the
        # soft_deleted signal lives in apps.courses and we must not import
        # from apps.courses at module level in this app.
        from .signals import connect_soft_delete_receivers
        connect_soft_delete_receivers()

        # Register system checks (pgvector extension presence).
        from . import checks  # noqa: F401
