# Generated manually to make the section-scoping migration data-safe.

from django.db import migrations, models
import django.db.models.deletion


def delete_unscoped_threads(apps, schema_editor):
    DiscussionThread = apps.get_model("discussions", "DiscussionThread")
    DiscussionThread.objects.filter(section__isnull=True).delete()


class Migration(migrations.Migration):
    # Deleting rows and altering the same table can leave pending trigger events
    # on PostgreSQL if wrapped in one transaction.
    atomic = False

    dependencies = [
        ("discussions", "0003_add_section_to_thread"),
    ]

    operations = [
        migrations.RunPython(delete_unscoped_threads, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="discussionthread",
            name="discussion__tenant__561934_idx",
        ),
        migrations.RenameIndex(
            model_name="discussionthread",
            new_name="discussion__tenant__daaf66_idx",
            old_name="discussion__tenant__section_status_idx",
        ),
        migrations.RenameIndex(
            model_name="discussionthread",
            new_name="discussion__tenant__04907c_idx",
            old_name="discussion__tenant__section_content_idx",
        ),
        migrations.AlterField(
            model_name="discussionthread",
            name="section",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="discussion_threads",
                to="academics.section",
            ),
        ),
    ]
