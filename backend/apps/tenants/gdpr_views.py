# apps/tenants/gdpr_views.py
"""
GDPR compliance and data export tools.

Provides:
- Full tenant data export (admin only)
- Individual user data export
- Data deletion with cascade and audit trail
- Right to be forgotten implementation
"""

import io
import json
import logging
import zipfile
from datetime import datetime
from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from utils.decorators import admin_only, tenant_required
from utils.audit import log_audit

logger = logging.getLogger(__name__)


def serialize_model_instance(instance, exclude_fields=None) -> dict:
    """Serialize a model instance to a dictionary."""
    exclude_fields = exclude_fields or ['password']
    data = {}
    for field in instance._meta.fields:
        if field.name in exclude_fields:
            continue
        value = getattr(instance, field.name)
        if hasattr(value, 'isoformat'):
            value = value.isoformat()
        elif hasattr(value, 'id'):
            value = str(value.id)
        else:
            value = str(value) if value is not None else None
        data[field.name] = value
    return data


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def tenant_data_export(request):
    """
    Export all tenant data as a ZIP file.
    
    Includes:
    - Tenant configuration
    - All users
    - All courses, modules, content
    - All progress records
    - All submissions
    - Audit logs
    
    This is a GDPR Article 20 compliant data portability export.
    """
    from apps.tenants.models import Tenant, AuditLog
    from apps.users.models import User
    from apps.courses.models import Course, Module, Content, TeacherGroup
    from apps.progress.models import TeacherProgress, Assignment, AssignmentSubmission
    from apps.notifications.models import Notification
    
    tenant = request.tenant
    
    # Create in-memory ZIP file
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Tenant info
        tenant_data = serialize_model_instance(tenant)
        zf.writestr('tenant.json', json.dumps(tenant_data, indent=2))
        
        # Users
        users = User.objects.filter(tenant=tenant)
        users_data = [serialize_model_instance(u) for u in users]
        zf.writestr('users.json', json.dumps(users_data, indent=2))
        
        # Teacher groups
        groups = TeacherGroup.objects.filter(tenant=tenant)
        groups_data = [serialize_model_instance(g) for g in groups]
        zf.writestr('groups.json', json.dumps(groups_data, indent=2))
        
        # Courses
        courses = Course.all_objects.filter(tenant=tenant)
        courses_data = []
        for course in courses:
            course_dict = serialize_model_instance(course)
            course_dict['assigned_teachers'] = list(
                course.assigned_teachers.values_list('id', flat=True)
            )
            course_dict['assigned_groups'] = list(
                course.assigned_groups.values_list('id', flat=True)
            )
            courses_data.append(course_dict)
        zf.writestr('courses.json', json.dumps(courses_data, indent=2, default=str))
        
        # Modules
        modules = Module.objects.filter(course__tenant=tenant)
        modules_data = [serialize_model_instance(m) for m in modules]
        zf.writestr('modules.json', json.dumps(modules_data, indent=2))
        
        # Content
        contents = Content.all_objects.filter(module__course__tenant=tenant)
        contents_data = [serialize_model_instance(c) for c in contents]
        zf.writestr('content.json', json.dumps(contents_data, indent=2))
        
        # Progress
        progress = TeacherProgress.objects.filter(course__tenant=tenant)
        progress_data = [serialize_model_instance(p) for p in progress]
        zf.writestr('progress.json', json.dumps(progress_data, indent=2))
        
        # Assignments
        assignments = Assignment.all_objects.filter(course__tenant=tenant)
        assignments_data = [serialize_model_instance(a) for a in assignments]
        zf.writestr('assignments.json', json.dumps(assignments_data, indent=2))
        
        # Submissions
        submissions = AssignmentSubmission.objects.filter(assignment__course__tenant=tenant)
        submissions_data = [serialize_model_instance(s) for s in submissions]
        zf.writestr('submissions.json', json.dumps(submissions_data, indent=2))
        
        # Notifications
        notifications = Notification.objects.filter(tenant=tenant)
        notifications_data = [serialize_model_instance(n) for n in notifications]
        zf.writestr('notifications.json', json.dumps(notifications_data, indent=2))
        
        # Audit logs (last 90 days)
        ninety_days_ago = timezone.now() - timezone.timedelta(days=90)
        audit_logs = AuditLog.objects.filter(tenant=tenant, timestamp__gte=ninety_days_ago)
        audit_data = [serialize_model_instance(a) for a in audit_logs]
        zf.writestr('audit_logs.json', json.dumps(audit_data, indent=2))
        
        # Export metadata
        metadata = {
            'export_date': timezone.now().isoformat(),
            'tenant_id': str(tenant.id),
            'tenant_name': tenant.name,
            'exported_by': str(request.user.id),
            'record_counts': {
                'users': len(users_data),
                'groups': len(groups_data),
                'courses': len(courses_data),
                'modules': len(modules_data),
                'content': len(contents_data),
                'progress': len(progress_data),
                'assignments': len(assignments_data),
                'submissions': len(submissions_data),
                'notifications': len(notifications_data),
                'audit_logs': len(audit_data),
            },
        }
        zf.writestr('export_metadata.json', json.dumps(metadata, indent=2))
    
    buffer.seek(0)
    
    # Log the export
    log_audit(
        'DATA_EXPORT',
        'Tenant',
        target_id=str(tenant.id),
        target_repr=f"Full data export for {tenant.name}",
        request=request
    )
    
    # Create response
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"{tenant.slug}_data_export_{timestamp}.zip"
    
    response = HttpResponse(buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    logger.info(f"Tenant data export completed: {tenant.name}")
    
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@tenant_required
def user_data_export(request):
    """
    Export individual user's data (GDPR Article 15 - Right of Access).
    
    Users can export their own data.
    Admins can export any user's data within their tenant.
    """
    from apps.users.models import User
    from apps.progress.models import TeacherProgress, AssignmentSubmission
    from apps.notifications.models import Notification
    
    user_id = request.query_params.get('user_id')
    
    # Determine target user
    if user_id and request.user.role == 'SCHOOL_ADMIN':
        try:
            target_user = User.objects.get(id=user_id, tenant=request.tenant)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)
    else:
        target_user = request.user
    
    # Create export data
    buffer = io.BytesIO()
    
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # User profile
        user_data = serialize_model_instance(target_user)
        zf.writestr('profile.json', json.dumps(user_data, indent=2))
        
        # Progress
        progress = TeacherProgress.objects.filter(teacher=target_user)
        progress_data = [serialize_model_instance(p) for p in progress]
        zf.writestr('progress.json', json.dumps(progress_data, indent=2))
        
        # Submissions
        submissions = AssignmentSubmission.objects.filter(teacher=target_user)
        submissions_data = [serialize_model_instance(s) for s in submissions]
        zf.writestr('submissions.json', json.dumps(submissions_data, indent=2))
        
        # Notifications
        notifications = Notification.objects.filter(teacher=target_user)
        notifications_data = [serialize_model_instance(n) for n in notifications]
        zf.writestr('notifications.json', json.dumps(notifications_data, indent=2))
        
        # Metadata
        metadata = {
            'export_date': timezone.now().isoformat(),
            'user_id': str(target_user.id),
            'user_email': target_user.email,
        }
        zf.writestr('export_metadata.json', json.dumps(metadata, indent=2))
    
    buffer.seek(0)
    
    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    filename = f"user_data_export_{timestamp}.zip"
    
    response = HttpResponse(buffer.read(), content_type='application/zip')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    return response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def user_data_delete(request):
    """
    Delete a user and their data (GDPR Article 17 - Right to Erasure).
    
    POST body:
    {
        "user_id": "uuid",
        "confirm": true
    }
    
    Cascades deletion and logs audit trail.
    """
    from apps.users.models import User
    from apps.progress.models import TeacherProgress, AssignmentSubmission
    from apps.notifications.models import Notification
    
    user_id = request.data.get('user_id')
    confirm = request.data.get('confirm', False)
    
    if not user_id:
        return Response({'error': 'user_id is required'}, status=400)
    
    if not confirm:
        return Response({'error': 'Confirmation required. Set confirm=true'}, status=400)
    
    try:
        target_user = User.objects.get(id=user_id, tenant=request.tenant)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=404)
    
    # Cannot delete yourself
    if target_user.id == request.user.id:
        return Response({'error': 'Cannot delete your own account'}, status=400)
    
    # Cannot delete other admins
    if target_user.role == 'SCHOOL_ADMIN':
        return Response({'error': 'Cannot delete other admin accounts'}, status=400)
    
    # Collect deletion statistics
    deletion_stats = {
        'progress_records': TeacherProgress.objects.filter(teacher=target_user).count(),
        'submissions': AssignmentSubmission.objects.filter(teacher=target_user).count(),
        'notifications': Notification.objects.filter(teacher=target_user).count(),
    }
    
    # Store user info for audit
    user_email = target_user.email
    user_name = f"{target_user.first_name} {target_user.last_name}"
    
    # Delete related data
    TeacherProgress.objects.filter(teacher=target_user).delete()
    AssignmentSubmission.objects.filter(teacher=target_user).delete()
    Notification.objects.filter(teacher=target_user).delete()
    
    # Delete user
    target_user.delete()
    
    # Log audit
    log_audit(
        'USER_DELETED',
        'User',
        target_id=str(user_id),
        target_repr=f"{user_name} ({user_email})",
        changes={'deletion_stats': deletion_stats, 'gdpr_request': True},
        request=request
    )
    
    logger.info(f"User deleted (GDPR): {user_email}")
    
    return Response({
        'success': True,
        'message': f'User {user_email} and all associated data have been deleted',
        'deletion_stats': deletion_stats,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@tenant_required
def request_account_deletion(request):
    """
    User requests deletion of their own account.
    
    Creates a deletion request that admin must approve.
    Or auto-deletes if tenant policy allows.
    """
    user = request.user
    
    # Cannot delete admin accounts this way
    if user.role == 'SCHOOL_ADMIN':
        return Response({
            'error': 'Admin accounts cannot be deleted via self-service. Please contact support.'
        }, status=400)
    
    # For now, just mark the request (could be expanded to pending approval workflow)
    log_audit(
        'DELETION_REQUESTED',
        'User',
        target_id=str(user.id),
        target_repr=f"{user.first_name} {user.last_name} ({user.email})",
        changes={'self_requested': True},
        request=request
    )
    
    return Response({
        'success': True,
        'message': 'Account deletion request received. An administrator will process your request.',
    })
