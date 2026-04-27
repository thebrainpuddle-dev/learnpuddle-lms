# Migration: Badge Rarity Tiers + Social Learning Category (Phase 4 Gamification)
#
# Changes:
#   - BadgeDefinition.rarity (CharField, max_length=20, default='common')
#     Six tiers: common → uncommon → rare → epic → legendary → mythic
#   - BADGE_CATEGORY_CHOICES gains 'social_learning' (non-database-enforced,
#     just a Django-level choice; existing rows are unaffected).
#
# This migration is additive-only: existing badge rows receive rarity='common'
# via the model default; no backfill query is required.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("progress", "0014_rubrics"),
    ]

    operations = [
        migrations.AddField(
            model_name="badgedefinition",
            name="rarity",
            field=models.CharField(
                choices=[
                    ("common", "Common"),
                    ("uncommon", "Uncommon"),
                    ("rare", "Rare"),
                    ("epic", "Epic"),
                    ("legendary", "Legendary"),
                    ("mythic", "Mythic"),
                ],
                default="common",
                help_text=(
                    "Prestige tier of this badge. "
                    "Affects visual treatment in the badge gallery."
                ),
                max_length=20,
            ),
        ),
    ]
