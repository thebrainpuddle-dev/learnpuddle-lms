import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0014_add_feature_maic"),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolAccreditation",
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
                (
                    "accreditation_type",
                    models.CharField(
                        choices=[
                            ("IB_PYP", "IB Primary Years Programme"),
                            ("IB_MYP", "IB Middle Years Programme"),
                            ("IB_DP", "IB Diploma Programme"),
                            ("IB_CP", "IB Career-related Programme"),
                            ("CBSE", "CBSE Affiliation"),
                            ("ICSE", "ICSE/ISC Affiliation"),
                            ("CAMBRIDGE_IGCSE", "Cambridge IGCSE"),
                            ("CAMBRIDGE_AL", "Cambridge AS/A Level"),
                            ("NABET", "NABET/QCI Accreditation"),
                            ("CIS", "CIS Accreditation"),
                            ("ISO_9001", "ISO 9001:2015"),
                            ("ISO_21001", "ISO 21001:2018"),
                            ("GREEN_SCHOOL", "IGBC Green School"),
                            ("OTHER", "Other"),
                        ],
                        help_text="Type of accreditation or affiliation",
                        max_length=30,
                    ),
                ),
                (
                    "custom_name",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Custom name if type is OTHER",
                        max_length=200,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("AUTHORIZED", "Authorized / Active"),
                            ("CANDIDACY", "Candidacy / In Progress"),
                            ("PENDING", "Application Pending"),
                            ("EXPIRED", "Expired"),
                            ("NOT_STARTED", "Not Started"),
                        ],
                        default="NOT_STARTED",
                        max_length=20,
                    ),
                ),
                (
                    "affiliation_number",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Official affiliation or registration number",
                        max_length=100,
                    ),
                ),
                ("valid_from", models.DateField(blank=True, null=True)),
                ("valid_to", models.DateField(blank=True, null=True)),
                (
                    "issuing_body",
                    models.CharField(
                        help_text="Name of the issuing/certifying body",
                        max_length=200,
                    ),
                ),
                (
                    "external_portal_url",
                    models.URLField(
                        blank=True,
                        default="",
                        help_text="URL to the external accreditation portal",
                        max_length=500,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "renewal_cycle_months",
                    models.IntegerField(
                        blank=True,
                        help_text="Renewal cycle in months (e.g., 60 for 5-year cycle)",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="accreditations",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "school_accreditations",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="AccreditationMilestone",
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
                ("title", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True, default="")),
                ("due_date", models.DateField(blank=True, null=True)),
                ("completed_date", models.DateField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("IN_PROGRESS", "In Progress"),
                            ("COMPLETED", "Completed"),
                            ("OVERDUE", "Overdue"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                (
                    "order",
                    models.IntegerField(
                        default=0,
                        help_text="Display order within accreditation",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "accreditation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="milestones",
                        to="tenants.schoolaccreditation",
                    ),
                ),
            ],
            options={
                "db_table": "accreditation_milestones",
                "ordering": ["order", "due_date"],
            },
        ),
        migrations.CreateModel(
            name="RankingEntry",
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
                (
                    "platform",
                    models.CharField(
                        help_text="Ranking platform name, e.g. Education World, HT Top Schools",
                        max_length=50,
                    ),
                ),
                (
                    "year",
                    models.IntegerField(help_text="Ranking year"),
                ),
                (
                    "rank",
                    models.IntegerField(
                        blank=True,
                        help_text="Rank position (lower is better)",
                        null=True,
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        help_text="Ranking category, e.g. City, State, National, STEM, etc.",
                        max_length=100,
                    ),
                ),
                (
                    "score",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Survey/assessment score if available",
                        max_digits=6,
                        null=True,
                    ),
                ),
                (
                    "survey_url",
                    models.URLField(blank=True, default="", max_length=500),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="rankings",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "ranking_entries",
                "ordering": ["-year", "platform"],
                "unique_together": {("tenant", "platform", "year", "category")},
            },
        ),
        migrations.AddIndex(
            model_name="schoolaccreditation",
            index=models.Index(
                fields=["tenant", "accreditation_type"],
                name="school_accr_tenant__idx",
            ),
        ),
        migrations.AddIndex(
            model_name="schoolaccreditation",
            index=models.Index(
                fields=["status"],
                name="school_accr_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="rankingentry",
            index=models.Index(
                fields=["tenant", "year"],
                name="ranking_ent_tenant__idx",
            ),
        ),
        migrations.AddIndex(
            model_name="rankingentry",
            index=models.Index(
                fields=["platform", "year"],
                name="ranking_ent_platfor_idx",
            ),
        ),
    ]
