# apps/discussions/tests.py
"""
Comprehensive tests for the discussions app.

Covers:
- Thread list/create/detail/update/delete
- Cross-tenant isolation (security)
- Reply create/edit/delete
- Reply likes and moderation
- Thread subscribe/unsubscribe
- Auth requirements for all endpoints
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.discussions.models import (
    DiscussionThread,
    DiscussionReply,
    DiscussionLike,
    DiscussionSubscription,
)


def _make_tenant(name, slug, subdomain, email):
    return Tenant.objects.create(
        name=name, slug=slug, subdomain=subdomain, email=email
    )


def _make_user(email, password, tenant, role='TEACHER', first='Test', last='User'):
    return User.objects.create_user(
        email=email, password=password,
        first_name=first, last_name=last,
        tenant=tenant, role=role,
    )


def _auth(user):
    """Return an APIClient force-authenticated as the given user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


HOST_A = 'test.lms.com'
HOST_B = 'other.lms.com'


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class DiscussionThreadAuthTestCase(TestCase):
    """Tests that all thread endpoints require authentication."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'disc-auth', 'test', 'a@test.com')
        self.client = APIClient()

    def test_list_threads_requires_auth(self):
        response = self.client.get('/api/v1/discussions/threads/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 401)

    def test_create_thread_requires_auth(self):
        response = self.client.post(
            '/api/v1/discussions/threads/',
            {'title': 'Hello', 'body': 'World'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 401)


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class DiscussionThreadCRUDTestCase(TestCase):
    """Tests for thread creation, reading, updating and deletion."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'disc-crud', 'test', 'admin@disctest.com')
        self.admin = _make_user('admin@disctest.com', 'pass123', self.tenant, role='SCHOOL_ADMIN', first='Admin')
        self.teacher = _make_user('teacher@disctest.com', 'pass123', self.tenant, role='TEACHER', first='Teacher')

    # ------------------------------------------------------------------ #
    # Create thread                                                        #
    # ------------------------------------------------------------------ #

    def test_create_thread_as_teacher(self):
        client = _auth(self.teacher)
        response = client.post(
            '/api/v1/discussions/threads/',
            {'title': 'New Thread', 'body': 'Thread body content here.'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['title'], 'New Thread')

    def test_create_thread_as_admin(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/discussions/threads/',
            {'title': 'Admin Thread', 'body': 'Admin body.'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)

    def test_create_thread_requires_title(self):
        client = _auth(self.teacher)
        response = client.post(
            '/api/v1/discussions/threads/',
            {'body': 'No title here.'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)

    def test_create_thread_requires_body(self):
        client = _auth(self.teacher)
        response = client.post(
            '/api/v1/discussions/threads/',
            {'title': 'No body thread'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_thread_auto_subscribes_author(self):
        """Creating a thread should auto-subscribe the author."""
        client = _auth(self.teacher)
        response = client.post(
            '/api/v1/discussions/threads/',
            {'title': 'Auto-subscribe Thread', 'body': 'Some content.'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        thread_id = response.data['id']
        thread = DiscussionThread.objects.get(id=thread_id)
        self.assertTrue(
            DiscussionSubscription.objects.filter(thread=thread, user=self.teacher).exists()
        )

    # ------------------------------------------------------------------ #
    # List threads                                                         #
    # ------------------------------------------------------------------ #

    def test_list_threads_returns_paginated_response(self):
        DiscussionThread.objects.create(
            tenant=self.tenant, title='T1', body='B1', author=self.teacher
        )
        client = _auth(self.teacher)
        response = client.get('/api/v1/discussions/threads/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)

    def test_list_threads_filters_by_status(self):
        DiscussionThread.objects.create(
            tenant=self.tenant, title='Open', body='B', author=self.teacher, status='open'
        )
        DiscussionThread.objects.create(
            tenant=self.tenant, title='Closed', body='B', author=self.teacher, status='closed'
        )
        client = _auth(self.teacher)
        response = client.get('/api/v1/discussions/threads/?status=closed', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        titles = [t['title'] for t in response.data['results']]
        self.assertIn('Closed', titles)
        self.assertNotIn('Open', titles)

    # ------------------------------------------------------------------ #
    # Thread detail                                                        #
    # ------------------------------------------------------------------ #

    def test_get_thread_detail_increments_view_count(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='View Thread', body='Body', author=self.teacher
        )
        self.assertEqual(thread.view_count, 0)

        client = _auth(self.teacher)
        response = client.get(
            f'/api/v1/discussions/threads/{thread.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)

        thread.refresh_from_db()
        self.assertEqual(thread.view_count, 1)

    def test_get_thread_detail_shows_subscription_status(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Sub Thread', body='Body', author=self.teacher
        )
        client = _auth(self.teacher)
        response = client.get(
            f'/api/v1/discussions/threads/{thread.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('is_subscribed', response.data)

    def test_get_thread_detail_shows_can_edit_and_can_delete(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Perm Thread', body='Body', author=self.teacher
        )
        client = _auth(self.teacher)
        response = client.get(
            f'/api/v1/discussions/threads/{thread.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('can_edit', response.data)
        self.assertIn('can_delete', response.data)
        # Teacher is author so can edit
        self.assertTrue(response.data['can_edit'])
        # Teacher cannot delete (only admin can)
        self.assertFalse(response.data['can_delete'])

    # ------------------------------------------------------------------ #
    # Update thread                                                        #
    # ------------------------------------------------------------------ #

    def test_author_can_update_thread(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Original', body='Body', author=self.teacher
        )
        client = _auth(self.teacher)
        response = client.put(
            f'/api/v1/discussions/threads/{thread.id}/',
            {'title': 'Updated Title'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Updated Title')

    def test_non_author_teacher_cannot_update_thread(self):
        other_teacher = _make_user('other@disctest.com', 'pass', self.tenant, first='Other')
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Original', body='Body', author=self.teacher
        )
        client = _auth(other_teacher)
        response = client.put(
            f'/api/v1/discussions/threads/{thread.id}/',
            {'title': 'Hijacked'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_can_update_any_thread(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Teacher Thread', body='Body', author=self.teacher
        )
        client = _auth(self.admin)
        response = client.put(
            f'/api/v1/discussions/threads/{thread.id}/',
            {'status': 'closed', 'is_pinned': True},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'closed')

    # ------------------------------------------------------------------ #
    # Delete thread                                                        #
    # ------------------------------------------------------------------ #

    def test_teacher_cannot_delete_thread(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='To Delete', body='Body', author=self.teacher
        )
        client = _auth(self.teacher)
        response = client.delete(
            f'/api/v1/discussions/threads/{thread.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(DiscussionThread.objects.filter(id=thread.id).exists())

    def test_admin_can_delete_any_thread(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Admin Delete', body='Body', author=self.teacher
        )
        client = _auth(self.admin)
        response = client.delete(
            f'/api/v1/discussions/threads/{thread.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(DiscussionThread.objects.filter(id=thread.id).exists())


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class DiscussionCrossTenantIsolationTestCase(TestCase):
    """Security tests: tenant A data must not be accessible by tenant B users."""

    def setUp(self):
        self.tenant_a = _make_tenant('School A', 'disc-a', 'test', 'a@a.com')
        self.tenant_b = _make_tenant('School B', 'disc-b', 'other', 'b@b.com')

        self.user_a = _make_user('user@a.com', 'pass', self.tenant_a)
        self.user_b = _make_user('user@b.com', 'pass', self.tenant_b)

        self.thread_a = DiscussionThread.objects.create(
            tenant=self.tenant_a, title='A Thread', body='Private to A', author=self.user_a
        )

    def test_list_threads_excludes_other_tenant_data(self):
        """Tenant B's user sees zero threads when scoped to Tenant A's host."""
        client = _auth(self.user_b)
        response = client.get('/api/v1/discussions/threads/', HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 200)
        thread_ids = [t['id'] for t in response.data.get('results', [])]
        # Tenant A's thread must NOT appear in Tenant B's scope
        self.assertNotIn(str(self.thread_a.id), thread_ids)

    def test_cross_tenant_user_gets_403_accessing_tenant_a_host(self):
        """User from Tenant B gets 403 when hitting Tenant A's host."""
        client = _auth(self.user_b)
        response = client.get(
            f'/api/v1/discussions/threads/{self.thread_a.id}/',
            HTTP_HOST=HOST_A,  # Tenant A's host
        )
        self.assertEqual(response.status_code, 403)


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class DiscussionReplyTestCase(TestCase):
    """Tests for reply creation, editing, deletion, and likes."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'disc-reply', 'test', 'r@test.com')
        self.teacher = _make_user('teacher@reply.com', 'pass', self.tenant)
        self.other_teacher = _make_user('other@reply.com', 'pass', self.tenant, first='Other')
        self.admin = _make_user('admin@reply.com', 'pass', self.tenant, role='SCHOOL_ADMIN')

        self.thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Reply Thread', body='Body', author=self.teacher
        )

    # ------------------------------------------------------------------ #
    # Create reply                                                        #
    # ------------------------------------------------------------------ #

    def test_create_reply_to_open_thread(self):
        client = _auth(self.teacher)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/',
            {'body': 'Great post!'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['body'], 'Great post!')

    def test_create_reply_requires_body(self):
        client = _auth(self.teacher)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/',
            {},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_reply_on_closed_thread_fails(self):
        self.thread.status = 'closed'
        self.thread.save()

        client = _auth(self.teacher)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/',
            {'body': 'Replying on closed thread.'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('closed', response.data.get('error', '').lower())

    def test_create_reply_updates_thread_reply_count(self):
        client = _auth(self.teacher)
        client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/',
            {'body': 'First reply.'},
            HTTP_HOST=HOST_A,
        )
        self.thread.refresh_from_db()
        self.assertEqual(self.thread.reply_count, 1)

    def test_create_nested_reply(self):
        parent_reply = DiscussionReply.objects.create(
            thread=self.thread, body='Parent reply', author=self.teacher
        )
        client = _auth(self.other_teacher)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/',
            {'body': 'Nested reply', 'parent_id': str(parent_reply.id)},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)

    # ------------------------------------------------------------------ #
    # Edit reply                                                          #
    # ------------------------------------------------------------------ #

    def test_author_can_edit_own_reply(self):
        reply = DiscussionReply.objects.create(
            thread=self.thread, body='Original', author=self.teacher
        )
        client = _auth(self.teacher)
        response = client.put(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{reply.id}/',
            {'body': 'Edited reply'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_edited'])

    def test_non_author_cannot_edit_reply(self):
        reply = DiscussionReply.objects.create(
            thread=self.thread, body='Original', author=self.teacher
        )
        client = _auth(self.other_teacher)
        response = client.put(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{reply.id}/',
            {'body': 'Attempted edit'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------ #
    # Delete reply                                                        #
    # ------------------------------------------------------------------ #

    def test_author_can_delete_own_reply(self):
        reply = DiscussionReply.objects.create(
            thread=self.thread, body='Delete me', author=self.teacher
        )
        client = _auth(self.teacher)
        response = client.delete(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{reply.id}/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(DiscussionReply.objects.filter(id=reply.id).exists())

    def test_admin_can_delete_any_reply(self):
        reply = DiscussionReply.objects.create(
            thread=self.thread, body='Admin deletes this', author=self.teacher
        )
        client = _auth(self.admin)
        response = client.delete(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{reply.id}/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 204)

    def test_other_teacher_cannot_delete_reply(self):
        reply = DiscussionReply.objects.create(
            thread=self.thread, body='My reply', author=self.teacher
        )
        client = _auth(self.other_teacher)
        response = client.delete(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{reply.id}/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------ #
    # Likes                                                               #
    # ------------------------------------------------------------------ #

    def test_like_reply(self):
        reply = DiscussionReply.objects.create(
            thread=self.thread, body='Like me', author=self.teacher
        )
        client = _auth(self.other_teacher)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{reply.id}/like/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['liked'])
        self.assertEqual(response.data['like_count'], 1)

    def test_unlike_reply(self):
        reply = DiscussionReply.objects.create(
            thread=self.thread, body='Unlike me', author=self.teacher, like_count=1
        )
        DiscussionLike.objects.create(reply=reply, user=self.other_teacher)

        client = _auth(self.other_teacher)
        response = client.delete(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{reply.id}/like/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['liked'])
        self.assertEqual(response.data['like_count'], 0)

    def test_double_like_is_idempotent(self):
        """Liking again doesn't increment count twice."""
        reply = DiscussionReply.objects.create(
            thread=self.thread, body='Double like', author=self.teacher
        )
        client = _auth(self.other_teacher)
        client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{reply.id}/like/',
            HTTP_HOST=HOST_A,
        )
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{reply.id}/like/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['like_count'], 1)


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class DiscussionModerationTestCase(TestCase):
    """Tests for admin moderation of replies."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'disc-mod', 'test', 'mod@test.com')
        self.admin = _make_user('admin@mod.com', 'pass', self.tenant, role='SCHOOL_ADMIN')
        self.teacher = _make_user('teacher@mod.com', 'pass', self.tenant)
        self.thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Mod Thread', body='Body', author=self.teacher
        )
        self.reply = DiscussionReply.objects.create(
            thread=self.thread, body='Bad content', author=self.teacher
        )

    def test_admin_can_hide_reply(self):
        client = _auth(self.admin)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{self.reply.id}/moderate/',
            {'action': 'hide', 'reason': 'Violates guidelines'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['hidden'])
        self.reply.refresh_from_db()
        self.assertTrue(self.reply.is_hidden)

    def test_admin_can_unhide_reply(self):
        self.reply.is_hidden = True
        self.reply.save()

        client = _auth(self.admin)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{self.reply.id}/moderate/',
            {'action': 'unhide'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['hidden'])

    def test_teacher_cannot_moderate_reply(self):
        client = _auth(self.teacher)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{self.reply.id}/moderate/',
            {'action': 'hide'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 403)

    def test_invalid_moderation_action_returns_400(self):
        client = _auth(self.admin)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/replies/{self.reply.id}/moderate/',
            {'action': 'invalidaction'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class DiscussionSubscriptionTestCase(TestCase):
    """Tests for thread subscription management."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'disc-sub', 'test', 'sub@test.com')
        self.teacher = _make_user('teacher@sub.com', 'pass', self.tenant)
        self.thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Sub Thread', body='Body', author=self.teacher
        )

    def test_subscribe_to_thread(self):
        client = _auth(self.teacher)
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/subscribe/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['subscribed'])
        self.assertTrue(
            DiscussionSubscription.objects.filter(
                thread=self.thread, user=self.teacher
            ).exists()
        )

    def test_unsubscribe_from_thread(self):
        DiscussionSubscription.objects.create(thread=self.thread, user=self.teacher)
        client = _auth(self.teacher)
        response = client.delete(
            f'/api/v1/discussions/threads/{self.thread.id}/subscribe/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['subscribed'])
        self.assertFalse(
            DiscussionSubscription.objects.filter(
                thread=self.thread, user=self.teacher
            ).exists()
        )

    def test_subscribe_twice_is_idempotent(self):
        client = _auth(self.teacher)
        client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/subscribe/',
            HTTP_HOST=HOST_A,
        )
        response = client.post(
            f'/api/v1/discussions/threads/{self.thread.id}/subscribe/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            DiscussionSubscription.objects.filter(
                thread=self.thread, user=self.teacher
            ).count(),
            1,
        )


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class DiscussionModelTestCase(TestCase):
    """Unit tests for Discussion model methods."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'disc-model', 'test', 'model@test.com')
        self.teacher = _make_user('teacher@model.com', 'pass', self.tenant)

    def test_thread_str(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Model Thread', body='Body', author=self.teacher
        )
        self.assertEqual(str(thread), 'Model Thread')

    def test_reply_depth_top_level_is_zero(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Depth Thread', body='Body', author=self.teacher
        )
        reply = DiscussionReply.objects.create(
            thread=thread, body='Top-level reply', author=self.teacher
        )
        self.assertEqual(reply.depth, 0)

    def test_reply_depth_nested_is_correct(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Nested Thread', body='Body', author=self.teacher
        )
        level0 = DiscussionReply.objects.create(
            thread=thread, body='Level 0', author=self.teacher
        )
        level1 = DiscussionReply.objects.create(
            thread=thread, body='Level 1', author=self.teacher, parent=level0
        )
        level2 = DiscussionReply.objects.create(
            thread=thread, body='Level 2', author=self.teacher, parent=level1
        )
        self.assertEqual(level1.depth, 1)
        self.assertEqual(level2.depth, 2)

    def test_update_reply_stats_on_thread(self):
        thread = DiscussionThread.objects.create(
            tenant=self.tenant, title='Stats Thread', body='Body', author=self.teacher
        )
        DiscussionReply.objects.create(
            thread=thread, body='Reply 1', author=self.teacher
        )
        DiscussionReply.objects.create(
            thread=thread, body='Reply 2', author=self.teacher
        )
        thread.update_reply_stats()
        self.assertEqual(thread.reply_count, 2)
        self.assertIsNotNone(thread.last_reply_at)
