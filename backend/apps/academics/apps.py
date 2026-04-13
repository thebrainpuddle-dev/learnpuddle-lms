# apps/academics/apps.py
from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.academics'
    verbose_name = 'Academics'

    def ready(self):
        # Import post_save / pre_save signal receivers
        from apps.academics import signals  # noqa: F401

        # Connect m2m_changed signals programmatically — the through-model
        # class must be resolved at runtime, not via string reference.
        from django.db.models.signals import m2m_changed
        from apps.courses.models import Course

        m2m_changed.connect(
            signals.on_course_targets_changed,
            sender=Course.target_sections.through,
            dispatch_uid='academics_target_sections_changed',
        )
        m2m_changed.connect(
            signals.on_course_targets_changed,
            sender=Course.target_grades.through,
            dispatch_uid='academics_target_grades_changed',
        )
