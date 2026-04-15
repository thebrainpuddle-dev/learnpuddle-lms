import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0016_compliance_items"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffCertification",
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
                    "certification_type",
                    models.CharField(
                        choices=[
                            ("IB_CAT1", "IB Category 1 Workshop"),
                            ("IB_CAT2", "IB Category 2 Workshop"),
                            ("IB_CAT3", "IB Category 3 Workshop"),
                            ("IB_LEADER", "IB Leadership Workshop"),
                            ("FIRST_AID", "First Aid Certification"),
                            ("POCSO", "POCSO Awareness Training"),
                            ("FIRE_SAFETY", "Fire Safety Training"),
                            ("CHILD_SAFEGUARDING", "Child Safeguarding"),
                            ("CPR", "CPR Certification"),
                            ("BACKGROUND_CHECK", "Background / Police Verification"),
                            ("TEACHING_LICENSE", "Teaching License"),
                            ("SUBJECT_CERT", "Subject Specialization Certificate"),
                            ("DIGITAL_LITERACY", "Digital Literacy / EdTech Training"),
                            ("NEP_TRAINING", "NEP 2020 Training"),
                            ("OTHER", "Other"),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "custom_name",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Custom name if certification_type is OTHER",
                        max_length=200,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("VALID", "Valid"),
                            ("EXPIRING", "Expiring Soon"),
                            ("EXPIRED", "Expired"),
                            ("NOT_STARTED", "Not Started"),
                        ],
                        default="NOT_STARTED",
                        max_length=20,
                    ),
                ),
                ("completed_date", models.DateField(blank=True, null=True)),
                ("expiry_date", models.DateField(blank=True, null=True)),
                (
                    "certificate_url",
                    models.URLField(
                        blank=True,
                        default="",
                        help_text="Link to uploaded certificate file",
                    ),
                ),
                (
                    "provider",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Training provider or issuing organization",
                        max_length=200,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_certifications",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_certifications",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "staff_certifications",
                "ordering": ["teacher__first_name", "certification_type"],
                "unique_together": {("tenant", "teacher", "certification_type")},
            },
        ),
        migrations.AddIndex(
            model_name="staffcertification",
            index=models.Index(
                fields=["tenant", "certification_type"],
                name="staff_cert_tenant_type_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="staffcertification",
            index=models.Index(
                fields=["tenant", "teacher"],
                name="staff_cert_tenant_teacher_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="staffcertification",
            index=models.Index(
                fields=["status"],
                name="staff_cert_status_idx",
            ),
        ),
    ]
