import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0015_accreditation_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="ComplianceItem",
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
                ("name", models.CharField(max_length=300)),
                ("description", models.TextField(blank=True, default="")),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("SAFETY", "Safety & Infrastructure"),
                            ("BOARD", "Board & Government"),
                            ("NEP", "NEP 2020 Alignment"),
                            ("FINANCIAL", "Financial & Fee Regulation"),
                            ("DATA", "Data & Privacy"),
                            ("OTHER", "Other"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("COMPLIANT", "Compliant"),
                            ("IN_PROGRESS", "In Progress"),
                            ("NON_COMPLIANT", "Non-Compliant"),
                            ("NOT_APPLICABLE", "Not Applicable"),
                            ("PENDING", "Pending Review"),
                        ],
                        default="PENDING",
                        max_length=20,
                    ),
                ),
                ("due_date", models.DateField(blank=True, null=True)),
                ("completed_date", models.DateField(blank=True, null=True)),
                (
                    "responsible_person",
                    models.CharField(blank=True, default="", max_length=200),
                ),
                (
                    "recurrence",
                    models.CharField(
                        choices=[
                            ("ONE_TIME", "One-time"),
                            ("ANNUAL", "Annual"),
                            ("QUARTERLY", "Quarterly"),
                            ("MONTHLY", "Monthly"),
                        ],
                        default="ANNUAL",
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "document_url",
                    models.URLField(blank=True, default="", max_length=500),
                ),
                ("reminder_days", models.IntegerField(default=30)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="compliance_items",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "compliance_items",
                "ordering": ["category", "due_date"],
            },
        ),
        migrations.AddIndex(
            model_name="complianceitem",
            index=models.Index(
                fields=["tenant", "category"],
                name="compliance__tenant__cat_idx",
            ),
        ),
    ]
