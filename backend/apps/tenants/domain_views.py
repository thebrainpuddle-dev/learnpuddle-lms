# apps/tenants/domain_views.py
"""
Custom domain management views.

Allows tenants to:
- Configure custom domain (e.g., lms.school.edu)
- Verify domain ownership via DNS TXT record
- Check SSL certificate status
"""

import hashlib
import logging
import secrets
from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.decorators import admin_only, tenant_required

logger = logging.getLogger(__name__)


def generate_verification_token(tenant_id: str) -> str:
    """Generate a DNS verification token for a tenant."""
    secret = settings.SECRET_KEY[:16]
    data = f"{tenant_id}:{secret}"
    return hashlib.sha256(data.encode()).hexdigest()[:32]


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def domain_status(request):
    """
    Get custom domain configuration status.
    
    Returns current domain settings and verification status.
    """
    tenant = request.tenant
    
    verification_token = generate_verification_token(str(tenant.id))
    
    return Response({
        'custom_domain': tenant.custom_domain or None,
        'verified': tenant.custom_domain_verified,
        'ssl_expires': tenant.custom_domain_ssl_expires.isoformat() if tenant.custom_domain_ssl_expires else None,
        'verification_token': verification_token,
        'verification_record': f"_lms-verify.{tenant.custom_domain}" if tenant.custom_domain else None,
        'verification_value': f"lms-verify={verification_token}",
        'default_domain': f"{tenant.subdomain}.{settings.PLATFORM_DOMAIN}",
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def domain_configure(request):
    """
    Configure custom domain for tenant.
    
    POST body:
    {
        "domain": "lms.school.edu"
    }
    
    Returns verification instructions.
    """
    domain = request.data.get('domain', '').strip().lower()
    
    if not domain:
        return Response(
            {'error': 'Domain is required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Basic validation
    if not '.' in domain or domain.startswith('.') or domain.endswith('.'):
        return Response(
            {'error': 'Invalid domain format'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Disallow subdomains of our platform domain
    platform_domain = settings.PLATFORM_DOMAIN.lower()
    if domain.endswith(f'.{platform_domain}') or domain == platform_domain:
        return Response(
            {'error': f'Cannot use {platform_domain} subdomains as custom domain'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if domain is already in use by another tenant
    from apps.tenants.models import Tenant
    existing = Tenant.objects.filter(
        custom_domain=domain
    ).exclude(id=request.tenant.id).first()
    
    if existing:
        return Response(
            {'error': 'This domain is already in use by another organization'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    tenant = request.tenant
    tenant.custom_domain = domain
    tenant.custom_domain_verified = False
    tenant.custom_domain_ssl_expires = None
    tenant.save()
    
    verification_token = generate_verification_token(str(tenant.id))
    
    logger.info(f"Custom domain configured for tenant {tenant.name}: {domain}")
    
    return Response({
        'success': True,
        'domain': domain,
        'verification_instructions': {
            'step1': f'Add a DNS TXT record to verify domain ownership',
            'record_type': 'TXT',
            'record_name': f'_lms-verify.{domain}',
            'record_value': f'lms-verify={verification_token}',
            'step2': 'Add a CNAME record to point your domain to our servers',
            'cname_name': domain,
            'cname_value': f'{tenant.subdomain}.{settings.PLATFORM_DOMAIN}',
            'step3': 'Click "Verify Domain" once DNS records propagate (may take up to 48 hours)',
        },
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def domain_verify(request):
    """
    Verify domain ownership via DNS TXT record.
    
    Checks for the verification TXT record in DNS.
    """
    import socket
    
    tenant = request.tenant
    
    if not tenant.custom_domain:
        return Response(
            {'error': 'No custom domain configured'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if tenant.custom_domain_verified:
        return Response({
            'success': True,
            'message': 'Domain is already verified',
        })
    
    expected_token = generate_verification_token(str(tenant.id))
    verification_host = f'_lms-verify.{tenant.custom_domain}'
    
    try:
        # Query DNS TXT records
        import dns.resolver
        
        try:
            answers = dns.resolver.resolve(verification_host, 'TXT')
            txt_records = [str(r).strip('"') for r in answers]
        except dns.resolver.NXDOMAIN:
            return Response({
                'success': False,
                'error': 'Verification DNS record not found',
                'expected_record': f'{verification_host} TXT "lms-verify={expected_token}"',
            }, status=status.HTTP_400_BAD_REQUEST)
        except dns.resolver.NoAnswer:
            return Response({
                'success': False,
                'error': 'No TXT records found for verification hostname',
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for our verification token
        expected_value = f'lms-verify={expected_token}'
        if expected_value not in txt_records:
            return Response({
                'success': False,
                'error': 'Verification token not found in DNS records',
                'found_records': txt_records,
                'expected_value': expected_value,
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Verification successful
        tenant.custom_domain_verified = True
        tenant.save()
        
        logger.info(f"Custom domain verified for tenant {tenant.name}: {tenant.custom_domain}")
        
        return Response({
            'success': True,
            'message': 'Domain verified successfully',
            'domain': tenant.custom_domain,
            'next_steps': [
                'Your custom domain is now active',
                'SSL certificate will be provisioned automatically',
                'Users can now access your LMS at: https://' + tenant.custom_domain,
            ],
        })
        
    except ImportError:
        # dnspython not installed - use basic check
        logger.warning("dnspython not installed, skipping DNS verification")
        return Response({
            'success': False,
            'error': 'DNS verification not available. Please contact support.',
        }, status=status.HTTP_501_NOT_IMPLEMENTED)
    except Exception as e:
        logger.error(f"Domain verification error: {e}")
        return Response({
            'success': False,
            'error': 'Failed to verify domain. Please try again later.',
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def domain_remove(request):
    """
    Remove custom domain configuration.
    
    Reverts to using the default subdomain.
    """
    tenant = request.tenant
    
    if not tenant.custom_domain:
        return Response(
            {'error': 'No custom domain configured'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    old_domain = tenant.custom_domain
    tenant.custom_domain = ''
    tenant.custom_domain_verified = False
    tenant.custom_domain_ssl_expires = None
    tenant.save()
    
    logger.info(f"Custom domain removed for tenant {tenant.name}: {old_domain}")
    
    return Response({
        'success': True,
        'message': 'Custom domain removed',
        'default_url': f"https://{tenant.subdomain}.{settings.PLATFORM_DOMAIN}",
    })
