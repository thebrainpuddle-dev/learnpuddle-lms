# Generated migration for Wave 5 tenant fields:
# - SSO/2FA feature flags and configuration
# - Custom domain support

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tenants", "0003_tenant_plans_features"),
    ]

    operations = [
        # SSO/2FA feature flags
        migrations.AddField(
            model_name="tenant",
            name="feature_sso",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tenant",
            name="feature_2fa",
            field=models.BooleanField(default=False),
        ),

        # SSO configuration
        migrations.AddField(
            model_name="tenant",
            name="sso_domains",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Comma-separated list of allowed SSO domains (e.g., school.edu,district.edu)",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="allow_sso_registration",
            field=models.BooleanField(
                default=True,
                help_text="Allow new users to register via SSO",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="require_sso",
            field=models.BooleanField(
                default=False,
                help_text="Require SSO for all users (disable password login)",
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="require_2fa",
            field=models.BooleanField(
                default=False,
                help_text="Require 2FA for all users",
            ),
        ),

        # Custom domain support
        migrations.AddField(
            model_name="tenant",
            name="custom_domain",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Custom domain (e.g., lms.school.edu)",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="tenant",
            name="custom_domain_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tenant",
            name="custom_domain_ssl_expires",
            field=models.DateTimeField(blank=True, null=True),
        ),

        # Index for custom domain lookups
        migrations.AddIndex(
            model_name="tenant",
            index=models.Index(fields=["custom_domain"], name="tenants_custom_domain_idx"),
        ),
    ]
