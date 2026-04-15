"""
Add section FK to DiscussionThread.

Step 1: Delete old unscoped threads (pre-redesign seed data).
Step 2: Add section field, starting as nullable then made non-nullable.
"""

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    # Need atomic=False because the RunPython delete creates pending
    # trigger events that conflict with ALTER TABLE in the same transaction.
    atomic = False

    dependencies = [
        ("discussions", "0002_rename_dr_thread_created_idx_discussion__thread__8faa27_idx_and_more"),
        ("academics", "0001_initial_academic_structure"),
    ]

    operations = [
        # Step 1: Add section as nullable
        migrations.AddField(
            model_name="discussionthread",
            name="section",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="discussion_threads",
                to="academics.section",
            ),
        ),

        # Step 2: Add new indexes
        migrations.AddIndex(
            model_name="discussionthread",
            index=models.Index(
                fields=["tenant", "section", "status"],
                name="discussion__tenant__section_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="discussionthread",
            index=models.Index(
                fields=["tenant", "section", "content"],
                name="discussion__tenant__section_content_idx",
            ),
        ),
    ]
