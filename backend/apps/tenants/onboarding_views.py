# apps/tenants/onboarding_views.py
"""
Public tenant self-service onboarding endpoints.

Allows new schools to:
1. Sign up with school name, admin email, plan selection
2. Creates tenant + admin account
3. Sends verification email
4. Auto-provision with FREE plan
"""

import logging
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from .models import Tenant


class SignupThrottle(ScopedRateThrottle):
    scope = 'tenant_signup'


class SubdomainCheckThrottle(ScopedRateThrottle):
    scope = 'subdomain_check'

logger = logging.getLogger(__name__)


def generate_unique_subdomain(name: str) -> str:
    """
    Generate a unique subdomain from school name.
    Appends numbers if subdomain already exists.
    """
    base = slugify(name)[:50]
    subdomain = base
    counter = 1
    
    while Tenant.objects.filter(subdomain=subdomain).exists():
        subdomain = f"{base}{counter}"
        counter += 1
    
    return subdomain


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([SignupThrottle])
def tenant_signup(request):
    """
    Public endpoint for new school registration.
    
    Request body:
    {
        "school_name": "Demo School",
        "admin_email": "admin@demo.com",
        "admin_first_name": "John",
        "admin_last_name": "Doe",
        "admin_password": "securepassword123",
        "plan": "FREE"  // Optional, defaults to FREE
    }
    
    Returns:
    {
        "success": true,
        "tenant_id": "uuid",
        "subdomain": "demo-school",
        "message": "Verification email sent"
    }
    """
    from apps.users.models import User
    
    # Validate required fields
    school_name = request.data.get('school_name', '').strip()
    admin_email = request.data.get('admin_email', '').strip().lower()
    admin_first_name = request.data.get('admin_first_name', '').strip()
    admin_last_name = request.data.get('admin_last_name', '').strip()
    admin_password = request.data.get('admin_password', '')
    plan = request.data.get('plan', 'FREE').upper()
    
    errors = {}
    
    if not school_name:
        errors['school_name'] = 'School name is required'
    elif len(school_name) < 3:
        errors['school_name'] = 'School name must be at least 3 characters'
    
    if not admin_email:
        errors['admin_email'] = 'Admin email is required'
    elif User.objects.filter(email=admin_email).exists():
        errors['admin_email'] = 'Email already registered'
    
    if not admin_first_name:
        errors['admin_first_name'] = 'First name is required'
    
    if not admin_last_name:
        errors['admin_last_name'] = 'Last name is required'
    
    if not admin_password:
        errors['admin_password'] = 'Password is required'
    else:
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_password(admin_password)
        except DjangoValidationError as e:
            errors['admin_password'] = list(e.messages)
    
    if plan not in ['FREE', 'STARTER', 'PRO']:
        errors['plan'] = 'Invalid plan selection'
    
    if errors:
        return Response({'errors': errors}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        with transaction.atomic():
            # Generate unique subdomain
            subdomain = generate_unique_subdomain(school_name)
            
            # Set trial period (14 days)
            trial_end = timezone.now().date() + timedelta(days=14)
            
            # Create tenant
            tenant = Tenant.objects.create(
                name=school_name,
                subdomain=subdomain,
                email=admin_email,
                is_active=True,
                is_trial=True,
                trial_end_date=trial_end,
                plan=plan,
                plan_started_at=timezone.now(),
                # Feature flags based on plan
                feature_video_upload=(plan != 'FREE'),
                feature_auto_quiz=(plan in ['PRO', 'ENTERPRISE']),
                feature_transcripts=(plan in ['PRO', 'ENTERPRISE']),
                feature_custom_branding=(plan != 'FREE'),
                feature_reports_export=(plan != 'FREE'),
                feature_certificates=(plan != 'FREE'),
            )
            
            # Create admin user
            admin_user = User.objects.create_user(
                email=admin_email,
                password=admin_password,
                first_name=admin_first_name,
                last_name=admin_last_name,
                role='SCHOOL_ADMIN',
                tenant=tenant,
                is_active=True,
                email_verified=False,  # Needs verification
            )
            
            # Send verification email
            send_verification_email(admin_user, tenant)
            
            logger.info(f"New tenant created: {tenant.name} ({tenant.subdomain})")
            
            return Response({
                'success': True,
                'tenant_id': str(tenant.id),
                'subdomain': tenant.subdomain,
                'message': 'Account created! Please check your email to verify your account.',
                'login_url': f"https://{tenant.subdomain}.{settings.PLATFORM_DOMAIN}/login",
            }, status=status.HTTP_201_CREATED)
            
    except Exception as e:
        logger.error(f"Tenant signup failed: {e}")
        return Response(
            {'error': 'Failed to create account. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


def send_verification_email(user, tenant):
    """Send email verification link to new admin."""
    from utils.email_verification import generate_verification_token
    
    try:
        token = generate_verification_token(user)
        verification_url = (
            f"https://{tenant.subdomain}.{settings.PLATFORM_DOMAIN}"
            f"/verify-email?token={token}"
        )
        
        subject = f"Verify your {settings.PLATFORM_NAME} account"
        message = f"""
Hello {user.first_name},

Welcome to {settings.PLATFORM_NAME}!

Your school "{tenant.name}" has been created. Please verify your email to activate your account:

{verification_url}

This link will expire in 24 hours.

Your login URL: https://{tenant.subdomain}.{settings.PLATFORM_DOMAIN}/login

Best regards,
The {settings.PLATFORM_NAME} Team
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([SubdomainCheckThrottle])
def check_subdomain(request):
    """
    Check if a subdomain is available.
    
    Query params:
    - name: School name to check
    
    Returns:
    {
        "available": true,
        "suggested_subdomain": "demo-school"
    }
    """
    name = request.query_params.get('name', '').strip()
    
    if not name or len(name) < 3:
        return Response({'error': 'Name must be at least 3 characters'}, status=400)
    
    suggested = generate_unique_subdomain(name)
    base = slugify(name)[:50]
    
    return Response({
        'available': not Tenant.objects.filter(subdomain=base).exists(),
        'suggested_subdomain': suggested,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def available_plans(request):
    """
    Get available subscription plans with features.
    
    Returns list of plans with pricing and features.
    """
    plans = [
        {
            'id': 'FREE',
            'name': 'Free',
            'price': 0,
            'price_yearly': 0,
            'max_teachers': 5,
            'max_courses': 3,
            'max_storage_mb': 100,
            'features': [
                'Up to 5 teachers',
                'Up to 3 courses',
                '100 MB storage',
                'Basic reporting',
                'Email support',
            ],
            'recommended': False,
        },
        {
            'id': 'STARTER',
            'name': 'Starter',
            'price': 29,
            'price_yearly': 290,
            'max_teachers': 25,
            'max_courses': 20,
            'max_storage_mb': 5000,
            'features': [
                'Up to 25 teachers',
                'Up to 20 courses',
                '5 GB storage',
                'Video uploads',
                'Custom branding',
                'Certificates',
                'Priority support',
            ],
            'recommended': True,
        },
        {
            'id': 'PRO',
            'name': 'Professional',
            'price': 79,
            'price_yearly': 790,
            'max_teachers': 100,
            'max_courses': 100,
            'max_storage_mb': 50000,
            'features': [
                'Up to 100 teachers',
                'Unlimited courses',
                '50 GB storage',
                'AI quiz generation',
                'Auto transcripts',
                'Advanced analytics',
                'API access',
                'Dedicated support',
            ],
            'recommended': False,
        },
    ]
    
    return Response(plans)
