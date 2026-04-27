# Migration: Puddle Coins (TASK-019, Phase 4 Gamification)
#
# Additive-only. Adds the Puddle Coins virtual currency ledger and cached
# balance row alongside the existing XP + Mastery Point ledgers.

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0019_mastery_points"),
        ("tenants", "0001_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        # --- GamificationConfig: Puddle Coin tunables ------------------------
        migrations.AddField(
            model_name="gamificationconfig",
            name="coins_per_level_up",
            field=models.PositiveIntegerField(
                default=100,
                help_text=(
                    "Puddle Coins granted when a teacher gains a level."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="coins_per_challenge",
            field=models.PositiveIntegerField(
                default=25,
                help_text=(
                    "Puddle Coins granted on challenge completion (in "
                    "addition to any challenge.reward_xp)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="coins_per_league_promote",
            field=models.PositiveIntegerField(
                default=50,
                help_text=(
                    "Puddle Coins granted when a teacher is promoted at the "
                    "weekly league close."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="coins_per_streak_milestone",
            field=models.PositiveIntegerField(
                default=20,
                help_text=(
                    "Puddle Coins granted every N-day streak milestone "
                    "(same cadence as freeze-token grants)."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="coin_price_streak_freeze",
            field=models.PositiveIntegerField(
                default=50,
                help_text=(
                    "Puddle Coin price to purchase one streak-freeze token."
                ),
            ),
        ),
        # --- CoinTransaction -------------------------------------------------
        migrations.CreateModel(
            name="CoinTransaction",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("amount", models.IntegerField()),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("level_up", "Level Up"),
                            ("challenge_reward", "Challenge Reward"),
                            ("league_promote", "League Promotion"),
                            ("streak_milestone", "Streak Milestone"),
                            ("admin_adjust", "Admin Adjustment"),
                            ("purchase_streak_freeze", "Purchase Streak Freeze"),
                            ("purchase_other", "Purchase Other"),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    "description",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                (
                    "reference_id",
                    models.UUIDField(
                        blank=True,
                        help_text=(
                            "ID of the related object (challenge, league, "
                            "token, etc.)."
                        ),
                        null=True,
                    ),
                ),
                (
                    "reference_type",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Type of related object.",
                        max_length=50,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="coin_transactions",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="coin_transactions",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "db_table": "coin_transactions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="cointransaction",
            index=models.Index(
                fields=["tenant", "teacher"],
                name="coin_txn_tenant_teacher_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="cointransaction",
            index=models.Index(
                fields=["tenant", "teacher", "reason"],
                name="coin_txn_tenant_reason_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="cointransaction",
            index=models.Index(
                fields=["created_at"],
                name="coin_txn_created_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="cointransaction",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("amount__gt", 0),
                    ("reference_id__isnull", False),
                ),
                fields=(
                    "teacher", "reason", "reference_type", "reference_id",
                ),
                name="uniq_coin_earn_per_reference",
            ),
        ),
        # --- TeacherCoinBalance ---------------------------------------------
        migrations.CreateModel(
            name="TeacherCoinBalance",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("balance", models.PositiveIntegerField(default=0)),
                ("lifetime_earned", models.PositiveIntegerField(default=0)),
                ("lifetime_spent", models.PositiveIntegerField(default=0)),
                ("last_txn_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="teacher_coin_balances",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "teacher",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="coin_balance",
                        to="users.user",
                    ),
                ),
            ],
            options={
                "db_table": "teacher_coin_balances",
            },
        ),
        migrations.AddIndex(
            model_name="teachercoinbalance",
            index=models.Index(
                fields=["tenant", "balance"],
                name="coin_bal_tenant_balance_idx",
            ),
        ),
    ]
