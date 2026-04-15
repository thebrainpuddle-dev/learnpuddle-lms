"""
Add teacher study-summary support: generated_by FK, is_shared flag,
and updated indexes.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0031_study_summary"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Make student nullable (teacher-created summaries have student=NULL)
        migrations.AlterField(
            model_name="studysummary",
            name="student",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="study_summaries",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        # 2. Add generated_by FK
        migrations.AddField(
            model_name="studysummary",
            name="generated_by",
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="created_study_summaries",
                to=settings.AUTH_USER_MODEL,
                help_text="Teacher who generated this summary (null for student-generated)",
            ),
        ),
        # 3. Add is_shared boolean
        migrations.AddField(
            model_name="studysummary",
            name="is_shared",
            field=models.BooleanField(
                default=False,
                help_text="When True, students in the course can see this summary",
            ),
        ),
        # 4. Remove old unique_together constraint
        migrations.AlterUniqueTogether(
            name="studysummary",
            unique_together=set(),
        ),
        # 5. Add index for teacher queries
        migrations.AddIndex(
            model_name="studysummary",
            index=models.Index(
                fields=["tenant", "generated_by"],
                name="study_summ_tenant_genby_idx",
            ),
        ),
        # 6. Add index for shared summary lookups
        migrations.AddIndex(
            model_name="studysummary",
            index=models.Index(
                fields=["content", "is_shared"],
                name="study_summ_content_shared_idx",
            ),
        ),
    ]
