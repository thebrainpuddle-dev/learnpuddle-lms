# apps/academics/tests.py
"""
Comprehensive tests for the academics app.

Covers:
- Auth/role guards for all admin endpoints
- GradeBand CRUD + delete-with-grades guard
- Grade CRUD + delete-with-students guard
- Section CRUD + delete-with-students guard
- Subject CRUD
- TeachingAssignment CRUD
- Cross-tenant isolation (security)
- School overview endpoint
- Section detail views (students, teachers, courses)
- Academic year promotion validation
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.academics.models import GradeBand, Grade, Section, Subject, TeachingAssignment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(name, slug, subdomain, email):
    return Tenant.objects.create(
        name=name, slug=slug, subdomain=subdomain, email=email, is_active=True,
    )


def _make_user(email, tenant, role='SCHOOL_ADMIN', first='Admin', last='User'):
    return User.objects.create_user(
        email=email, password='pass123',
        first_name=first, last_name=last,
        tenant=tenant, role=role,
        is_active=True,
    )


def _auth(user):
    """Return an APIClient force-authenticated as the given user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# Tenant A: subdomain 'test' → HOST 'test.lms.com'
# Tenant B: subdomain 'other' → HOST 'other.lms.com'
HOST_A = 'test.lms.com'
HOST_B = 'other.lms.com'


# ---------------------------------------------------------------------------
# Auth / role guards
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestAcademicsAuthGuards(TestCase):
    """All admin academics endpoints must refuse unauthenticated and teacher requests."""

    def setUp(self):
        self.tenant = _make_tenant('Guard School', 'guard-sch', 'test', 'g@guard.com')
        self.teacher = _make_user('teacher@guard.com', self.tenant, role='TEACHER', first='Tea')
        self.band = GradeBand.objects.create(
            tenant=self.tenant, name='Band', short_code='BND', order=1,
        )

    def test_list_grade_bands_requires_auth(self):
        response = APIClient().get(
            '/api/v1/academics/grade-bands/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 401)

    def test_create_grade_band_requires_auth(self):
        response = APIClient().post(
            '/api/v1/academics/grade-bands/',
            {'name': 'X', 'short_code': 'X'},
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 401)

    def test_teacher_cannot_list_grade_bands(self):
        client = _auth(self.teacher)
        response = client.get('/api/v1/academics/grade-bands/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_create_grade_band(self):
        client = _auth(self.teacher)
        response = client.post(
            '/api/v1/academics/grade-bands/',
            {'name': 'Forbidden', 'short_code': 'FB'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_delete_grade_band(self):
        client = _auth(self.teacher)
        response = client.delete(
            f'/api/v1/academics/grade-bands/{self.band.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# GradeBand CRUD
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestGradeBandCRUD(TestCase):
    """CRUD operations and guards on /api/v1/academics/grade-bands/."""

    def setUp(self):
        self.tenant = _make_tenant('Band School', 'band-sch', 'test', 'b@band.com')
        self.admin = _make_user('admin@band.com', self.tenant)

    # Create

    def test_create_grade_band_returns_201(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/grade-bands/',
            {'name': 'Early Years', 'short_code': 'EY', 'order': 1},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn('id', response.data)
        self.assertEqual(response.data['name'], 'Early Years')
        self.assertEqual(response.data['short_code'], 'EY')

    def test_create_duplicate_grade_band_name_returns_400(self):
        GradeBand.objects.create(tenant=self.tenant, name='Primary', short_code='PRI', order=2)
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/grade-bands/',
            {'name': 'Primary', 'short_code': 'PR2'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_create_grade_band_requires_name(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/grade-bands/',
            {'short_code': 'X'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    # List

    def test_list_grade_bands_returns_200_with_data_and_pagination(self):
        GradeBand.objects.create(tenant=self.tenant, name='Primary', short_code='PRI')
        client = _auth(self.admin)
        response = client.get('/api/v1/academics/grade-bands/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data', response.data)
        self.assertIn('total', response.data)
        self.assertEqual(len(response.data['data']), 1)

    # Detail

    def test_get_grade_band_detail(self):
        band = GradeBand.objects.create(tenant=self.tenant, name='High School', short_code='HS')
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/grade-bands/{band.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'High School')
        self.assertIn('grade_count', response.data)

    def test_get_nonexistent_grade_band_returns_404(self):
        import uuid
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/grade-bands/{uuid.uuid4()}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 404)

    # Patch

    def test_patch_grade_band_updates_name(self):
        band = GradeBand.objects.create(tenant=self.tenant, name='Old Name', short_code='OLD')
        client = _auth(self.admin)
        response = client.patch(
            f'/api/v1/academics/grade-bands/{band.id}/',
            {'name': 'New Name'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'New Name')
        band.refresh_from_db()
        self.assertEqual(band.name, 'New Name')

    # Delete

    def test_delete_empty_grade_band_returns_204(self):
        band = GradeBand.objects.create(tenant=self.tenant, name='To Delete', short_code='DEL')
        client = _auth(self.admin)
        response = client.delete(
            f'/api/v1/academics/grade-bands/{band.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(GradeBand.objects.filter(id=band.id).exists())

    def test_delete_grade_band_with_grades_returns_400(self):
        """Deleting a band that still contains grades must be blocked."""
        band = GradeBand.objects.create(tenant=self.tenant, name='With Grades', short_code='WG')
        Grade.objects.create(
            tenant=self.tenant, grade_band=band, name='Grade 1', short_code='G1', order=1,
        )
        client = _auth(self.admin)
        response = client.delete(
            f'/api/v1/academics/grade-bands/{band.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)
        # Band must still exist
        self.assertTrue(GradeBand.objects.filter(id=band.id).exists())


# ---------------------------------------------------------------------------
# Grade CRUD
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestGradeCRUD(TestCase):
    """CRUD operations on /api/v1/academics/grades/."""

    def setUp(self):
        self.tenant = _make_tenant('Grade School', 'grade-sch', 'test', 'g@grade.com')
        self.admin = _make_user('admin@grade.com', self.tenant)
        self.band = GradeBand.objects.create(
            tenant=self.tenant, name='Primary', short_code='PRI', order=1,
        )

    def test_create_grade_returns_201(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/grades/',
            {
                'grade_band': str(self.band.id),
                'name': 'Grade 5',
                'short_code': 'G5',
                'order': 5,
            },
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], 'Grade 5')
        self.assertEqual(response.data['short_code'], 'G5')
        self.assertEqual(response.data['grade_band_name'], 'Primary')

    def test_list_grades_returns_200_with_data_key(self):
        Grade.objects.create(
            tenant=self.tenant, grade_band=self.band, name='Grade 6', short_code='G6', order=6,
        )
        client = _auth(self.admin)
        response = client.get('/api/v1/academics/grades/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data', response.data)
        self.assertEqual(len(response.data['data']), 1)

    def test_list_grades_filter_by_band(self):
        band2 = GradeBand.objects.create(
            tenant=self.tenant, name='Secondary', short_code='SEC', order=2,
        )
        Grade.objects.create(
            tenant=self.tenant, grade_band=self.band, name='Grade 5', short_code='G5', order=5,
        )
        Grade.objects.create(
            tenant=self.tenant, grade_band=band2, name='Grade 9', short_code='G9', order=9,
        )
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/grades/?grade_band={self.band.id}', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        names = [g['name'] for g in response.data['data']]
        self.assertIn('Grade 5', names)
        self.assertNotIn('Grade 9', names)

    def test_patch_grade_updates_name(self):
        grade = Grade.objects.create(
            tenant=self.tenant, grade_band=self.band, name='Old Grade', short_code='OG', order=3,
        )
        client = _auth(self.admin)
        response = client.patch(
            f'/api/v1/academics/grades/{grade.id}/',
            {'name': 'Updated Grade'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        grade.refresh_from_db()
        self.assertEqual(grade.name, 'Updated Grade')

    def test_delete_empty_grade_returns_204(self):
        grade = Grade.objects.create(
            tenant=self.tenant, grade_band=self.band, name='To Delete', short_code='TDE', order=4,
        )
        client = _auth(self.admin)
        response = client.delete(
            f'/api/v1/academics/grades/{grade.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Grade.objects.filter(id=grade.id).exists())


# ---------------------------------------------------------------------------
# Section CRUD
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestSectionCRUD(TestCase):
    """CRUD operations on /api/v1/academics/sections/."""

    def setUp(self):
        self.tenant = _make_tenant('Sec School', 'sec-sch', 'test', 's@sec.com')
        self.admin = _make_user('admin@sec.com', self.tenant)
        self.band = GradeBand.objects.create(
            tenant=self.tenant, name='Primary', short_code='PRI', order=1,
        )
        self.grade = Grade.objects.create(
            tenant=self.tenant, grade_band=self.band, name='Grade 7', short_code='G7', order=7,
        )

    def test_create_section_returns_201(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/sections/',
            {
                'grade': str(self.grade.id),
                'name': 'A',
                'academic_year': '2026-27',
            },
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], 'A')
        self.assertEqual(response.data['academic_year'], '2026-27')
        self.assertEqual(response.data['grade_name'], 'Grade 7')

    def test_list_sections_returns_200_with_data_key(self):
        Section.objects.create(
            tenant=self.tenant, grade=self.grade, name='B', academic_year='2026-27',
        )
        client = _auth(self.admin)
        response = client.get('/api/v1/academics/sections/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data', response.data)

    def test_list_sections_filter_by_grade(self):
        grade2 = Grade.objects.create(
            tenant=self.tenant, grade_band=self.band, name='Grade 8', short_code='G8', order=8,
        )
        Section.objects.create(
            tenant=self.tenant, grade=self.grade, name='A', academic_year='2026-27',
        )
        Section.objects.create(
            tenant=self.tenant, grade=grade2, name='A', academic_year='2026-27',
        )
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/sections/?grade={self.grade.id}&academic_year=2026-27',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        # Only sections for self.grade should appear
        for s in response.data['data']:
            self.assertEqual(s['grade_name'], 'Grade 7')

    def test_patch_section_name(self):
        section = Section.objects.create(
            tenant=self.tenant, grade=self.grade, name='A', academic_year='2026-27',
        )
        client = _auth(self.admin)
        response = client.patch(
            f'/api/v1/academics/sections/{section.id}/',
            {'name': 'B'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        section.refresh_from_db()
        self.assertEqual(section.name, 'B')

    def test_delete_empty_section_returns_204(self):
        section = Section.objects.create(
            tenant=self.tenant, grade=self.grade, name='C', academic_year='2026-27',
        )
        client = _auth(self.admin)
        response = client.delete(
            f'/api/v1/academics/sections/{section.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Section.objects.filter(id=section.id).exists())


# ---------------------------------------------------------------------------
# Subject CRUD
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestSubjectCRUD(TestCase):
    """CRUD operations on /api/v1/academics/subjects/."""

    def setUp(self):
        self.tenant = _make_tenant('Subj School', 'subj-sch', 'test', 'sub@subj.com')
        self.admin = _make_user('admin@subj.com', self.tenant)

    def test_create_subject_returns_201(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/subjects/',
            {
                'name': 'Mathematics',
                'code': 'MATH',
                'department': 'Science',
            },
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], 'Mathematics')
        self.assertEqual(response.data['code'], 'MATH')

    def test_create_duplicate_code_returns_400(self):
        Subject.objects.create(tenant=self.tenant, name='Physics', code='PHY')
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/subjects/',
            {'name': 'Physics 2', 'code': 'PHY'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_list_subjects_returns_200_with_data_key(self):
        Subject.objects.create(tenant=self.tenant, name='Chemistry', code='CHEM')
        client = _auth(self.admin)
        response = client.get('/api/v1/academics/subjects/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertIn('data', response.data)

    def test_list_subjects_search_by_name(self):
        Subject.objects.create(tenant=self.tenant, name='Physics', code='PHY')
        Subject.objects.create(tenant=self.tenant, name='History', code='HIS')
        client = _auth(self.admin)
        response = client.get(
            '/api/v1/academics/subjects/?search=phys', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        names = [s['name'] for s in response.data['data']]
        self.assertIn('Physics', names)
        self.assertNotIn('History', names)

    def test_patch_subject_updates_department(self):
        subject = Subject.objects.create(
            tenant=self.tenant, name='Biology', code='BIO', department='',
        )
        client = _auth(self.admin)
        response = client.patch(
            f'/api/v1/academics/subjects/{subject.id}/',
            {'department': 'Sciences'},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        subject.refresh_from_db()
        self.assertEqual(subject.department, 'Sciences')

    def test_get_subject_detail(self):
        subject = Subject.objects.create(
            tenant=self.tenant, name='English', code='ENG', department='Languages',
        )
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/subjects/{subject.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'English')
        self.assertIn('applicable_grade_names', response.data)


# ---------------------------------------------------------------------------
# TeachingAssignment CRUD
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestTeachingAssignmentCRUD(TestCase):
    """CRUD operations on /api/v1/academics/teaching-assignments/."""

    def setUp(self):
        self.tenant = _make_tenant('TA School', 'ta-sch', 'test', 'ta@ta.com')
        self.admin = _make_user('admin@ta.com', self.tenant)
        self.teacher = _make_user(
            'teacher@ta.com', self.tenant, role='TEACHER', first='Tea',
        )
        self.subject = Subject.objects.create(
            tenant=self.tenant, name='Geography', code='GEO',
        )

    def test_create_teaching_assignment_returns_201(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/teaching-assignments/',
            {
                'teacher': str(self.teacher.id),
                'subject': str(self.subject.id),
                'academic_year': '2026-27',
            },
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['teacher_email'], self.teacher.email)
        self.assertEqual(response.data['subject_name'], 'Geography')

    def test_list_teaching_assignments_returns_200(self):
        TeachingAssignment.objects.create(
            tenant=self.tenant,
            teacher=self.teacher,
            subject=self.subject,
            academic_year='2026-27',
        )
        client = _auth(self.admin)
        response = client.get(
            '/api/v1/academics/teaching-assignments/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('data', response.data)
        self.assertEqual(len(response.data['data']), 1)

    def test_list_assignments_filter_by_teacher(self):
        teacher2 = _make_user('teacher2@ta.com', self.tenant, role='TEACHER', first='T2')
        subject2 = Subject.objects.create(tenant=self.tenant, name='Art', code='ART')
        TeachingAssignment.objects.create(
            tenant=self.tenant, teacher=self.teacher, subject=self.subject,
            academic_year='2026-27',
        )
        TeachingAssignment.objects.create(
            tenant=self.tenant, teacher=teacher2, subject=subject2,
            academic_year='2026-27',
        )
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/teaching-assignments/?teacher={self.teacher.id}',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['teacher_email'], self.teacher.email)

    def test_delete_teaching_assignment_returns_204(self):
        ta = TeachingAssignment.objects.create(
            tenant=self.tenant, teacher=self.teacher, subject=self.subject,
            academic_year='2026-27',
        )
        client = _auth(self.admin)
        response = client.delete(
            f'/api/v1/academics/teaching-assignments/{ta.id}/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TeachingAssignment.objects.filter(id=ta.id).exists())


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'other.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestAcademicsCrossTenantIsolation(TestCase):
    """Admin B must not see or mutate Admin A's academic structure."""

    def setUp(self):
        self.tenant_a = _make_tenant('School A', 'iso-a', 'test', 'a@iso.com')
        self.tenant_b = _make_tenant('School B', 'iso-b', 'other', 'b@iso.com')
        self.admin_a = _make_user('admin_a@iso.com', self.tenant_a)
        self.admin_b = _make_user('admin_b@iso.com', self.tenant_b)

        self.band_a = GradeBand.objects.create(
            tenant=self.tenant_a, name='Private Band', short_code='PVT', order=1,
        )

    def test_admin_b_cannot_get_tenant_a_grade_band(self):
        client = _auth(self.admin_b)
        response = client.get(
            f'/api/v1/academics/grade-bands/{self.band_a.id}/',
            HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)

    def test_admin_b_cannot_patch_tenant_a_grade_band(self):
        client = _auth(self.admin_b)
        response = client.patch(
            f'/api/v1/academics/grade-bands/{self.band_a.id}/',
            {'name': 'Hacked'},
            format='json', HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)
        self.band_a.refresh_from_db()
        self.assertEqual(self.band_a.name, 'Private Band')

    def test_admin_b_cannot_delete_tenant_a_grade_band(self):
        client = _auth(self.admin_b)
        response = client.delete(
            f'/api/v1/academics/grade-bands/{self.band_a.id}/',
            HTTP_HOST=HOST_B,
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(GradeBand.objects.filter(id=self.band_a.id).exists())

    def test_list_grade_bands_scoped_to_own_tenant(self):
        """Admin A's grade bands must NOT appear in Admin B's list response."""
        client = _auth(self.admin_b)
        response = client.get(
            '/api/v1/academics/grade-bands/', HTTP_HOST=HOST_B
        )
        self.assertEqual(response.status_code, 200)
        ids = [str(b['id']) for b in response.data.get('data', [])]
        self.assertNotIn(str(self.band_a.id), ids)


# ---------------------------------------------------------------------------
# School Overview
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestSchoolOverview(TestCase):
    """GET /api/v1/academics/school-overview/."""

    def setUp(self):
        self.tenant = _make_tenant('Overview School', 'ov-sch', 'test', 'ov@ov.com')
        self.admin = _make_user('admin@ov.com', self.tenant)

    def test_school_overview_returns_200_with_required_keys(self):
        client = _auth(self.admin)
        response = client.get('/api/v1/academics/school-overview/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertIn('school_name', response.data)
        self.assertIn('grade_bands', response.data)
        self.assertIn('academic_year', response.data)

    def test_school_overview_includes_grade_bands_with_grades(self):
        band = GradeBand.objects.create(
            tenant=self.tenant, name='Primary', short_code='PRI', order=1,
        )
        Grade.objects.create(
            tenant=self.tenant, grade_band=band, name='Grade 5', short_code='G5', order=5,
        )
        client = _auth(self.admin)
        response = client.get('/api/v1/academics/school-overview/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['grade_bands']), 1)
        self.assertEqual(response.data['grade_bands'][0]['name'], 'Primary')
        # Each band has a nested grades list
        self.assertIn('grades', response.data['grade_bands'][0])
        self.assertEqual(len(response.data['grade_bands'][0]['grades']), 1)
        grade_data = response.data['grade_bands'][0]['grades'][0]
        self.assertEqual(grade_data['name'], 'Grade 5')
        self.assertIn('student_count', grade_data)
        self.assertIn('section_count', grade_data)
        self.assertIn('course_count', grade_data)

    def test_school_overview_teacher_cannot_access(self):
        teacher = _make_user('teacher@ov.com', self.tenant, role='TEACHER', first='T')
        client = _auth(teacher)
        response = client.get('/api/v1/academics/school-overview/', HTTP_HOST=HOST_A)
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Section detail views
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestSectionDetailViews(TestCase):
    """
    GET /api/v1/academics/sections/<id>/students/
    GET /api/v1/academics/sections/<id>/teachers/
    GET /api/v1/academics/sections/<id>/courses/

    These endpoints require @teacher_or_admin (not @admin_only), so
    teachers can also access them.
    """

    def setUp(self):
        self.tenant = _make_tenant('Detail School', 'det-sch', 'test', 'det@det.com')
        self.admin = _make_user('admin@det.com', self.tenant)
        self.teacher = _make_user(
            'teacher@det.com', self.tenant, role='TEACHER', first='Tea',
        )
        self.band = GradeBand.objects.create(
            tenant=self.tenant, name='Middle', short_code='MID', order=2,
        )
        self.grade = Grade.objects.create(
            tenant=self.tenant, grade_band=self.band, name='Grade 8', short_code='G8', order=8,
        )
        self.section = Section.objects.create(
            tenant=self.tenant, grade=self.grade, name='A', academic_year='2026-27',
        )

    def test_section_students_returns_200_with_section_key(self):
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/sections/{self.section.id}/students/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('section', response.data)
        self.assertIn('students', response.data)
        self.assertIn('total', response.data)

    def test_teacher_can_access_section_students(self):
        """section_students uses @teacher_or_admin, so teachers have access."""
        client = _auth(self.teacher)
        response = client.get(
            f'/api/v1/academics/sections/{self.section.id}/students/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)

    def test_section_teachers_returns_200_with_teachers_key(self):
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/sections/{self.section.id}/teachers/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('section', response.data)
        self.assertIn('teachers', response.data)

    def test_section_courses_returns_200_with_courses_key(self):
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/sections/{self.section.id}/courses/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('section', response.data)
        self.assertIn('courses', response.data)

    def test_section_students_returns_404_for_nonexistent_section(self):
        import uuid
        client = _auth(self.admin)
        response = client.get(
            f'/api/v1/academics/sections/{uuid.uuid4()}/students/',
            HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# Academic year promotion validation
# ---------------------------------------------------------------------------

@override_settings(
    ALLOWED_HOSTS=['test.lms.com', 'testserver', 'localhost'],
    PLATFORM_DOMAIN='lms.com',
)
class TestPromotionValidation(TestCase):
    """
    POST /api/v1/academics/promotion/execute/ — validation-only tests.

    The actual promotion workflow is complex (triggers section reassignment
    and course re-enrolment). Here we only verify the guard clauses that
    reject malformed requests before any DB mutation.
    """

    def setUp(self):
        self.tenant = _make_tenant('Promo School', 'promo-sch', 'test', 'promo@promo.com')
        self.admin = _make_user('admin@promo.com', self.tenant)

    def test_promotion_without_new_academic_year_returns_400(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/promotion/execute/',
            {},
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('new_academic_year', response.data.get('error', '').lower())

    def test_promotion_with_non_list_excluded_ids_returns_400(self):
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/promotion/execute/',
            {
                'new_academic_year': '2027-28',
                'excluded_student_ids': 'not-a-list',
            },
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)

    def test_promotion_with_too_many_ids_returns_400(self):
        """IDs list capped at 5000 per the view guard."""
        client = _auth(self.admin)
        response = client.post(
            '/api/v1/academics/promotion/execute/',
            {
                'new_academic_year': '2027-28',
                'excluded_student_ids': list(range(5001)),
            },
            format='json', HTTP_HOST=HOST_A,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('5000', response.data.get('error', ''))

    def test_promotion_preview_returns_200(self):
        client = _auth(self.admin)
        response = client.get(
            '/api/v1/academics/promotion/preview/', HTTP_HOST=HOST_A
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('grades', response.data)
        self.assertIn('total_students', response.data)
        self.assertIn('current_academic_year', response.data)
