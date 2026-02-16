# apps/users/sso_pipeline.py
"""
Custom social auth pipeline functions for SSO integration.

Handles:
- Email-based user matching (existing users)
- Tenant detection from email domain
- Controlled user creation based on tenant settings
"""

import logging
from django.conf import settings
from social_core.exceptions import AuthForbidden

logger = logging.getLogger(__name__)


def associate_by_email(backend, details, user=None, *args, **kwargs):
    """
    Associate SSO login with existing user by email.
    
    If user already exists with this email, link the social account.
    """
    if user:
        return {'user': user}
    
    email = details.get('email', '').lower()
    if not email:
        return None
    
    from apps.users.models import User
    
    try:
        existing_user = User.objects.get(email=email)
        return {'user': existing_user, 'is_new': False}
    except User.DoesNotExist:
        return None


def create_user_if_allowed(
    strategy, details, backend, user=None, *args, **kwargs
):
    """
    Create a new user only if the tenant allows SSO registration.
    
    Determines tenant from email domain and checks if:
    1. Tenant exists with matching SSO domain
    2. Tenant allows SSO registration
    3. User limit hasn't been reached
    """
    if user:
        return {'user': user}
    
    email = details.get('email', '').lower()
    if not email:
        raise AuthForbidden(backend, 'Email not provided')
    
    # Extract domain from email
    try:
        domain = email.split('@')[1]
    except IndexError:
        raise AuthForbidden(backend, 'Invalid email format')
    
    from apps.tenants.models import Tenant
    from apps.users.models import User
    
    # Find tenant by SSO domain configuration
    tenant = None
    
    # Check if domain matches any tenant's SSO domains
    tenants = Tenant.objects.filter(is_active=True)
    for t in tenants:
        sso_domains = getattr(t, 'sso_domains', '') or ''
        allowed_domains = [d.strip().lower() for d in sso_domains.split(',') if d.strip()]
        
        if domain in allowed_domains:
            tenant = t
            break
    
    # Also check subdomain matching (e.g., school.lms.com → school)
    if not tenant:
        # Try to match by subdomain from request
        request = strategy.request
        if request:
            host = request.get_host().lower()
            for t in tenants:
                if host.startswith(f"{t.subdomain}."):
                    tenant = t
                    break
    
    if not tenant:
        logger.warning(f"SSO login rejected: no tenant found for domain {domain}")
        raise AuthForbidden(backend, f'No organization found for domain {domain}')
    
    # Check if tenant allows SSO registration
    if not getattr(tenant, 'allow_sso_registration', True):
        logger.warning(f"SSO registration disabled for tenant {tenant.name}")
        raise AuthForbidden(backend, 'SSO registration is disabled for this organization')
    
    # Check user limits
    current_users = User.objects.filter(tenant=tenant, is_active=True).count()
    if current_users >= tenant.max_teachers:
        logger.warning(f"Tenant {tenant.name} has reached user limit")
        raise AuthForbidden(backend, 'Organization has reached maximum user limit')
    
    # Create the user
    first_name = details.get('first_name', '')
    last_name = details.get('last_name', '')
    full_name = details.get('fullname', '')
    
    if not first_name and full_name:
        parts = full_name.split(' ', 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ''
    
    user = User.objects.create(
        email=email,
        first_name=first_name or 'User',
        last_name=last_name or '',
        tenant=tenant,
        role='TEACHER',  # Default role for SSO users
        is_active=True,
        email_verified=True,  # SSO emails are pre-verified
    )
    
    # Set unusable password (SSO-only account)
    user.set_unusable_password()
    user.save()
    
    logger.info(f"Created SSO user {email} for tenant {tenant.name}")
    
    return {
        'user': user,
        'is_new': True,
    }
