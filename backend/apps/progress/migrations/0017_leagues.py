# Migration: 10-Tier League Leaderboards (TASK-016, Phase 4 Gamification)
#
# Additive-only. No backfill — teachers join their first league on their next
# activity via lazy-assignment in the engine.

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0016_streak_freeze_tokens"),
        ("tenants", "0001_initial"),
        ("users", "0001_initial"),
    ]

    operations = [
        # --- GamificationConfig: league tunables --------------------------
        migrations.AddField(
            model_name="gamificationconfig",
            name="leagues_enabled",
            field=models.BooleanField(
                default=True,
                help_text="Master switch for the league leaderboard feature.",
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="leagues_opt_in_required",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "If True, teachers must explicitly opt in to leagues "
                    "(league_opted_out defaults to True). If False, all "
                    "non-opted-out teachers are enrolled."
                ),
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="league_cohort_size",
            field=models.PositiveIntegerField(
                default=30,
                help_text="Target number of teachers per league cohort.",
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="league_promote_count",
            field=models.PositiveIntegerField(
                default=7,
                help_text="How many top finishers are promoted each week.",
            ),
        ),
        migrations.AddField(
            model_name="gamificationconfig",
            name="league_demote_count",
            field=models.PositiveIntegerField(
                default=7,
                help_text="How many bottom finishers are demoted each week.",
            ),
        ),
        # --- TeacherXPSummary: league_opted_out ---------------------------
        migrations.AddField(
            model_name="teacherxpsummary",
            name="league_opted_out",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Per-teacher opt-out for the league leaderboard "
                    "specifically."
                ),
            ),
        ),

        # --- League -------------------------------------------------------
        migrations.CreateModel(
            name="League",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("tier_code", models.CharField(
                    max_length=20,
                    choices=[
                        ("bronze_1", "Bronze I"),
                        ("bronze_2", "Bronze II"),
                        ("bronze_3", "Bronze III"),
                        ("silver_1", "Silver I"),
                        ("silver_2", "Silver II"),
                        ("silver_3", "Silver III"),
                        ("gold_1", "Gold I"),
                        ("gold_2", "Gold II"),
                        ("gold_3", "Gold III"),
                        ("diamond", "Diamond"),
                    ],
                )),
                ("tier_rank", models.PositiveSmallIntegerField(
                    help_text="Denormalized 1..10 for fast sorting.",
                )),
                ("week_start_date", models.DateField(
                    help_text=(
                        "ISO-week Monday on which this league opened (UTC)."
                    ),
                )),
                ("closed_at", models.DateTimeField(null=True, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="leagues",
                    to="tenants.tenant",
                )),
            ],
            options={
                "db_table": "progress_leagues",
                "ordering": ["-week_start_date", "tier_rank"],
            },
        ),
        migrations.AddIndex(
            model_name="league",
            index=models.Index(
                fields=["tenant", "week_start_date", "tier_rank"],
                name="league_tenant_week_tier_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="league",
            index=models.Index(
                fields=["tenant", "closed_at"],
                name="league_tenant_closed_idx",
            ),
        ),

        # --- LeagueMembership --------------------------------------------
        migrations.CreateModel(
            name="LeagueMembership",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("weekly_xp", models.PositiveIntegerField(default=0)),
                ("final_rank", models.PositiveIntegerField(null=True, blank=True)),
                ("outcome", models.CharField(
                    max_length=10,
                    choices=[
                        ("promote", "Promote"),
                        ("hold", "Hold"),
                        ("demote", "Demote"),
                    ],
                    null=True, blank=True,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="league_memberships",
                    to="tenants.tenant",
                )),
                ("league", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="memberships",
                    to="progress.league",
                )),
                ("teacher", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="league_memberships",
                    to="users.user",
                )),
            ],
            options={
                "db_table": "progress_league_memberships",
            },
        ),
        migrations.AddConstraint(
            model_name="leaguemembership",
            constraint=models.UniqueConstraint(
                fields=["teacher", "league"],
                name="uniq_league_membership_per_teacher_per_league",
            ),
        ),
        migrations.AddIndex(
            model_name="leaguemembership",
            index=models.Index(
                fields=["tenant", "league", "weekly_xp"],
                name="lgm_tenant_league_xp_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leaguemembership",
            index=models.Index(
                fields=["tenant", "teacher"],
                name="lgm_tenant_teacher_idx",
            ),
        ),

        # --- LeagueRankSnapshot ------------------------------------------
        migrations.CreateModel(
            name="LeagueRankSnapshot",
            fields=[
                ("id", models.UUIDField(
                    primary_key=True, default=uuid.uuid4,
                    editable=False, serialize=False,
                )),
                ("tier_code", models.CharField(
                    max_length=20,
                    choices=[
                        ("bronze_1", "Bronze I"),
                        ("bronze_2", "Bronze II"),
                        ("bronze_3", "Bronze III"),
                        ("silver_1", "Silver I"),
                        ("silver_2", "Silver II"),
                        ("silver_3", "Silver III"),
                        ("gold_1", "Gold I"),
                        ("gold_2", "Gold II"),
                        ("gold_3", "Gold III"),
                        ("diamond", "Diamond"),
                    ],
                )),
                ("tier_rank", models.PositiveSmallIntegerField()),
                ("week_start_date", models.DateField()),
                ("final_rank", models.PositiveIntegerField()),
                ("weekly_xp", models.PositiveIntegerField(default=0)),
                ("outcome", models.CharField(
                    max_length=10,
                    choices=[
                        ("promote", "Promote"),
                        ("hold", "Hold"),
                        ("demote", "Demote"),
                    ],
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("tenant", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="league_rank_snapshots",
                    to="tenants.tenant",
                )),
                ("league", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="snapshots",
                    to="progress.league",
                )),
                ("teacher", models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name="league_rank_snapshots",
                    to="users.user",
                )),
            ],
            options={
                "db_table": "progress_league_rank_snapshots",
                "ordering": ["-week_start_date", "tier_rank", "final_rank"],
            },
        ),
        migrations.AddIndex(
            model_name="leagueranksnapshot",
            index=models.Index(
                fields=["tenant", "teacher", "-week_start_date"],
                name="lgs_tenant_teacher_week_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="leagueranksnapshot",
            index=models.Index(
                fields=["tenant", "week_start_date", "tier_rank"],
                name="lgs_tenant_week_tier_idx",
            ),
        ),
    ]
