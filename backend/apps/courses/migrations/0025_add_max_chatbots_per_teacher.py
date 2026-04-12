from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0024_chatbot_models"),
    ]

    operations = [
        migrations.AddField(
            model_name="tenantaiconfig",
            name="max_chatbots_per_teacher",
            field=models.PositiveIntegerField(
                default=10,
                help_text="Maximum chatbots a teacher can create",
            ),
        ),
    ]
