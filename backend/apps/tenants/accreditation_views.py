# apps/tenants/accreditation_views.py

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from collections import defaultdict

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import admin_only, tenant_required
from apps.users.models import User
from .accreditation_models import (
    SchoolAccreditation,
    AccreditationMilestone,
    RankingEntry,
    ComplianceItem,
    StaffCertification,
    ACCREDITATION_TYPES,
    ACCREDITATION_STATUS_CHOICES,
    MILESTONE_STATUS_CHOICES,
    COMPLIANCE_CATEGORY_CHOICES,
    COMPLIANCE_STATUS_CHOICES,
    COMPLIANCE_RECURRENCE_CHOICES,
    CERT_TYPE_CHOICES,
    STAFF_CERT_STATUS_CHOICES,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

VALID_ACCREDITATION_TYPES = {t[0] for t in ACCREDITATION_TYPES}
VALID_ACCREDITATION_STATUSES = {s[0] for s in ACCREDITATION_STATUS_CHOICES}
VALID_MILESTONE_STATUSES = {s[0] for s in MILESTONE_STATUS_CHOICES}


def _serialize_accreditation(acc, include_milestones=False):
    """Serialize a SchoolAccreditation instance to a dict."""
    days_remaining = None
    if acc.valid_to:
        delta = acc.valid_to - date.today()
        days_remaining = delta.days

    data = {
        'id': str(acc.id),
        'accreditation_type': acc.accreditation_type,
        'accreditation_type_display': acc.get_accreditation_type_display(),
        'display_name': acc.get_accreditation_type_display(),
        'custom_name': acc.custom_name,
        'status': acc.status,
        'status_display': acc.get_status_display(),
        'affiliation_number': acc.affiliation_number,
        'valid_from': acc.valid_from.isoformat() if acc.valid_from else None,
        'valid_to': acc.valid_to.isoformat() if acc.valid_to else None,
        'days_remaining': days_remaining,
        'issuing_body': acc.issuing_body,
        'external_portal_url': acc.external_portal_url,
        'notes': acc.notes,
        'renewal_cycle_months': acc.renewal_cycle_months,
        'created_at': acc.created_at.isoformat(),
        'updated_at': acc.updated_at.isoformat(),
    }
    if include_milestones:
        data['milestones'] = [
            _serialize_milestone(m) for m in acc.milestones.all()
        ]
    return data


def _serialize_milestone(milestone):
    """Serialize an AccreditationMilestone instance to a dict."""
    return {
        'id': str(milestone.id),
        'accreditation_id': str(milestone.accreditation_id),
        'title': milestone.title,
        'description': milestone.description,
        'due_date': milestone.due_date.isoformat() if milestone.due_date else None,
        'completed_date': milestone.completed_date.isoformat() if milestone.completed_date else None,
        'status': milestone.status,
        'status_display': milestone.get_status_display(),
        'order': milestone.order,
        'created_at': milestone.created_at.isoformat(),
        'updated_at': milestone.updated_at.isoformat(),
    }


def _serialize_ranking(entry):
    """Serialize a RankingEntry instance to a dict."""
    return {
        'id': str(entry.id),
        'platform': entry.platform,
        'platform_display': entry.platform,
        'year': entry.year,
        'rank': entry.rank,
        'category': entry.category,
        'score': str(entry.score) if entry.score is not None else None,
        'survey_url': entry.survey_url,
        'notes': entry.notes,
        'created_at': entry.created_at.isoformat(),
        'updated_at': entry.updated_at.isoformat(),
    }


def _parse_date(value):
    """Parse a date string (YYYY-MM-DD) or return None."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


# ── Accreditation Views ──────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def accreditation_list(request):
    """List all accreditations for the current tenant, with nested milestones."""
    accreditations = SchoolAccreditation.objects.filter(
        tenant=request.tenant,
    ).prefetch_related('milestones').order_by('-created_at')

    data = [_serialize_accreditation(acc, include_milestones=True) for acc in accreditations]
    return Response(data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def accreditation_create(request):
    """Create a new accreditation for the current tenant."""
    data = request.data
    errors = {}

    # Required fields
    accreditation_type = data.get('accreditation_type', '').strip()
    if not accreditation_type:
        errors['accreditation_type'] = 'This field is required.'
    elif accreditation_type not in VALID_ACCREDITATION_TYPES:
        errors['accreditation_type'] = f'Invalid type. Must be one of: {", ".join(sorted(VALID_ACCREDITATION_TYPES))}'

    issuing_body = data.get('issuing_body', '').strip()
    if not issuing_body:
        errors['issuing_body'] = 'This field is required.'

    acc_status = data.get('status', 'NOT_STARTED').strip()
    if acc_status not in VALID_ACCREDITATION_STATUSES:
        errors['status'] = f'Invalid status. Must be one of: {", ".join(sorted(VALID_ACCREDITATION_STATUSES))}'

    valid_from = _parse_date(data.get('valid_from'))
    valid_to = _parse_date(data.get('valid_to'))
    if data.get('valid_from') and valid_from is None:
        errors['valid_from'] = 'Invalid date format. Use YYYY-MM-DD.'
    if data.get('valid_to') and valid_to is None:
        errors['valid_to'] = 'Invalid date format. Use YYYY-MM-DD.'

    renewal_cycle_months = data.get('renewal_cycle_months')
    if renewal_cycle_months is not None and renewal_cycle_months != '':
        try:
            renewal_cycle_months = int(renewal_cycle_months)
            if renewal_cycle_months < 1:
                errors['renewal_cycle_months'] = 'Must be a positive integer.'
        except (ValueError, TypeError):
            errors['renewal_cycle_months'] = 'Must be a valid integer.'
    else:
        renewal_cycle_months = None

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    acc = SchoolAccreditation.objects.create(
        tenant=request.tenant,
        accreditation_type=accreditation_type,
        custom_name=data.get('custom_name', '').strip(),
        status=acc_status,
        affiliation_number=data.get('affiliation_number', '').strip(),
        valid_from=valid_from,
        valid_to=valid_to,
        issuing_body=issuing_body,
        external_portal_url=data.get('external_portal_url', '').strip(),
        notes=data.get('notes', '').strip(),
        renewal_cycle_months=renewal_cycle_months,
    )
    return Response(_serialize_accreditation(acc, include_milestones=True), status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def accreditation_update(request, pk):
    """Update an existing accreditation."""
    try:
        acc = SchoolAccreditation.objects.get(pk=pk, tenant=request.tenant)
    except SchoolAccreditation.DoesNotExist:
        return Response({'detail': 'Accreditation not found.'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    errors = {}

    if 'accreditation_type' in data:
        val = data['accreditation_type'].strip()
        if val not in VALID_ACCREDITATION_TYPES:
            errors['accreditation_type'] = f'Invalid type. Must be one of: {", ".join(sorted(VALID_ACCREDITATION_TYPES))}'
        else:
            acc.accreditation_type = val

    if 'status' in data:
        val = data['status'].strip()
        if val not in VALID_ACCREDITATION_STATUSES:
            errors['status'] = f'Invalid status. Must be one of: {", ".join(sorted(VALID_ACCREDITATION_STATUSES))}'
        else:
            acc.status = val

    if 'valid_from' in data:
        parsed = _parse_date(data['valid_from'])
        if data['valid_from'] and parsed is None:
            errors['valid_from'] = 'Invalid date format. Use YYYY-MM-DD.'
        else:
            acc.valid_from = parsed

    if 'valid_to' in data:
        parsed = _parse_date(data['valid_to'])
        if data['valid_to'] and parsed is None:
            errors['valid_to'] = 'Invalid date format. Use YYYY-MM-DD.'
        else:
            acc.valid_to = parsed

    if 'renewal_cycle_months' in data:
        val = data['renewal_cycle_months']
        if val is not None and val != '':
            try:
                val = int(val)
                if val < 1:
                    errors['renewal_cycle_months'] = 'Must be a positive integer.'
                else:
                    acc.renewal_cycle_months = val
            except (ValueError, TypeError):
                errors['renewal_cycle_months'] = 'Must be a valid integer.'
        else:
            acc.renewal_cycle_months = None

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    # Simple string fields
    for field in ('custom_name', 'affiliation_number', 'issuing_body', 'external_portal_url', 'notes'):
        if field in data:
            setattr(acc, field, str(data[field]).strip())

    acc.save()
    return Response(_serialize_accreditation(acc, include_milestones=True), status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def accreditation_delete(request, pk):
    """Delete an accreditation and its milestones."""
    try:
        acc = SchoolAccreditation.objects.get(pk=pk, tenant=request.tenant)
    except SchoolAccreditation.DoesNotExist:
        return Response({'detail': 'Accreditation not found.'}, status=status.HTTP_404_NOT_FOUND)

    acc.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Milestone Views ──────────────────────────────────────────────────────────

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def milestone_list_create(request, accreditation_pk):
    """List or create milestones for a given accreditation."""
    try:
        acc = SchoolAccreditation.objects.get(pk=accreditation_pk, tenant=request.tenant)
    except SchoolAccreditation.DoesNotExist:
        return Response({'detail': 'Accreditation not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        milestones = acc.milestones.all()
        data = [_serialize_milestone(m) for m in milestones]
        return Response(data, status=status.HTTP_200_OK)

    # POST — create milestone
    data = request.data
    errors = {}

    title = data.get('title', '').strip()
    if not title:
        errors['title'] = 'This field is required.'

    ms_status = data.get('status', 'PENDING').strip()
    if ms_status not in VALID_MILESTONE_STATUSES:
        errors['status'] = f'Invalid status. Must be one of: {", ".join(sorted(VALID_MILESTONE_STATUSES))}'

    due_date = _parse_date(data.get('due_date'))
    if data.get('due_date') and due_date is None:
        errors['due_date'] = 'Invalid date format. Use YYYY-MM-DD.'

    completed_date = _parse_date(data.get('completed_date'))
    if data.get('completed_date') and completed_date is None:
        errors['completed_date'] = 'Invalid date format. Use YYYY-MM-DD.'

    order = data.get('order', 0)
    try:
        order = int(order)
    except (ValueError, TypeError):
        errors['order'] = 'Must be a valid integer.'

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    milestone = AccreditationMilestone.objects.create(
        accreditation=acc,
        title=title,
        description=data.get('description', '').strip(),
        due_date=due_date,
        completed_date=completed_date,
        status=ms_status,
        order=order,
    )
    return Response(_serialize_milestone(milestone), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def milestone_update_delete(request, accreditation_pk, pk):
    """Update or delete a specific milestone."""
    try:
        acc = SchoolAccreditation.objects.get(pk=accreditation_pk, tenant=request.tenant)
    except SchoolAccreditation.DoesNotExist:
        return Response({'detail': 'Accreditation not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        milestone = AccreditationMilestone.objects.get(pk=pk, accreditation=acc)
    except AccreditationMilestone.DoesNotExist:
        return Response({'detail': 'Milestone not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "DELETE":
        milestone.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # PATCH — update milestone
    data = request.data
    errors = {}

    if 'title' in data:
        val = data['title'].strip()
        if not val:
            errors['title'] = 'This field cannot be blank.'
        else:
            milestone.title = val

    if 'status' in data:
        val = data['status'].strip()
        if val not in VALID_MILESTONE_STATUSES:
            errors['status'] = f'Invalid status. Must be one of: {", ".join(sorted(VALID_MILESTONE_STATUSES))}'
        else:
            milestone.status = val

    if 'due_date' in data:
        parsed = _parse_date(data['due_date'])
        if data['due_date'] and parsed is None:
            errors['due_date'] = 'Invalid date format. Use YYYY-MM-DD.'
        else:
            milestone.due_date = parsed

    if 'completed_date' in data:
        parsed = _parse_date(data['completed_date'])
        if data['completed_date'] and parsed is None:
            errors['completed_date'] = 'Invalid date format. Use YYYY-MM-DD.'
        else:
            milestone.completed_date = parsed

    if 'order' in data:
        try:
            milestone.order = int(data['order'])
        except (ValueError, TypeError):
            errors['order'] = 'Must be a valid integer.'

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    if 'description' in data:
        milestone.description = str(data['description']).strip()

    # Auto-set completed_date when status changes to COMPLETED
    if milestone.status == 'COMPLETED' and not milestone.completed_date:
        milestone.completed_date = date.today()

    milestone.save()
    return Response(_serialize_milestone(milestone), status=status.HTTP_200_OK)


# ── Ranking Views ────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ranking_list(request):
    """
    List all ranking entries for the current tenant.
    Includes a computed `trend` field comparing rank to the previous year
    for the same platform + category.
    """
    rankings = RankingEntry.objects.filter(
        tenant=request.tenant,
    ).order_by('-year', 'platform')

    # Build a lookup for previous-year comparison: (platform, category, year) -> rank
    rank_lookup = {}
    for entry in rankings:
        rank_lookup[(entry.platform, entry.category, entry.year)] = entry.rank

    results = []
    for entry in rankings:
        data = _serialize_ranking(entry)
        # Compute trend as a string: 'up', 'down', 'same', or 'new'
        prev_rank = rank_lookup.get((entry.platform, entry.category, entry.year - 1))
        data['previous_rank'] = prev_rank
        if entry.rank is None or prev_rank is None:
            # No previous year entry for this platform+category
            data['trend'] = 'new'
        elif entry.rank < prev_rank:
            data['trend'] = 'up'
        elif entry.rank > prev_rank:
            data['trend'] = 'down'
        else:
            data['trend'] = 'same'
        results.append(data)

    return Response(results, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ranking_create(request):
    """Create a new ranking entry."""
    data = request.data
    errors = {}

    platform = data.get('platform', '').strip()
    if not platform:
        errors['platform'] = 'This field is required.'
    elif len(platform) > 50:
        errors['platform'] = 'Must be 50 characters or fewer.'

    year = data.get('year')
    if year is None or year == '':
        errors['year'] = 'This field is required.'
    else:
        try:
            year = int(year)
            if year < 1900 or year > 2100:
                errors['year'] = 'Year must be between 1900 and 2100.'
        except (ValueError, TypeError):
            errors['year'] = 'Must be a valid integer.'

    category = data.get('category', '').strip()
    if not category:
        errors['category'] = 'This field is required.'
    elif len(category) > 100:
        errors['category'] = 'Must be 100 characters or fewer.'

    rank = data.get('rank')
    if rank is not None and rank != '':
        try:
            rank = int(rank)
            if rank < 1:
                errors['rank'] = 'Rank must be a positive integer.'
        except (ValueError, TypeError):
            errors['rank'] = 'Must be a valid integer.'
    else:
        rank = None

    score = data.get('score')
    if score is not None and score != '':
        try:
            score = Decimal(str(score))
            if score < 0:
                errors['score'] = 'Score must be non-negative.'
        except (InvalidOperation, ValueError, TypeError):
            errors['score'] = 'Must be a valid decimal number.'
    else:
        score = None

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    # Check unique_together
    if not errors and RankingEntry.objects.filter(
        tenant=request.tenant, platform=platform, year=year, category=category,
    ).exists():
        return Response(
            {'detail': 'A ranking entry for this platform, year, and category already exists.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    entry = RankingEntry.objects.create(
        tenant=request.tenant,
        platform=platform,
        year=year,
        rank=rank,
        category=category,
        score=score,
        survey_url=data.get('survey_url', '').strip(),
        notes=data.get('notes', '').strip(),
    )
    return Response(_serialize_ranking(entry), status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ranking_update(request, pk):
    """Update an existing ranking entry."""
    try:
        entry = RankingEntry.objects.get(pk=pk, tenant=request.tenant)
    except RankingEntry.DoesNotExist:
        return Response({'detail': 'Ranking entry not found.'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    errors = {}

    if 'platform' in data:
        val = data['platform'].strip()
        if not val:
            errors['platform'] = 'This field cannot be blank.'
        elif len(val) > 50:
            errors['platform'] = 'Must be 50 characters or fewer.'
        else:
            entry.platform = val

    if 'year' in data:
        try:
            val = int(data['year'])
            if val < 1900 or val > 2100:
                errors['year'] = 'Year must be between 1900 and 2100.'
            else:
                entry.year = val
        except (ValueError, TypeError):
            errors['year'] = 'Must be a valid integer.'

    if 'category' in data:
        val = data['category'].strip()
        if not val:
            errors['category'] = 'This field cannot be blank.'
        elif len(val) > 100:
            errors['category'] = 'Must be 100 characters or fewer.'
        else:
            entry.category = val

    if 'rank' in data:
        val = data['rank']
        if val is not None and val != '':
            try:
                val = int(val)
                if val < 1:
                    errors['rank'] = 'Rank must be a positive integer.'
                else:
                    entry.rank = val
            except (ValueError, TypeError):
                errors['rank'] = 'Must be a valid integer.'
        else:
            entry.rank = None

    if 'score' in data:
        val = data['score']
        if val is not None and val != '':
            try:
                val = Decimal(str(val))
                if val < 0:
                    errors['score'] = 'Score must be non-negative.'
                else:
                    entry.score = val
            except (InvalidOperation, ValueError, TypeError):
                errors['score'] = 'Must be a valid decimal number.'
        else:
            entry.score = None

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    # Check unique_together if any of the unique fields changed
    if any(f in data for f in ('platform', 'year', 'category')):
        dup = RankingEntry.objects.filter(
            tenant=request.tenant,
            platform=entry.platform,
            year=entry.year,
            category=entry.category,
        ).exclude(pk=entry.pk)
        if dup.exists():
            return Response(
                {'detail': 'A ranking entry for this platform, year, and category already exists.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

    for field in ('survey_url', 'notes'):
        if field in data:
            setattr(entry, field, str(data[field]).strip())

    entry.save()
    return Response(_serialize_ranking(entry), status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ranking_delete(request, pk):
    """Delete a ranking entry."""
    try:
        entry = RankingEntry.objects.get(pk=pk, tenant=request.tenant)
    except RankingEntry.DoesNotExist:
        return Response({'detail': 'Ranking entry not found.'}, status=status.HTTP_404_NOT_FOUND)

    entry.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Compliance Views ────────────────────────────────────────────────────────

VALID_COMPLIANCE_CATEGORIES = {c[0] for c in COMPLIANCE_CATEGORY_CHOICES}
VALID_COMPLIANCE_STATUSES = {s[0] for s in COMPLIANCE_STATUS_CHOICES}
VALID_COMPLIANCE_RECURRENCES = {r[0] for r in COMPLIANCE_RECURRENCE_CHOICES}

CATEGORY_DISPLAY = dict(COMPLIANCE_CATEGORY_CHOICES)
STATUS_DISPLAY = dict(COMPLIANCE_STATUS_CHOICES)
RECURRENCE_DISPLAY = dict(COMPLIANCE_RECURRENCE_CHOICES)


def _serialize_compliance(item):
    """Serialize a ComplianceItem instance to a dict with computed fields."""
    today = date.today()
    days_until_due = None
    is_overdue = False

    if item.due_date:
        delta = item.due_date - today
        days_until_due = delta.days
        if delta.days < 0 and item.status not in ('COMPLIANT', 'NOT_APPLICABLE'):
            is_overdue = True

    return {
        'id': str(item.id),
        'name': item.name,
        'description': item.description,
        'category': item.category,
        'category_display': CATEGORY_DISPLAY.get(item.category, item.category),
        'status': item.status,
        'status_display': STATUS_DISPLAY.get(item.status, item.status),
        'due_date': item.due_date.isoformat() if item.due_date else None,
        'completed_date': item.completed_date.isoformat() if item.completed_date else None,
        'responsible_person': item.responsible_person,
        'recurrence': item.recurrence,
        'recurrence_display': RECURRENCE_DISPLAY.get(item.recurrence, item.recurrence),
        'notes': item.notes,
        'document_url': item.document_url,
        'reminder_days': item.reminder_days,
        'days_until_due': days_until_due,
        'is_overdue': is_overdue,
        'created_at': item.created_at.isoformat(),
        'updated_at': item.updated_at.isoformat(),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def compliance_list(request):
    """
    List all compliance items for the current tenant with summary stats.
    Returns items ordered by category then due_date, plus a summary object.
    """
    items = ComplianceItem.objects.filter(
        tenant=request.tenant,
    ).order_by('category', 'due_date')

    today = date.today()
    total = 0
    compliant_count = 0
    in_progress_count = 0
    overdue_count = 0
    upcoming_count = 0

    serialized = []
    for item in items:
        data = _serialize_compliance(item)
        serialized.append(data)
        total += 1
        if item.status == 'COMPLIANT':
            compliant_count += 1
        elif item.status == 'IN_PROGRESS':
            in_progress_count += 1
        if data['is_overdue']:
            overdue_count += 1
        if item.due_date and 0 <= (item.due_date - today).days <= 30 and item.status not in ('COMPLIANT', 'NOT_APPLICABLE'):
            upcoming_count += 1

    return Response({
        'summary': {
            'total': total,
            'compliant': compliant_count,
            'in_progress': in_progress_count,
            'overdue': overdue_count,
            'upcoming': upcoming_count,
        },
        'items': serialized,
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def compliance_create(request):
    """Create a new compliance item for the current tenant."""
    data = request.data
    errors = {}

    # Required fields
    name = data.get('name', '').strip()
    if not name:
        errors['name'] = 'This field is required.'
    elif len(name) > 300:
        errors['name'] = 'Must be 300 characters or fewer.'

    category = data.get('category', '').strip()
    if not category:
        errors['category'] = 'This field is required.'
    elif category not in VALID_COMPLIANCE_CATEGORIES:
        errors['category'] = f'Invalid category. Must be one of: {", ".join(sorted(VALID_COMPLIANCE_CATEGORIES))}'

    # Optional validated fields
    item_status = data.get('status', 'PENDING').strip()
    if item_status not in VALID_COMPLIANCE_STATUSES:
        errors['status'] = f'Invalid status. Must be one of: {", ".join(sorted(VALID_COMPLIANCE_STATUSES))}'

    recurrence = data.get('recurrence', 'ANNUAL').strip()
    if recurrence not in VALID_COMPLIANCE_RECURRENCES:
        errors['recurrence'] = f'Invalid recurrence. Must be one of: {", ".join(sorted(VALID_COMPLIANCE_RECURRENCES))}'

    due_date = _parse_date(data.get('due_date'))
    if data.get('due_date') and due_date is None:
        errors['due_date'] = 'Invalid date format. Use YYYY-MM-DD.'

    completed_date = _parse_date(data.get('completed_date'))
    if data.get('completed_date') and completed_date is None:
        errors['completed_date'] = 'Invalid date format. Use YYYY-MM-DD.'

    reminder_days = data.get('reminder_days', 30)
    if reminder_days is not None and reminder_days != '':
        try:
            reminder_days = int(reminder_days)
            if reminder_days < 0:
                errors['reminder_days'] = 'Must be a non-negative integer.'
        except (ValueError, TypeError):
            errors['reminder_days'] = 'Must be a valid integer.'
    else:
        reminder_days = 30

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    item = ComplianceItem.objects.create(
        tenant=request.tenant,
        name=name,
        description=data.get('description', '').strip(),
        category=category,
        status=item_status,
        due_date=due_date,
        completed_date=completed_date,
        responsible_person=data.get('responsible_person', '').strip(),
        recurrence=recurrence,
        notes=data.get('notes', '').strip(),
        document_url=data.get('document_url', '').strip(),
        reminder_days=reminder_days,
    )
    return Response(_serialize_compliance(item), status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def compliance_update(request, pk):
    """Update an existing compliance item."""
    try:
        item = ComplianceItem.objects.get(pk=pk, tenant=request.tenant)
    except ComplianceItem.DoesNotExist:
        return Response({'detail': 'Compliance item not found.'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    errors = {}

    if 'name' in data:
        val = data['name'].strip()
        if not val:
            errors['name'] = 'This field cannot be blank.'
        elif len(val) > 300:
            errors['name'] = 'Must be 300 characters or fewer.'
        else:
            item.name = val

    if 'category' in data:
        val = data['category'].strip()
        if val not in VALID_COMPLIANCE_CATEGORIES:
            errors['category'] = f'Invalid category. Must be one of: {", ".join(sorted(VALID_COMPLIANCE_CATEGORIES))}'
        else:
            item.category = val

    if 'status' in data:
        val = data['status'].strip()
        if val not in VALID_COMPLIANCE_STATUSES:
            errors['status'] = f'Invalid status. Must be one of: {", ".join(sorted(VALID_COMPLIANCE_STATUSES))}'
        else:
            item.status = val

    if 'recurrence' in data:
        val = data['recurrence'].strip()
        if val not in VALID_COMPLIANCE_RECURRENCES:
            errors['recurrence'] = f'Invalid recurrence. Must be one of: {", ".join(sorted(VALID_COMPLIANCE_RECURRENCES))}'
        else:
            item.recurrence = val

    if 'due_date' in data:
        parsed = _parse_date(data['due_date'])
        if data['due_date'] and parsed is None:
            errors['due_date'] = 'Invalid date format. Use YYYY-MM-DD.'
        else:
            item.due_date = parsed

    if 'completed_date' in data:
        parsed = _parse_date(data['completed_date'])
        if data['completed_date'] and parsed is None:
            errors['completed_date'] = 'Invalid date format. Use YYYY-MM-DD.'
        else:
            item.completed_date = parsed

    if 'reminder_days' in data:
        val = data['reminder_days']
        if val is not None and val != '':
            try:
                val = int(val)
                if val < 0:
                    errors['reminder_days'] = 'Must be a non-negative integer.'
                else:
                    item.reminder_days = val
            except (ValueError, TypeError):
                errors['reminder_days'] = 'Must be a valid integer.'
        else:
            item.reminder_days = 30

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    # Simple string fields
    for field in ('description', 'responsible_person', 'notes', 'document_url'):
        if field in data:
            setattr(item, field, str(data[field]).strip())

    item.save()
    return Response(_serialize_compliance(item), status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def compliance_delete(request, pk):
    """Delete a compliance item."""
    try:
        item = ComplianceItem.objects.get(pk=pk, tenant=request.tenant)
    except ComplianceItem.DoesNotExist:
        return Response({'detail': 'Compliance item not found.'}, status=status.HTTP_404_NOT_FOUND)

    item.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


# ── Staff Certification / PD Tracker Views ────────────────────────────────

VALID_CERT_TYPES = {t[0] for t in CERT_TYPE_CHOICES}
VALID_STAFF_CERT_STATUSES = {s[0] for s in STAFF_CERT_STATUS_CHOICES}
CERT_TYPE_DISPLAY = dict(CERT_TYPE_CHOICES)

# Certification types that count towards IB training compliance
IB_CERT_TYPES = {'IB_CAT1', 'IB_CAT2', 'IB_CAT3', 'IB_LEADER'}

# Certification types tracked in the compliance summary
TRACKED_COMPLIANCE_TYPES = ['IB_CAT1', 'IB_CAT2', 'IB_CAT3', 'POCSO', 'FIRST_AID', 'FIRE_SAFETY', 'CHILD_SAFEGUARDING']


def _compute_cert_status(cert):
    """Compute the effective status of a StaffCertification based on dates."""
    today = date.today()
    if cert.completed_date is None:
        return 'NOT_STARTED'
    if cert.expiry_date:
        if cert.expiry_date < today:
            return 'EXPIRED'
        if cert.expiry_date <= today + timedelta(days=90):
            return 'EXPIRING'
    return 'VALID'


def _serialize_staff_cert(cert):
    """Serialize a StaffCertification instance to a dict."""
    computed_status = _compute_cert_status(cert)
    return {
        'id': str(cert.id),
        'certification_type': cert.certification_type,
        'display_name': CERT_TYPE_DISPLAY.get(cert.certification_type, cert.certification_type),
        'custom_name': cert.custom_name,
        'status': computed_status,
        'completed_date': cert.completed_date.isoformat() if cert.completed_date else None,
        'expiry_date': cert.expiry_date.isoformat() if cert.expiry_date else None,
        'certificate_url': cert.certificate_url,
        'provider': cert.provider,
        'notes': cert.notes,
        'created_at': cert.created_at.isoformat(),
        'updated_at': cert.updated_at.isoformat(),
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def staff_certifications_list(request):
    """
    List staff certifications grouped by teacher, with summary statistics.

    Query params:
        ?teacher_id=<uuid>  — filter by a specific teacher
        ?type=<cert_type>   — filter by certification type
    """
    tenant = request.tenant

    # Get all teachers for this tenant (TEACHER, HOD, IB_COORDINATOR roles)
    teacher_roles = ['TEACHER', 'HOD', 'IB_COORDINATOR']
    teachers_qs = User.objects.filter(
        tenant=tenant,
        role__in=teacher_roles,
        is_active=True,
        is_deleted=False,
    ).order_by('first_name', 'last_name')

    teacher_id_filter = request.query_params.get('teacher_id')
    if teacher_id_filter:
        teachers_qs = teachers_qs.filter(pk=teacher_id_filter)

    # Get all certifications for this tenant
    certs_qs = StaffCertification.objects.filter(tenant=tenant)

    cert_type_filter = request.query_params.get('type')
    if cert_type_filter and cert_type_filter in VALID_CERT_TYPES:
        certs_qs = certs_qs.filter(certification_type=cert_type_filter)

    if teacher_id_filter:
        certs_qs = certs_qs.filter(teacher_id=teacher_id_filter)

    # Build a lookup: teacher_id -> list of serialized certs
    certs_by_teacher = defaultdict(list)
    for cert in certs_qs.select_related('teacher'):
        certs_by_teacher[cert.teacher_id].append(cert)

    # Compute summary stats
    total_teachers = teachers_qs.count()
    ib_trained_count = 0  # Teachers who have at least IB_CAT1 completed
    expiring_count = 0
    today = date.today()

    # Compliance category tracking
    compliance_categories = {}
    for ct in TRACKED_COMPLIANCE_TYPES:
        compliance_categories[ct] = {'required': total_teachers, 'completed': 0}

    # Build teacher list
    teacher_list = []
    for teacher in teachers_qs:
        teacher_certs = certs_by_teacher.get(teacher.pk, [])
        serialized_certs = []
        has_ib_cat1 = False

        for cert in teacher_certs:
            serialized = _serialize_staff_cert(cert)
            serialized_certs.append(serialized)

            computed_status = serialized['status']

            # Check IB Cat 1 completion
            if cert.certification_type == 'IB_CAT1' and computed_status == 'VALID':
                has_ib_cat1 = True

            # Count expiring
            if computed_status == 'EXPIRING':
                expiring_count += 1

            # Update compliance category counts
            if cert.certification_type in compliance_categories:
                if computed_status in ('VALID', 'EXPIRING'):
                    compliance_categories[cert.certification_type]['completed'] += 1

        if has_ib_cat1:
            ib_trained_count += 1

        teacher_list.append({
            'id': str(teacher.pk),
            'name': teacher.get_full_name(),
            'email': teacher.email,
            'certifications': serialized_certs,
        })

    ib_trained_percentage = round(
        (ib_trained_count / total_teachers * 100) if total_teachers > 0 else 0
    )

    return Response({
        'summary': {
            'total_teachers': total_teachers,
            'ib_trained_count': ib_trained_count,
            'ib_trained_percentage': ib_trained_percentage,
            'expiring_count': expiring_count,
            'compliance_categories': compliance_categories,
        },
        'teachers': teacher_list,
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def staff_certification_create(request):
    """Create a new staff certification record."""
    data = request.data
    errors = {}

    # Required: teacher_id
    teacher_id = data.get('teacher_id', '').strip() if isinstance(data.get('teacher_id'), str) else str(data.get('teacher_id', ''))
    if not teacher_id:
        errors['teacher_id'] = 'This field is required.'
    else:
        try:
            teacher = User.objects.get(pk=teacher_id, tenant=request.tenant, is_deleted=False)
        except (User.DoesNotExist, ValueError):
            errors['teacher_id'] = 'Teacher not found.'
            teacher = None

    # Required: certification_type
    certification_type = data.get('certification_type', '').strip()
    if not certification_type:
        errors['certification_type'] = 'This field is required.'
    elif certification_type not in VALID_CERT_TYPES:
        errors['certification_type'] = f'Invalid type. Must be one of: {", ".join(sorted(VALID_CERT_TYPES))}'

    # Optional dates
    completed_date = _parse_date(data.get('completed_date'))
    if data.get('completed_date') and completed_date is None:
        errors['completed_date'] = 'Invalid date format. Use YYYY-MM-DD.'

    expiry_date = _parse_date(data.get('expiry_date'))
    if data.get('expiry_date') and expiry_date is None:
        errors['expiry_date'] = 'Invalid date format. Use YYYY-MM-DD.'

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    # Check unique_together
    if StaffCertification.objects.filter(
        tenant=request.tenant, teacher=teacher, certification_type=certification_type,
    ).exists():
        return Response(
            {'detail': 'This teacher already has this certification type recorded.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    cert = StaffCertification.objects.create(
        tenant=request.tenant,
        teacher=teacher,
        certification_type=certification_type,
        custom_name=data.get('custom_name', '').strip() if data.get('custom_name') else '',
        completed_date=completed_date,
        expiry_date=expiry_date,
        certificate_url=data.get('certificate_url', '').strip() if data.get('certificate_url') else '',
        provider=data.get('provider', '').strip() if data.get('provider') else '',
        notes=data.get('notes', '').strip() if data.get('notes') else '',
    )
    # Set status based on computed dates
    cert.status = _compute_cert_status(cert)
    cert.save(update_fields=['status'])

    return Response(_serialize_staff_cert(cert), status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def staff_certification_update(request, pk):
    """Update an existing staff certification record."""
    try:
        cert = StaffCertification.objects.get(pk=pk, tenant=request.tenant)
    except StaffCertification.DoesNotExist:
        return Response({'detail': 'Staff certification not found.'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data
    errors = {}

    if 'certification_type' in data:
        val = data['certification_type'].strip()
        if val not in VALID_CERT_TYPES:
            errors['certification_type'] = f'Invalid type. Must be one of: {", ".join(sorted(VALID_CERT_TYPES))}'
        else:
            cert.certification_type = val

    if 'completed_date' in data:
        parsed = _parse_date(data['completed_date'])
        if data['completed_date'] and parsed is None:
            errors['completed_date'] = 'Invalid date format. Use YYYY-MM-DD.'
        else:
            cert.completed_date = parsed

    if 'expiry_date' in data:
        parsed = _parse_date(data['expiry_date'])
        if data['expiry_date'] and parsed is None:
            errors['expiry_date'] = 'Invalid date format. Use YYYY-MM-DD.'
        else:
            cert.expiry_date = parsed

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    # Simple string fields
    for field in ('custom_name', 'certificate_url', 'provider', 'notes'):
        if field in data:
            setattr(cert, field, str(data[field]).strip())

    # Re-compute status based on dates
    cert.status = _compute_cert_status(cert)
    cert.save()

    return Response(_serialize_staff_cert(cert), status=status.HTTP_200_OK)


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def staff_certification_delete(request, pk):
    """Delete a staff certification record."""
    try:
        cert = StaffCertification.objects.get(pk=pk, tenant=request.tenant)
    except StaffCertification.DoesNotExist:
        return Response({'detail': 'Staff certification not found.'}, status=status.HTTP_404_NOT_FOUND)

    cert.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def staff_certification_bulk_create(request):
    """
    Bulk create staff certifications.
    Expects: {"items": [{"teacher_id": "...", "certification_type": "...", ...}, ...]}
    Silently skips duplicates.
    """
    items = request.data.get('items', [])
    if not isinstance(items, list) or len(items) == 0:
        return Response({'detail': 'items must be a non-empty list.'}, status=status.HTTP_400_BAD_REQUEST)

    created = []
    skipped = 0

    for item_data in items:
        teacher_id = str(item_data.get('teacher_id', '')).strip()
        certification_type = str(item_data.get('certification_type', '')).strip()

        if not teacher_id or not certification_type:
            skipped += 1
            continue

        if certification_type not in VALID_CERT_TYPES:
            skipped += 1
            continue

        try:
            teacher = User.objects.get(pk=teacher_id, tenant=request.tenant, is_deleted=False)
        except (User.DoesNotExist, ValueError):
            skipped += 1
            continue

        # Skip duplicates silently
        if StaffCertification.objects.filter(
            tenant=request.tenant, teacher=teacher, certification_type=certification_type,
        ).exists():
            skipped += 1
            continue

        completed_date = _parse_date(item_data.get('completed_date'))
        expiry_date = _parse_date(item_data.get('expiry_date'))

        cert = StaffCertification.objects.create(
            tenant=request.tenant,
            teacher=teacher,
            certification_type=certification_type,
            custom_name=str(item_data.get('custom_name', '')).strip(),
            completed_date=completed_date,
            expiry_date=expiry_date,
            certificate_url=str(item_data.get('certificate_url', '')).strip(),
            provider=str(item_data.get('provider', '')).strip(),
            notes=str(item_data.get('notes', '')).strip(),
        )
        cert.status = _compute_cert_status(cert)
        cert.save(update_fields=['status'])
        created.append(_serialize_staff_cert(cert))

    return Response({
        'created_count': len(created),
        'skipped_count': skipped,
        'items': created,
    }, status=status.HTTP_201_CREATED)
