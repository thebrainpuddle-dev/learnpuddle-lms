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


def provision_saml_user(*, tenant, config, assertion):
    """Resolve or create a user from a verified SAML assertion.

    Args:
        tenant: The :class:`apps.tenants.models.Tenant` the ACS is for.
        config: The :class:`apps.tenants.saml_models.TenantSAMLConfig` row.
        assertion: A verified :class:`apps.users.saml_service.SAMLAssertion`.

    Returns the :class:`apps.users.models.User` to log in as.

    Raises:
        PermissionError: if the user doesn't exist and the tenant has
            ``auto_provision`` disabled, or if creating a new user would
            exceed tenant limits.
    """
    from apps.users.models import User

    email = (assertion.email or "").strip().lower()
    if not email:
        raise PermissionError("SAML assertion contained no email attribute.")

    # Look up an existing user in this tenant first.  We also match
    # cross-tenant users only if they already belong to this tenant — we
    # never silently move users across tenants.  Use ``all_objects`` so
    # soft-deleted users are surfaced (we refuse to re-activate them).
    lookup_manager = getattr(User, "all_objects", None) or User.objects
    existing = lookup_manager.filter(email__iexact=email).first()
    # SECURITY: never silently adopt a user into a tenant they don't already
    # belong to.  An orphan (tenant_id is None — e.g. historic SUPER_ADMIN
    # rows or rows whose tenant was hard-deleted) must NOT be auto-assigned
    # to whichever tenant the IdP targets.  Reject both mismatched and
    # orphan accounts; admins must explicitly re-associate the user.
    if existing is not None and (
        existing.tenant_id is None or existing.tenant_id != tenant.id
    ):
        raise PermissionError(
            "This email is registered with another account; contact support."
        )
    if existing and getattr(existing, "is_deleted", False):
        raise PermissionError("User account is disabled.")
    if existing:
        # Refresh profile fields from the IdP, but never overwrite role
        # without explicit admin action.
        updated = False
        if assertion.first_name and existing.first_name != assertion.first_name:
            existing.first_name = assertion.first_name
            updated = True
        if assertion.last_name and existing.last_name != assertion.last_name:
            existing.last_name = assertion.last_name
            updated = True
        if not existing.email_verified:
            existing.email_verified = True
            updated = True
        if not existing.is_active:
            # An admin explicitly deactivated this user — respect that.
            raise PermissionError("User account is disabled.")
        if updated:
            existing.save(
                update_fields=["first_name", "last_name", "email_verified"]
            )
        return existing

    if not config.auto_provision:
        raise PermissionError(
            "Auto-provisioning is disabled for this tenant; contact your administrator."
        )

    if not config.domain_allowed(email):
        raise PermissionError("Email domain is not allowed for SAML SSO.")

    # Enforce tenant user limit.
    role = (config.default_role or "TEACHER").upper()
    active_count = User.objects.filter(tenant=tenant, is_active=True).count()
    if role == "STUDENT":
        limit = getattr(tenant, "max_students", 0) or 0
    else:
        limit = getattr(tenant, "max_teachers", 0) or 0
    if limit and active_count >= limit:
        raise PermissionError("Organization has reached its user limit.")

    user = User.objects.create(
        email=email,
        first_name=assertion.first_name or "User",
        last_name=assertion.last_name or "",
        tenant=tenant,
        role=role,
        is_active=True,
        email_verified=True,
    )
    user.set_unusable_password()
    user.save()
    logger.info("Auto-provisioned SAML user %s for tenant %s", email, tenant.subdomain)
    return user
