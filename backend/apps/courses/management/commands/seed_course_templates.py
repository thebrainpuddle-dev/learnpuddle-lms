"""
Seed 3 sample published CourseTemplates. Idempotent: re-running leaves the
same 3 rows in place.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.courses.template_clone import BLUEPRINT_SCHEMA_VERSION
from apps.courses.template_models import CourseTemplate


def _content(title: str, content_type: str = "TEXT", order: int = 1) -> dict:
    return {
        "title": title,
        "content_type": content_type,
        "order": order,
        "text_content": "" if content_type == "TEXT" else "",
        "file_url": "",
        "duration": None,
        "is_mandatory": True,
        "meta_json": {},
    }


def _module(title: str, order: int, contents: list[dict]) -> dict:
    return {
        "title": title,
        "description": "",
        "order": order,
        "contents": contents,
    }


def _blueprint(course_title: str, hours: int, modules: list[dict]) -> dict:
    return {
        "schema_version": BLUEPRINT_SCHEMA_VERSION,
        "course": {
            "title": course_title,
            "description": "",
            "estimated_hours": hours,
            "is_mandatory": False,
        },
        "modules": modules,
    }


TEMPLATES = [
    {
        "slug": "ib-pyp-unit-planning-essentials",
        "title": "IB PYP Unit Planning Essentials",
        "description": (
            "A foundational starter for IB PYP educators: framing lines of "
            "inquiry, concept-driven learning, and assessment touchpoints."
        ),
        "category": "IB_PYP",
        "language": "en",
        "estimated_hours": 12,
        "level": "BEGINNER",
        "thumbnail_url": "",
        "blueprint": _blueprint(
            "IB PYP Unit Planning Essentials",
            12,
            [
                _module("Orientation to the PYP framework", 1, [
                    _content("Welcome & outcomes", "TEXT", 1),
                    _content("PYP at a glance (video)", "VIDEO", 2),
                    _content("Reflection prompts", "DOCUMENT", 3),
                ]),
                _module("Transdisciplinary themes", 2, [
                    _content("The six themes", "TEXT", 1),
                    _content("Case study", "DOCUMENT", 2),
                    _content("Unit brainstorm worksheet", "DOCUMENT", 3),
                ]),
                _module("Lines of inquiry", 3, [
                    _content("Crafting lines of inquiry", "TEXT", 1),
                    _content("Walkthrough video", "VIDEO", 2),
                    _content("Practice activity", "TEXT", 3),
                ]),
                _module("Assessment & reflection", 4, [
                    _content("Formative tools", "TEXT", 1),
                    _content("Summative capstone", "DOCUMENT", 2),
                    _content("Closing quiz", "TEXT", 3),
                ]),
            ],
        ),
    },
    {
        "slug": "differentiated-instruction-101",
        "title": "Differentiated Instruction 101",
        "description": (
            "Practical strategies for tailoring content, process, and product "
            "to diverse learners."
        ),
        "category": "TEACHING_SKILLS",
        "language": "en",
        "estimated_hours": 6,
        "level": "INTERMEDIATE",
        "thumbnail_url": "",
        "blueprint": _blueprint(
            "Differentiated Instruction 101",
            6,
            [
                _module("Foundations of differentiation", 1, [
                    _content("What is differentiation?", "TEXT", 1),
                    _content("Intro video", "VIDEO", 2),
                    _content("Self-audit checklist", "DOCUMENT", 3),
                ]),
                _module("Strategies that work", 2, [
                    _content("Tiered tasks", "TEXT", 1),
                    _content("Flexible grouping", "TEXT", 2),
                    _content("Choice boards (template)", "DOCUMENT", 3),
                ]),
                _module("Putting it together", 3, [
                    _content("Lesson redesign walkthrough", "VIDEO", 1),
                    _content("Peer-review rubric", "DOCUMENT", 2),
                    _content("Knowledge check", "TEXT", 3),
                ]),
            ],
        ),
    },
    {
        "slug": "teacher-wellbeing-foundations",
        "title": "Teacher Wellbeing Foundations",
        "description": (
            "Simple, science-backed habits to protect energy and prevent "
            "burnout over a school year."
        ),
        "category": "WELLBEING",
        "language": "en",
        "estimated_hours": 4,
        "level": "BEGINNER",
        "thumbnail_url": "",
        "blueprint": _blueprint(
            "Teacher Wellbeing Foundations",
            4,
            [
                _module("Protecting your energy", 1, [
                    _content("Why wellbeing matters", "TEXT", 1),
                    _content("Grounding exercise (audio/video)", "VIDEO", 2),
                ]),
                _module("Everyday habits", 2, [
                    _content("Morning + evening routines", "TEXT", 1),
                    _content("Reflection journal (template)", "DOCUMENT", 2),
                ]),
            ],
        ),
    },
]


class Command(BaseCommand):
    help = "Seed 3 published CourseTemplates. Idempotent."

    def handle(self, *args, **options):
        created = 0
        updated = 0
        for spec in TEMPLATES:
            defaults = {
                "title": spec["title"],
                "description": spec["description"],
                "category": spec["category"],
                "language": spec["language"],
                "estimated_hours": spec["estimated_hours"],
                "level": spec["level"],
                "thumbnail_url": spec["thumbnail_url"],
                "blueprint_json": spec["blueprint"],
                "is_published": True,
            }
            obj, was_created = CourseTemplate.objects.get_or_create(
                slug=spec["slug"],
                defaults=defaults,
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(
                    f"Created template: {obj.slug}"
                ))
            else:
                # Keep idempotency strong: refresh the blueprint + metadata so
                # edits to this seed file propagate without creating dupes.
                dirty = False
                for field, value in defaults.items():
                    if getattr(obj, field) != value:
                        setattr(obj, field, value)
                        dirty = True
                if dirty:
                    obj.save()
                    updated += 1
                    self.stdout.write(self.style.WARNING(
                        f"Updated template: {obj.slug}"
                    ))
                else:
                    self.stdout.write(f"Unchanged: {obj.slug}")
        self.stdout.write(self.style.SUCCESS(
            f"Done. created={created}, updated={updated}, total={CourseTemplate.objects.count()}"
        ))
