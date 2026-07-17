from django.core.management.base import BaseCommand

from apps.billing.models import SubscriptionPlan


PLAN_SEEDS = [
    {
        "plan_code": "FREE",
        "defaults": {
            "name": "Free",
            "description": "Get started with the basics — perfect for small teams exploring the platform.",
            "price_monthly_cents": 0,
            "price_yearly_cents": 0,
            "currency": "usd",
            "is_active": True,
            "is_recommended": False,
            "is_custom_pricing": False,
            "sort_order": 0,
            "features_json": [
                "Up to 10 teachers",
                "Up to 5 courses",
                "500 MB storage",
                "Basic reminders",
                "Teacher groups",
            ],
            "ai_entitlements": {
                "monthly_generations": 0,
                "max_concurrent_generations": 0,
                "storage_bytes": 0,
                "max_classrooms_per_teacher": 0,
                "student_generation_enabled": False,
                "high_cost_modalities": [],
            },
        },
    },
    {
        "plan_code": "STARTER",
        "defaults": {
            "name": "Starter",
            "description": "Everything a growing school needs — video uploads, transcripts, and custom branding.",
            "price_monthly_cents": 2900,
            "price_yearly_cents": 29000,
            "currency": "usd",
            "is_active": True,
            "is_recommended": False,
            "is_custom_pricing": False,
            "sort_order": 1,
            "features_json": [
                "Up to 50 teachers",
                "Up to 20 courses",
                "5 GB storage",
                "Video uploads",
                "Transcripts",
                "Custom branding",
                "Teacher authoring",
                "Teacher groups",
                "Reminders",
            ],
            "ai_entitlements": {
                "monthly_generations": 25,
                "max_concurrent_generations": 1,
                "storage_bytes": 5368709120,
                "max_classrooms_per_teacher": 20,
                "student_generation_enabled": False,
                "high_cost_modalities": [],
            },
        },
    },
    {
        "plan_code": "PRO",
        "defaults": {
            "name": "Professional",
            "description": "Full-featured plan for serious institutions — includes API access, certificates, and advanced analytics.",
            "price_monthly_cents": 7900,
            "price_yearly_cents": 79000,
            "currency": "usd",
            "is_active": True,
            "is_recommended": True,
            "is_custom_pricing": False,
            "sort_order": 2,
            "features_json": [
                "Up to 200 teachers",
                "Up to 100 courses",
                "50 GB storage",
                "Video uploads",
                "Transcripts",
                "Auto-generated quizzes",
                "Certificates",
                "Custom branding",
                "Reports & export",
                "Teacher authoring",
                "Teacher groups",
                "Reminders",
                "API access",
            ],
            "ai_entitlements": {
                "monthly_generations": 200,
                "max_concurrent_generations": 3,
                "storage_bytes": 53687091200,
                "max_classrooms_per_teacher": 100,
                "student_generation_enabled": False,
                "high_cost_modalities": ["image"],
            },
        },
    },
    {
        "plan_code": "ENTERPRISE",
        "defaults": {
            "name": "Enterprise",
            "description": "Tailored for large organisations — unlimited usage, SSO, custom domains, and dedicated support.",
            "price_monthly_cents": 0,
            "price_yearly_cents": 0,
            "currency": "usd",
            "is_active": True,
            "is_recommended": False,
            "is_custom_pricing": True,
            "sort_order": 3,
            "features_json": [
                "Unlimited teachers",
                "Unlimited courses",
                "500 GB storage",
                "Video uploads",
                "Transcripts",
                "Auto-generated quizzes",
                "Certificates",
                "Custom branding",
                "Reports & export",
                "Teacher authoring",
                "Teacher groups",
                "Reminders",
                "API access",
                "SSO / SAML integration",
                "Custom domain",
                "Two-factor authentication",
                "Dedicated support",
            ],
            "ai_entitlements": {
                "monthly_generations": 0,
                "max_concurrent_generations": 10,
                "storage_bytes": 536870912000,
                "max_classrooms_per_teacher": 0,
                "student_generation_enabled": True,
                "high_cost_modalities": ["image", "video"],
            },
        },
    },
]


class Command(BaseCommand):
    help = "Seed the SubscriptionPlan table with the four standard plans (FREE, STARTER, PRO, ENTERPRISE)."

    def handle(self, *args, **options):
        created_count = 0
        updated_count = 0

        for seed in PLAN_SEEDS:
            _, created = SubscriptionPlan.objects.update_or_create(
                plan_code=seed["plan_code"],
                defaults=seed["defaults"],
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  Created plan: {seed['plan_code']}"))
            else:
                updated_count += 1
                self.stdout.write(f"  Updated plan: {seed['plan_code']}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone — {created_count} created, {updated_count} updated."
            )
        )
