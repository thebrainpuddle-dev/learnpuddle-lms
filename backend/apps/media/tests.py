# apps/media/tests.py
"""
Comprehensive tests for the media app.

Covers:
- MediaAsset CRUD (admin only)
- Cross-tenant isolation (security)
- Media stats endpoint
- Search/filter functionality
- Soft-delete behavior
- serve_media_file path traversal protection
"""

import io

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.media.models import MediaAsset


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, slug, subdomain, email):
    return Tenant.objects.create(
        name=name, slug=slug, subdomain=subdomain, email=email
    )


def _make_user(email, tenant, role='SCHOOL_ADMIN', first='Admin', last='User'):
    return User.objects.create_user(
        email=email, password='pass123',
        first_name=first, last_name=last,
        tenant=tenant, role=role,
    )


def _make_link_asset(tenant, admin, title='Link Asset', url='https://example.com/asset'):
    return MediaAsset.objects.create(
        tenant=tenant,
        title=title,
        media_type='LINK',
        file_url=url,
        uploaded_by=admin,
    )


def _auth(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


HOST_A = 'test.lms.com'
HOST_B = 'other.lms.com'


# ===========================================================================
# Auth & Role Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class MediaAuthTestCase(TestCase):
    """Tests that media endpoints enforce authentication and admin role."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'media-auth', 'test', 'auth@media.com')
        self.teacher = _make_user('teacher@media.com', self.tenant, role='TEACHER', first='Tea')
        self.client = APIClient()

    def test_list_media_requires_auth(self):
        response = self.client.get('/api/v1/media/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 401)

    def test_create_media_requires_auth(self):
        response = self.client.post(
            '/api/v1/media/',
            {'title': 'New', 'media_type': 'LINK', 'file_url': 'https://x.com'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 401)

    def test_teacher_cannot_list_media(self):
        client = _auth(self.teacher)
        response = client.get('/api/v1/media/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_create_media(self):
        client = _auth(self.teacher)
        response = client.post(
            '/api/v1/media/',
            {'title': 'New', 'media_type': 'LINK', 'file_url': 'https://x.com'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_access_media_stats(self):
        client = _auth(self.teacher)
        response = client.get('/api/v1/media/stats/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 403)


# ===========================================================================
# Media CRUD Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class MediaCRUDTestCase(TestCase):
    """Tests for media list, create, detail, patch, and delete."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'media-crud', 'test', 'crud@media.com')
        self.admin = _make_user('admin@mediacrud.com', self.tenant)

    # ------------------------------------------------------------------ #
    # List                                                                #
    # ------------------------------------------------------------------ #

    def test_list_media_returns_paginated_response(self):
        _make_link_asset(self.tenant, self.admin)
        client = _auth(self.admin)
        response = client.get('/api/v1/media/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertIn('count', response.data)

    def test_list_media_excludes_inactive_assets(self):
        active = _make_link_asset(self.tenant, self.admin, title='Active')
        inactive = _make_link_asset(self.tenant, self.admin, title='Inactive')
        inactive.is_active = False
        inactive.save()

        client = _auth(self.admin)
        response = client.get('/api/v1/media/', HTTP_HOST=HOST_A)
        ids = [a['id'] for a in response.data['results']]
        self.assertIn(str(active.id), ids)
        self.assertNotIn(str(inactive.id), ids)

    def test_list_media_filters_by_media_type(self):
        _make_link_asset(self.tenant, self.admin, title='A Link')
        MediaAsset.objects.create(
            tenant=self.tenant, title='A Video', media_type='VIDEO',
            file_url='https://example.com/vid', uploaded_by=self.admin,
        )
        client = _auth(self.admin)
        response = client.get('/api/v1/media/?media_type=VIDEO', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        for asset in response.data['results']:
            self.assertEqual(asset['media_type'], 'VIDEO')

    def test_search_media_by_title(self):
        _make_link_asset(self.tenant, self.admin, title='Python Tutorial')
        _make_link_asset(self.tenant, self.admin, title='Django Best Practices')
        client = _auth(self.admin)
        response = client.get('/api/v1/media/?search=Python', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        titles = [a['title'] for a in response.data['results']]
        self.assertIn('Python Tutorial', titles)
        self.assertNotIn('Django Best Practices', titles)

    # ------------------------------------------------------------------ #
    # Create                                                              #
    # ------------------------------------------------------------------ #

    def test_create_link_asset(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/media/',
            {
                'title': 'Useful Link',
                'media_type': 'LINK',
                'file_url': 'https://docs.example.com/guide',
            },
            format='json',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['media_type'], 'LINK')

    def test_create_link_asset_requires_file_url(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/media/',
            {'title': 'Link No URL', 'media_type': 'LINK'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_document_asset_requires_file_or_url(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/media/',
            {'title': 'Doc No File', 'media_type': 'DOCUMENT'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_document_asset_from_url(self):
        """A document asset can be created from an existing CDN URL."""
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/media/',
            {
                'title': 'PDF from CDN',
                'media_type': 'DOCUMENT',
                'file_url': 'https://cdn.example.com/tenant/1/file.pdf',
            },
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['media_type'], 'DOCUMENT')

    def test_create_asset_with_tags(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/media/',
            {
                'title': 'Tagged Link',
                'media_type': 'LINK',
                'file_url': 'https://example.com/tagged',
                'tags': ['math', 'grade-9'],
            },
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)

    # ------------------------------------------------------------------ #
    # Detail                                                              #
    # ------------------------------------------------------------------ #

    def test_get_media_detail(self):
        asset = _make_link_asset(self.tenant, self.admin, title='Detail Asset')
        client = _auth(self.admin)
        response = client.get(f'/api/v1/media/{asset.id}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'Detail Asset')
        self.assertIn('id', response.data)
        self.assertIn('media_type', response.data)

    def test_get_nonexistent_media_returns_404(self):
        import uuid
        client = _auth(self.admin)
        response = client.get(f'/api/v1/media/{uuid.uuid4()}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------ #
    # Patch                                                               #
    # ------------------------------------------------------------------ #

    def test_patch_media_title(self):
        asset = _make_link_asset(self.tenant, self.admin, title='Old Title')
        client = _auth(self.admin)
        response = client.patch(
            f'/api/v1/media/{asset.id}/',
            {'title': 'New Title'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['title'], 'New Title')

    def test_patch_media_tags(self):
        asset = _make_link_asset(self.tenant, self.admin)
        client = _auth(self.admin)
        response = client.patch(
            f'/api/v1/media/{asset.id}/',
            {'tags': ['science', 'biology']},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------------ #
    # Delete (soft)                                                       #
    # ------------------------------------------------------------------ #

    def test_delete_media_soft_deletes(self):
        """DELETE must set is_active=False, not hard-delete the record."""
        asset = _make_link_asset(self.tenant, self.admin, title='Soft Delete Test')
        client = _auth(self.admin)
        response = client.delete(f'/api/v1/media/{asset.id}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 204)

        # Record still exists
        asset.refresh_from_db()
        self.assertFalse(asset.is_active)

    def test_deleted_asset_excluded_from_list(self):
        asset = _make_link_asset(self.tenant, self.admin, title='Will Be Deleted')
        client = _auth(self.admin)
        client.delete(f'/api/v1/media/{asset.id}/', HTTP_HOST=HOST_A)

        response = client.get('/api/v1/media/', HTTP_HOST=HOST_A)
        ids = [a['id'] for a in response.data['results']]
        self.assertNotIn(str(asset.id), ids)


# ===========================================================================
# Media Stats Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class MediaStatsTestCase(TestCase):
    """Tests for GET /api/v1/media/stats/."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'media-stats', 'test', 'stats@media.com')
        self.admin = _make_user('admin@mediastats.com', self.tenant)

    def test_stats_returns_zero_when_empty(self):
        client = _auth(self.admin)
        response = client.get('/api/v1/media/stats/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get('total', 0), 0)

    def test_stats_counts_by_media_type(self):
        # Create 2 videos, 1 document, 3 links
        for i in range(2):
            MediaAsset.objects.create(
                tenant=self.tenant, title=f'Video {i}',
                media_type='VIDEO', file_url=f'https://x.com/v{i}',
                uploaded_by=self.admin,
            )
        MediaAsset.objects.create(
            tenant=self.tenant, title='Doc', media_type='DOCUMENT',
            file_url='https://x.com/d1', uploaded_by=self.admin,
        )
        for i in range(3):
            MediaAsset.objects.create(
                tenant=self.tenant, title=f'Link {i}',
                media_type='LINK', file_url=f'https://x.com/l{i}',
                uploaded_by=self.admin,
            )
        client = _auth(self.admin)
        response = client.get('/api/v1/media/stats/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 6)
        self.assertEqual(response.data.get('VIDEO', 0), 2)
        self.assertEqual(response.data.get('DOCUMENT', 0), 1)
        self.assertEqual(response.data.get('LINK', 0), 3)

    def test_stats_excludes_inactive_assets(self):
        asset = MediaAsset.objects.create(
            tenant=self.tenant, title='Inactive',
            media_type='LINK', file_url='https://x.com/x',
            uploaded_by=self.admin, is_active=False,
        )
        client = _auth(self.admin)
        response = client.get('/api/v1/media/stats/', HTTP_HOST=HOST_A)
        self.assertEqual(response.data.get('total', 0), 0)


# ===========================================================================
# Cross-Tenant Isolation Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class MediaCrossTenantIsolationTestCase(TestCase):
    """
    Security tests: Tenant A's media must not be accessible to Tenant B users.
    This validates TenantManager-based auto-filtering.
    """

    def setUp(self):
        self.tenant_a = _make_tenant('School A', 'media-a', 'test', 'a@mediaisol.com')
        self.tenant_b = _make_tenant('School B', 'media-b', 'other', 'b@mediaisol.com')

        self.admin_a = _make_user('admin@mediaisol-a.com', self.tenant_a)
        self.admin_b = _make_user('admin@mediaisol-b.com', self.tenant_b)

        self.asset_a = _make_link_asset(
            self.tenant_a, self.admin_a, title='Private Asset A'
        )

    def test_tenant_a_admin_cannot_see_zero_results_in_own_tenant(self):
        """Sanity check: Admin A can see their own asset."""
        client = _auth(self.admin_a)
        response = client.get('/api/v1/media/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        ids = [a['id'] for a in response.data['results']]
        self.assertIn(str(self.asset_a.id), ids)

    def test_tenant_b_admin_sees_no_tenant_a_assets_in_own_scope(self):
        """Admin B's list should not include Tenant A's assets."""
        client = _auth(self.admin_b)
        response = client.get('/api/v1/media/', HTTP_HOST=HOST_B)
        self.assertEqual(response.status_code, 200)
        ids = [a['id'] for a in response.data['results']]
        self.assertNotIn(str(self.asset_a.id), ids)

    def test_tenant_b_admin_gets_403_accessing_tenant_a_host(self):
        """Admin B gets 403 when hitting Tenant A's host (wrong tenant)."""
        client = _auth(self.admin_b)
        response = client.get('/api/v1/media/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 403)

    def test_tenant_b_cannot_get_tenant_a_asset_detail(self):
        """Admin B cannot GET detail of Tenant A's asset even with correct ID."""
        client = _auth(self.admin_b)
        response = client.get(
            f'/api/v1/media/{self.asset_a.id}/',
            HTTP_HOST=HOST_B,
        )
        # Should not be found because TenantManager filters by tenant
        self.assertIn(response.status_code, [403, 404])

    def test_tenant_b_cannot_delete_tenant_a_asset(self):
        """Admin B cannot delete Tenant A's asset."""
        client = _auth(self.admin_b)
        client.get('/api/v1/media/', HTTP_HOST=HOST_B)  # Establish B's context
        response = client.delete(
            f'/api/v1/media/{self.asset_a.id}/',
            HTTP_HOST=HOST_B,
        )
        self.assertIn(response.status_code, [403, 404])
        # Asset must still be active
        self.asset_a.refresh_from_db()
        self.assertTrue(self.asset_a.is_active)


# ===========================================================================
# MediaAsset Model Tests
# ===========================================================================

class MediaAssetModelTestCase(TestCase):
    """Unit tests for MediaAsset model."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Model School', slug='model-media', subdomain='model', email='model@m.com'
        )
        self.admin = User.objects.create_user(
            email='admin@model.com', password='pass',
            first_name='A', last_name='B',
            tenant=self.tenant, role='SCHOOL_ADMIN',
        )

    def test_str_representation(self):
        asset = MediaAsset.objects.create(
            tenant=self.tenant, title='My Asset', media_type='LINK',
            file_url='https://x.com/a', uploaded_by=self.admin,
        )
        self.assertIn('My Asset', str(asset))
        self.assertIn('LINK', str(asset))

    def test_default_is_active_true(self):
        asset = MediaAsset.objects.create(
            tenant=self.tenant, title='Active by Default', media_type='LINK',
            file_url='https://x.com/active', uploaded_by=self.admin,
        )
        self.assertTrue(asset.is_active)

    def test_default_tags_empty_list(self):
        asset = MediaAsset.objects.create(
            tenant=self.tenant, title='No Tags', media_type='LINK',
            file_url='https://x.com/notags', uploaded_by=self.admin,
        )
        self.assertEqual(asset.tags, [])


# ===========================================================================
# Serve Media File Path Traversal Tests
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
    STORAGE_BACKEND='local',
    USE_X_ACCEL_REDIRECT=False,
    DEBUG=True,
)
class ServeMediaFileSecurityTestCase(TestCase):
    """
    Tests for path traversal protection in serve_media_file view.
    """

    def setUp(self):
        self.tenant = _make_tenant('Sec School', 'serve-sec', 'test', 'sec@serve.com')
        self.admin = _make_user('admin@serve.com', self.tenant)

    def test_path_traversal_attempt_returns_404(self):
        """Path containing '..' must return 404."""
        client = _auth(self.admin)
        response = client.get(
            '/api/v1/media/file/../../../etc/passwd',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 404)

    def test_absolute_path_attempt_returns_404(self):
        """Paths that resolve to absolute paths must return 404."""
        client = _auth(self.admin)
        response = client.get(
            '/api/v1/media/file/tenant/1/../../etc/shadow',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 404)
