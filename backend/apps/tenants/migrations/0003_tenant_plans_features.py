from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0002_tenant_font_family_tenant_secondary_color"),
    ]

    operations = [
        # Subscription plan
        migrations.AddField(model_name="tenant", name="plan", field=models.CharField(choices=[("FREE", "Free"), ("STARTER", "Starter"), ("PRO", "Professional"), ("ENTERPRISE", "Enterprise")], default="FREE", max_length=20)),
        migrations.AddField(model_name="tenant", name="plan_started_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="tenant", name="plan_expires_at", field=models.DateTimeField(blank=True, null=True)),
        # Limits
        migrations.AddField(model_name="tenant", name="max_teachers", field=models.PositiveIntegerField(default=10, help_text="Max teacher accounts")),
        migrations.AddField(model_name="tenant", name="max_courses", field=models.PositiveIntegerField(default=5, help_text="Max courses")),
        migrations.AddField(model_name="tenant", name="max_storage_mb", field=models.PositiveIntegerField(default=500, help_text="Max storage in MB")),
        migrations.AddField(model_name="tenant", name="max_video_duration_minutes", field=models.PositiveIntegerField(default=60, help_text="Max single video duration (min)")),
        # Feature flags
        migrations.AddField(model_name="tenant", name="feature_video_upload", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tenant", name="feature_auto_quiz", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tenant", name="feature_transcripts", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tenant", name="feature_reminders", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="tenant", name="feature_custom_branding", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tenant", name="feature_reports_export", field=models.BooleanField(default=False)),
        migrations.AddField(model_name="tenant", name="feature_groups", field=models.BooleanField(default=True)),
        migrations.AddField(model_name="tenant", name="feature_certificates", field=models.BooleanField(default=False)),
        # Notes
        migrations.AddField(model_name="tenant", name="internal_notes", field=models.TextField(blank=True, default="")),
    ]
