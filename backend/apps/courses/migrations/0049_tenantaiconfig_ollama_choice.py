from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0048_tenantaiconfig_pdf_phase10"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tenantaiconfig",
            name="llm_model",
            field=models.CharField(
                default="openai/gpt-4o-mini",
                help_text=(
                    "Model identifier, e.g. openai/gpt-4o-mini, "
                    "openrouter/openai/gpt-4o-mini, ollama/llama3.2:3b"
                ),
                max_length=100,
            ),
        ),
        migrations.AlterField(
            model_name="tenantaiconfig",
            name="llm_provider",
            field=models.CharField(
                choices=[
                    ("openai", "OpenAI"),
                    ("anthropic", "Anthropic"),
                    ("google", "Google AI"),
                    ("openrouter", "OpenRouter"),
                    ("azure", "Azure OpenAI"),
                    ("ollama", "Ollama / Self-hosted"),
                ],
                default="openai",
                max_length=20,
            ),
        ),
    ]
