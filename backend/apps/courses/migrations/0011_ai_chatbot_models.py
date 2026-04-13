# Stub migration — original created ChatSession/ChatMessage/CourseEmbedding
# models that have since been fully removed. Kept as no-op to preserve
# migration graph consistency.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0010_rename_rich_text_i_tenant__183a54_idx_rich_text_i_tenant__b2415b_idx_and_more"),
    ]

    operations = []
