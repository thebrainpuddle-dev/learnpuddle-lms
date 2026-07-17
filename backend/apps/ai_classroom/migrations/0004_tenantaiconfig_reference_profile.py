from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai_classroom", "0003_aiclassroommediaasset")]

    operations = [
        migrations.AddField(
            model_name="tenantairuntimeconfig",
            name="reference_profile_id",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="tenantairuntimeconfig",
            name="reference_profile_sha256",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
