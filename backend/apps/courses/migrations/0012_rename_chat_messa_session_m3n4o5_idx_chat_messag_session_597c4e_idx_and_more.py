# Stub migration — original renamed indexes on ChatSession/ChatMessage/CourseEmbedding
# models that have since been fully removed. Kept as no-op to preserve
# migration graph consistency.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0011_ai_chatbot_models'),
    ]

    operations = []
