# Generated for TASK-045 revision 2 — distinct feature_saml flag.
# Backfills ``feature_saml = True`` for any tenant that previously had
# ``feature_sso = True`` so SAML keeps working during the transition.

from django.db import migrations, models


def copy_feature_sso_to_saml(apps, schema_editor):
    Tenant = apps.get_model("tenants", "Tenant")
    for t in Tenant.objects.filter(feature_sso=True):
        if not t.feature_saml:
            t.feature_saml = True
            t.save(update_fields=["feature_saml"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0019_saml_and_password_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="feature_saml",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Enable SAML 2.0 SSO (per TASK-045). Distinct from "
                    "OAuth-style feature_sso."
                ),
            ),
        ),
        migrations.RunPython(copy_feature_sso_to_saml, noop_reverse),
    ]
