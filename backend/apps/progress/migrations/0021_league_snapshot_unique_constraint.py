# Migration: Add unique constraint to LeagueRankSnapshot (teacher, week_start_date).
#
# Defence-in-depth: the close_league_week task should only ever write one snapshot
# per teacher per week, but enforcing this at the DB level prevents silent duplicates
# from a double-run or race condition.
#
# Additive-only — adds a UniqueConstraint. Zero-downtime: the constraint is applied
# in a single ALTER TABLE ADD CONSTRAINT which is fast on an empty or small table
# (leagues were added in 0017 and no production data exists yet).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0020_puddle_coins"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="leagueranksnapshot",
            constraint=models.UniqueConstraint(
                fields=["teacher", "week_start_date"],
                name="unique_league_rank_snapshot_per_teacher_per_week",
            ),
        ),
    ]
