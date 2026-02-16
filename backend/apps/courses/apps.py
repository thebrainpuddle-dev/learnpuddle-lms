from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.courses"

    def ready(self):
        # Import learning_path_models to ensure Django discovers them for migrations
        import apps.courses.learning_path_models  # noqa: F401
