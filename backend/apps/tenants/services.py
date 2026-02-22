# apps/tenants/services.py

from collections import Counter

from django.db import models, transaction
from django.utils.text import slugify

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.progress.completion_metrics import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_NOT_STARTED,
    build_teacher_course_snapshots,
)


# ── Plan presets ─────────────────────────────────────────────────────────────
# When super admin changes a plan, these defaults are applied.
# Individual limits/flags can still be overridden after applying a preset.

PLAN_PRESETS = {
    "FREE": {
        "max_teachers": 10,
        "max_courses": 5,
        "max_storage_mb": 500,
        "max_video_duration_minutes": 30,
        "feature_video_upload": False,
        "feature_auto_quiz": False,
        "feature_transcripts": False,
        "feature_reminders": True,
        "feature_custom_branding": False,
        "feature_reports_export": False,
        "feature_groups": True,
        "feature_certificates": False,
        "feature_teacher_authoring": False,
    },
    "STARTER": {
        "max_teachers": 50,
        "max_courses": 20,
        "max_storage_mb": 5000,
        "max_video_duration_minutes": 60,
        "feature_video_upload": True,
        "feature_auto_quiz": False,
        "feature_transcripts": True,
        "feature_reminders": True,
        "feature_custom_branding": True,
        "feature_reports_export": False,
        "feature_groups": True,
        "feature_certificates": False,
        "feature_teacher_authoring": True,
    },
    "PRO": {
        "max_teachers": 200,
        "max_courses": 100,
        "max_storage_mb": 50000,
        "max_video_duration_minutes": 60,
        "feature_video_upload": True,
        "feature_auto_quiz": True,
        "feature_transcripts": True,
        "feature_reminders": True,
        "feature_custom_branding": True,
        "feature_reports_export": True,
        "feature_groups": True,
        "feature_certificates": True,
        "feature_teacher_authoring": True,
    },
    "ENTERPRISE": {
        "max_teachers": 9999,
        "max_courses": 9999,
        "max_storage_mb": 500000,
        "max_video_duration_minutes": 120,
        "feature_video_upload": True,
        "feature_auto_quiz": True,
        "feature_transcripts": True,
        "feature_reminders": True,
        "feature_custom_branding": True,
        "feature_reports_export": True,
        "feature_groups": True,
        "feature_certificates": True,
        "feature_teacher_authoring": True,
    },
}


def apply_plan_preset(tenant: Tenant, plan: str, save: bool = True) -> Tenant:
    """Apply a plan's preset limits and feature flags to a tenant."""
    preset = PLAN_PRESETS.get(plan)
    if not preset:
        raise ValueError(f"Unknown plan: {plan}")
    tenant.plan = plan
    for key, value in preset.items():
        setattr(tenant, key, value)
    if save:
        tenant.save()
    return tenant


TEACHER_ROLES = ("TEACHER", "HOD", "IB_COORDINATOR")


def get_tenant_usage(tenant: Tenant) -> dict:
    """Return current resource usage counts for a tenant."""
    from apps.courses.models import Course
    from apps.courses.models import RichTextImageAsset
    from apps.media.models import MediaAsset
    teacher_count = User.objects.filter(tenant=tenant, role__in=TEACHER_ROLES, is_active=True).count()
    course_count = Course.objects.filter(tenant=tenant).count()
    # Storage: sum file sizes from tenant-owned assets (bytes → MB)
    from apps.courses.models import Content
    content_bytes = Content.objects.filter(
        module__course__tenant=tenant, file_size__isnull=False
    ).aggregate(total=models.Sum("file_size"))["total"] or 0
    media_bytes = MediaAsset.objects.filter(
        tenant=tenant, file_size__isnull=False
    ).aggregate(total=models.Sum("file_size"))["total"] or 0
    rich_text_bytes = RichTextImageAsset.all_objects.filter(
        tenant=tenant, file_size__isnull=False
    ).aggregate(total=models.Sum("file_size"))["total"] or 0

    storage_bytes = content_bytes + media_bytes + rich_text_bytes
    storage_mb = round(storage_bytes / (1024 * 1024), 1)

    return {
        "teachers": {"used": teacher_count, "limit": tenant.max_teachers},
        "courses": {"used": course_count, "limit": tenant.max_courses},
        "storage_mb": {"used": storage_mb, "limit": tenant.max_storage_mb},
    }


def check_limit(tenant: Tenant, resource: str) -> bool:
    """Return True if tenant is within limits for the given resource."""
    usage = get_tenant_usage(tenant)
    bucket = usage.get(resource)
    if not bucket:
        return True
    return bucket["used"] < bucket["limit"]


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
        Get statistics for a tenant — all computed dynamically from DB.
        """
        from apps.users.models import User
        from apps.courses.models import Course, Content
        from apps.progress.models import TeacherProgress, Assignment, AssignmentSubmission, QuizSubmission

        teachers = User.objects.filter(tenant=tenant, role__in=['TEACHER', 'HOD', 'IB_COORDINATOR'], is_active=True)
        teacher_count = teachers.count()
        courses = Course.objects.filter(tenant=tenant, is_active=True)
        published = courses.filter(is_published=True).order_by('title')

        teacher_ids = list(teachers.values_list('id', flat=True))
        published_courses = list(published)
        published_course_ids = [course.id for course in published_courses]
        completion_snapshots = build_teacher_course_snapshots(published_course_ids, teacher_ids)

        def _assigned_teacher_ids(course):
            if course.assigned_to_all:
                return teacher_ids
            return list(
                teachers.filter(
                    models.Q(assigned_courses=course) | models.Q(teacher_groups__courses=course)
                ).distinct().values_list('id', flat=True)
            )

        course_completions = 0
        course_in_progress = 0
        total_course_slots = 0
        completed_by_teacher: Counter = Counter()
        for course in published_courses:
            assigned_ids = _assigned_teacher_ids(course)
            total_course_slots += len(assigned_ids)
            for teacher_id in assigned_ids:
                snapshot = completion_snapshots.get((str(course.id), str(teacher_id)))
                if not snapshot:
                    continue
                if snapshot.status == STATUS_COMPLETED:
                    course_completions += 1
                    completed_by_teacher[teacher_id] += 1
                elif snapshot.status == STATUS_IN_PROGRESS:
                    course_in_progress += 1

        avg_completion_pct = round((course_completions / total_course_slots * 100) if total_course_slots > 0 else 0, 1)

        # Content-level stats
        total_content = Content.objects.filter(module__course__tenant=tenant, is_active=True).count()
        content_completions = TeacherProgress.objects.filter(
            course__tenant=tenant, content__isnull=False, status='COMPLETED'
        ).count()

        # Assignment stats
        total_assignments = Assignment.objects.filter(course__tenant=tenant, is_active=True).count()
        total_submissions = AssignmentSubmission.objects.filter(assignment__course__tenant=tenant).count()
        graded_submissions = AssignmentSubmission.objects.filter(
            assignment__course__tenant=tenant, status='GRADED'
        ).count()
        pending_regular = AssignmentSubmission.objects.filter(
            assignment__course__tenant=tenant, status='SUBMITTED'
        )
        pending_quiz = QuizSubmission.objects.filter(
            quiz__assignment__course__tenant=tenant,
            graded_at__isnull=True,
        ).exclude(answers={})
        pending_submissions_count = pending_regular.count() + pending_quiz.count()

        # Active teachers (logged in within last 30 days)
        from django.utils import timezone
        import datetime
        thirty_days_ago = timezone.now() - datetime.timedelta(days=30)
        active_teachers = teachers.filter(last_login__gte=thirty_days_ago).count()

        # Teachers with no progress at all (never started any course)
        teachers_with_progress_ids = set(
            TeacherProgress.objects.filter(
                course__tenant=tenant, teacher__in=teachers
            ).values_list('teacher_id', flat=True).distinct()
        )
        inactive_teachers = teacher_count - len(teachers_with_progress_ids)
        inactive_teachers_detail = [
            {
                'id': str(t.id),
                'name': f"{t.first_name} {t.last_name}".strip() or t.email,
                'email': t.email,
            }
            for t in teachers.exclude(id__in=teachers_with_progress_ids).order_by('last_name', 'first_name')[:50]
        ]

        # Pending review detail: regular submissions + quiz submissions awaiting grading
        pending_review_detail = []
        for s in pending_regular.select_related('teacher', 'assignment', 'assignment__course')[:50]:
            pending_review_detail.append({
                'submission_id': str(s.id),
                'teacher_id': str(s.teacher_id),
                'teacher_name': f"{s.teacher.first_name} {s.teacher.last_name}".strip() or s.teacher.email,
                'teacher_email': s.teacher.email,
                'assignment_id': str(s.assignment_id),
                'assignment_title': s.assignment.title,
                'course_id': str(s.assignment.course_id),
                'course_title': s.assignment.course.title,
                'submitted_at': s.submitted_at.isoformat() if s.submitted_at else None,
                'is_quiz': False,
            })
        for qs in pending_quiz.select_related('teacher', 'quiz__assignment', 'quiz__assignment__course')[:50]:
            a = qs.quiz.assignment
            pending_review_detail.append({
                'submission_id': str(qs.id),
                'teacher_id': str(qs.teacher_id),
                'teacher_name': f"{qs.teacher.first_name} {qs.teacher.last_name}".strip() or qs.teacher.email,
                'teacher_email': qs.teacher.email,
                'assignment_id': str(a.id),
                'assignment_title': a.title,
                'course_id': str(a.course_id),
                'course_title': a.course.title,
                'submitted_at': qs.submitted_at.isoformat() if qs.submitted_at else None,
                'is_quiz': True,
            })
        pending_review_detail.sort(key=lambda x: x['submitted_at'] or '', reverse=True)

        # Top performing teachers (most canonical course completions).
        teacher_by_id = {teacher.id: teacher for teacher in teachers}
        top_teacher_rows = sorted(
            completed_by_teacher.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
        top_teachers = []
        for teacher_id, completed_count in top_teacher_rows:
            teacher = teacher_by_id.get(teacher_id)
            if not teacher:
                continue
            top_teachers.append(
                {
                    'name': f"{teacher.first_name} {teacher.last_name}".strip() or teacher.email,
                    'completed_courses': completed_count,
                }
            )

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
            'total_teachers': teacher_count,
            'active_teachers': active_teachers,
            'inactive_teachers': inactive_teachers,
            'total_admins': User.objects.filter(tenant=tenant, role='SCHOOL_ADMIN').count(),
            'total_courses': courses.count(),
            'published_courses': len(published_courses),
            'total_content_items': total_content,
            'avg_completion_pct': avg_completion_pct,
            'course_completions': course_completions,
            'courses_in_progress': course_in_progress,
            'content_completions': content_completions,
            'total_assignments': total_assignments,
            'total_submissions': total_submissions,
            'graded_submissions': graded_submissions,
            'pending_review': pending_submissions_count,
            'inactive_teachers_detail': inactive_teachers_detail,
            'pending_review_detail': pending_review_detail,
            'top_teachers': top_teachers,
            'recent_activity': recent_activity,
        }

    @staticmethod
    def get_tenant_analytics(tenant, course_id=None, months=6):
        """
        Analytics data for Chart.js graphs — course-level and teacher-level breakdowns.
        course_id: optional filter for course breakdown and monthly trend.
        months: number of months for monthly trend (6–12).
        """
        from apps.users.models import User
        from apps.courses.models import Course
        from apps.progress.models import Assignment
        from django.db.models import Count, Q
        from django.utils import timezone

        teachers = User.objects.filter(tenant=tenant, role__in=['TEACHER', 'HOD', 'IB_COORDINATOR'], is_active=True)
        published_courses = Course.objects.filter(tenant=tenant, is_active=True, is_published=True)
        if course_id:
            try:
                published_courses = published_courses.filter(id=course_id)
            except (TypeError, ValueError):
                pass

        teacher_ids = list(teachers.values_list('id', flat=True))
        published_course_list = list(published_courses.order_by('title'))
        breakdown_courses = published_course_list[:20]
        completion_snapshots = build_teacher_course_snapshots(
            [course.id for course in published_course_list],
            teacher_ids,
        )

        def _assigned_teacher_ids(course):
            if course.assigned_to_all:
                return teacher_ids
            return list(
                teachers.filter(
                    Q(assigned_courses=course) | Q(teacher_groups__courses=course)
                ).distinct().values_list('id', flat=True)
            )

        teacher_course_status_map: dict = {}
        assigned_teacher_ids_by_course = {}
        for c in published_course_list:
            assigned_ids = _assigned_teacher_ids(c)
            assigned_teacher_ids_by_course[str(c.id)] = assigned_ids
            for teacher_id in assigned_ids:
                snapshot = completion_snapshots.get((str(c.id), str(teacher_id)))
                status = snapshot.status if snapshot else STATUS_NOT_STARTED
                teacher_course_status_map[(str(teacher_id), str(c.id))] = status

        # --- Per-course completion breakdown ---
        course_breakdown = []
        for c in breakdown_courses:
            assigned_ids = assigned_teacher_ids_by_course.get(str(c.id), [])
            assigned_count = len(assigned_ids)
            completed = 0
            in_progress = 0
            for teacher_id in assigned_ids:
                status = teacher_course_status_map.get((str(teacher_id), str(c.id)), STATUS_NOT_STARTED)
                if status == STATUS_COMPLETED:
                    completed += 1
                elif status == STATUS_IN_PROGRESS:
                    in_progress += 1
            not_started = max(0, assigned_count - completed - in_progress)
            course_breakdown.append({
                'course_id': str(c.id),
                'title': c.title[:40],
                'assigned': assigned_count,
                'completed': completed,
                'in_progress': in_progress,
                'not_started': not_started,
            })

        # --- Monthly completion trend (last N months) ---
        now = timezone.now()
        # Step back by calendar months to avoid skipped/duplicated months
        # that occur when using timedelta(days=30*i) on dates like the 31st.
        current_first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_starts = []
        for i in range(months):
            # Subtract i months from the current month's first day
            y = current_first.year
            m = current_first.month - i
            while m <= 0:
                m += 12
                y -= 1
            month_starts.append(current_first.replace(year=y, month=m))
        month_starts.reverse()  # oldest first

        monthly_trend = []
        completed_snapshots = [
            snapshot
            for snapshot in completion_snapshots.values()
            if snapshot.status == STATUS_COMPLETED and snapshot.last_completed_at is not None
        ]
        for idx, month_start in enumerate(month_starts):
            if idx + 1 < len(month_starts):
                month_end = month_starts[idx + 1]
            else:
                month_end = now  # current (partial) month goes up to now
            count = sum(
                1
                for snapshot in completed_snapshots
                if month_start <= snapshot.last_completed_at < month_end
            )
            monthly_trend.append({
                'month': month_start.strftime('%b %Y'),
                'completions': count,
            })

        # --- Assignment type breakdown ---
        assignments = Assignment.objects.filter(course__tenant=tenant, is_active=True)
        assignment_breakdown = {
            'total': assignments.count(),
            'manual': assignments.filter(generation_source='MANUAL').count(),
            'auto_quiz': assignments.filter(generation_source='VIDEO_AUTO').exclude(quiz__isnull=True).count(),
            'auto_reflection': assignments.filter(generation_source='VIDEO_AUTO', quiz__isnull=True).count(),
        }

        # --- Teacher engagement distribution ---
        engagement = {'highly_active': 0, 'active': 0, 'low_activity': 0, 'inactive': 0}
        for t in teachers:
            statuses = [
                status
                for (teacher_id, _course_id), status in teacher_course_status_map.items()
                if teacher_id == str(t.id)
            ]
            completed = sum(1 for status in statuses if status == STATUS_COMPLETED)
            started = sum(1 for status in statuses if status != STATUS_NOT_STARTED)
            if completed >= 3:
                engagement['highly_active'] += 1
            elif completed >= 1:
                engagement['active'] += 1
            elif started >= 1:
                engagement['low_activity'] += 1
            else:
                engagement['inactive'] += 1

        # --- Department-wise stats ---
        dept_stats_qs = (
            teachers.exclude(department='').values('department')
            .annotate(count=Count('id'))
            .order_by('-count')[:10]
        )
        dept_stats = list(dept_stats_qs)

        return {
            'course_breakdown': course_breakdown,
            'monthly_trend': monthly_trend,
            'assignment_breakdown': assignment_breakdown,
            'teacher_engagement': engagement,
            'department_stats': dept_stats,
        }
