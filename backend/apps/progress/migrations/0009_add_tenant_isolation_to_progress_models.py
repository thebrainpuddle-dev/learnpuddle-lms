# Migration: Add tenant FK + TenantManager isolation and progress_percentage CHECK constraint
#
# Strategy for null=True on tenant fields:
#   New tenant FK fields are added as nullable so existing rows are not rejected.
#   All new records created by the application MUST supply a tenant value (enforced at model
#   level). Existing data should be back-filled via a management command before deploying to
#   any environment that has pre-existing progress records.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('progress', '0008_alter_courseskiprequest_unique_together_and_more'),
        ('tenants', '0001_initial'),
    ]

    operations = [
        # ── TeacherProgress ────────────────────────────────────────────────
        migrations.AddField(
            model_name='teacherprogress',
            name='tenant',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='teacher_progress',
                to='tenants.tenant',
            ),
        ),
        # Remove old non-tenant indexes, add tenant-scoped replacements.
        migrations.RemoveIndex(
            model_name='teacherprogress',
            name='teacher_pro_teacher_d34bd5_idx',
        ),
        migrations.RemoveIndex(
            model_name='teacherprogress',
            name='teacher_pro_teacher_898779_idx',
        ),
        migrations.RemoveIndex(
            model_name='teacherprogress',
            name='teacher_pro_course__2629c9_idx',
        ),
        migrations.AddIndex(
            model_name='teacherprogress',
            index=models.Index(
                fields=['tenant', 'teacher', 'course'],
                name='teacher_pro_tenant__tc_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='teacherprogress',
            index=models.Index(
                fields=['tenant', 'teacher', 'status'],
                name='teacher_pro_tenant__ts_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='teacherprogress',
            index=models.Index(
                fields=['tenant', 'course', 'status'],
                name='teacher_pro_tenant__cs_idx',
            ),
        ),
        # CHECK constraint: progress_percentage must be between 0 and 100.
        migrations.AddConstraint(
            model_name='teacherprogress',
            constraint=models.CheckConstraint(
                check=models.Q(progress_percentage__gte=0) & models.Q(progress_percentage__lte=100),
                name='teacher_progress_percentage_valid_range',
            ),
        ),

        # ── Assignment ─────────────────────────────────────────────────────
        migrations.AddField(
            model_name='assignment',
            name='tenant',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='assignments',
                to='tenants.tenant',
            ),
        ),
        migrations.RemoveIndex(
            model_name='assignment',
            name='assignments_course__eb2ee8_idx',
        ),
        migrations.RemoveIndex(
            model_name='assignment',
            name='assignments_due_dat_c68cce_idx',
        ),
        migrations.AddIndex(
            model_name='assignment',
            index=models.Index(
                fields=['tenant', 'course', 'is_active'],
                name='assignments_tenant__ca_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='assignment',
            index=models.Index(
                fields=['tenant', 'due_date', 'is_active'],
                name='assignments_tenant__da_idx',
            ),
        ),

        # ── Quiz ───────────────────────────────────────────────────────────
        migrations.AddField(
            model_name='quiz',
            name='tenant',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='quizzes',
                to='tenants.tenant',
            ),
        ),

        # ── QuizQuestion ───────────────────────────────────────────────────
        migrations.AddField(
            model_name='quizquestion',
            name='tenant',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='quiz_questions',
                to='tenants.tenant',
            ),
        ),
        migrations.AddIndex(
            model_name='quizquestion',
            index=models.Index(
                fields=['tenant', 'quiz'],
                name='quiz_questi_tenant__q_idx',
            ),
        ),

        # ── QuizSubmission ─────────────────────────────────────────────────
        migrations.AddField(
            model_name='quizsubmission',
            name='tenant',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='quiz_submissions',
                to='tenants.tenant',
            ),
        ),
        migrations.RemoveIndex(
            model_name='quizsubmission',
            name='quiz_submis_teacher_9323d4_idx',
        ),
        migrations.AddIndex(
            model_name='quizsubmission',
            index=models.Index(
                fields=['tenant', 'teacher', 'submitted_at'],
                name='quiz_submis_tenant__ts_idx',
            ),
        ),

        # ── AssignmentSubmission ───────────────────────────────────────────
        migrations.AddField(
            model_name='assignmentsubmission',
            name='tenant',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='assignment_submissions',
                to='tenants.tenant',
            ),
        ),
        migrations.RemoveIndex(
            model_name='assignmentsubmission',
            name='assignment__assignm_68808b_idx',
        ),
        migrations.RemoveIndex(
            model_name='assignmentsubmission',
            name='assignment__teacher_0372b4_idx',
        ),
        migrations.AddIndex(
            model_name='assignmentsubmission',
            index=models.Index(
                fields=['tenant', 'assignment', 'status'],
                name='assgn_sub_tenant__as_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='assignmentsubmission',
            index=models.Index(
                fields=['tenant', 'teacher', 'status'],
                name='assgn_sub_tenant__ts_idx',
            ),
        ),

        # ── TeacherQuestClaim ──────────────────────────────────────────────
        migrations.AddField(
            model_name='teacherquestclaim',
            name='tenant',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='teacher_quest_claims',
                to='tenants.tenant',
            ),
        ),
        migrations.RemoveIndex(
            model_name='teacherquestclaim',
            name='teacher_que_teacher_ab6699_idx',
        ),
        migrations.RemoveIndex(
            model_name='teacherquestclaim',
            name='teacher_que_teacher_01435d_idx',
        ),
        migrations.AddIndex(
            model_name='teacherquestclaim',
            index=models.Index(
                fields=['tenant', 'teacher', 'claim_date'],
                name='teacher_que_tenant__tcd_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='teacherquestclaim',
            index=models.Index(
                fields=['tenant', 'teacher', 'quest_key'],
                name='teacher_que_tenant__tqk_idx',
            ),
        ),
    ]
