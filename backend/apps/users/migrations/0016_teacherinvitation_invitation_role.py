from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0015_migrate_legacy_2fa_to_encrypted"),
    ]

    operations = [
        migrations.AddField(
            model_name="teacherinvitation",
            name="invitation_role",
            field=models.CharField(
                choices=[("TEACHER", "Teacher"), ("STUDENT", "Student")],
                default="TEACHER",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="teacherinvitation",
            index=models.Index(
                fields=["tenant", "invitation_role", "status"],
                name="teacher_inv_tenant__297fa8_idx",
            ),
        ),
    ]
