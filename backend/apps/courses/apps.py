from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.courses"

    def ready(self):
        # Import learning_path_models to ensure Django discovers them for migrations
        import apps.courses.learning_path_models  # noqa: F401

        # Connect chatbot auto-ingestion signals
        from django.db.models.signals import post_save, m2m_changed
        from apps.courses.models import Content
        from apps.courses.chatbot_models import AIChatbot
        from apps.courses import chatbot_signals

        post_save.connect(
            chatbot_signals.on_content_created_or_updated,
            sender=Content,
            dispatch_uid='chatbot_auto_ingest_content',
        )
        m2m_changed.connect(
            chatbot_signals.on_chatbot_sections_changed,
            sender=AIChatbot.sections.through,
            dispatch_uid='chatbot_auto_ingest_sections',
        )

        # Connect file cleanup signal for Content deletion
        import apps.courses.signals  # noqa: F401
