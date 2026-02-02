# apps/tenants/services.py

from apps.tenants.models import Tenant
from apps.users.models import User
from django.db import transaction
from django.utils.text import slugify


class TenantService:
    """
    Business logic for tenant operations.
    """
    
    @staticmethod
    @transaction.atomic
    def create_tenant_with_admin(
        name, 
        email, 
        admin_first_name, 
        admin_last_name, 
        admin_password
    ):
        """
        Create a new tenant along with its admin user.
        This is used during school onboarding.
        """
        # Generate subdomain from name
        subdomain = slugify(name).replace('-', '')[:20]
        
        # Check if subdomain exists
        counter = 1
        original_subdomain = subdomain
        while Tenant.objects.filter(subdomain=subdomain).exists():
            subdomain = f"{original_subdomain}{counter}"
            counter += 1
        
        # Create tenant
        tenant = Tenant.objects.create(
            name=name,
            slug=slugify(name),
            subdomain=subdomain,
            email=email,
            is_trial=True
        )
        
        # Create admin user
        admin_user = User.objects.create_user(
            email=email,
            password=admin_password,
            first_name=admin_first_name,
            last_name=admin_last_name,
            tenant=tenant,
            role='SCHOOL_ADMIN',
            is_active=True,
            email_verified=False
        )
        
        return {
            'tenant': tenant,
            'admin': admin_user,
            'subdomain': subdomain,
            'login_url': f"http://{subdomain}.localhost:8000"  # Update for production
        }
    
    @staticmethod
    def get_tenant_stats(tenant):
        """
        Get statistics for a tenant.
        """
        from apps.users.models import User
        from apps.courses.models import Course
        from apps.progress.models import TeacherProgress
        
        # Recent activity: last 10 completions
        recent_activity_qs = TeacherProgress.objects.filter(
            course__tenant=tenant,
            status='COMPLETED',
            completed_at__isnull=False
        ).select_related('teacher', 'course', 'content').order_by('-completed_at')[:10]
        
        recent_activity = [
            {
                'teacher_name': f"{p.teacher.first_name} {p.teacher.last_name}".strip() or p.teacher.email,
                'course_title': p.course.title,
                'content_title': p.content.title if p.content else None,
                'completed_at': p.completed_at.isoformat(),
            }
            for p in recent_activity_qs
        ]
        
        return {
            'total_teachers': User.objects.filter(tenant=tenant, role='TEACHER').count(),
            'total_admins': User.objects.filter(tenant=tenant, role='SCHOOL_ADMIN').count(),
            'total_courses': Course.objects.filter(tenant=tenant).count(),
            'published_courses': Course.objects.filter(tenant=tenant, is_published=True).count(),
            'recent_activity': recent_activity,
        }
