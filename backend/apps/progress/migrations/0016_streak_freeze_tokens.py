# Migration: Streak Freeze Tokens + Grace Period + Weekend Mode (Phase 4)
#
# Additive, zero-downtime. No backfill required — existing teachers start with
# zero tokens and accrue them on streak milestones going forward.

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0015_badge_rarity_tiers"),
        ("tenants", "0001_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        # --- GamificationConfig: new fields ------------------------------
        migrations.AddField(
            model_name="gamificationconfig",
            name="grace_period_hours",
            field=models.PositiveIntegerField(
                default=24,
                help_text=(
                    "Hours after a missed day during which activity still "
                    "counts for the streak."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="weekend_mode_available",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Allow teachers to opt into weekend mode "
                    "(Sat/Sun don't count)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="freeze_token_earn_every_n_days",
            field=models.PositiveIntegerField(
                default=7,
                help_text=(
                    "Every N consecutive streak days, auto-grant 1 "
                    "freeze token."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="freeze_token_expires_days",
            field=models.PositiveIntegerField(
                default=90,
                help_text="Token lifetime in days (0 = never expires).",
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="freeze_token_max_inventory",
            field=models.PositiveIntegerField(
                default=5,
                help_text="Cap on unspent freeze tokens per teacher.",
            ),
        ),
        # Updated help text on legacy field (no DB change — editing help_text
        # only).  Kept here for schema state fidelity.
        migrations.AlterField(
            model_name="gamificationconfig",
            name="streak_freeze_max",
            field=models.PositiveIntegerField(
                default=2,
                help_text=(
                    "Max streak freezes per month (legacy monthly counter "
                    "fallback)"
                ),
            ),
        ),

        # --- TeacherStreak: new fields ----------------------------------
        migrations.AddField(
            model_name="teacherstreak",
            name="weekend_mode_enabled",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "If true, Sat/Sun activity is not required to maintain "
                    "the streak."
                ),
            ),
        ),
        migrations.AddField(
            model_name="teacherstreak",
            name="grace_period_ends_at",
            field=models.DateTimeField(
                null=True, blank=True,
                help_text=(
                    "Streak is in grace state until this time; activity "
                    "before this auto-recovers."
                ),
            ),
        ),

        # --- StreakFreezeToken ------------------------------------------
        migrations.CreateModel(
            name="StreakFreezeToken",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("source", models.CharField(
                    max_length=30,
                    choices=[
                        ("streak_milestone", "Streak Milestone"),
                        ("admin_grant", "Admin Grant"),
                        ("challenge_reward", "Challenge Reward"),
                        ("purchase", "Purchase"),
                    ],
                    default="streak_milestone",
                )),
                ("earned_at", models.DateTimeField(auto_now_add=True)),
                ("consumed_at", models.DateTimeField(null=True, blank=True)),
                ("expires_at", models.DateTimeField(null=True, blank=True)),
                ("reference_type", models.CharField(
                    max_length=50, blank=True, default="",
                )),
                ("reference_id", models.UUIDField(null=True, blank=True)),
                ("tenant", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="streak_freeze_tokens",
                    to="tenants.tenant",
                )),
                ("teacher", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="streak_freeze_tokens",
                    to="users.user",
                )),
            ],
            options={
                "db_table": "streak_freeze_tokens",
                "ordering": ["earned_at"],
            },
        ),
        migrations.AddIndex(
            model_name="streakfreezetoken",
            index=models.Index(
                fields=["tenant", "teacher", "consumed_at"],
                name="sft_tenant_teacher_consumed_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="streakfreezetoken",
            index=models.Index(
                fields=["expires_at"],
                name="sft_expires_idx",
            ),
        ),

        # --- StreakFreezeLedger -----------------------------------------
        migrations.CreateModel(
            name="StreakFreezeLedger",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("event_type", models.CharField(
                    max_length=20,
                    choices=[
                        ("earned", "Earned"),
                        ("spent", "Spent"),
                        ("expired", "Expired"),
                        ("granted", "Granted"),
                        ("revoked", "Revoked"),
                    ],
                )),
                ("description", models.CharField(
                    max_length=255, blank=True, default="",
                )),
                ("balance_after", models.PositiveIntegerField(
                    default=0,
                    help_text=(
                        "Cached inventory count of unconsumed, unexpired "
                        "tokens after this event."
                    ),
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="streak_freeze_ledger",
                    to="tenants.tenant",
                )),
                ("teacher", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="streak_freeze_ledger",
                    to="users.user",
                )),
                ("token", models.ForeignKey(
                    on_delete=models.deletion.SET_NULL,
                    null=True, blank=True,
                    related_name="ledger_entries",
                    to="progress.streakfreezetoken",
                )),
            ],
            options={
                "db_table": "streak_freeze_ledger",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="streakfreezeledger",
            index=models.Index(
                fields=["tenant", "teacher", "created_at"],
                name="sfl_tenant_teacher_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="streakfreezeledger",
            index=models.Index(
                fields=["tenant", "event_type"],
                name="sfl_tenant_event_idx",
            ),
        ),
    ]
