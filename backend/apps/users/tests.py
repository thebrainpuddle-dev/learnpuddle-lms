# apps/users/tests.py

from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from apps.tenants.models import Tenant
from apps.users.models import User


@override_settings(ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'])
class AuthenticationTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Create tenant
        self.tenant = Tenant.objects.create(
            name='Test School',
            slug='test',
            subdomain='test',
            email='test@school.com'
        )
        
        # Create user
        self.user = User.objects.create_user(
            email='teacher@test.com',
            password='testpass123',
            first_name='Test',
            last_name='Teacher',
            tenant=self.tenant,
            role='TEACHER'
        )
        
        # Set HTTP_HOST for tenant identification
        self.tenant_host = 'test.lms.com'
    
    def test_login_success(self):
        """Test successful login."""
        response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('tokens', response.data)
        self.assertIn('access', response.data['tokens'])
        self.assertIn('refresh', response.data['tokens'])
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['email'], 'teacher@test.com')
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'wrongpassword'
        })
        
        self.assertEqual(response.status_code, 400)

    def test_login_ignores_stale_authorization_header(self):
        """Login should work even when a stale Bearer token is present."""
        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid.token.value')
        response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'testpass123'
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('tokens', response.data)
    
    def test_login_inactive_user(self):
        """Test that inactive users cannot login."""
        self.user.is_active = False
        self.user.save()
        
        response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'testpass123'
        })
        
        self.assertEqual(response.status_code, 400)
    
    def test_me_endpoint(self):
        """Test getting current user."""
        # Login first
        login_response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'testpass123'
        })
        
        access_token = login_response.data['tokens']['access']
        
        # Use token to access me endpoint with tenant header
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.get('/api/users/auth/me/', HTTP_HOST=self.tenant_host)
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['email'], 'teacher@test.com')
        self.assertEqual(response.data['role'], 'TEACHER')
    
    def test_me_endpoint_without_token(self):
        """Test me endpoint without authentication."""
        response = self.client.get('/api/users/auth/me/', HTTP_HOST=self.tenant_host)
        
        self.assertEqual(response.status_code, 401)
    
    def test_token_refresh(self):
        """Test token refresh."""
        # Login
        login_response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'testpass123'
        })
        
        refresh_token = login_response.data['tokens']['refresh']
        
        # Refresh token
        response = self.client.post('/api/users/auth/refresh/', {
            'refresh_token': refresh_token
        })
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
    
    def test_token_refresh_invalid(self):
        """Test token refresh with invalid token."""
        response = self.client.post('/api/users/auth/refresh/', {
            'refresh_token': 'invalid_token'
        })
        
        self.assertEqual(response.status_code, 401)

    def test_token_refresh_ignores_stale_authorization_header(self):
        """Refresh should not be blocked by a stale Authorization header."""
        login_response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'testpass123'
        })
        refresh_token = login_response.data['tokens']['refresh']

        self.client.credentials(HTTP_AUTHORIZATION='Bearer invalid.token.value')
        response = self.client.post('/api/users/auth/refresh/', {
            'refresh_token': refresh_token
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
    
    def test_logout(self):
        """Test logout blacklists token."""
        # Login
        login_response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'testpass123'
        })
        
        access_token = login_response.data['tokens']['access']
        refresh_token = login_response.data['tokens']['refresh']
        
        # Logout with tenant header
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.post('/api/users/auth/logout/', {
            'refresh_token': refresh_token
        }, HTTP_HOST=self.tenant_host)
        
        self.assertEqual(response.status_code, 200)
        
        # Try to refresh with blacklisted token
        self.client.credentials()  # Clear credentials
        refresh_response = self.client.post('/api/users/auth/refresh/', {
            'refresh_token': refresh_token
        })
        
        self.assertEqual(refresh_response.status_code, 401)
    
    def test_change_password(self):
        """Test password change."""
        # Login
        login_response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'testpass123'
        })
        
        access_token = login_response.data['tokens']['access']
        
        # Change password with tenant header
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.post('/api/users/auth/change-password/', {
            'old_password': 'testpass123',
            'new_password': 'newpassword456',
            'new_password_confirm': 'newpassword456'
        }, HTTP_HOST=self.tenant_host)
        
        self.assertEqual(response.status_code, 200)
        
        # Login with new password
        self.client.credentials()
        new_login_response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'newpassword456'
        })
        
        self.assertEqual(new_login_response.status_code, 200)
    
    def test_change_password_wrong_old(self):
        """Test password change with wrong old password."""
        # Login
        login_response = self.client.post('/api/users/auth/login/', {
            'email': 'teacher@test.com',
            'password': 'testpass123'
        })
        
        access_token = login_response.data['tokens']['access']
        
        # Try to change password with wrong old password (with tenant header)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        response = self.client.post('/api/users/auth/change-password/', {
            'old_password': 'wrongoldpassword',
            'new_password': 'newpassword456',
            'new_password_confirm': 'newpassword456'
        }, HTTP_HOST=self.tenant_host)
        
        self.assertEqual(response.status_code, 400)


class TokenClaimsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        
        # Create tenant
        self.tenant = Tenant.objects.create(
            name='Claims Test School',
            slug='claims-test',
            subdomain='claimstest',
            email='claims@test.com'
        )
        
        # Create user
        self.user = User.objects.create_user(
            email='claims_user@test.com',
            password='testpass123',
            first_name='Claims',
            last_name='User',
            tenant=self.tenant,
            role='SCHOOL_ADMIN'
        )
    
    def test_token_contains_custom_claims(self):
        """Test that tokens contain custom claims."""
        from apps.users.tokens import get_tokens_for_user
        import jwt
        from django.conf import settings
        
        tokens = get_tokens_for_user(self.user)
        
        # Decode access token (without verification for testing)
        decoded = jwt.decode(
            tokens['access'], 
            settings.SECRET_KEY, 
            algorithms=['HS256']
        )
        
        self.assertEqual(decoded['email'], 'claims_user@test.com')
        self.assertEqual(decoded['role'], 'SCHOOL_ADMIN')
        self.assertEqual(decoded['tenant_id'], str(self.tenant.id))
