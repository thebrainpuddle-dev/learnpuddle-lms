# Migration: Daily / Weekly Challenges (TASK-017, Phase 4 Gamification)
#
# Additive-only. Two new tables: Challenge, ChallengeParticipation.
# Also extends the XP_REASON_CHOICES set on XPTransaction to include
# 'challenge_reward'.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0017_leagues"),
        ("tenants", "0001_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        # --- XP reason: add 'challenge_reward' to choices -------------------
        migrations.AlterField(
            model_name="xptransaction",
            name="reason",
            field=models.CharField(
                max_length=50,
                choices=[
                    ("content_completion", "Content Completion"),
                    ("course_completion", "Course Completion"),
                    ("assignment_submission", "Assignment Submission"),
                    ("quiz_submission", "Quiz Submission"),
                    ("lesson_reflection", "Lesson Reflection"),
                    ("streak_bonus", "Streak Bonus"),
                    ("badge_award", "Badge Award"),
                    ("admin_adjust", "Admin Adjustment"),
                    ("quest_reward", "Quest Reward"),
                    ("challenge_reward", "Challenge Reward"),
                ],
            ),
        ),

        # --- Challenge ------------------------------------------------------
        migrations.CreateModel(
            name="Challenge",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("title", models.CharField(max_length=150)),
                ("description", models.TextField(blank=True, default="")),
                ("challenge_type", models.CharField(
                    max_length=10,
                    choices=[("DAILY", "Daily"), ("WEEKLY", "Weekly")],
                    default="DAILY",
                )),
                ("goal_type", models.CharField(
                    max_length=30,
                    choices=[
                        ("complete_lessons", "Complete N Lessons"),
                        ("earn_xp", "Earn N XP"),
                        ("finish_course", "Finish a Specific Course"),
                        ("maintain_streak", "Maintain N-Day Streak"),
                        ("submit_assignments", "Submit N Assignments"),
                    ],
                )),
                ("goal_target", models.PositiveIntegerField(default=1)),
                ("goal_reference_id", models.UUIDField(null=True, blank=True)),
                ("start_at", models.DateTimeField()),
                ("end_at", models.DateTimeField()),
                ("reward_xp", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="challenges",
                    to="tenants.tenant",
                )),
                ("reward_badge", models.ForeignKey(
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name="challenge_rewards",
                    to="progress.badgedefinition",
                )),
                ("created_by", models.ForeignKey(
                    on_delete=django.db.models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name="created_challenges",
                    to="users.user",
                )),
            ],
            options={
                "db_table": "progress_challenges",
                "ordering": ["-start_at"],
            },
        ),
        migrations.AddIndex(
            model_name="challenge",
            index=models.Index(
                fields=["tenant", "is_active", "end_at"],
                name="ch_tenant_active_end_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="challenge",
            index=models.Index(
                fields=["tenant", "challenge_type"],
                name="ch_tenant_type_idx",
            ),
        ),

        # --- ChallengeParticipation ----------------------------------------
        migrations.CreateModel(
            name="ChallengeParticipation",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("progress_value", models.PositiveIntegerField(default=0)),
                ("completed_at", models.DateTimeField(null=True, blank=True)),
                ("reward_issued", models.BooleanField(default=False)),
                ("last_reference_key", models.CharField(
                    max_length=120, blank=True, default="",
                )),
                ("increments_log", models.JSONField(default=list, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="challenge_participations",
                    to="tenants.tenant",
                )),
                ("challenge", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="participations",
                    to="progress.challenge",
                )),
                ("teacher", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="challenge_participations",
                    to="users.user",
                )),
            ],
            options={
                "db_table": "progress_challenge_participations",
            },
        ),
        migrations.AddConstraint(
            model_name="challengeparticipation",
            constraint=models.UniqueConstraint(
                fields=["challenge", "teacher"],
                name="uniq_challenge_participation_per_teacher",
            ),
        ),
        migrations.AddIndex(
            model_name="challengeparticipation",
            index=models.Index(
                fields=["tenant", "teacher", "completed_at"],
                name="chp_tenant_teacher_done_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="challengeparticipation",
            index=models.Index(
                fields=["tenant", "challenge"],
                name="chp_tenant_challenge_idx",
            ),
        ),
    ]
