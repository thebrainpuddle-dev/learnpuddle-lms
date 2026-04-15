# apps/tenants/management/commands/seed_keystone_demo.py
#
# Seeds competency skills, gamification badges, and sample XP/leaderboard
# data for the Keystone International School tenant (subdomain: "keystone").
#
# Usage:
#   python manage.py seed_keystone_demo
#
# Idempotent — safe to run multiple times (uses get_or_create throughout).

import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.progress.skills_models import Skill, TeacherSkill
from apps.progress.gamification_models import (
    BadgeDefinition,
    GamificationConfig,
    LeaderboardSnapshot,
    TeacherBadge,
    TeacherStreak,
    TeacherXPSummary,
    XPTransaction,
)


# ---------------------------------------------------------------------------
# Skill definitions (IB / Cambridge framework for Keystone)
# ---------------------------------------------------------------------------

SKILLS = [
    # Approaches to Teaching (IB ATT)
    ("Approaches to Teaching", "Inquiry-Based Teaching", 4),
    ("Approaches to Teaching", "Conceptual Understanding", 4),
    ("Approaches to Teaching", "Local & Global Contexts", 3),
    ("Approaches to Teaching", "Collaborative Teaching", 4),
    ("Approaches to Teaching", "Differentiation & Inclusion", 4),
    ("Approaches to Teaching", "Assessment-Informed Teaching", 4),
    # Approaches to Learning (IB ATL)
    ("Approaches to Learning", "Thinking Skills Development", 4),
    ("Approaches to Learning", "Communication Skills Development", 4),
    ("Approaches to Learning", "Social Skills Development", 3),
    ("Approaches to Learning", "Self-Management Skills Development", 3),
    ("Approaches to Learning", "Research Skills Development", 4),
    # Pedagogical Practice
    ("Pedagogical Practice", "Project-Based Learning", 4),
    ("Pedagogical Practice", "Reggio Emilia Approaches", 3),
    ("Pedagogical Practice", "Technology Integration", 3),
    ("Pedagogical Practice", "Curriculum Design", 4),
    # Professional Growth
    ("Professional Growth", "Reflective Practice", 4),
    ("Professional Growth", "Action Research", 3),
    ("Professional Growth", "Mentoring & Coaching", 3),
    ("Professional Growth", "Professional Learning Communities", 3),
]


# ---------------------------------------------------------------------------
# Badge definitions
# ---------------------------------------------------------------------------

BADGES = [
    # Milestone badges
    {
        "name": "First Steps",
        "description": "Earned your first 50 XP on your professional development journey.",
        "category": "milestone",
        "criteria_type": "xp_threshold",
        "criteria_value": 50,
        "color": "#3b82f6",
        "icon": "\U0001f3af",  # target emoji
        "sort_order": 1,
    },
    {
        "name": "Century Club",
        "description": "Reached 100 XP — a true commitment to growth.",
        "category": "milestone",
        "criteria_type": "xp_threshold",
        "criteria_value": 100,
        "color": "#6366f1",
        "icon": "\U0001f4af",  # 100 emoji
        "sort_order": 2,
    },
    {
        "name": "Knowledge Seeker",
        "description": "Accumulated 500 XP through dedicated learning.",
        "category": "milestone",
        "criteria_type": "xp_threshold",
        "criteria_value": 500,
        "color": "#8b5cf6",
        "icon": "\U0001f4da",  # books emoji
        "sort_order": 3,
    },
    {
        "name": "Master Educator",
        "description": "Reached the 1000 XP milestone — a master of professional development.",
        "category": "milestone",
        "criteria_type": "xp_threshold",
        "criteria_value": 1000,
        "color": "#7c3aed",
        "icon": "\U0001f393",  # graduation cap emoji
        "sort_order": 4,
    },
    # Completion badges
    {
        "name": "Course Pioneer",
        "description": "Completed your very first course.",
        "category": "completion",
        "criteria_type": "courses_completed",
        "criteria_value": 1,
        "color": "#10b981",
        "icon": "\U0001f331",  # seedling emoji
        "sort_order": 10,
    },
    {
        "name": "Curriculum Explorer",
        "description": "Completed 3 courses — exploring the curriculum landscape.",
        "category": "completion",
        "criteria_type": "courses_completed",
        "criteria_value": 3,
        "color": "#059669",
        "icon": "\U0001f9ed",  # compass emoji
        "sort_order": 11,
    },
    {
        "name": "PD Champion",
        "description": "Completed 5 courses — a champion of professional development.",
        "category": "completion",
        "criteria_type": "courses_completed",
        "criteria_value": 5,
        "color": "#047857",
        "icon": "\U0001f3c6",  # trophy emoji
        "sort_order": 12,
    },
    # Streak badges
    {
        "name": "Consistent Learner",
        "description": "Maintained a 7-day learning streak.",
        "category": "streak",
        "criteria_type": "streak_days",
        "criteria_value": 7,
        "color": "#f59e0b",
        "icon": "\U0001f525",  # fire emoji
        "sort_order": 20,
    },
    {
        "name": "Dedicated Educator",
        "description": "Maintained an impressive 30-day learning streak.",
        "category": "streak",
        "criteria_type": "streak_days",
        "criteria_value": 30,
        "color": "#d97706",
        "icon": "\u26a1",  # lightning emoji
        "sort_order": 21,
    },
    # Skill badges (manual award)
    {
        "name": "IB Practitioner",
        "description": "Demonstrated mastery in IB teaching approaches.",
        "category": "skill",
        "criteria_type": "manual",
        "criteria_value": 0,
        "color": "#0ea5e9",
        "icon": "\U0001f30d",  # globe emoji
        "sort_order": 30,
    },
    {
        "name": "Inquiry Champion",
        "description": "Led outstanding inquiry-based learning initiatives.",
        "category": "skill",
        "criteria_type": "manual",
        "criteria_value": 0,
        "color": "#06b6d4",
        "icon": "\U0001f52c",  # microscope emoji
        "sort_order": 31,
    },
    {
        "name": "Reflective Leader",
        "description": "Exemplary reflective practice and peer mentoring.",
        "category": "skill",
        "criteria_type": "manual",
        "criteria_value": 0,
        "color": "#14b8a6",
        "icon": "\U0001fa9e",  # mirror emoji
        "sort_order": 32,
    },
]


# ---------------------------------------------------------------------------
# Priya Sharma skill levels (strong IB, moderate pedagogy)
# ---------------------------------------------------------------------------

PRIYA_SKILL_LEVELS = {
    # Approaches to Teaching — strong IB (3-5)
    "Inquiry-Based Teaching": 5,
    "Conceptual Understanding": 4,
    "Local & Global Contexts": 3,
    "Collaborative Teaching": 4,
    "Differentiation & Inclusion": 3,
    "Assessment-Informed Teaching": 4,
    # Approaches to Learning — strong IB (3-5)
    "Thinking Skills Development": 4,
    "Communication Skills Development": 5,
    "Social Skills Development": 3,
    "Self-Management Skills Development": 3,
    "Research Skills Development": 4,
    # Pedagogical Practice — moderate (2-4)
    "Project-Based Learning": 4,
    "Reggio Emilia Approaches": 2,
    "Technology Integration": 3,
    "Curriculum Design": 4,
    # Professional Growth — moderate (2-4)
    "Reflective Practice": 4,
    "Action Research": 3,
    "Mentoring & Coaching": 2,
    "Professional Learning Communities": 3,
}


# ---------------------------------------------------------------------------
# XP transaction templates for Priya
# ---------------------------------------------------------------------------

PRIYA_XP_TRANSACTIONS = [
    {
        "xp_amount": 50,
        "reason": "course_completion",
        "description": "Completed 'IB Approaches to Teaching' course",
        "days_ago": 45,
    },
    {
        "xp_amount": 50,
        "reason": "course_completion",
        "description": "Completed 'Assessment for Learning' course",
        "days_ago": 30,
    },
    {
        "xp_amount": 10,
        "reason": "content_completion",
        "description": "Completed module: Inquiry Cycle Design",
        "days_ago": 28,
    },
    {
        "xp_amount": 15,
        "reason": "quiz_submission",
        "description": "Quiz: Differentiation Strategies — scored 92%",
        "days_ago": 22,
    },
    {
        "xp_amount": 15,
        "reason": "assignment_submission",
        "description": "Submitted unit plan: Interdisciplinary Mathematics",
        "days_ago": 15,
    },
    {
        "xp_amount": 10,
        "reason": "content_completion",
        "description": "Completed module: Technology-Enhanced Learning",
        "days_ago": 10,
    },
    {
        "xp_amount": 15,
        "reason": "quiz_submission",
        "description": "Quiz: IB Learner Profile — scored 88%",
        "days_ago": 5,
    },
    {
        "xp_amount": 2,
        "reason": "streak_bonus",
        "description": "12-day streak bonus",
        "days_ago": 0,
    },
]


# ---------------------------------------------------------------------------
# Other teachers' XP profiles (lower but realistic)
# ---------------------------------------------------------------------------

OTHER_TEACHER_PROFILES = {
    "raj.patel@keystoneeducation.in": {
        "total_xp": 420,
        "level": 2,
        "level_name": "Certified Teacher",
        "xp_this_month": 85,
        "current_streak": 5,
        "longest_streak": 14,
        "skill_range": (2, 4),
        "badges": ["First Steps", "Century Club", "Course Pioneer", "Consistent Learner"],
        "transactions": [
            {"xp_amount": 50, "reason": "course_completion", "description": "Completed 'Science Pedagogy Essentials'", "days_ago": 60},
            {"xp_amount": 50, "reason": "course_completion", "description": "Completed 'Lab Safety & Design'", "days_ago": 40},
            {"xp_amount": 10, "reason": "content_completion", "description": "Completed module: Experimental Design", "days_ago": 25},
            {"xp_amount": 15, "reason": "assignment_submission", "description": "Submitted lab safety audit report", "days_ago": 18},
            {"xp_amount": 10, "reason": "content_completion", "description": "Completed module: Data Analysis in Science", "days_ago": 8},
        ],
    },
    "anita.desai@keystoneeducation.in": {
        "total_xp": 310,
        "level": 2,
        "level_name": "Certified Teacher",
        "xp_this_month": 60,
        "current_streak": 3,
        "longest_streak": 10,
        "skill_range": (1, 4),
        "badges": ["First Steps", "Century Club", "Course Pioneer"],
        "transactions": [
            {"xp_amount": 50, "reason": "course_completion", "description": "Completed 'Creative Writing Workshop'", "days_ago": 50},
            {"xp_amount": 10, "reason": "content_completion", "description": "Completed module: Poetry in the Classroom", "days_ago": 35},
            {"xp_amount": 15, "reason": "quiz_submission", "description": "Quiz: Literature Analysis — scored 85%", "days_ago": 20},
            {"xp_amount": 10, "reason": "content_completion", "description": "Completed module: Storytelling Techniques", "days_ago": 12},
        ],
    },
    "vikram.singh@keystoneeducation.in": {
        "total_xp": 195,
        "level": 1,
        "level_name": "Associate Educator",
        "xp_this_month": 45,
        "current_streak": 2,
        "longest_streak": 7,
        "skill_range": (1, 3),
        "badges": ["First Steps", "Century Club", "Course Pioneer"],
        "transactions": [
            {"xp_amount": 50, "reason": "course_completion", "description": "Completed 'Digital Pedagogy Foundations'", "days_ago": 38},
            {"xp_amount": 10, "reason": "content_completion", "description": "Completed module: Coding Across Curriculum", "days_ago": 20},
            {"xp_amount": 15, "reason": "assignment_submission", "description": "Submitted lesson plan: AI Ethics for Grade 10", "days_ago": 10},
        ],
    },
}


class Command(BaseCommand):
    help = (
        "Seed competency skills, gamification badges, and sample XP data "
        "for Keystone International School (subdomain: keystone)."
    )

    def handle(self, *args, **options):
        # ── Resolve tenant ──────────────────────────────────────────────
        try:
            tenant = Tenant.objects.get(subdomain="keystone")
        except Tenant.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    'Tenant with subdomain "keystone" does not exist. '
                    "Run seed_keystone or create_demo_tenant first."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f'Found tenant: {tenant.name} (id={tenant.id})')
        )

        # ── Step 1: Seed skills ─────────────────────────────────────────
        self._seed_skills(tenant)

        # ── Step 2: Assign skills to teachers ───────────────────────────
        self._assign_teacher_skills(tenant)

        # ── Step 3: Seed badge definitions ──────────────────────────────
        self._seed_badges(tenant)

        # ── Step 4: Ensure gamification config ──────────────────────────
        self._ensure_gamification_config(tenant)

        # ── Step 5: Create XP data for Priya Sharma ─────────────────────
        self._seed_priya_xp(tenant)

        # ── Step 6: Create XP data for other teachers ───────────────────
        self._seed_other_teachers_xp(tenant)

        # ── Step 7: Create leaderboard snapshot ─────────────────────────
        self._create_leaderboard_snapshot(tenant)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(
            self.style.SUCCESS("  Keystone demo data seeded successfully!")
        )
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write("")

    # =====================================================================
    # Step 1: Seed Skills
    # =====================================================================

    def _seed_skills(self, tenant):
        self.stdout.write("\n  [1/7] Seeding skills...")
        created_count = 0
        for category, name, target in SKILLS:
            _, created = Skill.all_objects.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "description": f"{name} — mapped to IB/Cambridge framework.",
                    "category": category,
                    "level_required": target,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            f"        {created_count} new skills created, "
            f"{len(SKILLS) - created_count} already existed."
        )

    # =====================================================================
    # Step 2: Assign TeacherSkill records
    # =====================================================================

    def _assign_teacher_skills(self, tenant):
        self.stdout.write("\n  [2/7] Assigning skills to teachers...")
        teachers = list(
            User.objects.filter(tenant=tenant, role__in=["TEACHER", "HOD", "IB_COORDINATOR"])
        )
        if not teachers:
            self.stdout.write(
                self.style.WARNING("        No teachers found for this tenant.")
            )
            return

        skills = list(Skill.all_objects.filter(tenant=tenant))
        if not skills:
            self.stdout.write(
                self.style.WARNING("        No skills found — skipping assignment.")
            )
            return

        priya = None
        for t in teachers:
            if t.email == "priya.sharma@keystoneeducation.in":
                priya = t
                break

        created_count = 0
        for teacher in teachers:
            for skill in skills:
                if teacher == priya:
                    current_level = PRIYA_SKILL_LEVELS.get(skill.name, 2)
                elif teacher.email in OTHER_TEACHER_PROFILES:
                    lo, hi = OTHER_TEACHER_PROFILES[teacher.email]["skill_range"]
                    current_level = random.randint(lo, hi)
                else:
                    # Generic realistic spread for any other teachers
                    current_level = random.randint(1, 3)

                _, created = TeacherSkill.all_objects.get_or_create(
                    teacher=teacher,
                    skill=skill,
                    defaults={
                        "tenant": tenant,
                        "current_level": current_level,
                        "target_level": skill.level_required,
                        "last_assessed": timezone.now() - timedelta(days=random.randint(5, 60)),
                    },
                )
                if created:
                    created_count += 1

        self.stdout.write(
            f"        {created_count} TeacherSkill records created for "
            f"{len(teachers)} teachers x {len(skills)} skills."
        )

    # =====================================================================
    # Step 3: Seed Badge Definitions
    # =====================================================================

    def _seed_badges(self, tenant):
        self.stdout.write("\n  [3/7] Seeding badge definitions...")
        created_count = 0
        for badge_data in BADGES:
            _, created = BadgeDefinition.all_objects.get_or_create(
                tenant=tenant,
                name=badge_data["name"],
                defaults={
                    "description": badge_data["description"],
                    "category": badge_data["category"],
                    "criteria_type": badge_data["criteria_type"],
                    "criteria_value": badge_data["criteria_value"],
                    "color": badge_data["color"],
                    "icon": badge_data["icon"],
                    "sort_order": badge_data["sort_order"],
                    "is_active": True,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            f"        {created_count} new badges created, "
            f"{len(BADGES) - created_count} already existed."
        )

    # =====================================================================
    # Step 4: Ensure GamificationConfig
    # =====================================================================

    def _ensure_gamification_config(self, tenant):
        self.stdout.write("\n  [4/7] Ensuring gamification config...")
        _, created = GamificationConfig.objects.get_or_create(
            tenant=tenant,
            defaults={
                "leaderboard_enabled": True,
                "opt_out_allowed": True,
                "is_active": True,
            },
        )
        if created:
            self.stdout.write("        Created GamificationConfig.")
        else:
            self.stdout.write("        GamificationConfig already exists.")

    # =====================================================================
    # Step 5: Priya Sharma XP data
    # =====================================================================

    def _seed_priya_xp(self, tenant):
        self.stdout.write("\n  [5/7] Seeding XP data for Priya Sharma...")
        try:
            priya = User.objects.get(email="priya.sharma@keystoneeducation.in")
        except User.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(
                    "        Priya Sharma not found — skipping her XP data."
                )
            )
            return

        # -- XP Summary --
        summary, created = TeacherXPSummary.all_objects.get_or_create(
            teacher=priya,
            defaults={
                "tenant": tenant,
                "total_xp": 685,
                "level": 3,
                "level_name": "Senior Educator",
                "xp_this_month": 145,
                "xp_this_week": 27,
                "last_xp_at": timezone.now(),
                "opted_out": False,
            },
        )
        if created:
            self.stdout.write("        Created TeacherXPSummary (685 XP, Level 3).")
        else:
            self.stdout.write("        TeacherXPSummary already exists.")

        # -- Streak --
        streak, created = TeacherStreak.all_objects.get_or_create(
            teacher=priya,
            defaults={
                "tenant": tenant,
                "current_streak": 12,
                "longest_streak": 23,
                "last_activity_date": date.today(),
            },
        )
        if created:
            self.stdout.write("        Created TeacherStreak (current=12, longest=23).")
        else:
            self.stdout.write("        TeacherStreak already exists.")

        # -- XP Transactions --
        now = timezone.now()
        tx_created = 0
        for tx in PRIYA_XP_TRANSACTIONS:
            ts = now - timedelta(days=tx["days_ago"])
            _, created = XPTransaction.all_objects.get_or_create(
                tenant=tenant,
                teacher=priya,
                reason=tx["reason"],
                description=tx["description"],
                defaults={
                    "xp_amount": tx["xp_amount"],
                },
            )
            if created:
                # Backdate created_at for realistic ordering
                XPTransaction.all_objects.filter(
                    tenant=tenant,
                    teacher=priya,
                    reason=tx["reason"],
                    description=tx["description"],
                ).update(created_at=ts)
                tx_created += 1

        self.stdout.write(f"        {tx_created} XP transactions created.")

        # -- Award badges to Priya --
        priya_badge_names = [
            "First Steps",
            "Century Club",
            "Knowledge Seeker",
            "Course Pioneer",
            "Curriculum Explorer",
            "Consistent Learner",
            "IB Practitioner",
        ]
        badges_awarded = 0
        for badge_name in priya_badge_names:
            try:
                badge_def = BadgeDefinition.all_objects.get(
                    tenant=tenant, name=badge_name
                )
            except BadgeDefinition.DoesNotExist:
                continue
            _, created = TeacherBadge.all_objects.get_or_create(
                teacher=priya,
                badge=badge_def,
                defaults={
                    "tenant": tenant,
                    "awarded_reason": f"Auto-awarded: {badge_def.criteria_type}",
                },
            )
            if created:
                badges_awarded += 1

        self.stdout.write(f"        {badges_awarded} badges awarded to Priya.")

    # =====================================================================
    # Step 6: Other teachers' XP data
    # =====================================================================

    def _seed_other_teachers_xp(self, tenant):
        self.stdout.write("\n  [6/7] Seeding XP data for other teachers...")

        for email, profile in OTHER_TEACHER_PROFILES.items():
            try:
                teacher = User.objects.get(email=email)
            except User.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"        {email} not found — skipping.")
                )
                continue

            # -- XP Summary --
            summary, created = TeacherXPSummary.all_objects.get_or_create(
                teacher=teacher,
                defaults={
                    "tenant": tenant,
                    "total_xp": profile["total_xp"],
                    "level": profile["level"],
                    "level_name": profile["level_name"],
                    "xp_this_month": profile["xp_this_month"],
                    "xp_this_week": random.randint(10, profile["xp_this_month"]),
                    "last_xp_at": timezone.now() - timedelta(days=random.randint(0, 3)),
                    "opted_out": False,
                },
            )
            status = "created" if created else "exists"
            self.stdout.write(
                f"        {teacher.first_name} {teacher.last_name}: "
                f"XPSummary {status} ({profile['total_xp']} XP, L{profile['level']})"
            )

            # -- Streak --
            TeacherStreak.all_objects.get_or_create(
                teacher=teacher,
                defaults={
                    "tenant": tenant,
                    "current_streak": profile["current_streak"],
                    "longest_streak": profile["longest_streak"],
                    "last_activity_date": date.today()
                    - timedelta(days=random.randint(0, 2)),
                },
            )

            # -- XP Transactions --
            now = timezone.now()
            for tx in profile["transactions"]:
                ts = now - timedelta(days=tx["days_ago"])
                _, created = XPTransaction.all_objects.get_or_create(
                    tenant=tenant,
                    teacher=teacher,
                    reason=tx["reason"],
                    description=tx["description"],
                    defaults={
                        "xp_amount": tx["xp_amount"],
                    },
                )
                if created:
                    XPTransaction.all_objects.filter(
                        tenant=tenant,
                        teacher=teacher,
                        reason=tx["reason"],
                        description=tx["description"],
                    ).update(created_at=ts)

            # -- Badges --
            for badge_name in profile["badges"]:
                try:
                    badge_def = BadgeDefinition.all_objects.get(
                        tenant=tenant, name=badge_name
                    )
                except BadgeDefinition.DoesNotExist:
                    continue
                TeacherBadge.all_objects.get_or_create(
                    teacher=teacher,
                    badge=badge_def,
                    defaults={
                        "tenant": tenant,
                        "awarded_reason": f"Auto-awarded: {badge_def.criteria_type}",
                    },
                )

    # =====================================================================
    # Step 7: Leaderboard snapshot
    # =====================================================================

    def _create_leaderboard_snapshot(self, tenant):
        self.stdout.write("\n  [7/7] Creating weekly leaderboard snapshot...")

        today = date.today()

        # Collect all teachers with XP summaries for this tenant
        summaries = list(
            TeacherXPSummary.all_objects.filter(tenant=tenant)
            .select_related("teacher")
            .order_by("-total_xp")
        )

        if not summaries:
            self.stdout.write(
                self.style.WARNING(
                    "        No XP summaries found — skipping leaderboard."
                )
            )
            return

        created_count = 0
        for rank, summary in enumerate(summaries, start=1):
            _, created = LeaderboardSnapshot.all_objects.get_or_create(
                tenant=tenant,
                teacher=summary.teacher,
                period="weekly",
                snapshot_date=today,
                defaults={
                    "rank": rank,
                    "xp_total": summary.total_xp,
                    "xp_period": summary.xp_this_week,
                },
            )
            if created:
                created_count += 1

        self.stdout.write(
            f"        {created_count} leaderboard entries created "
            f"({len(summaries)} teachers ranked)."
        )
