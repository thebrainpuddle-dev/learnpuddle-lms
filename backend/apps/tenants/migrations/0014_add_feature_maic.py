from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0013_initial_academic_structure"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenant",
            name="feature_maic",
            field=models.BooleanField(
                default=False,
                help_text="Enable OpenMAIC AI Classroom feature",
            ),
        ),
    ]
