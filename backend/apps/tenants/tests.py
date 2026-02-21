# apps/tenants/tests.py

from unittest.mock import patch

from django.test import TestCase, RequestFactory, override_settings
from rest_framework.test import APIClient
from apps.tenants.models import Tenant
from apps.users.models import User
from utils.tenant_utils import get_tenant_from_request
from utils.tenant_middleware import TenantMiddleware, get_current_tenant, set_current_tenant, clear_current_tenant


@override_settings(ALLOWED_HOSTS=['*'])
class TenantUtilsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        
        # Create test tenant
        self.tenant = Tenant.objects.create(
            name='Test School',
            slug='test-school',
            subdomain='test',
            email='test@school.com'
        )
        
        # Create demo tenant for localhost testing
        self.demo_tenant = Tenant.objects.create(
            name='Demo School',
            slug='demo',
            subdomain='demo',
            email='demo@demo.com'
        )
    
    def test_get_tenant_from_subdomain(self):
        """Test extracting tenant from subdomain."""
        request = self.factory.get('/', HTTP_HOST='test.lms.com')
        tenant = get_tenant_from_request(request)
        self.assertEqual(tenant.id, self.tenant.id)
    
    def test_localhost_uses_demo_tenant(self):
        """Test localhost defaults to demo tenant."""
        request = self.factory.get('/', HTTP_HOST='localhost:8000')
        tenant = get_tenant_from_request(request)
        self.assertEqual(tenant.subdomain, 'demo')
    
    def test_127_0_0_1_uses_demo_tenant(self):
        """Test 127.0.0.1 defaults to demo tenant."""
        request = self.factory.get('/', HTTP_HOST='127.0.0.1:8000')
        tenant = get_tenant_from_request(request)
        self.assertEqual(tenant.subdomain, 'demo')
    
    def test_inactive_tenant_raises_error(self):
        """Test that inactive tenants are not accessible."""
        self.tenant.is_active = False
        self.tenant.save()
        
        request = self.factory.get('/', HTTP_HOST='test.lms.com')
        
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            get_tenant_from_request(request)
    
    def test_nonexistent_tenant_raises_error(self):
        """Test that nonexistent tenants raise error."""
        request = self.factory.get('/', HTTP_HOST='nonexistent.lms.com')
        
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            get_tenant_from_request(request)

    @override_settings(PLATFORM_DOMAIN='learnpuddle.com')
    def test_platform_root_returns_none(self):
        """Platform apex domain should not resolve to a tenant."""
        request = self.factory.get('/', HTTP_HOST='learnpuddle.com')
        tenant = get_tenant_from_request(request)
        self.assertIsNone(tenant)

    @override_settings(PLATFORM_DOMAIN='learnpuddle.com')
    def test_platform_www_root_returns_none(self):
        """Platform www domain should not resolve to a tenant."""
        request = self.factory.get('/', HTTP_HOST='www.learnpuddle.com')
        tenant = get_tenant_from_request(request)
        self.assertIsNone(tenant)


class TenantContextTestCase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name='Context Test School',
            slug='context-test',
            subdomain='contexttest',
            email='context@test.com'
        )
    
    def tearDown(self):
        clear_current_tenant()
    
    def test_set_and_get_current_tenant(self):
        """Test setting and getting current tenant."""
        set_current_tenant(self.tenant)
        current = get_current_tenant()
        self.assertEqual(current.id, self.tenant.id)
    
    def test_clear_current_tenant(self):
        """Test clearing current tenant."""
        set_current_tenant(self.tenant)
        clear_current_tenant()
        current = get_current_tenant()
        self.assertIsNone(current)
    
    def test_no_tenant_returns_none(self):
        """Test that no tenant returns None."""
        clear_current_tenant()
        current = get_current_tenant()
        self.assertIsNone(current)


class TenantMiddlewareTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        
        # Create demo tenant
        self.demo_tenant = Tenant.objects.create(
            name='Demo School',
            slug='demo',
            subdomain='demo',
            email='demo@demo.com'
        )
        
        # Create a simple view for testing
        def simple_view(request):
            from django.http import JsonResponse
            return JsonResponse({'status': 'ok'})
        
        self.middleware = TenantMiddleware(simple_view)
    
    def tearDown(self):
        clear_current_tenant()
    
    def test_middleware_sets_tenant_on_request(self):
        """Test that middleware sets tenant on request object."""
        request = self.factory.get('/api/test/', HTTP_HOST='localhost:8000')
        request.user = type('User', (), {'is_authenticated': False})()
        
        response = self.middleware(request)
        
        # Check tenant was set (via thread local)
        # Note: tenant is cleared after response, so we check response status
        self.assertEqual(response.status_code, 200)
    
    def test_middleware_skips_admin_paths(self):
        """Test that middleware skips /admin/ paths."""
        request = self.factory.get('/admin/', HTTP_HOST='localhost:8000')
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)
    
    def test_middleware_skips_health_paths(self):
        """Test that middleware skips /health/ paths."""
        request = self.factory.get('/health/', HTTP_HOST='localhost:8000')
        
        response = self.middleware(request)
        
        self.assertEqual(response.status_code, 200)


class TenantServiceTestCase(TestCase):
    def test_create_tenant_with_admin(self):
        """Test creating a tenant with admin user."""
        from apps.tenants.services import TenantService
        
        result = TenantService.create_tenant_with_admin(
            name='New School',
            email='admin@newschool.com',
            admin_first_name='John',
            admin_last_name='Doe',
            admin_password='password123'
        )
        
        self.assertIsNotNone(result['tenant'])
        self.assertIsNotNone(result['admin'])
        self.assertEqual(result['admin'].email, 'admin@newschool.com')
        self.assertEqual(result['admin'].role, 'SCHOOL_ADMIN')
        self.assertEqual(result['admin'].tenant, result['tenant'])
    
    def test_get_tenant_stats(self):
        """Test getting tenant statistics."""
        from apps.tenants.services import TenantService
        
        # Create tenant
        tenant = Tenant.objects.create(
            name='Stats School',
            slug='stats-school',
            subdomain='stats',
            email='stats@school.com'
        )
        
        # Create users
        User.objects.create_user(
            email='teacher1@stats.com',
            password='pass',
            first_name='Teacher',
            last_name='One',
            tenant=tenant,
            role='TEACHER'
        )
        
        User.objects.create_user(
            email='admin@stats.com',
            password='pass',
            first_name='Admin',
            last_name='User',
            tenant=tenant,
            role='SCHOOL_ADMIN'
        )
        
        stats = TenantService.get_tenant_stats(tenant)
        
        self.assertEqual(stats['total_teachers'], 1)
        self.assertEqual(stats['total_admins'], 1)


@override_settings(PLATFORM_DOMAIN='learnpuddle.com', ALLOWED_HOSTS=['*'])
class TenantThemeViewHostTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_theme_on_platform_apex_host_returns_platform_theme(self):
        response = self.client.get('/api/tenants/theme/', HTTP_HOST='learnpuddle.com')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('tenant_found'))
        self.assertEqual(response.data.get('subdomain'), '')
        self.assertEqual(response.data.get('name'), 'LearnPuddle')

    def test_theme_on_platform_www_host_returns_platform_theme(self):
        response = self.client.get('/api/tenants/theme/', HTTP_HOST='www.learnpuddle.com')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('tenant_found'))
        self.assertEqual(response.data.get('subdomain'), '')
        self.assertEqual(response.data.get('name'), 'LearnPuddle')


@override_settings(ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'])
class TenantConfigViewTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name='Config School',
            slug='config-school',
            subdomain='test',
            email='config@test.com'
        )
        self.admin = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            first_name='Admin',
            last_name='User',
            tenant=self.tenant,
            role='SCHOOL_ADMIN'
        )
        self.client.force_authenticate(user=self.admin)

    def test_tenant_config_returns_limits_and_usage(self):
        response = self.client.get('/api/tenants/config/', HTTP_HOST='test.lms.com')
        self.assertEqual(response.status_code, 200)
        self.assertIn('limits', response.data)
        self.assertIn('usage', response.data)
        self.assertFalse(response.data.get('degraded', False))

    @patch('apps.tenants.services.get_tenant_usage', side_effect=RuntimeError('usage failure'))
    def test_tenant_config_returns_degraded_response_when_usage_fails(self, _mock_usage):
        response = self.client.get('/api/tenants/config/', HTTP_HOST='test.lms.com')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('degraded'))
        self.assertIn('usage', response.data)
        self.assertEqual(response.data['usage']['teachers']['limit'], self.tenant.max_teachers)
