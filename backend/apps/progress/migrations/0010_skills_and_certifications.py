# Migration: Add Skills Matrix and Certification Management models
#
# New tables:
#   - skills: Competency/skill definitions (tenant-scoped)
#   - course_skills: Maps skills to courses with level_taught
#   - teacher_skills: Tracks teacher proficiency per skill
#   - certification_types: Defines certification templates (tenant-scoped)
#   - teacher_certifications: Tracks issued certifications with expiry

import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('progress', '0009_add_tenant_isolation_to_progress_models'),
        ('tenants', '0001_initial'),
        ('courses', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── Skill ──────────────────────────────────────────────────────
        migrations.CreateModel(
            name='Skill',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('category', models.CharField(blank=True, max_length=100)),
                ('level_required', models.IntegerField(
                    default=1,
                    help_text='Required proficiency level (1-5)',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ],
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='skills',
                    to='tenants.tenant',
                )),
            ],
            options={
                'db_table': 'skills',
                'ordering': ['category', 'name'],
            },
        ),
        migrations.AddConstraint(
            model_name='skill',
            constraint=models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='unique_skill_per_tenant',
            ),
        ),
        migrations.AddIndex(
            model_name='skill',
            index=models.Index(fields=['tenant', 'category'], name='skill_tenant_category_idx'),
        ),
        migrations.AddIndex(
            model_name='skill',
            index=models.Index(fields=['tenant', 'name'], name='skill_tenant_name_idx'),
        ),

        # ── CourseSkill ────────────────────────────────────────────────
        migrations.CreateModel(
            name='CourseSkill',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('level_taught', models.IntegerField(
                    default=1,
                    help_text='Proficiency level this course teaches (1-5)',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ],
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('course', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='course_skills',
                    to='courses.course',
                )),
                ('skill', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='course_skills',
                    to='progress.skill',
                )),
            ],
            options={
                'db_table': 'course_skills',
            },
        ),
        migrations.AddConstraint(
            model_name='courseskill',
            constraint=models.UniqueConstraint(
                fields=['course', 'skill'],
                name='unique_course_skill',
            ),
        ),
        migrations.AddIndex(
            model_name='courseskill',
            index=models.Index(fields=['course', 'skill'], name='courseskill_course_skill_idx'),
        ),
        migrations.AddIndex(
            model_name='courseskill',
            index=models.Index(fields=['skill', 'level_taught'], name='courseskill_skill_level_idx'),
        ),

        # ── TeacherSkill ───────────────────────────────────────────────
        migrations.CreateModel(
            name='TeacherSkill',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('current_level', models.IntegerField(
                    default=0,
                    help_text='Current proficiency level (0=not assessed, 1-5)',
                    validators=[
                        django.core.validators.MinValueValidator(0),
                        django.core.validators.MaxValueValidator(5),
                    ],
                )),
                ('target_level', models.IntegerField(
                    default=1,
                    help_text='Target proficiency level (1-5)',
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(5),
                    ],
                )),
                ('last_assessed', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('teacher', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='teacher_skills',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('skill', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='teacher_skills',
                    to='progress.skill',
                )),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='teacher_skills',
                    to='tenants.tenant',
                )),
            ],
            options={
                'db_table': 'teacher_skills',
                'ordering': ['skill__category', 'skill__name'],
            },
        ),
        migrations.AddConstraint(
            model_name='teacherskill',
            constraint=models.UniqueConstraint(
                fields=['teacher', 'skill'],
                name='unique_teacher_skill',
            ),
        ),
        migrations.AddIndex(
            model_name='teacherskill',
            index=models.Index(fields=['tenant', 'teacher'], name='teacherskill_tenant_teacher_idx'),
        ),
        migrations.AddIndex(
            model_name='teacherskill',
            index=models.Index(fields=['tenant', 'skill'], name='teacherskill_tenant_skill_idx'),
        ),
        migrations.AddIndex(
            model_name='teacherskill',
            index=models.Index(fields=['teacher', 'current_level'], name='teacherskill_teacher_level_idx'),
        ),

        # ── CertificationType ─────────────────────────────────────────
        migrations.CreateModel(
            name='CertificationType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('validity_months', models.IntegerField(
                    default=12,
                    help_text='Number of months the certification is valid',
                )),
                ('auto_renew', models.BooleanField(
                    default=False,
                    help_text='Automatically renew when expired (if all required courses are completed)',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='certification_types',
                    to='tenants.tenant',
                )),
                ('required_courses', models.ManyToManyField(
                    blank=True,
                    related_name='required_for_certifications',
                    to='courses.course',
                    help_text='Courses that must be completed for this certification',
                )),
            ],
            options={
                'db_table': 'certification_types',
                'ordering': ['name'],
            },
        ),
        migrations.AddConstraint(
            model_name='certificationtype',
            constraint=models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='unique_certtype_per_tenant',
            ),
        ),
        migrations.AddIndex(
            model_name='certificationtype',
            index=models.Index(fields=['tenant', 'name'], name='certtype_tenant_name_idx'),
        ),

        # ── TeacherCertification ───────────────────────────────────────
        migrations.CreateModel(
            name='TeacherCertification',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('issued_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('status', models.CharField(
                    choices=[
                        ('active', 'Active'),
                        ('expired', 'Expired'),
                        ('revoked', 'Revoked'),
                        ('pending_renewal', 'Pending Renewal'),
                    ],
                    default='active',
                    max_length=20,
                )),
                ('certificate_file', models.FileField(
                    blank=True,
                    null=True,
                    upload_to='certificates/',
                )),
                ('revoked_reason', models.TextField(blank=True, default='')),
                ('renewal_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('teacher', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='teacher_certifications',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('certification_type', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='issued_certifications',
                    to='progress.certificationtype',
                )),
                ('tenant', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='teacher_certifications',
                    to='tenants.tenant',
                )),
                ('issued_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='issued_certifications',
                    to=settings.AUTH_USER_MODEL,
                    help_text='Admin who issued this certification',
                )),
            ],
            options={
                'db_table': 'teacher_certifications',
                'ordering': ['-issued_at'],
            },
        ),
        migrations.AddIndex(
            model_name='teachercertification',
            index=models.Index(fields=['tenant', 'teacher', 'status'], name='tcert_tenant_teacher_status_idx'),
        ),
        migrations.AddIndex(
            model_name='teachercertification',
            index=models.Index(fields=['tenant', 'certification_type', 'status'], name='tcert_tenant_type_status_idx'),
        ),
        migrations.AddIndex(
            model_name='teachercertification',
            index=models.Index(fields=['expires_at', 'status'], name='tcert_expires_status_idx'),
        ),
        migrations.AddIndex(
            model_name='teachercertification',
            index=models.Index(fields=['tenant', 'expires_at'], name='tcert_tenant_expires_idx'),
        ),
    ]
