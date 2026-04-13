# apps/webhooks/tests.py
"""
Comprehensive tests for the webhooks app.

Covers:
- HMAC signature generation (P0 security fix verification)
- SSRF protection in URL validation (P0 security fix verification)
- Webhook endpoint CRUD (admin only)
- Cross-tenant isolation
- WebhookDelivery list
- trigger_webhook service
"""

import hmac
import hashlib
from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.webhooks.models import WebhookEndpoint, WebhookDelivery
from apps.webhooks.services import generate_signature, trigger_webhook
from apps.webhooks.views import _validate_webhook_url


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


def _make_endpoint(tenant, admin, name='Hook', url='https://external.com/hook',
                   events=None):
    return WebhookEndpoint.objects.create(
        tenant=tenant,
        name=name,
        url=url,
        events=events or ['course.published'],
        created_by=admin,
    )


def _auth(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


HOST_A = 'test.lms.com'
HOST_B = 'other.lms.com'


# ===========================================================================
# Phase 1 Security Fix: HMAC Signature Tests
# ===========================================================================

class WebhookSignatureSecurityTestCase(TestCase):
    """
    P0 Security Fix Verification: HMAC-SHA256 webhook signatures.

    These tests confirm that:
    - Signatures are generated correctly and verifiably
    - Different payloads/secrets produce different signatures
    - Recipients can independently verify signatures
    """

    def test_generate_signature_returns_64_char_hex(self):
        sig = generate_signature('{"test": "payload"}', 'my-secret')
        self.assertIsInstance(sig, str)
        # SHA-256 hex digest is always 64 characters
        self.assertEqual(len(sig), 64)
        # All hex characters
        self.assertTrue(all(c in '0123456789abcdef' for c in sig))

    def test_signature_is_deterministic(self):
        payload = '{"event": "course.published", "course_id": "abc123"}'
        secret = 'super-secret-key'
        sig1 = generate_signature(payload, secret)
        sig2 = generate_signature(payload, secret)
        self.assertEqual(sig1, sig2)

    def test_different_payloads_produce_different_signatures(self):
        secret = 'shared-secret'
        sig1 = generate_signature('{"course_id": "AAA"}', secret)
        sig2 = generate_signature('{"course_id": "BBB"}', secret)
        self.assertNotEqual(sig1, sig2)

    def test_different_secrets_produce_different_signatures(self):
        payload = '{"event": "test"}'
        sig1 = generate_signature(payload, 'secret-one')
        sig2 = generate_signature(payload, 'secret-two')
        self.assertNotEqual(sig1, sig2)

    def test_recipient_can_verify_signature(self):
        """Standard hmac module must verify our generated signature."""
        payload = '{"event": "progress.completed", "user_id": "xyz"}'
        secret = 'my-webhook-secret-32-bytes-long!!'
        sig = generate_signature(payload, secret)

        expected = hmac.new(
            secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

        self.assertTrue(hmac.compare_digest(expected, sig))

    def test_empty_payload_has_valid_signature(self):
        """Edge case: empty payload should still produce a valid signature."""
        sig = generate_signature('', 'secret')
        self.assertEqual(len(sig), 64)

    def test_unicode_payload_handled_correctly(self):
        """Non-ASCII payload should not raise errors."""
        payload = '{"message": "Héllo Wörld 🎉"}'
        sig = generate_signature(payload, 'secret')
        self.assertEqual(len(sig), 64)


# ===========================================================================
# Phase 1 Security Fix: SSRF Protection Tests
# ===========================================================================

class WebhookSSRFProtectionTestCase(TestCase):
    """
    P0 Security Fix Verification: SSRF protection for webhook URLs.

    These tests confirm that internal/private URLs are rejected
    before a webhook endpoint is created.
    """

    def test_valid_https_url_passes(self):
        self.assertIsNone(_validate_webhook_url('https://api.example.com/webhook'))

    def test_http_url_rejected(self):
        error = _validate_webhook_url('http://example.com/webhook')
        self.assertIsNotNone(error)
        self.assertIn('HTTPS', error)

    def test_localhost_rejected(self):
        error = _validate_webhook_url('https://localhost/hook')
        self.assertIsNotNone(error)

    def test_127_0_0_1_rejected(self):
        error = _validate_webhook_url('https://127.0.0.1/hook')
        self.assertIsNotNone(error)

    def test_private_ip_class_a_rejected(self):
        error = _validate_webhook_url('https://10.0.0.1/hook')
        self.assertIsNotNone(error)

    def test_private_ip_class_b_rejected(self):
        error = _validate_webhook_url('https://172.16.0.1/hook')
        self.assertIsNotNone(error)

    def test_private_ip_class_c_rejected(self):
        error = _validate_webhook_url('https://192.168.1.100/hook')
        self.assertIsNotNone(error)

    def test_docker_service_names_rejected(self):
        for service in ('web', 'db', 'redis', 'worker', 'nginx', 'postgres'):
            with self.subTest(service=service):
                error = _validate_webhook_url(f'https://{service}/hook')
                self.assertIsNotNone(error)

    def test_internal_domain_suffix_rejected(self):
        error = _validate_webhook_url('https://internal.service.local/hook')
        self.assertIsNotNone(error)

    def test_google_metadata_server_rejected(self):
        error = _validate_webhook_url('https://metadata.google.internal/hook')
        self.assertIsNotNone(error)

    def test_ipv6_loopback_rejected(self):
        error = _validate_webhook_url('https://[::1]/hook')
        self.assertIsNotNone(error)

    def test_url_without_hostname_rejected(self):
        error = _validate_webhook_url('https:///path')
        self.assertIsNotNone(error)


# ===========================================================================
# Webhook Endpoint Management Views
# ===========================================================================

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class WebhookListCreateTestCase(TestCase):
    """Tests for GET/POST /api/v1/webhooks/."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'wh-lc', 'test', 'a@wh.com')
        self.admin = _make_user('admin@wh.com', self.tenant)
        self.teacher = _make_user('teacher@wh.com', self.tenant, role='TEACHER', first='Tea')

    def test_list_webhooks_requires_auth(self):
        response = APIClient().get('/api/v1/webhooks/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 401)

    def test_teacher_cannot_list_webhooks(self):
        client = _auth(self.teacher)
        response = client.get('/api/v1/webhooks/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_webhooks(self):
        _make_endpoint(self.tenant, self.admin)
        client = _auth(self.admin)
        response = client.get('/api/v1/webhooks/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)

    def test_create_webhook_success(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/webhooks/',
            {
                'name': 'Prod Webhook',
                'url': 'https://hooks.external.io/lms',
                'events': ['course.published', 'progress.completed'],
            },
            format='json',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', response.data)
        self.assertIn('secret', response.data)
        self.assertTrue(len(response.data['secret']) > 0)

    def test_create_webhook_auto_generates_secret(self):
        client = _auth(self.admin)
        resp1 = client.post(
            '/api/v1/webhooks/',
            {'name': 'Hook 1', 'url': 'https://a.example.com/h', 'events': ['user.registered']},
            format='json', HTTP_HOST=HOST_A,
        )
        resp2 = client.post(
            '/api/v1/webhooks/',
            {'name': 'Hook 2', 'url': 'https://b.example.com/h', 'events': ['user.registered']},
            format='json', HTTP_HOST=HOST_A,
        )
        # Secrets should be unique per endpoint
        self.assertNotEqual(resp1.data['secret'], resp2.data['secret'])

    def test_create_webhook_requires_name(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/webhooks/',
            {'url': 'https://x.com/hook', 'events': ['course.published']},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_webhook_requires_url(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/webhooks/',
            {'name': 'No URL', 'events': ['course.published']},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_webhook_requires_events(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/webhooks/',
            {'name': 'No Events', 'url': 'https://x.com/hook', 'events': []},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_webhook_rejects_http_url(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/webhooks/',
            {'name': 'HTTP Hook', 'url': 'http://external.com/hook', 'events': ['course.published']},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('HTTPS', response.data.get('error', ''))

    def test_create_webhook_rejects_localhost(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/webhooks/',
            {'name': 'SSRF Hook', 'url': 'https://localhost/steal', 'events': ['course.published']},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_webhook_rejects_private_ip(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/webhooks/',
            {'name': 'Private IP', 'url': 'https://192.168.0.1/hook', 'events': ['course.published']},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_webhook_rejects_invalid_events(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/webhooks/',
            {'name': 'Bad Events', 'url': 'https://x.com/h', 'events': ['invalid.event']},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_webhook_allows_wildcard_event(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/webhooks/',
            {'name': 'Wildcard', 'url': 'https://x.com/all', 'events': ['*']},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)

    def test_list_webhooks_only_returns_own_tenant(self):
        """Cross-tenant isolation: admin only sees their tenant's webhooks."""
        # Tenant B setup
        tenant_b = _make_tenant('Other School', 'wh-b', 'other', 'b@wh.com')
        admin_b = _make_user('admin_b@wh.com', tenant_b)
        _make_endpoint(tenant_b, admin_b, name='Tenant B Hook')

        # Tenant A endpoint
        ep_a = _make_endpoint(self.tenant, self.admin, name='Tenant A Hook')

        client = _auth(self.admin)
        response = client.get('/api/v1/webhooks/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        ids = [ep['id'] for ep in response.data]
        self.assertIn(str(ep_a.id), ids)
        self.assertEqual(len(ids), 1)


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class WebhookDetailTestCase(TestCase):
    """Tests for GET/PUT/DELETE /api/v1/webhooks/<id>/."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'wh-det', 'test', 'det@wh.com')
        self.admin = _make_user('admin@whdet.com', self.tenant)
        self.endpoint = _make_endpoint(self.tenant, self.admin, name='Detailed Endpoint')

        # Tenant B for isolation tests
        self.tenant_b = _make_tenant('Other School', 'wh-det-b', 'other', 'detb@wh.com')
        self.admin_b = _make_user('admin_b@whdet.com', self.tenant_b)

    def test_get_webhook_detail(self):
        client = _auth(self.admin)
        response = client.get(f'/api/v1/webhooks/{self.endpoint.id}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Detailed Endpoint')
        self.assertIn('secret', response.data)

    def test_get_nonexistent_webhook_returns_404(self):
        import uuid
        client = _auth(self.admin)
        response = client.get(f'/api/v1/webhooks/{uuid.uuid4()}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 404)

    def test_update_webhook_name(self):
        client = _auth(self.admin)
        response = client.put(
            f'/api/v1/webhooks/{self.endpoint.id}/',
            {'name': 'Updated Name'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Updated Name')

    def test_update_webhook_deactivate(self):
        client = _auth(self.admin)
        response = client.put(
            f'/api/v1/webhooks/{self.endpoint.id}/',
            {'is_active': False},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['is_active'])

    def test_update_webhook_rejects_http_url(self):
        client = _auth(self.admin)
        response = client.put(
            f'/api/v1/webhooks/{self.endpoint.id}/',
            {'url': 'http://external.com/hook'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_delete_webhook(self):
        client = _auth(self.admin)
        response = client.delete(f'/api/v1/webhooks/{self.endpoint.id}/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(WebhookEndpoint.objects.filter(id=self.endpoint.id).exists())

    def test_cross_tenant_cannot_access_other_webhook_detail(self):
        """Admin B cannot retrieve details of Admin A's endpoint."""
        client = _auth(self.admin_b)
        response = client.get(
            f'/api/v1/webhooks/{self.endpoint.id}/',
            HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)

    def test_cross_tenant_cannot_delete_other_webhook(self):
        client = _auth(self.admin_b)
        response = client.delete(
            f'/api/v1/webhooks/{self.endpoint.id}/',
            HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)
        # Endpoint must still exist
        self.assertTrue(WebhookEndpoint.objects.filter(id=self.endpoint.id).exists())


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class WebhookSecretRegenerateTestCase(TestCase):
    """Tests for POST /api/v1/webhooks/<id>/secret/."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'wh-sec', 'test', 'sec@wh.com')
        self.admin = _make_user('admin@whsec.com', self.tenant)
        self.endpoint = _make_endpoint(self.tenant, self.admin, name='Secret Endpoint')

    def test_regenerate_secret_changes_secret(self):
        old_secret = self.endpoint.secret
        client = _auth(self.admin)
        response = client.post(
            f'/api/v1/webhooks/{self.endpoint.id}/secret/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('secret', response.data)
        new_secret = response.data['secret']
        self.assertNotEqual(new_secret, old_secret)
        # Verify it's saved
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.secret, new_secret)

    def test_regenerate_secret_new_value_is_64_hex_chars(self):
        client = _auth(self.admin)
        response = client.post(
            f'/api/v1/webhooks/{self.endpoint.id}/secret/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['secret']), 64)


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class WebhookEventsListTestCase(TestCase):
    """Tests for GET /api/v1/webhooks/events/."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'wh-ev', 'test', 'ev@wh.com')
        self.admin = _make_user('admin@whev.com', self.tenant)

    def test_get_events_list(self):
        client = _auth(self.admin)
        response = client.get('/api/v1/webhooks/events/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)

    def test_events_list_includes_course_events(self):
        client = _auth(self.admin)
        response = client.get('/api/v1/webhooks/events/', HTTP_HOST=HOST_A)
        event_ids = [e['id'] for e in response.data]
        self.assertIn('course.published', event_ids)
        self.assertIn('course.created', event_ids)

    def test_events_list_includes_progress_events(self):
        client = _auth(self.admin)
        response = client.get('/api/v1/webhooks/events/', HTTP_HOST=HOST_A)
        event_ids = [e['id'] for e in response.data]
        self.assertIn('progress.completed', event_ids)

    def test_events_have_category_field(self):
        client = _auth(self.admin)
        response = client.get('/api/v1/webhooks/events/', HTTP_HOST=HOST_A)
        for event in response.data:
            self.assertIn('category', event)
            # category should be the first part of the event id (e.g. 'course')
            self.assertEqual(event['category'], event['id'].split('.')[0])


@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class WebhookDeliveriesViewTestCase(TestCase):
    """Tests for GET /api/v1/webhooks/<id>/deliveries/."""

    def setUp(self):
        self.tenant = _make_tenant('Test School', 'wh-dlv', 'test', 'dlv@wh.com')
        self.admin = _make_user('admin@whdlv.com', self.tenant)
        self.endpoint = _make_endpoint(self.tenant, self.admin, name='Delivery Endpoint')

    def test_get_deliveries_empty(self):
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/webhooks/{self.endpoint.id}/deliveries/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_get_deliveries_returns_records(self):
        WebhookDelivery.objects.create(
            endpoint=self.endpoint,
            event_type='course.published',
            payload={'course_id': 'abc'},
            status='success',
        )
        WebhookDelivery.objects.create(
            endpoint=self.endpoint,
            event_type='user.registered',
            payload={'user_id': 'xyz'},
            status='failed',
        )
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/webhooks/{self.endpoint.id}/deliveries/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)

    def test_deliveries_include_required_fields(self):
        WebhookDelivery.objects.create(
            endpoint=self.endpoint,
            event_type='course.published',
            payload={},
            status='success',
        )
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/webhooks/{self.endpoint.id}/deliveries/', HTTP_HOST=HOST_A
        )
        delivery = response.data[0]
        for field in ('id', 'event_type', 'status', 'attempt_count', 'created_at'):
            self.assertIn(field, delivery)


# ===========================================================================
# Webhook Service Tests
# ===========================================================================

class WebhookTriggerServiceTestCase(TestCase):
    """Unit tests for the trigger_webhook service function."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Service School', slug='svc-school', subdomain='svc', email='svc@svc.com'
        )
        self.admin = User.objects.create_user(
            email='admin@svc.com', password='pass',
            first_name='Admin', last_name='Svc',
            tenant=self.tenant, role='SCHOOL_ADMIN',
        )
        self.endpoint = WebhookEndpoint.objects.create(
            tenant=self.tenant,
            name='Svc Endpoint',
            url='https://svc.external.com/hook',
            events=['course.published'],
            created_by=self.admin,
        )

    @patch('apps.webhooks.services.execute_delivery')
    def test_trigger_creates_delivery_for_subscribed_event(self, mock_exec):
        mock_exec.return_value = True
        delivery_ids = trigger_webhook(
            str(self.tenant.id),
            'course.published',
            {'course_id': 'abc'},
            delay=False,
        )
        self.assertEqual(len(delivery_ids), 1)
        self.assertTrue(WebhookDelivery.objects.filter(id=delivery_ids[0]).exists())

    @patch('apps.webhooks.services.execute_delivery')
    def test_trigger_creates_no_delivery_for_unsubscribed_event(self, mock_exec):
        delivery_ids = trigger_webhook(
            str(self.tenant.id),
            'quiz.submitted',   # endpoint is subscribed to 'course.published' only
            {'quiz_id': 'xyz'},
            delay=False,
        )
        self.assertEqual(len(delivery_ids), 0)
        mock_exec.assert_not_called()

    def test_trigger_nonexistent_tenant_returns_empty_list(self):
        import uuid
        delivery_ids = trigger_webhook(
            str(uuid.uuid4()),
            'course.published',
            {},
            delay=False,
        )
        self.assertEqual(delivery_ids, [])

    @patch('apps.webhooks.services.execute_delivery')
    def test_trigger_increments_total_deliveries_on_endpoint(self, mock_exec):
        mock_exec.return_value = True
        initial = self.endpoint.total_deliveries
        trigger_webhook(
            str(self.tenant.id), 'course.published', {}, delay=False
        )
        self.endpoint.refresh_from_db()
        self.assertEqual(self.endpoint.total_deliveries, initial + 1)

    @patch('apps.webhooks.services.execute_delivery')
    def test_trigger_wildcard_endpoint_matches_any_event(self, mock_exec):
        mock_exec.return_value = True
        wildcard_ep = WebhookEndpoint.objects.create(
            tenant=self.tenant,
            name='Wildcard',
            url='https://wildcard.external.com/hook',
            events=['*'],
            created_by=self.admin,
        )
        delivery_ids = trigger_webhook(
            str(self.tenant.id),
            'user.registered',
            {},
            delay=False,
        )
        created_endpoint_ids = [
            str(WebhookDelivery.objects.get(id=d).endpoint_id)
            for d in delivery_ids
        ]
        self.assertIn(str(wildcard_ep.id), created_endpoint_ids)

    @patch('apps.webhooks.services.execute_delivery')
    def test_trigger_skips_inactive_endpoints(self, mock_exec):
        self.endpoint.is_active = False
        self.endpoint.save()
        delivery_ids = trigger_webhook(
            str(self.tenant.id), 'course.published', {}, delay=False
        )
        self.assertEqual(len(delivery_ids), 0)
        mock_exec.assert_not_called()


# ===========================================================================
# WebhookEndpoint Model Tests
# ===========================================================================

class WebhookEndpointModelTestCase(TestCase):
    """Unit tests for WebhookEndpoint model methods."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Model School', slug='model-school', subdomain='model', email='m@m.com'
        )
        self.admin = User.objects.create_user(
            email='admin@model.com', password='pass',
            first_name='A', last_name='B',
            tenant=self.tenant, role='SCHOOL_ADMIN',
        )

    def test_secret_auto_generated_on_create(self):
        endpoint = WebhookEndpoint.objects.create(
            tenant=self.tenant,
            name='Auto Secret',
            url='https://x.com/h',
            events=['course.published'],
            created_by=self.admin,
        )
        self.assertTrue(len(endpoint.secret) > 0)

    def test_success_rate_zero_when_no_deliveries(self):
        endpoint = WebhookEndpoint.objects.create(
            tenant=self.tenant,
            name='Zero Rate',
            url='https://x.com/h',
            events=['course.published'],
            created_by=self.admin,
        )
        self.assertEqual(endpoint.success_rate, 0.0)

    def test_success_rate_calculated_correctly(self):
        endpoint = WebhookEndpoint.objects.create(
            tenant=self.tenant,
            name='Rate Test',
            url='https://x.com/h',
            events=['course.published'],
            created_by=self.admin,
        )
        endpoint.total_deliveries = 10
        endpoint.successful_deliveries = 7
        endpoint.save()
        self.assertEqual(endpoint.success_rate, 70.0)

    def test_str_representation(self):
        endpoint = WebhookEndpoint.objects.create(
            tenant=self.tenant,
            name='Str Test',
            url='https://str.example.com/hook',
            events=['course.published'],
            created_by=self.admin,
        )
        self.assertIn('Str Test', str(endpoint))
        self.assertIn('https://str.example.com/hook', str(endpoint))
