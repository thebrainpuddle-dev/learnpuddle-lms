# apps/progress/gamification_tasks.py

"""
Celery tasks for the LearnPuddle gamification system.

- process_daily_streaks: daily streak maintenance (freezes, resets)
- compute_leaderboard_snapshots: periodic leaderboard ranking
- backfill_xp_for_existing_progress: one-time XP backfill for historical data
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name='progress.process_daily_streaks')
def process_daily_streaks():
    """
    Daily task to process streak breaks and freeze resets.

    For each tenant with active gamification:
    1. Find all TeacherStreak records where last_activity_date < yesterday
    2. If teacher has freeze available and freeze_used_today is False:
       - Use a freeze (increment freeze_count_this_month, set freeze_used_today=True)
       - Don't break streak
    3. If no freeze: reset current_streak to 0
    4. Reset freeze_used_today = False for all streaks (new day)
    5. If it's the 1st of the month: reset freeze_count_this_month = 0
    """
    from apps.progress.gamification_models import GamificationConfig, TeacherStreak

    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    is_first_of_month = today.day == 1

    summary = {
        'tenants_processed': 0,
        'streaks_frozen': 0,
        'streaks_broken': 0,
        'freezes_reset': 0,
        'monthly_freeze_counts_reset': 0,
    }

    configs = GamificationConfig.objects.filter(is_active=True).select_related('tenant')

    for config in configs:
        tenant = config.tenant
        if not tenant.is_active:
            continue

        summary['tenants_processed'] += 1

        # --- Step 1-3: Process streaks that missed yesterday ---
        missed_streaks = TeacherStreak.all_objects.filter(
            tenant=tenant,
            current_streak__gt=0,
            last_activity_date__lt=yesterday,
        )

        streaks_to_freeze = []
        streaks_to_break = []

        for streak in missed_streaks:
            if (
                streak.freeze_count_this_month < config.streak_freeze_max
                and not streak.freeze_used_today
            ):
                # Use a freeze to preserve the streak
                streak.freeze_count_this_month += 1
                streak.freeze_used_today = True
                streak.streak_frozen_until = today
                streaks_to_freeze.append(streak)
            else:
                # No freeze available — break the streak
                streak.current_streak = 0
                streaks_to_break.append(streak)

        if streaks_to_freeze:
            with transaction.atomic():
                TeacherStreak.all_objects.bulk_update(
                    streaks_to_freeze,
                    ['freeze_count_this_month', 'freeze_used_today', 'streak_frozen_until'],
                )
            summary['streaks_frozen'] += len(streaks_to_freeze)
            logger.info(
                "Tenant %s: froze %d streaks",
                tenant.id, len(streaks_to_freeze),
            )

        if streaks_to_break:
            with transaction.atomic():
                TeacherStreak.all_objects.bulk_update(
                    streaks_to_break,
                    ['current_streak'],
                )
            summary['streaks_broken'] += len(streaks_to_break)
            logger.info(
                "Tenant %s: broke %d streaks",
                tenant.id, len(streaks_to_break),
            )

        # --- Step 4: Reset freeze_used_today for all streaks (new day) ---
        with transaction.atomic():
            reset_count = TeacherStreak.all_objects.filter(
                tenant=tenant,
                freeze_used_today=True,
            ).update(freeze_used_today=False)
        summary['freezes_reset'] += reset_count

        # --- Step 5: Reset monthly freeze count on the 1st ---
        if is_first_of_month:
            with transaction.atomic():
                monthly_reset_count = TeacherStreak.all_objects.filter(
                    tenant=tenant,
                    freeze_count_this_month__gt=0,
                ).update(freeze_count_this_month=0)
            summary['monthly_freeze_counts_reset'] += monthly_reset_count
            if monthly_reset_count:
                logger.info(
                    "Tenant %s: reset monthly freeze count for %d streaks",
                    tenant.id, monthly_reset_count,
                )

    logger.info("process_daily_streaks complete: %s", summary)
    return summary


@shared_task(name='progress.compute_leaderboard_snapshots')
def compute_leaderboard_snapshots():
    """
    Compute and store leaderboard snapshots for all active tenants.

    For each tenant with active gamification and leaderboard_enabled:
    1. Get all non-opted-out TeacherXPSummary records, ordered by total_xp desc
    2. Create/update LeaderboardSnapshot entries for 'all_time' period
    3. For 'weekly': filter XP transactions from last 7 days, rank by period XP
    4. For 'monthly': filter XP transactions from this calendar month, rank by period XP
    5. Assign ranks (1-based, dense ranking)
    6. Delete snapshots older than 90 days
    """
    from apps.progress.gamification_models import (
        GamificationConfig,
        LeaderboardSnapshot,
        TeacherXPSummary,
        XPTransaction,
    )

    today = timezone.localdate()
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cutoff_90_days = today - timedelta(days=90)

    summary = {
        'tenants_processed': 0,
        'snapshots_created': 0,
        'snapshots_updated': 0,
        'old_snapshots_deleted': 0,
    }

    configs = GamificationConfig.objects.filter(
        is_active=True,
        leaderboard_enabled=True,
    ).select_related('tenant')

    for config in configs:
        tenant = config.tenant
        if not tenant.is_active:
            continue

        summary['tenants_processed'] += 1

        # Get all eligible teachers (not opted out)
        eligible_summaries = TeacherXPSummary.all_objects.filter(
            tenant=tenant,
            opted_out=False,
        ).order_by('-total_xp')

        if not eligible_summaries.exists():
            continue

        teacher_ids = list(eligible_summaries.values_list('teacher_id', flat=True))

        # ----- ALL TIME -----
        all_time_entries = []
        for rank, xp_summary in enumerate(eligible_summaries, start=1):
            all_time_entries.append({
                'teacher_id': xp_summary.teacher_id,
                'rank': rank,
                'xp_total': xp_summary.total_xp,
                'xp_period': xp_summary.total_xp,
            })

        created, updated = _upsert_snapshots(
            tenant, 'all_time', today, all_time_entries,
        )
        summary['snapshots_created'] += created
        summary['snapshots_updated'] += updated

        # ----- WEEKLY -----
        weekly_xp = (
            XPTransaction.all_objects.filter(
                tenant=tenant,
                teacher_id__in=teacher_ids,
                created_at__gte=week_ago,
            )
            .values('teacher_id')
            .annotate(period_xp=Sum('xp_amount'))
            .order_by('-period_xp')
        )

        weekly_xp_map = {row['teacher_id']: max(0, row['period_xp'] or 0) for row in weekly_xp}
        # Build ranked list (teachers with 0 weekly XP still appear)
        weekly_entries = _build_ranked_entries(
            teacher_ids, eligible_summaries, weekly_xp_map,
        )

        created, updated = _upsert_snapshots(
            tenant, 'weekly', today, weekly_entries,
        )
        summary['snapshots_created'] += created
        summary['snapshots_updated'] += updated

        # ----- MONTHLY -----
        monthly_xp = (
            XPTransaction.all_objects.filter(
                tenant=tenant,
                teacher_id__in=teacher_ids,
                created_at__gte=month_start,
            )
            .values('teacher_id')
            .annotate(period_xp=Sum('xp_amount'))
            .order_by('-period_xp')
        )

        monthly_xp_map = {row['teacher_id']: max(0, row['period_xp'] or 0) for row in monthly_xp}
        monthly_entries = _build_ranked_entries(
            teacher_ids, eligible_summaries, monthly_xp_map,
        )

        created, updated = _upsert_snapshots(
            tenant, 'monthly', today, monthly_entries,
        )
        summary['snapshots_created'] += created
        summary['snapshots_updated'] += updated

        # ----- CLEANUP: delete snapshots older than 90 days -----
        deleted_count, _ = LeaderboardSnapshot.all_objects.filter(
            tenant=tenant,
            snapshot_date__lt=cutoff_90_days,
        ).delete()
        summary['old_snapshots_deleted'] += deleted_count

    logger.info("compute_leaderboard_snapshots complete: %s", summary)
    return summary


def _build_ranked_entries(teacher_ids, eligible_summaries, period_xp_map):
    """
    Build a list of ranked entries sorted by period XP (desc), using dense ranking.

    Teachers not in period_xp_map get 0 period XP.
    """
    xp_summary_map = {s.teacher_id: s for s in eligible_summaries}

    entries = []
    for teacher_id in teacher_ids:
        xp_summary = xp_summary_map.get(teacher_id)
        if not xp_summary:
            continue
        entries.append({
            'teacher_id': teacher_id,
            'xp_total': xp_summary.total_xp,
            'xp_period': period_xp_map.get(teacher_id, 0),
        })

    # Sort by period XP descending, then by total XP descending as tiebreaker
    entries.sort(key=lambda e: (-e['xp_period'], -e['xp_total']))

    # Dense ranking
    prev_xp = None
    rank = 0
    for entry in entries:
        if entry['xp_period'] != prev_xp:
            rank += 1
            prev_xp = entry['xp_period']
        entry['rank'] = rank

    return entries


def _upsert_snapshots(tenant, period, snapshot_date, entries):
    """
    Create or update LeaderboardSnapshot entries for a given tenant/period/date.

    Returns (created_count, updated_count).
    """
    from apps.progress.gamification_models import LeaderboardSnapshot

    created_count = 0
    updated_count = 0

    to_create = []
    to_update = []

    # Fetch existing snapshots for this tenant/period/date
    existing = {
        snap.teacher_id: snap
        for snap in LeaderboardSnapshot.all_objects.filter(
            tenant=tenant,
            period=period,
            snapshot_date=snapshot_date,
        )
    }

    for entry in entries:
        teacher_id = entry['teacher_id']
        if teacher_id in existing:
            snap = existing[teacher_id]
            snap.rank = entry['rank']
            snap.xp_total = entry['xp_total']
            snap.xp_period = entry['xp_period']
            to_update.append(snap)
        else:
            to_create.append(
                LeaderboardSnapshot(
                    tenant=tenant,
                    teacher_id=teacher_id,
                    period=period,
                    rank=entry['rank'],
                    xp_total=entry['xp_total'],
                    xp_period=entry['xp_period'],
                    snapshot_date=snapshot_date,
                )
            )

    if to_create:
        with transaction.atomic():
            LeaderboardSnapshot.all_objects.bulk_create(to_create)
        created_count = len(to_create)

    if to_update:
        with transaction.atomic():
            LeaderboardSnapshot.all_objects.bulk_update(
                to_update,
                ['rank', 'xp_total', 'xp_period'],
            )
        updated_count = len(to_update)

    return created_count, updated_count


@shared_task(name='progress.backfill_xp_for_existing_progress')
def backfill_xp_for_existing_progress(tenant_id=None):
    """
    One-time task to backfill XP for existing teacher progress.

    Scans all completed TeacherProgress, AssignmentSubmission, QuizSubmission
    and creates XPTransactions for any that don't have corresponding entries.

    Can be run for a specific tenant or all tenants.
    Uses gamification_engine.award_xp with deduplication (won't double-award).
    """
    from apps.progress.gamification_engine import award_xp
    from apps.progress.gamification_models import GamificationConfig, XPTransaction
    from apps.progress.models import AssignmentSubmission, QuizSubmission, TeacherProgress
    from apps.tenants.models import Tenant

    summary = {
        'tenants_processed': 0,
        'content_completions_awarded': 0,
        'course_completions_awarded': 0,
        'assignment_submissions_awarded': 0,
        'quiz_submissions_awarded': 0,
        'skipped_already_exists': 0,
    }

    if tenant_id:
        tenants = Tenant.objects.filter(id=tenant_id, is_active=True)
    else:
        tenants = Tenant.objects.filter(is_active=True)

    for tenant in tenants:
        # Only backfill for tenants with active gamification
        try:
            config = GamificationConfig.objects.get(tenant=tenant, is_active=True)
        except GamificationConfig.DoesNotExist:
            continue

        summary['tenants_processed'] += 1
        logger.info("Backfilling XP for tenant %s (%s)", tenant.id, tenant.name)

        # --- Content completions ---
        completed_content = TeacherProgress.all_objects.filter(
            tenant=tenant,
            content__isnull=False,
            status='COMPLETED',
        ).select_related('teacher', 'content')

        for progress in completed_content.iterator():
            # Check for existing XP transaction (deduplication)
            exists = XPTransaction.all_objects.filter(
                tenant=tenant,
                teacher=progress.teacher,
                reason='content_completion',
                reference_id=progress.content_id,
                reference_type='content',
            ).exists()

            if exists:
                summary['skipped_already_exists'] += 1
                continue

            txn = award_xp(
                teacher=progress.teacher,
                reason='content_completion',
                description=f'Backfill: content completion',
                reference_id=progress.content_id,
                reference_type='content',
            )
            if txn:
                summary['content_completions_awarded'] += 1

        # --- Course completions (course-level progress with no content) ---
        completed_courses = TeacherProgress.all_objects.filter(
            tenant=tenant,
            content__isnull=True,
            status='COMPLETED',
        ).select_related('teacher', 'course')

        for progress in completed_courses.iterator():
            exists = XPTransaction.all_objects.filter(
                tenant=tenant,
                teacher=progress.teacher,
                reason='course_completion',
                reference_id=progress.course_id,
                reference_type='course',
            ).exists()

            if exists:
                summary['skipped_already_exists'] += 1
                continue

            txn = award_xp(
                teacher=progress.teacher,
                reason='course_completion',
                description=f'Backfill: course completion',
                reference_id=progress.course_id,
                reference_type='course',
            )
            if txn:
                summary['course_completions_awarded'] += 1

        # --- Assignment submissions ---
        submitted_assignments = AssignmentSubmission.all_objects.filter(
            tenant=tenant,
            status__in=['SUBMITTED', 'GRADED'],
        ).select_related('teacher', 'assignment')

        for submission in submitted_assignments.iterator():
            exists = XPTransaction.all_objects.filter(
                tenant=tenant,
                teacher=submission.teacher,
                reason='assignment_submission',
                reference_id=submission.id,
                reference_type='assignment_submission',
            ).exists()

            if exists:
                summary['skipped_already_exists'] += 1
                continue

            txn = award_xp(
                teacher=submission.teacher,
                reason='assignment_submission',
                description=f'Backfill: assignment submission',
                reference_id=submission.id,
                reference_type='assignment_submission',
            )
            if txn:
                summary['assignment_submissions_awarded'] += 1

        # --- Quiz submissions ---
        quiz_submissions = QuizSubmission.all_objects.filter(
            tenant=tenant,
        ).select_related('teacher', 'quiz')

        for submission in quiz_submissions.iterator():
            exists = XPTransaction.all_objects.filter(
                tenant=tenant,
                teacher=submission.teacher,
                reason='quiz_submission',
                reference_id=submission.id,
                reference_type='quiz_submission',
            ).exists()

            if exists:
                summary['skipped_already_exists'] += 1
                continue

            txn = award_xp(
                teacher=submission.teacher,
                reason='quiz_submission',
                description=f'Backfill: quiz submission',
                reference_id=submission.id,
                reference_type='quiz_submission',
            )
            if txn:
                summary['quiz_submissions_awarded'] += 1

        logger.info("Tenant %s backfill complete", tenant.id)

    logger.info("backfill_xp_for_existing_progress complete: %s", summary)
    return summary
