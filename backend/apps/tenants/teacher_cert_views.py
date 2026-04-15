# apps/tenants/teacher_cert_views.py

from datetime import date

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from utils.decorators import tenant_required
from .accreditation_models import StaffCertification, CERT_TYPE_CHOICES
from .accreditation_views import _compute_cert_status, _serialize_staff_cert


# Certification types that every teacher is required to hold
REQUIRED_CERT_TYPES = [
    'IB_CAT1',
    'POCSO',
    'FIRST_AID',
    'FIRE_SAFETY',
    'CHILD_SAFEGUARDING',
]

CERT_TYPE_DISPLAY = dict(CERT_TYPE_CHOICES)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@tenant_required
def my_certifications(request):
    """
    Teachers see their own certifications with summary stats.

    Returns:
      - certifications: list of serialized certification objects
      - summary: total, completed, expiring, expired counts
      - required: list of required certification types with status
      - missing: list of required certifications the teacher does not yet have
    """
    certs = StaffCertification.objects.filter(
        tenant=request.tenant,
        teacher=request.user,
    ).order_by('certification_type')

    today = date.today()

    serialized = []
    completed_count = 0
    expiring_count = 0
    expired_count = 0

    # Track which cert types the teacher holds and their computed status
    held_types = {}

    for cert in certs:
        data = _serialize_staff_cert(cert)
        serialized.append(data)

        computed = data['status']
        held_types[cert.certification_type] = computed

        if computed == 'VALID':
            completed_count += 1
        elif computed == 'EXPIRING':
            expiring_count += 1
            completed_count += 1  # still valid, just expiring soon
        elif computed == 'EXPIRED':
            expired_count += 1

    # Build required certifications list with status
    required_list = []
    missing = []
    for cert_type in REQUIRED_CERT_TYPES:
        display = CERT_TYPE_DISPLAY.get(cert_type, cert_type)
        if cert_type in held_types:
            required_list.append({
                'certification_type': cert_type,
                'display_name': display,
                'status': held_types[cert_type],
                'held': True,
            })
            # If expired, also count as "missing" for compliance purposes
            if held_types[cert_type] == 'EXPIRED':
                missing.append({
                    'certification_type': cert_type,
                    'display_name': display,
                    'reason': 'expired',
                })
        else:
            required_list.append({
                'certification_type': cert_type,
                'display_name': display,
                'status': 'NOT_STARTED',
                'held': False,
            })
            missing.append({
                'certification_type': cert_type,
                'display_name': display,
                'reason': 'not_started',
            })

    return Response({
        'summary': {
            'total': len(serialized),
            'completed': completed_count,
            'expiring': expiring_count,
            'expired': expired_count,
            'required_total': len(REQUIRED_CERT_TYPES),
            'required_met': len(REQUIRED_CERT_TYPES) - len(missing),
            'missing_count': len(missing),
        },
        'certifications': serialized,
        'required': required_list,
        'missing': missing,
    }, status=status.HTTP_200_OK)
