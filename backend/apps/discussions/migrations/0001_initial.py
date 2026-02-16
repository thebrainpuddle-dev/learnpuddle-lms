# Initial migration for discussions app

import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("tenants", "0004_tenant_sso_2fa_custom_domain"),
        ("courses", "0006_course_soft_delete_search_vector"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── DiscussionThread ────────────────────────────────────────────
        migrations.CreateModel(
            name="DiscussionThread",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=300)),
                ("body", models.TextField()),
                ("status", models.CharField(choices=[("open", "Open"), ("closed", "Closed"), ("archived", "Archived")], default="open", max_length=20)),
                ("is_pinned", models.BooleanField(default=False)),
                ("is_announcement", models.BooleanField(default=False)),
                ("reply_count", models.PositiveIntegerField(default=0)),
                ("view_count", models.PositiveIntegerField(default=0)),
                ("last_reply_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="discussion_threads", to="tenants.tenant")),
                ("course", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="discussion_threads", to="courses.course")),
                ("content", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="discussion_threads", to="courses.content")),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="started_threads", to=settings.AUTH_USER_MODEL)),
                ("last_reply_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "discussion_threads",
                "ordering": ["-is_pinned", "-last_reply_at", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="discussionthread",
            index=models.Index(fields=["tenant", "course", "status"], name="dt_tenant_course_status_idx"),
        ),
        migrations.AddIndex(
            model_name="discussionthread",
            index=models.Index(fields=["tenant", "content", "status"], name="dt_tenant_content_status_idx"),
        ),
        migrations.AddIndex(
            model_name="discussionthread",
            index=models.Index(fields=["author", "created_at"], name="dt_author_created_idx"),
        ),

        # ── DiscussionReply ─────────────────────────────────────────────
        migrations.CreateModel(
            name="DiscussionReply",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("body", models.TextField()),
                ("is_hidden", models.BooleanField(default=False)),
                ("hidden_reason", models.CharField(blank=True, max_length=200)),
                ("is_edited", models.BooleanField(default=False)),
                ("edited_at", models.DateTimeField(blank=True, null=True)),
                ("like_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("thread", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="replies", to="discussions.discussionthread")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="children", to="discussions.discussionreply")),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="discussion_replies", to=settings.AUTH_USER_MODEL)),
                ("hidden_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="hidden_replies", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "discussion_replies",
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="discussionreply",
            index=models.Index(fields=["thread", "created_at"], name="dr_thread_created_idx"),
        ),
        migrations.AddIndex(
            model_name="discussionreply",
            index=models.Index(fields=["author", "created_at"], name="dr_author_created_idx"),
        ),
        migrations.AddIndex(
            model_name="discussionreply",
            index=models.Index(fields=["parent"], name="dr_parent_idx"),
        ),

        # ── DiscussionLike ──────────────────────────────────────────────
        migrations.CreateModel(
            name="DiscussionLike",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reply", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="likes", to="discussions.discussionreply")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="discussion_likes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "discussion_likes",
                "unique_together": {("reply", "user")},
            },
        ),

        # ── DiscussionSubscription ──────────────────────────────────────
        migrations.CreateModel(
            name="DiscussionSubscription",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("notify_on_reply", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("thread", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="subscriptions", to="discussions.discussionthread")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="thread_subscriptions", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "discussion_subscriptions",
                "unique_together": {("thread", "user")},
            },
        ),
    ]
