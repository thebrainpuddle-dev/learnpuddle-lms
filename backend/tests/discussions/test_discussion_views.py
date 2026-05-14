# tests/discussions/test_discussion_views.py
"""
Tests for the discussions app.

Covers generic (role-agnostic) discussion endpoints:
- /api/v1/discussions/threads/ — list & create
- /api/v1/discussions/threads/{id}/ — retrieve, update, delete
- /api/v1/discussions/threads/{id}/replies/ — create reply
- /api/v1/discussions/threads/{id}/replies/{id}/ — edit/delete reply
- /api/v1/discussions/threads/{id}/replies/{id}/like/ — like/unlike
- /api/v1/discussions/threads/{id}/replies/{id}/moderate/ — hide/unhide (admin-only)
- /api/v1/discussions/threads/{id}/subscribe/ — subscribe/unsubscribe

Also covers teacher views:
- /api/v1/teacher/discussions/threads/ — teacher thread list
- /api/v1/teacher/discussions/sections/ — teacher sections list

Tenant isolation and authentication are tested throughout.
"""

import pytest
from rest_framework.test import APIClient

from apps.discussions.models import (
    DiscussionThread,
    DiscussionReply,
    DiscussionLike,
    DiscussionSubscription,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_section(tenant):
    """Create the minimum real academic section required by discussion threads."""
    from apps.academics.models import GradeBand, Grade, Section

    band, _ = GradeBand.all_objects.get_or_create(
        tenant=tenant,
        short_code="DISC",
        defaults={"name": "Discussion Band", "order": 1},
    )
    grade, _ = Grade.all_objects.get_or_create(
        tenant=tenant,
        short_code="DISC",
        defaults={"grade_band": band, "name": "Discussion Grade", "order": 1},
    )
    section, _ = Section.all_objects.get_or_create(
        tenant=tenant,
        grade=grade,
        name="A",
        academic_year="2026-27",
    )
    return section


def _thread_payload(tenant, **overrides):
    payload = {
        "title": "New Thread",
        "body": "Thread content here",
        "section_id": str(_make_section(tenant).id),
    }
    payload.update(overrides)
    return payload


def _make_thread(tenant, user, title="Test Thread", body="Test body", section=None):
    """Create a DiscussionThread directly with the required section scope."""
    return DiscussionThread.objects.create(
        tenant=tenant,
        section=section or _make_section(tenant),
        title=title,
        body=body,
        author=user,
    )


def _make_reply(thread, user, body="A reply"):
    """Create a DiscussionReply on an open thread."""
    reply = DiscussionReply.objects.create(
        thread=thread,
        body=body,
        author=user,
    )
    thread.reply_count += 1
    thread.save(update_fields=["reply_count"])
    return reply


# ---------------------------------------------------------------------------
# Authentication Tests
# ---------------------------------------------------------------------------

class TestDiscussionAuthRequired:
    """All discussion endpoints require authentication."""

    def test_thread_list_requires_auth(self, api_client, tenant):
        response = api_client.get(
            "/api/v1/discussions/threads/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401

    def test_thread_create_requires_auth(self, api_client, tenant):
        response = api_client.post(
            "/api/v1/discussions/threads/",
            data={"title": "T", "body": "B"},
            format="json",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401

    def test_teacher_thread_list_requires_auth(self, api_client, tenant):
        response = api_client.get(
            "/api/v1/teacher/discussions/threads/",
            HTTP_HOST=f"{tenant.subdomain}.lms.com",
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Thread List Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestThreadList:
    """GET /api/v1/discussions/threads/"""

    def test_admin_can_list_threads(self, admin_client):
        response = admin_client.get("/api/v1/discussions/threads/")
        assert response.status_code == 200

    def test_teacher_can_list_threads(self, teacher_client):
        response = teacher_client.get("/api/v1/discussions/threads/")
        assert response.status_code == 200

    def test_list_returns_paginated_results(self, admin_client, admin_user, tenant):
        _make_thread(tenant, admin_user, title="Thread 1")
        _make_thread(tenant, admin_user, title="Thread 2")
        response = admin_client.get("/api/v1/discussions/threads/")
        assert response.status_code == 200
        assert "results" in response.data
        assert len(response.data["results"]) >= 2

    def test_list_shows_only_tenant_threads(
        self, admin_client, admin_user, tenant, admin_user_b, tenant_b
    ):
        """Threads from tenant B must not appear in tenant A's list."""
        _make_thread(tenant, admin_user, title="Tenant A Thread")
        _make_thread(tenant_b, admin_user_b, title="Tenant B Secret Thread")
        response = admin_client.get("/api/v1/discussions/threads/")
        assert response.status_code == 200
        titles = [t["title"] for t in response.data["results"]]
        assert "Tenant A Thread" in titles
        assert "Tenant B Secret Thread" not in titles

    def test_filter_by_status(self, admin_client, admin_user, tenant):
        _make_thread(tenant, admin_user, title="Open Thread")
        closed = _make_thread(tenant, admin_user, title="Closed Thread")
        closed.status = "closed"
        closed.save()
        response = admin_client.get("/api/v1/discussions/threads/?status=open")
        assert response.status_code == 200
        titles = [t["title"] for t in response.data["results"]]
        assert "Open Thread" in titles
        assert "Closed Thread" not in titles

    def test_threads_have_required_fields(self, admin_client, admin_user, tenant):
        _make_thread(tenant, admin_user, title="Field Test Thread")
        response = admin_client.get("/api/v1/discussions/threads/")
        assert response.status_code == 200
        assert len(response.data["results"]) > 0
        thread = response.data["results"][0]
        assert "id" in thread
        assert "title" in thread
        assert "author" in thread
        assert "status" in thread
        assert "reply_count" in thread
        assert "created_at" in thread


# ---------------------------------------------------------------------------
# Thread Create Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestThreadCreate:
    """POST /api/v1/discussions/threads/"""

    def test_admin_can_create_thread(self, admin_client, tenant):
        response = admin_client.post(
            "/api/v1/discussions/threads/",
            data=_thread_payload(tenant, title="New Thread", body="Thread content here"),
            format="json",
        )
        assert response.status_code == 201
        assert response.data["title"] == "New Thread"

    def test_teacher_can_create_thread(self, teacher_client, tenant):
        response = teacher_client.post(
            "/api/v1/discussions/threads/",
            data=_thread_payload(tenant, title="Teacher Thread", body="Teacher body"),
            format="json",
        )
        assert response.status_code == 201

    def test_create_without_title_returns_400(self, admin_client, tenant):
        response = admin_client.post(
            "/api/v1/discussions/threads/",
            data=_thread_payload(tenant, title="", body="No title"),
            format="json",
        )
        assert response.status_code == 400

    def test_create_without_body_returns_400(self, admin_client, tenant):
        response = admin_client.post(
            "/api/v1/discussions/threads/",
            data=_thread_payload(tenant, title="No body", body=""),
            format="json",
        )
        assert response.status_code == 400

    def test_created_thread_belongs_to_request_tenant(self, admin_client, tenant):
        response = admin_client.post(
            "/api/v1/discussions/threads/",
            data=_thread_payload(tenant, title="Tenant Check Thread", body="Body"),
            format="json",
        )
        assert response.status_code == 201
        thread = DiscussionThread.objects.get(id=response.data["id"])
        assert str(thread.tenant_id) == str(tenant.id)
        assert str(thread.section.tenant_id) == str(tenant.id)

    def test_author_auto_subscribed_on_create(self, admin_client, admin_user, tenant):
        """Author is automatically subscribed to their thread."""
        response = admin_client.post(
            "/api/v1/discussions/threads/",
            data=_thread_payload(tenant, title="Auto Subscribe Thread", body="Body"),
            format="json",
        )
        assert response.status_code == 201
        thread = DiscussionThread.objects.get(id=response.data["id"])
        assert DiscussionSubscription.objects.filter(
            thread=thread, user=admin_user
        ).exists()


# ---------------------------------------------------------------------------
# Thread Detail Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestThreadDetail:
    """GET/PUT/DELETE /api/v1/discussions/threads/{id}/"""

    def test_admin_can_get_thread(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user, title="Detail Thread")
        response = admin_client.get(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 200
        assert response.data["title"] == "Detail Thread"

    def test_teacher_can_get_thread(self, teacher_client, teacher_user, tenant):
        thread = _make_thread(tenant, teacher_user, title="Teacher Thread")
        response = teacher_client.get(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 200

    def test_get_nonexistent_thread_returns_404(self, admin_client):
        import uuid
        response = admin_client.get(f"/api/v1/discussions/threads/{uuid.uuid4()}/")
        assert response.status_code == 404

    def test_get_thread_from_other_tenant_returns_404(
        self, admin_client, admin_user_b, tenant_b
    ):
        thread_b = _make_thread(tenant_b, admin_user_b, title="Tenant B Thread")
        response = admin_client.get(f"/api/v1/discussions/threads/{thread_b.id}/")
        assert response.status_code == 404

    def test_get_increments_view_count(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        initial_views = thread.view_count
        admin_client.get(f"/api/v1/discussions/threads/{thread.id}/")
        thread.refresh_from_db()
        assert thread.view_count == initial_views + 1

    def test_author_can_update_title(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user, title="Old Title")
        response = admin_client.put(
            f"/api/v1/discussions/threads/{thread.id}/",
            data={"title": "New Title"},
            format="json",
        )
        assert response.status_code == 200
        thread.refresh_from_db()
        assert thread.title == "New Title"

    def test_non_author_cannot_update_thread(
        self, teacher_client, admin_user, tenant
    ):
        """Teacher (non-author) cannot update another user's thread."""
        thread = _make_thread(tenant, admin_user, title="Admin Thread")
        response = teacher_client.put(
            f"/api/v1/discussions/threads/{thread.id}/",
            data={"title": "Hijacked"},
            format="json",
        )
        assert response.status_code == 403

    def test_admin_can_delete_thread(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        response = admin_client.delete(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 204
        assert not DiscussionThread.objects.filter(id=thread.id).exists()

    def test_teacher_cannot_delete_thread(
        self, teacher_client, teacher_user, tenant
    ):
        """Teacher cannot delete threads — admin-only."""
        thread = _make_thread(tenant, teacher_user)
        response = teacher_client.delete(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 403

    def test_admin_can_pin_thread(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        response = admin_client.put(
            f"/api/v1/discussions/threads/{thread.id}/",
            data={"is_pinned": True},
            format="json",
        )
        assert response.status_code == 200
        thread.refresh_from_db()
        assert thread.is_pinned is True


# ---------------------------------------------------------------------------
# Reply Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReplyCRUD:
    """POST /api/v1/discussions/threads/{id}/replies/"""

    def test_admin_can_create_reply(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/",
            data={"body": "First reply!"},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["body"] == "First reply!"

    def test_teacher_can_create_reply(self, teacher_client, teacher_user, tenant):
        thread = _make_thread(tenant, teacher_user)
        response = teacher_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/",
            data={"body": "Teacher replies"},
            format="json",
        )
        assert response.status_code == 201

    def test_reply_without_body_returns_400(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/",
            data={},
            format="json",
        )
        assert response.status_code == 400

    def test_reply_to_closed_thread_returns_400(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        thread.status = "closed"
        thread.save()
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/",
            data={"body": "Reply to closed"},
            format="json",
        )
        assert response.status_code == 400

    def test_reply_increments_reply_count(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        initial_count = thread.reply_count
        admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/",
            data={"body": "Counting reply"},
            format="json",
        )
        thread.refresh_from_db()
        assert thread.reply_count == initial_count + 1

    def test_threaded_reply_with_parent_id(self, admin_client, admin_user, tenant):
        """Replies can nest by specifying parent_id."""
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user, body="Parent reply")
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/",
            data={"body": "Nested reply", "parent_id": str(reply.id)},
            format="json",
        )
        assert response.status_code == 201


@pytest.mark.django_db
class TestReplyEditDelete:
    """PUT/DELETE /api/v1/discussions/threads/{id}/replies/{id}/"""

    def test_author_can_edit_reply(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user, body="Original")
        response = admin_client.put(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/",
            data={"body": "Edited"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["is_edited"] is True
        reply.refresh_from_db()
        assert reply.body == "Edited"

    def test_non_author_cannot_edit_reply(
        self, teacher_client, admin_user, teacher_user, tenant
    ):
        """Teacher cannot edit admin's reply."""
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user, body="Admin reply")
        response = teacher_client.put(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/",
            data={"body": "Hijacked"},
            format="json",
        )
        assert response.status_code == 403

    def test_author_can_delete_own_reply(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user, body="To delete")
        response = admin_client.delete(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/"
        )
        assert response.status_code == 204
        assert not DiscussionReply.objects.filter(id=reply.id).exists()

    def test_admin_can_delete_any_reply(
        self, admin_client, admin_user, teacher_user, tenant
    ):
        """Admin can delete any user's reply."""
        thread = _make_thread(tenant, teacher_user)
        reply = _make_reply(thread, teacher_user, body="Teacher's reply")
        response = admin_client.delete(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/"
        )
        assert response.status_code == 204

    def test_non_author_non_admin_cannot_delete_reply(
        self, teacher_client, admin_user, teacher_user, tenant
    ):
        """Teacher cannot delete admin's reply."""
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user, body="Admin's reply")
        response = teacher_client.delete(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/"
        )
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Like Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReplyLikes:
    """POST/DELETE /api/v1/discussions/threads/{id}/replies/{id}/like/"""

    def test_admin_can_like_reply(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user, body="Likeable")
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/like/"
        )
        assert response.status_code == 200
        assert response.data["liked"] is True
        assert response.data["like_count"] == 1

    def test_like_is_idempotent(self, admin_client, admin_user, tenant):
        """Liking twice doesn't double-count."""
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user)
        admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/like/"
        )
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/like/"
        )
        assert response.status_code == 200
        reply.refresh_from_db()
        # Should not double-count
        assert reply.like_count <= 1

    def test_unlike_removes_like(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user)
        # Like first
        admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/like/"
        )
        # Unlike
        response = admin_client.delete(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/like/"
        )
        assert response.status_code == 200
        assert response.data["liked"] is False
        reply.refresh_from_db()
        assert reply.like_count == 0


# ---------------------------------------------------------------------------
# Moderation Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestReplyModeration:
    """POST /api/v1/discussions/threads/{id}/replies/{id}/moderate/"""

    def test_admin_can_hide_reply(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user, body="Problematic reply")
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/moderate/",
            data={"action": "hide", "reason": "spam"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["hidden"] is True
        reply.refresh_from_db()
        assert reply.is_hidden is True

    def test_admin_can_unhide_reply(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user, body="Hidden reply")
        reply.is_hidden = True
        reply.save()
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/moderate/",
            data={"action": "unhide"},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["hidden"] is False

    def test_teacher_cannot_moderate_replies(
        self, teacher_client, teacher_user, tenant
    ):
        """Non-admin users cannot moderate replies."""
        thread = _make_thread(tenant, teacher_user)
        reply = _make_reply(thread, teacher_user, body="Teacher reply")
        response = teacher_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/moderate/",
            data={"action": "hide"},
            format="json",
        )
        assert response.status_code == 403

    def test_invalid_action_returns_400(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        reply = _make_reply(thread, admin_user)
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/{reply.id}/moderate/",
            data={"action": "explode"},
            format="json",
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# Subscription Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestSubscriptions:
    """POST/DELETE /api/v1/discussions/threads/{id}/subscribe/"""

    def test_admin_can_subscribe(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        response = admin_client.post(
            f"/api/v1/discussions/threads/{thread.id}/subscribe/"
        )
        assert response.status_code == 200
        assert response.data["subscribed"] is True
        assert DiscussionSubscription.objects.filter(
            thread=thread, user=admin_user
        ).exists()

    def test_admin_can_unsubscribe(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        DiscussionSubscription.objects.create(thread=thread, user=admin_user)
        response = admin_client.delete(
            f"/api/v1/discussions/threads/{thread.id}/subscribe/"
        )
        assert response.status_code == 200
        assert response.data["subscribed"] is False
        assert not DiscussionSubscription.objects.filter(
            thread=thread, user=admin_user
        ).exists()

    def test_subscribe_is_idempotent(self, admin_client, admin_user, tenant):
        """Subscribing twice doesn't create duplicate subscriptions."""
        thread = _make_thread(tenant, admin_user)
        admin_client.post(f"/api/v1/discussions/threads/{thread.id}/subscribe/")
        admin_client.post(f"/api/v1/discussions/threads/{thread.id}/subscribe/")
        count = DiscussionSubscription.objects.filter(
            thread=thread, user=admin_user
        ).count()
        assert count == 1


# ---------------------------------------------------------------------------
# Thread Detail Response Shape Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestThreadDetailShape:
    """Verify the thread detail serializer shape."""

    def test_thread_detail_has_replies_list(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user, title="Detail Shape Thread")
        _make_reply(thread, admin_user, body="Reply for shape test")
        response = admin_client.get(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 200
        data = response.data
        assert "replies" in data
        assert isinstance(data["replies"], list)

    def test_thread_detail_shows_subscription_status(
        self, admin_client, admin_user, tenant
    ):
        thread = _make_thread(tenant, admin_user)
        response = admin_client.get(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 200
        assert "is_subscribed" in response.data

    def test_thread_detail_shows_can_edit(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        response = admin_client.get(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 200
        assert "can_edit" in response.data

    def test_thread_detail_shows_view_count(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        response = admin_client.get(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 200
        assert "view_count" in response.data

    def test_author_field_has_correct_structure(self, admin_client, admin_user, tenant):
        thread = _make_thread(tenant, admin_user)
        response = admin_client.get(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 200
        author = response.data["author"]
        assert "id" in author
        assert "name" in author
        assert "role" in author


# ---------------------------------------------------------------------------
# Cross-Tenant Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestDiscussionTenantIsolation:
    """Comprehensive cross-tenant isolation for discussions."""

    def test_admin_b_cannot_see_tenant_a_threads(
        self, admin_user, tenant, admin_user_b, tenant_b, api_client_for
    ):
        _make_thread(tenant, admin_user, title="Tenant A Private Thread")
        client_b = api_client_for(admin_user_b, tenant_b)
        response = client_b.get("/api/v1/discussions/threads/")
        assert response.status_code == 200
        titles = [t["title"] for t in response.data["results"]]
        assert "Tenant A Private Thread" not in titles

    def test_admin_b_cannot_access_tenant_a_thread_detail(
        self, admin_user, tenant, admin_user_b, tenant_b, api_client_for
    ):
        thread = _make_thread(tenant, admin_user)
        client_b = api_client_for(admin_user_b, tenant_b)
        response = client_b.get(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 404

    def test_admin_b_cannot_reply_to_tenant_a_thread(
        self, admin_user, tenant, admin_user_b, tenant_b, api_client_for
    ):
        thread = _make_thread(tenant, admin_user)
        client_b = api_client_for(admin_user_b, tenant_b)
        response = client_b.post(
            f"/api/v1/discussions/threads/{thread.id}/replies/",
            data={"body": "Cross-tenant reply"},
            format="json",
        )
        assert response.status_code == 404

    def test_admin_b_cannot_delete_tenant_a_thread(
        self, admin_user, tenant, admin_user_b, tenant_b, api_client_for
    ):
        thread = _make_thread(tenant, admin_user)
        client_b = api_client_for(admin_user_b, tenant_b)
        response = client_b.delete(f"/api/v1/discussions/threads/{thread.id}/")
        assert response.status_code == 404
        # Thread still exists
        assert DiscussionThread.objects.filter(id=thread.id).exists()
