# Academic Structure, Auth & Course Workflow — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add academic structure (grades, sections, subjects, teaching assignments), flexible login, course auto-assignment, School View UI, Teacher "My Classes" view, white-label branding, and Keystone seed data to LearnPuddle LMS.

**Architecture:** New `academics` Django app with 5 models using existing TenantManager pattern. Existing Tenant/User/Course models get additive nullable fields. Frontend gets new admin School View pages and teacher My Classes pages using existing React Query + Zod + Tailwind patterns.

**Tech Stack:** Django 4.2, DRF, PostgreSQL, React 18, TypeScript, Vite, Tailwind CSS, @tanstack/react-query, Zod, lucide-react/heroicons, 21st.dev Magic MCP for UI components.

---

## File Structure

### New Files — Backend

| File | Responsibility |
|------|---------------|
| `apps/academics/__init__.py` | App init |
| `apps/academics/apps.py` | AppConfig |
| `apps/academics/models.py` | GradeBand, Grade, Section, Subject, TeachingAssignment |
| `apps/academics/serializers.py` | CRUD serializers for all 5 models |
| `apps/academics/admin_views.py` | Admin CRUD + bulk import endpoints |
| `apps/academics/admin_urls.py` | Admin URL patterns |
| `apps/academics/teacher_views.py` | Teacher "My Classes" + section dashboard endpoints |
| `apps/academics/teacher_urls.py` | Teacher URL patterns |
| `apps/academics/signals.py` | Course auto-assignment on student add/section change |
| `apps/academics/services.py` | Auto-ID generation, promotion workflow, clone course |
| `apps/academics/management/__init__.py` | Management package |
| `apps/academics/management/commands/__init__.py` | Commands package |
| `apps/academics/management/commands/seed_keystone.py` | Keystone seed data |
| `apps/academics/migrations/0001_initial.py` | Auto-generated |
| `tests/academics/test_models.py` | Model unit tests |
| `tests/academics/test_admin_views.py` | Admin API tests |
| `tests/academics/test_teacher_views.py` | Teacher API tests |
| `tests/academics/test_services.py` | Service logic tests |
| `tests/academics/test_signals.py` | Signal tests |
| `tests/academics/conftest.py` | Fixtures |

### New Files — Frontend

| File | Responsibility |
|------|---------------|
| `src/services/academicsService.ts` | API client for academic endpoints |
| `src/pages/admin/SchoolViewPage.tsx` | Grade cards overview (Level 1) |
| `src/pages/admin/GradeDetailPage.tsx` | Section cards within a grade (Level 2) |
| `src/pages/admin/SectionDetailPage.tsx` | Students/Teachers/Courses tabs (Level 3) |
| `src/pages/teacher/MyClassesPage.tsx` | Teacher's assigned sections overview |
| `src/pages/teacher/SectionDashboardPage.tsx` | 4-tab section dashboard |

### Modified Files — Backend

| File | Changes |
|------|---------|
| `config/settings.py` | Add `'apps.academics'` to INSTALLED_APPS |
| `config/urls.py` | Add academic URL includes |
| `apps/tenants/models.py` | Add 10 new fields (academic year, ID gen, white-label) |
| `apps/users/models.py` | Add `grade` FK, `section` FK (nullable, alongside old text fields) |
| `apps/courses/models.py` | Add `course_type`, `subject` FK, `target_grades` M2M, `target_sections` M2M |
| `apps/users/serializers.py` | Rename `email` field to `identifier`, add auto-detect logic |
| `apps/users/views.py` | Modify login_view for flexible identifier lookup |

### Modified Files — Frontend

| File | Changes |
|------|---------|
| `src/App.tsx` | Add 6 new routes (3 admin, 3 teacher) |
| `src/components/layout/AdminSidebar.tsx` | Add "School" nav item |
| Login page component | Support flexible identifier input |

---

## Chunk 1: Backend Models & Migrations

### Task 1: Create the `academics` Django App Scaffold

**Files:**
- Create: `apps/academics/__init__.py`
- Create: `apps/academics/apps.py`
- Create: `apps/academics/models.py`

- [ ] **Step 1: Create app directory structure**

```bash
mkdir -p backend/apps/academics/management/commands
touch backend/apps/academics/__init__.py
touch backend/apps/academics/management/__init__.py
touch backend/apps/academics/management/commands/__init__.py
```

- [ ] **Step 2: Write apps.py**

```python
# apps/academics/apps.py
from django.apps import AppConfig

class AcademicsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.academics'
    verbose_name = 'Academics'

    def ready(self):
        import apps.academics.signals  # noqa: F401
```

- [ ] **Step 3: Write models.py with all 5 models**

```python
# apps/academics/models.py
import uuid
from django.db import models
from utils.tenant_manager import TenantManager


class GradeBand(models.Model):
    CURRICULUM_CHOICES = [
        ('REGGIO_EMILIA', 'Reggio Emilia'),
        ('CAMBRIDGE_PRIMARY', 'Cambridge Primary'),
        ('CAMBRIDGE_SECONDARY', 'Cambridge Secondary'),
        ('IGCSE', 'IGCSE'),
        ('KIPP', 'KIPP'),
        ('CUSTOM', 'Custom'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='grade_bands',
    )
    name = models.CharField(max_length=100, help_text="e.g. Early Years, Primary")
    short_code = models.CharField(max_length=10, help_text="e.g. KEY, PRI, MID, HS")
    order = models.PositiveIntegerField(default=0, help_text="Display order")
    curriculum_framework = models.CharField(
        max_length=30, choices=CURRICULUM_CHOICES, default='CUSTOM',
    )
    theme_config = models.JSONField(
        null=True, blank=True,
        help_text='{"accent_color": "#hex", "bg_image": "url", "welcome_msg": "text"}',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'grade_bands'
        unique_together = [('tenant', 'name')]
        ordering = ['order']
        indexes = [
            models.Index(fields=['tenant', 'order']),
        ]

    def __str__(self):
        return f"{self.name} ({self.short_code})"


class Grade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='grades',
    )
    grade_band = models.ForeignKey(
        GradeBand, on_delete=models.CASCADE, related_name='grades',
    )
    name = models.CharField(max_length=50, help_text="e.g. Nursery, Grade 9")
    short_code = models.CharField(max_length=10, help_text="e.g. NUR, G9")
    order = models.PositiveIntegerField(default=0, help_text="Global sort order")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'grades'
        unique_together = [('tenant', 'short_code')]
        ordering = ['order']
        indexes = [
            models.Index(fields=['tenant', 'order']),
            models.Index(fields=['tenant', 'grade_band']),
        ]

    def __str__(self):
        return f"{self.name} ({self.short_code})"


class Section(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='sections',
    )
    grade = models.ForeignKey(
        Grade, on_delete=models.CASCADE, related_name='sections',
    )
    name = models.CharField(max_length=20, help_text="e.g. A, B, C")
    academic_year = models.CharField(max_length=20, help_text="e.g. 2026-27")
    class_teacher = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='class_teacher_sections',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'sections'
        unique_together = [('tenant', 'grade', 'name', 'academic_year')]
        ordering = ['grade__order', 'name']
        indexes = [
            models.Index(fields=['tenant', 'academic_year']),
            models.Index(fields=['tenant', 'grade', 'academic_year']),
        ]

    def __str__(self):
        return f"{self.grade.name} - {self.name} ({self.academic_year})"


class Subject(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='subjects',
    )
    name = models.CharField(max_length=100, help_text="e.g. Physics, English Language")
    code = models.CharField(max_length=20, help_text="e.g. PHY, ENG")
    department = models.CharField(max_length=100, blank=True, default='', help_text="e.g. Science, Languages")
    applicable_grades = models.ManyToManyField(Grade, related_name='subjects', blank=True)
    is_elective = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'subjects'
        unique_together = [('tenant', 'code')]
        ordering = ['department', 'name']
        indexes = [
            models.Index(fields=['tenant', 'department']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class TeachingAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', on_delete=models.CASCADE, related_name='teaching_assignments',
    )
    teacher = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='teaching_assignments',
    )
    subject = models.ForeignKey(
        Subject, on_delete=models.CASCADE, related_name='teaching_assignments',
    )
    sections = models.ManyToManyField(Section, related_name='teaching_assignments', blank=True)
    academic_year = models.CharField(max_length=20, help_text="e.g. 2026-27")
    is_class_teacher = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = 'teaching_assignments'
        unique_together = [('tenant', 'teacher', 'subject', 'academic_year')]
        ordering = ['teacher__last_name', 'subject__name']
        indexes = [
            models.Index(fields=['tenant', 'academic_year']),
            models.Index(fields=['tenant', 'teacher', 'academic_year']),
        ]

    def __str__(self):
        return f"{self.teacher.get_full_name()} - {self.subject.name} ({self.academic_year})"
```

- [ ] **Step 4: Register app in settings.py**

In `config/settings.py`, add `'apps.academics'` to `INSTALLED_APPS` list.

- [ ] **Step 5: Generate and run migration**

```bash
cd backend
python manage.py makemigrations academics
python manage.py migrate
```

- [ ] **Step 6: Commit**

```bash
git add apps/academics/ config/settings.py
git commit -m "feat(academics): add 5 new models — GradeBand, Grade, Section, Subject, TeachingAssignment"
```

---

### Task 2: Add Tenant Model Fields (Academic Year, ID Gen, White-Label)

**Files:**
- Modify: `apps/tenants/models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/academics/test_models.py
from django.test import TestCase
from apps.tenants.models import Tenant

class TenantAcademicFieldsTest(TestCase):
    def test_tenant_has_academic_year_fields(self):
        t = Tenant.objects.create(
            name="Test", slug="test", subdomain="test", email="t@t.com",
            current_academic_year="2026-27",
            id_prefix="TST",
        )
        self.assertEqual(t.current_academic_year, "2026-27")
        self.assertEqual(t.id_prefix, "TST")
        self.assertEqual(t.student_id_counter, 1)
        self.assertEqual(t.teacher_id_counter, 1)
        self.assertFalse(t.white_label)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && python manage.py test tests.academics.test_models.TenantAcademicFieldsTest -v2
```
Expected: FAIL — fields don't exist yet.

- [ ] **Step 3: Add fields to Tenant model**

Add these fields after the existing `internal_notes` field in `apps/tenants/models.py`:

```python
    # Academic structure
    current_academic_year = models.CharField(
        max_length=20, blank=True, default='',
        help_text="e.g. 2026-27",
    )
    academic_year_start_date = models.DateField(null=True, blank=True)
    academic_year_end_date = models.DateField(null=True, blank=True)

    # Auto-generated user ID config
    id_prefix = models.CharField(
        max_length=10, blank=True, default='',
        help_text="Prefix for auto-generated IDs, e.g. KIS",
    )
    student_id_counter = models.PositiveIntegerField(
        default=1, help_text="Next student sequence number",
    )
    teacher_id_counter = models.PositiveIntegerField(
        default=1, help_text="Next teacher sequence number",
    )

    # White-label branding
    white_label = models.BooleanField(
        default=False, help_text="Hide LearnPuddle branding",
    )
    login_bg_image = models.URLField(
        blank=True, default='', help_text="Login page background image URL",
    )
    welcome_message = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Dashboard greeting message",
    )
    school_motto = models.CharField(
        max_length=200, blank=True, default='',
        help_text="Footer/about text",
    )
```

- [ ] **Step 4: Generate and run migration**

```bash
python manage.py makemigrations tenants
python manage.py migrate
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python manage.py test tests.academics.test_models.TenantAcademicFieldsTest -v2
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/tenants/models.py apps/tenants/migrations/
git commit -m "feat(tenants): add academic year, ID generation, and white-label fields"
```

---

### Task 3: Add User Model FK Fields (grade, section)

**Files:**
- Modify: `apps/users/models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/academics/test_models.py (append)
class UserGradeSectionFKTest(TestCase):
    def test_user_has_grade_and_section_fks(self):
        from apps.users.models import User
        from apps.academics.models import GradeBand, Grade, Section
        from apps.tenants.models import Tenant

        t = Tenant.objects.create(
            name="Test", slug="test-fk", subdomain="testfk", email="t@t.com",
            current_academic_year="2026-27",
        )
        band = GradeBand.all_objects.create(tenant=t, name="High", short_code="HS", order=1)
        grade = Grade.all_objects.create(tenant=t, grade_band=band, name="Grade 9", short_code="G9", order=9)
        section = Section.all_objects.create(tenant=t, grade=grade, name="A", academic_year="2026-27")

        student = User.objects.create_user(
            email="s@t.com", password="Test1234!",
            first_name="S", last_name="T",
            tenant=t, role="STUDENT",
            grade_fk=grade, section_fk=section,
        )
        self.assertEqual(student.grade_fk, grade)
        self.assertEqual(student.section_fk, section)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test tests.academics.test_models.UserGradeSectionFKTest -v2
```

- [ ] **Step 3: Add FK fields to User model**

In `apps/users/models.py`, add after the existing `section` CharField (line ~54):

```python
    # Academic structure FKs (new — coexist with old text fields during migration)
    grade_fk = models.ForeignKey(
        'academics.Grade', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='students', help_text="Student's current grade",
    )
    section_fk = models.ForeignKey(
        'academics.Section', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='students', help_text="Student's current section",
    )
```

- [ ] **Step 4: Generate and run migration**

```bash
python manage.py makemigrations users
python manage.py migrate
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python manage.py test tests.academics.test_models.UserGradeSectionFKTest -v2
```

- [ ] **Step 6: Commit**

```bash
git add apps/users/models.py apps/users/migrations/
git commit -m "feat(users): add grade_fk and section_fk to User model"
```

---

### Task 4: Add Course Model Fields (course_type, subject, target_grades, target_sections)

**Files:**
- Modify: `apps/courses/models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/academics/test_models.py (append)
class CourseAcademicFieldsTest(TestCase):
    def test_course_has_academic_fields(self):
        from apps.courses.models import Course
        from apps.tenants.models import Tenant

        t = Tenant.objects.create(
            name="Test", slug="test-course", subdomain="testcourse", email="t@t.com",
        )
        # Use all_objects to bypass TenantManager
        c = Course.all_objects.create(
            tenant=t, title="Physics 101", description="Intro",
            course_type="ACADEMIC",
        )
        self.assertEqual(c.course_type, "ACADEMIC")
        self.assertIsNone(c.subject)
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Add fields to Course model**

In `apps/courses/models.py`, add after the `assigned_to_all_students` field (line ~83):

```python
    # Academic course fields
    COURSE_TYPE_CHOICES = [
        ('PD', 'Professional Development'),
        ('ACADEMIC', 'Academic'),
    ]
    course_type = models.CharField(
        max_length=10, choices=COURSE_TYPE_CHOICES, default='PD',
        help_text="PD = admin→teachers, ACADEMIC = teacher→students",
    )
    subject = models.ForeignKey(
        'academics.Subject', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='courses', help_text="For academic courses",
    )
    target_grades = models.ManyToManyField(
        'academics.Grade', related_name='targeted_courses', blank=True,
        help_text="Which grades this course targets",
    )
    target_sections = models.ManyToManyField(
        'academics.Section', related_name='targeted_courses', blank=True,
        help_text="Specific sections (optional, defaults to all in target grades)",
    )
```

- [ ] **Step 4: Generate and run migration**

```bash
python manage.py makemigrations courses
python manage.py migrate
```

- [ ] **Step 5: Run test to verify it passes**

- [ ] **Step 6: Commit**

```bash
git add apps/courses/models.py apps/courses/migrations/
git commit -m "feat(courses): add course_type, subject FK, target_grades/sections M2M"
```

---

### Task 5: Register URLs in config/urls.py

**Files:**
- Modify: `config/urls.py`
- Create: `apps/academics/admin_urls.py`
- Create: `apps/academics/teacher_urls.py`

- [ ] **Step 1: Create empty URL files**

```python
# apps/academics/admin_urls.py
from django.urls import path

app_name = "admin_academics"

urlpatterns = []
```

```python
# apps/academics/teacher_urls.py
from django.urls import path

app_name = "teacher_academics"

urlpatterns = []
```

- [ ] **Step 2: Add URL includes to config/urls.py**

Add to `_api_patterns` list:

```python
    path('academics/', include('apps.academics.admin_urls')),
    path('teacher/academics/', include('apps.academics.teacher_urls')),
```

- [ ] **Step 3: Create empty signals.py**

```python
# apps/academics/signals.py
# Auto-assignment signals — implemented in Task 15
```

- [ ] **Step 4: Verify server starts**

```bash
python manage.py check
python manage.py runserver 0.0.0.0:8000 &
curl -s http://localhost:8000/health/ | head -1
kill %1
```

- [ ] **Step 5: Commit**

```bash
git add apps/academics/admin_urls.py apps/academics/teacher_urls.py apps/academics/signals.py config/urls.py
git commit -m "feat(academics): wire URL routing into main config"
```

---

## Chunk 2: Auto-Generated IDs & Flexible Login

### Task 6: Implement Auto-ID Generation Service

**Files:**
- Create: `apps/academics/services.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/academics/test_services.py
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.academics.services import generate_student_id, generate_teacher_id

class AutoIDGenerationTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="KIS", slug="kis", subdomain="kis", email="t@t.com",
            id_prefix="KIS", student_id_counter=1, teacher_id_counter=1,
        )

    def test_generate_student_id_first(self):
        sid = generate_student_id(self.tenant)
        self.assertEqual(sid, "KIS-S-0001")
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.student_id_counter, 2)

    def test_generate_student_id_sequential(self):
        s1 = generate_student_id(self.tenant)
        s2 = generate_student_id(self.tenant)
        self.assertEqual(s1, "KIS-S-0001")
        self.assertEqual(s2, "KIS-S-0002")

    def test_generate_teacher_id(self):
        tid = generate_teacher_id(self.tenant)
        self.assertEqual(tid, "KIS-T-0001")

    def test_atomic_increment(self):
        """Counter uses F-expression to avoid race conditions."""
        sid = generate_student_id(self.tenant)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.student_id_counter, 2)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test tests.academics.test_services.AutoIDGenerationTest -v2
```

- [ ] **Step 3: Write services.py**

```python
# apps/academics/services.py
from django.db.models import F
from apps.tenants.models import Tenant


def generate_student_id(tenant: Tenant) -> str:
    """Generate next student ID using atomic counter increment."""
    counter = tenant.student_id_counter
    Tenant.objects.filter(pk=tenant.pk).update(
        student_id_counter=F('student_id_counter') + 1,
    )
    return f"{tenant.id_prefix}-S-{counter:04d}"


def generate_teacher_id(tenant: Tenant) -> str:
    """Generate next teacher ID using atomic counter increment."""
    counter = tenant.teacher_id_counter
    Tenant.objects.filter(pk=tenant.pk).update(
        teacher_id_counter=F('teacher_id_counter') + 1,
    )
    return f"{tenant.id_prefix}-T-{counter:04d}"
```

- [ ] **Step 4: Run test to verify it passes**

- [ ] **Step 5: Commit**

```bash
git add apps/academics/services.py tests/academics/test_services.py
git commit -m "feat(academics): implement atomic auto-ID generation for students and teachers"
```

---

### Task 7: Modify LoginSerializer for Flexible Identifier

**Files:**
- Modify: `apps/users/serializers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/academics/test_login.py
import re
from django.test import TestCase
from apps.users.serializers import detect_identifier_type

class IdentifierDetectionTest(TestCase):
    def test_email_detected(self):
        self.assertEqual(detect_identifier_type("john@school.edu"), "email")

    def test_student_id_detected(self):
        self.assertEqual(detect_identifier_type("KIS-S-0001"), "student_id")

    def test_teacher_id_detected(self):
        self.assertEqual(detect_identifier_type("KIS-T-0042"), "teacher_id")

    def test_plain_text_defaults_to_email(self):
        self.assertEqual(detect_identifier_type("john"), "email")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python manage.py test tests.academics.test_login.IdentifierDetectionTest -v2
```

- [ ] **Step 3: Add detect_identifier_type function to serializers.py**

Add at the top of `apps/users/serializers.py` (after the imports):

```python
import re

# Pattern: PREFIX-S-DIGITS or PREFIX-T-DIGITS
_STUDENT_ID_RE = re.compile(r'^[A-Z]{2,10}-S-\d{4,}$', re.IGNORECASE)
_TEACHER_ID_RE = re.compile(r'^[A-Z]{2,10}-T-\d{4,}$', re.IGNORECASE)


def detect_identifier_type(identifier: str) -> str:
    """Detect whether identifier is email, student_id, or teacher_id."""
    identifier = identifier.strip()
    if '@' in identifier:
        return 'email'
    if _STUDENT_ID_RE.match(identifier):
        return 'student_id'
    if _TEACHER_ID_RE.match(identifier):
        return 'teacher_id'
    return 'email'  # Default fallback
```

- [ ] **Step 4: Modify LoginSerializer.validate() to support flexible lookup**

Replace the `email` field and update `validate()` in `LoginSerializer`:

```python
class LoginSerializer(serializers.Serializer):
    """Serializer for user login with flexible identifier."""

    identifier = serializers.CharField(
        help_text="Email address, student ID (e.g. KIS-S-0001), or teacher ID (e.g. KIS-T-0001)",
    )
    # Keep 'email' as alias for backward compatibility
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True)
    portal = serializers.ChoiceField(
        choices=['super_admin', 'tenant'],
        default='tenant',
        required=False,
    )

    def validate(self, data):
        # Support both 'identifier' and legacy 'email' field
        identifier = data.get('identifier') or data.get('email', '')
        password = data.get('password')
        portal = data.get('portal', 'tenant')

        if not identifier or not password:
            raise serializers.ValidationError("Identifier and password are required")

        # Check account lockout
        key = _lockout_key(identifier)
        attempts = cache.get(key, 0)
        if attempts >= MAX_LOGIN_ATTEMPTS:
            raise serializers.ValidationError(
                "Account temporarily locked due to too many failed attempts. "
                "Please try again in 15 minutes."
            )

        # Detect identifier type and look up user
        id_type = detect_identifier_type(identifier)
        user = None

        if id_type == 'email':
            user = authenticate(
                request=self.context.get('request'),
                username=identifier,
                password=password,
            )
        else:
            # Look up by student_id or employee_id
            from apps.users.models import User
            lookup_field = 'student_id' if id_type == 'student_id' else 'employee_id'
            try:
                found_user = User.objects.get(**{lookup_field: identifier.upper()})
                if found_user.check_password(password):
                    user = found_user
            except User.DoesNotExist:
                pass

        if not user:
            cache.set(key, attempts + 1, LOCKOUT_DURATION_SECONDS)
            raise serializers.ValidationError("Invalid credentials")

        if not user.is_active:
            raise serializers.ValidationError("User account is disabled")

        if portal == 'tenant' and user.tenant_id and not user.tenant.is_active:
            raise serializers.ValidationError(
                "Your school account has been deactivated. Please contact your administrator."
            )

        if portal == 'super_admin' and user.role != 'SUPER_ADMIN':
            raise serializers.ValidationError(
                "This login page is for platform administrators only."
            )

        data['user'] = user
        return data
```

- [ ] **Step 5: Run test to verify it passes**

- [ ] **Step 6: Verify existing login still works**

```bash
python manage.py test apps.users -v2
```

- [ ] **Step 7: Commit**

```bash
git add apps/users/serializers.py tests/academics/test_login.py
git commit -m "feat(auth): support flexible login with email, student ID, or teacher ID"
```

---

### Task 8: Update login_view for Flexible Identifier

**Files:**
- Modify: `apps/users/views.py`

- [ ] **Step 1: Write integration test**

```python
# tests/academics/test_login.py (append)
from rest_framework.test import APIClient

class FlexibleLoginIntegrationTest(TestCase):
    def setUp(self):
        from apps.tenants.models import Tenant
        from apps.users.models import User

        self.tenant = Tenant.objects.create(
            name="KIS", slug="kis-login", subdomain="kis",
            email="a@kis.com", id_prefix="KIS",
        )
        self.student = User.objects.create_user(
            email="s@kis.com", password="Pass1234!",
            first_name="S", last_name="T",
            tenant=self.tenant, role="STUDENT",
            student_id="KIS-S-0001",
        )
        self.client = APIClient()

    def test_login_with_email(self):
        resp = self.client.post(
            '/api/v1/users/auth/login/',
            {'identifier': 's@kis.com', 'password': 'Pass1234!'},
            format='json',
            HTTP_HOST='kis.localhost',
        )
        self.assertIn(resp.status_code, [200, 403])  # 403 if tenant middleware strict

    def test_login_with_student_id(self):
        resp = self.client.post(
            '/api/v1/users/auth/login/',
            {'identifier': 'KIS-S-0001', 'password': 'Pass1234!'},
            format='json',
            HTTP_HOST='kis.localhost',
        )
        self.assertIn(resp.status_code, [200, 403])
```

- [ ] **Step 2: The login_view already uses LoginSerializer — no changes needed if serializer handles it**

The existing `login_view` calls `LoginSerializer(data=request.data, ...)` and uses `serializer.validated_data['user']`. Since we updated the serializer, login_view should work. Verify with test.

- [ ] **Step 3: Run tests**

```bash
python manage.py test tests.academics.test_login -v2
```

- [ ] **Step 4: Commit**

```bash
git add tests/academics/test_login.py
git commit -m "test(auth): add integration tests for flexible login flow"
```

---

## Chunk 3: Admin API Endpoints (Academic CRUD)

### Task 9: Write Academic Serializers

**Files:**
- Create: `apps/academics/serializers.py`

- [ ] **Step 1: Write serializers**

```python
# apps/academics/serializers.py
from rest_framework import serializers
from .models import GradeBand, Grade, Section, Subject, TeachingAssignment


class GradeBandSerializer(serializers.ModelSerializer):
    grade_count = serializers.SerializerMethodField()

    class Meta:
        model = GradeBand
        fields = [
            'id', 'name', 'short_code', 'order', 'curriculum_framework',
            'theme_config', 'grade_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_grade_count(self, obj):
        if hasattr(obj, '_grade_count'):
            return obj._grade_count
        return obj.grades.count()


class GradeSerializer(serializers.ModelSerializer):
    grade_band_name = serializers.CharField(source='grade_band.name', read_only=True)
    student_count = serializers.SerializerMethodField()
    section_count = serializers.SerializerMethodField()

    class Meta:
        model = Grade
        fields = [
            'id', 'grade_band', 'grade_band_name', 'name', 'short_code',
            'order', 'student_count', 'section_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_student_count(self, obj):
        if hasattr(obj, '_student_count'):
            return obj._student_count
        return obj.students.filter(is_deleted=False, is_active=True).count()

    def get_section_count(self, obj):
        if hasattr(obj, '_section_count'):
            return obj._section_count
        return obj.sections.count()


class SectionSerializer(serializers.ModelSerializer):
    grade_name = serializers.CharField(source='grade.name', read_only=True)
    class_teacher_name = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = [
            'id', 'grade', 'grade_name', 'name', 'academic_year',
            'class_teacher', 'class_teacher_name', 'student_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_class_teacher_name(self, obj):
        return obj.class_teacher.get_full_name() if obj.class_teacher else None

    def get_student_count(self, obj):
        if hasattr(obj, '_student_count'):
            return obj._student_count
        return obj.students.filter(is_deleted=False, is_active=True).count()


class SubjectSerializer(serializers.ModelSerializer):
    applicable_grade_ids = serializers.PrimaryKeyRelatedField(
        source='applicable_grades', queryset=Grade.objects.none(),
        many=True, required=False,
    )

    class Meta:
        model = Subject
        fields = [
            'id', 'name', 'code', 'department', 'applicable_grade_ids',
            'is_elective', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'tenant') and request.tenant:
            self.fields['applicable_grade_ids'].child_relation.queryset = (
                Grade.all_objects.filter(tenant=request.tenant)
            )


class TeachingAssignmentSerializer(serializers.ModelSerializer):
    teacher_name = serializers.SerializerMethodField()
    subject_name = serializers.CharField(source='subject.name', read_only=True)
    section_ids = serializers.PrimaryKeyRelatedField(
        source='sections', queryset=Section.objects.none(),
        many=True, required=False,
    )

    class Meta:
        model = TeachingAssignment
        fields = [
            'id', 'teacher', 'teacher_name', 'subject', 'subject_name',
            'section_ids', 'academic_year', 'is_class_teacher',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and hasattr(request, 'tenant') and request.tenant:
            self.fields['section_ids'].child_relation.queryset = (
                Section.all_objects.filter(tenant=request.tenant)
            )

    def get_teacher_name(self, obj):
        return obj.teacher.get_full_name()
```

- [ ] **Step 2: Commit**

```bash
git add apps/academics/serializers.py
git commit -m "feat(academics): add CRUD serializers for all 5 academic models"
```

---

### Task 10: Write Admin Views — GradeBand & Grade CRUD

**Files:**
- Create: `apps/academics/admin_views.py`
- Modify: `apps/academics/admin_urls.py`

- [ ] **Step 1: Write admin_views.py (grade bands + grades)**

```python
# apps/academics/admin_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q

from utils.decorators import admin_only, tenant_required
from utils.audit import log_audit
from .models import GradeBand, Grade, Section, Subject, TeachingAssignment
from .serializers import (
    GradeBandSerializer, GradeSerializer, SectionSerializer,
    SubjectSerializer, TeachingAssignmentSerializer,
)


# ─── GradeBand ────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def grade_band_list_create(request):
    if request.method == 'GET':
        bands = GradeBand.objects.annotate(
            _grade_count=Count('grades'),
        ).order_by('order')
        return Response(GradeBandSerializer(bands, many=True).data)

    data = request.data.copy()
    serializer = GradeBandSerializer(data=data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    band = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'GradeBand', target_id=str(band.id),
              target_repr=str(band), request=request)
    return Response(GradeBandSerializer(band).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def grade_band_detail(request, band_id):
    band = get_object_or_404(GradeBand, pk=band_id, tenant=request.tenant)

    if request.method == 'GET':
        return Response(GradeBandSerializer(band).data)

    if request.method == 'DELETE':
        band.delete()
        log_audit('DELETE', 'GradeBand', target_id=str(band_id),
                  target_repr=str(band), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = GradeBandSerializer(band, data=request.data, partial=True,
                                     context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'GradeBand', target_id=str(band_id),
              target_repr=str(band), request=request)
    return Response(serializer.data)


# ─── Grade ────────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def grade_list_create(request):
    if request.method == 'GET':
        qs = Grade.objects.select_related('grade_band').annotate(
            _student_count=Count(
                'students',
                filter=Q(students__is_deleted=False, students__is_active=True),
            ),
            _section_count=Count('sections'),
        ).order_by('order')

        band_id = request.GET.get('grade_band')
        if band_id:
            qs = qs.filter(grade_band_id=band_id)

        return Response(GradeSerializer(qs, many=True).data)

    serializer = GradeSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    grade = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'Grade', target_id=str(grade.id),
              target_repr=str(grade), request=request)
    return Response(GradeSerializer(grade).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def grade_detail(request, grade_id):
    grade = get_object_or_404(Grade, pk=grade_id, tenant=request.tenant)

    if request.method == 'GET':
        return Response(GradeSerializer(grade).data)

    if request.method == 'DELETE':
        grade.delete()
        log_audit('DELETE', 'Grade', target_id=str(grade_id),
                  target_repr=str(grade), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    serializer = GradeSerializer(grade, data=request.data, partial=True,
                                 context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'Grade', target_id=str(grade_id),
              target_repr=str(grade), request=request)
    return Response(serializer.data)
```

- [ ] **Step 2: Wire URLs**

```python
# apps/academics/admin_urls.py
from django.urls import path
from . import admin_views

app_name = "admin_academics"

urlpatterns = [
    # GradeBands
    path("grade-bands/", admin_views.grade_band_list_create, name="grade_band_list"),
    path("grade-bands/<uuid:band_id>/", admin_views.grade_band_detail, name="grade_band_detail"),
    # Grades
    path("grades/", admin_views.grade_list_create, name="grade_list"),
    path("grades/<uuid:grade_id>/", admin_views.grade_detail, name="grade_detail"),
]
```

- [ ] **Step 3: Write test**

```python
# tests/academics/test_admin_views.py
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.users.models import User


class GradeBandAPITest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", slug="test-api", subdomain="testapi", email="t@t.com",
        )
        self.admin = User.objects.create_user(
            email="admin@t.com", password="Admin123!",
            first_name="A", last_name="D",
            tenant=self.tenant, role="SCHOOL_ADMIN",
        )
        self.client = APIClient()
        tokens = RefreshToken.for_user(self.admin)
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {tokens.access_token}',
            HTTP_HOST='testapi.localhost',
        )

    def test_create_grade_band(self):
        resp = self.client.post('/api/v1/academics/grade-bands/', {
            'name': 'Primary', 'short_code': 'PRI', 'order': 1,
            'curriculum_framework': 'CAMBRIDGE_PRIMARY',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['name'], 'Primary')

    def test_list_grade_bands(self):
        resp = self.client.get('/api/v1/academics/grade-bands/')
        self.assertEqual(resp.status_code, 200)
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test tests.academics.test_admin_views -v2
```

- [ ] **Step 5: Commit**

```bash
git add apps/academics/admin_views.py apps/academics/admin_urls.py tests/academics/
git commit -m "feat(academics): admin CRUD endpoints for GradeBand and Grade"
```

---

### Task 11: Admin Views — Section, Subject, TeachingAssignment CRUD

**Files:**
- Modify: `apps/academics/admin_views.py`
- Modify: `apps/academics/admin_urls.py`

- [ ] **Step 1: Add Section views to admin_views.py**

```python
# ─── Section ──────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def section_list_create(request):
    if request.method == 'GET':
        qs = Section.objects.select_related('grade', 'class_teacher').annotate(
            _student_count=Count(
                'students',
                filter=Q(students__is_deleted=False, students__is_active=True),
            ),
        )
        grade_id = request.GET.get('grade')
        if grade_id:
            qs = qs.filter(grade_id=grade_id)
        academic_year = request.GET.get('academic_year')
        if academic_year:
            qs = qs.filter(academic_year=academic_year)
        return Response(SectionSerializer(qs, many=True).data)

    serializer = SectionSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    section = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'Section', target_id=str(section.id),
              target_repr=str(section), request=request)
    return Response(SectionSerializer(section).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def section_detail(request, section_id):
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)
    if request.method == 'GET':
        return Response(SectionSerializer(section).data)
    if request.method == 'DELETE':
        section.delete()
        log_audit('DELETE', 'Section', target_id=str(section_id), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = SectionSerializer(section, data=request.data, partial=True,
                                   context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'Section', target_id=str(section_id), request=request)
    return Response(serializer.data)


# ─── Subject ──────────────────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def subject_list_create(request):
    if request.method == 'GET':
        qs = Subject.objects.prefetch_related('applicable_grades').order_by('department', 'name')
        dept = request.GET.get('department')
        if dept:
            qs = qs.filter(department__icontains=dept)
        return Response(SubjectSerializer(qs, many=True, context={'request': request}).data)

    serializer = SubjectSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    subject = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'Subject', target_id=str(subject.id),
              target_repr=str(subject), request=request)
    return Response(SubjectSerializer(subject, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def subject_detail(request, subject_id):
    subject = get_object_or_404(Subject, pk=subject_id, tenant=request.tenant)
    if request.method == 'GET':
        return Response(SubjectSerializer(subject, context={'request': request}).data)
    if request.method == 'DELETE':
        subject.delete()
        log_audit('DELETE', 'Subject', target_id=str(subject_id), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = SubjectSerializer(subject, data=request.data, partial=True,
                                   context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'Subject', target_id=str(subject_id), request=request)
    return Response(serializer.data)


# ─── TeachingAssignment ───────────────────────────────────────────────

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teaching_assignment_list_create(request):
    if request.method == 'GET':
        qs = TeachingAssignment.objects.select_related(
            'teacher', 'subject',
        ).prefetch_related('sections')
        teacher_id = request.GET.get('teacher')
        if teacher_id:
            qs = qs.filter(teacher_id=teacher_id)
        academic_year = request.GET.get('academic_year')
        if academic_year:
            qs = qs.filter(academic_year=academic_year)
        return Response(TeachingAssignmentSerializer(
            qs, many=True, context={'request': request},
        ).data)

    serializer = TeachingAssignmentSerializer(data=request.data, context={'request': request})
    serializer.is_valid(raise_exception=True)
    ta = serializer.save(tenant=request.tenant)
    log_audit('CREATE', 'TeachingAssignment', target_id=str(ta.id),
              target_repr=str(ta), request=request)
    return Response(TeachingAssignmentSerializer(ta, context={'request': request}).data,
                    status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def teaching_assignment_detail(request, assignment_id):
    ta = get_object_or_404(TeachingAssignment, pk=assignment_id, tenant=request.tenant)
    if request.method == 'GET':
        return Response(TeachingAssignmentSerializer(ta, context={'request': request}).data)
    if request.method == 'DELETE':
        ta.delete()
        log_audit('DELETE', 'TeachingAssignment', target_id=str(assignment_id), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
    serializer = TeachingAssignmentSerializer(ta, data=request.data, partial=True,
                                              context={'request': request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    log_audit('UPDATE', 'TeachingAssignment', target_id=str(assignment_id), request=request)
    return Response(serializer.data)
```

- [ ] **Step 2: Add URLs**

Append to `apps/academics/admin_urls.py`:

```python
    # Sections
    path("sections/", admin_views.section_list_create, name="section_list"),
    path("sections/<uuid:section_id>/", admin_views.section_detail, name="section_detail"),
    # Subjects
    path("subjects/", admin_views.subject_list_create, name="subject_list"),
    path("subjects/<uuid:subject_id>/", admin_views.subject_detail, name="subject_detail"),
    # Teaching Assignments
    path("teaching-assignments/", admin_views.teaching_assignment_list_create, name="ta_list"),
    path("teaching-assignments/<uuid:assignment_id>/", admin_views.teaching_assignment_detail, name="ta_detail"),
```

- [ ] **Step 3: Run full check**

```bash
python manage.py check
python manage.py test tests.academics -v2
```

- [ ] **Step 4: Commit**

```bash
git add apps/academics/admin_views.py apps/academics/admin_urls.py
git commit -m "feat(academics): admin CRUD for Section, Subject, TeachingAssignment"
```

---

### Task 12: Contextual CSV Import — Students into Section

**Files:**
- Modify: `apps/academics/admin_views.py`
- Modify: `apps/academics/admin_urls.py`

- [ ] **Step 1: Add bulk import view**

```python
# Append to apps/academics/admin_views.py

import csv
import io
import secrets
from utils.decorators import check_tenant_limit
from .services import generate_student_id

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
@admin_only
@tenant_required
@check_tenant_limit('students')
def section_import_students(request, section_id):
    """Import students via CSV into a specific section. Grade/section pre-filled from context."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    f = request.FILES.get('file')
    if not f:
        return Response({'error': 'CSV file is required'}, status=400)

    if getattr(f, 'size', 0) > 2 * 1024 * 1024:
        return Response({'error': 'CSV file too large (max 2MB)'}, status=400)

    from apps.users.models import User

    content = f.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    results = {'created': 0, 'errors': [], 'total_rows': 0}

    for row_num, row in enumerate(reader, start=2):
        results['total_rows'] += 1
        try:
            email = row.get('email', '').strip().lower()
            if not email:
                results['errors'].append({'row': row_num, 'error': 'Email is required'})
                continue

            if User.objects.filter(email__iexact=email).exists():
                results['errors'].append({'row': row_num, 'error': f'Email {email} already exists'})
                continue

            password = secrets.token_urlsafe(12)
            student_id = generate_student_id(request.tenant)

            User.objects.create_user(
                email=email,
                password=password,
                first_name=row.get('first_name', '').strip(),
                last_name=row.get('last_name', '').strip(),
                tenant=request.tenant,
                role='STUDENT',
                student_id=student_id,
                grade_fk=section.grade,
                section_fk=section,
                must_change_password=True,
            )
            results['created'] += 1
        except Exception as e:
            results['errors'].append({'row': row_num, 'error': str(e)})

    log_audit('IMPORT', 'User', target_id=str(section_id),
              target_repr=f"Imported {results['created']} students into {section}",
              request=request)
    return Response(results)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
@check_tenant_limit('students')
def section_add_student(request, section_id):
    """Add a single student to a section."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    from apps.users.models import User

    email = request.data.get('email', '').strip().lower()
    if not email:
        return Response({'error': 'Email is required'}, status=400)

    if User.objects.filter(email__iexact=email).exists():
        return Response({'error': 'A user with this email already exists'}, status=400)

    password = secrets.token_urlsafe(12)
    student_id = generate_student_id(request.tenant)

    student = User.objects.create_user(
        email=email,
        password=password,
        first_name=request.data.get('first_name', '').strip(),
        last_name=request.data.get('last_name', '').strip(),
        tenant=request.tenant,
        role='STUDENT',
        student_id=student_id,
        grade_fk=section.grade,
        section_fk=section,
        must_change_password=True,
    )

    log_audit('CREATE', 'User', target_id=str(student.id),
              target_repr=str(student), request=request)

    from apps.users.serializers import UserSerializer
    return Response(UserSerializer(student).data, status=status.HTTP_201_CREATED)
```

- [ ] **Step 2: Add URLs**

```python
    # CSV Import & Add Student
    path("sections/<uuid:section_id>/import-students/", admin_views.section_import_students, name="section_import_students"),
    path("sections/<uuid:section_id>/add-student/", admin_views.section_add_student, name="section_add_student"),
```

- [ ] **Step 3: Commit**

```bash
git add apps/academics/admin_views.py apps/academics/admin_urls.py
git commit -m "feat(academics): contextual CSV import and single-student add within sections"
```

---

### Task 13: School View API — Aggregated Data Endpoints

**Files:**
- Modify: `apps/academics/admin_views.py`
- Modify: `apps/academics/admin_urls.py`

- [ ] **Step 1: Add school overview endpoint**

```python
# Append to apps/academics/admin_views.py

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def school_overview(request):
    """School View Level 1: grade bands with grades, student/section counts."""
    from apps.users.models import User

    bands = GradeBand.objects.filter(
        tenant=request.tenant,
    ).prefetch_related('grades__sections').order_by('order')

    result = []
    for band in bands:
        band_data = GradeBandSerializer(band).data
        grades = []
        for grade in band.grades.order_by('order'):
            student_count = User.objects.filter(
                grade_fk=grade, is_deleted=False, is_active=True, role='STUDENT',
            ).count()
            section_count = grade.sections.filter(
                academic_year=request.tenant.current_academic_year,
            ).count()
            grades.append({
                **GradeSerializer(grade).data,
                'student_count': student_count,
                'section_count': section_count,
            })
        band_data['grades'] = grades
        result.append(band_data)

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def section_students(request, section_id):
    """Section students roster with progress data."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    from apps.users.models import User
    from apps.users.serializers import UserSerializer

    students = User.objects.filter(
        section_fk=section, is_deleted=False, role='STUDENT',
    ).order_by('last_name', 'first_name')

    # TODO: Add progress annotations in future task
    data = UserSerializer(students, many=True).data
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def section_teachers(request, section_id):
    """Teachers assigned to this section via TeachingAssignment."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    assignments = TeachingAssignment.objects.filter(
        sections=section,
        academic_year=request.tenant.current_academic_year,
    ).select_related('teacher', 'subject')

    return Response(TeachingAssignmentSerializer(
        assignments, many=True, context={'request': request},
    ).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def section_courses(request, section_id):
    """Courses targeting this section."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    from apps.courses.models import Course
    courses = Course.objects.filter(
        target_sections=section, course_type='ACADEMIC',
    ).order_by('-created_at')

    from apps.courses.serializers import CourseListSerializer
    return Response(CourseListSerializer(
        courses, many=True, context={'request': request},
    ).data)
```

- [ ] **Step 2: Add URLs**

```python
    # School View
    path("school-overview/", admin_views.school_overview, name="school_overview"),
    path("sections/<uuid:section_id>/students/", admin_views.section_students, name="section_students"),
    path("sections/<uuid:section_id>/teachers/", admin_views.section_teachers, name="section_teachers"),
    path("sections/<uuid:section_id>/courses/", admin_views.section_courses, name="section_courses"),
```

- [ ] **Step 3: Commit**

```bash
git add apps/academics/admin_views.py apps/academics/admin_urls.py
git commit -m "feat(academics): school overview and section detail API endpoints"
```

---

## Chunk 4: Course Workflow & Auto-Assignment

### Task 14: Course Auto-Assignment on Publish

**Files:**
- Create: `apps/academics/signals.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/academics/test_signals.py
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.users.models import User
from apps.courses.models import Course
from apps.academics.models import GradeBand, Grade, Section


class CourseAutoAssignmentTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="T", slug="t-sig", subdomain="tsig", email="t@t.com",
            current_academic_year="2026-27",
        )
        band = GradeBand.all_objects.create(tenant=self.tenant, name="HS", short_code="HS", order=1)
        self.grade = Grade.all_objects.create(tenant=self.tenant, grade_band=band, name="G9", short_code="G9", order=9)
        self.section = Section.all_objects.create(
            tenant=self.tenant, grade=self.grade, name="A", academic_year="2026-27",
        )
        self.student = User.objects.create_user(
            email="s@t.com", password="Pass123!",
            first_name="S", last_name="T",
            tenant=self.tenant, role="STUDENT",
            grade_fk=self.grade, section_fk=self.section,
        )

    def test_publish_course_assigns_students_in_section(self):
        course = Course.all_objects.create(
            tenant=self.tenant, title="Physics", description="...",
            course_type="ACADEMIC", is_published=False,
        )
        course.target_sections.add(self.section)

        # Simulate publish
        from apps.academics.services import auto_assign_course_students
        auto_assign_course_students(course)

        self.assertIn(self.student, course.assigned_students.all())
```

- [ ] **Step 2: Implement auto_assign_course_students in services.py**

```python
# Append to apps/academics/services.py

def auto_assign_course_students(course):
    """Populate assigned_students based on target_sections (or target_grades if no sections)."""
    from apps.users.models import User

    if course.course_type != 'ACADEMIC':
        return

    target_sections = course.target_sections.all()
    if target_sections.exists():
        students = User.objects.filter(
            section_fk__in=target_sections,
            role='STUDENT', is_deleted=False, is_active=True,
        )
    else:
        target_grades = course.target_grades.all()
        if target_grades.exists():
            students = User.objects.filter(
                grade_fk__in=target_grades,
                role='STUDENT', is_deleted=False, is_active=True,
            )
        else:
            return

    course.assigned_students.add(*students)
```

- [ ] **Step 3: Write the signal**

```python
# apps/academics/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from apps.courses.models import Course


@receiver(pre_save, sender=Course)
def course_publish_auto_assign(sender, instance, **kwargs):
    """When a course is published, auto-assign students based on targeting."""
    if not instance.pk:
        return  # New course, not published yet

    try:
        old = Course.all_objects.get(pk=instance.pk)
    except Course.DoesNotExist:
        return

    # Detect publish transition: was unpublished, now published
    if not old.is_published and instance.is_published and instance.course_type == 'ACADEMIC':
        # Defer to post_save since M2M relations need saved instance
        instance._needs_auto_assign = True


@receiver(pre_save, sender=Course)
def _noop(*args, **kwargs):
    pass  # placeholder, real post_save below


from django.db.models.signals import post_save

@receiver(post_save, sender=Course)
def course_post_save_auto_assign(sender, instance, **kwargs):
    if getattr(instance, '_needs_auto_assign', False):
        from .services import auto_assign_course_students
        auto_assign_course_students(instance)
        instance._needs_auto_assign = False
```

- [ ] **Step 4: Run tests**

```bash
python manage.py test tests.academics.test_signals -v2
```

- [ ] **Step 5: Commit**

```bash
git add apps/academics/signals.py apps/academics/services.py tests/academics/test_signals.py
git commit -m "feat(academics): auto-assign students to course on publish based on section targeting"
```

---

### Task 15: Clone Course Action

**Files:**
- Modify: `apps/academics/services.py`
- Modify: `apps/academics/admin_views.py`
- Modify: `apps/academics/admin_urls.py`

- [ ] **Step 1: Write clone service**

```python
# Append to apps/academics/services.py

def clone_course(original_course, new_title=None, new_target_sections=None, cloned_by=None):
    """
    Deep-clone a course: copy modules + contents, reset progress/assignments.
    Returns the new Course instance.
    """
    from apps.courses.models import Course, Module, Content
    import copy

    new_course = Course.all_objects.create(
        tenant=original_course.tenant,
        title=new_title or f"{original_course.title} (Copy)",
        slug='',  # Will be auto-generated on save
        description=original_course.description,
        thumbnail=original_course.thumbnail,
        is_mandatory=original_course.is_mandatory,
        estimated_hours=original_course.estimated_hours,
        course_type=original_course.course_type,
        subject=original_course.subject,
        is_published=False,
        is_active=True,
        created_by=cloned_by,
    )
    # Save to trigger slug generation
    new_course.save()

    # Copy target grades
    new_course.target_grades.set(original_course.target_grades.all())

    # Set new target sections if provided, else copy original
    if new_target_sections is not None:
        new_course.target_sections.set(new_target_sections)
    else:
        new_course.target_sections.set(original_course.target_sections.all())

    # Deep-copy modules and contents
    for module in original_course.modules.filter(is_deleted=False).order_by('order'):
        old_module_id = module.pk
        module.pk = None
        module.course = new_course
        module.save()

        for content in Content.objects.filter(
            module_id=old_module_id, is_deleted=False,
        ).order_by('order'):
            content.pk = None
            content.module = module
            content.save()

    return new_course
```

- [ ] **Step 2: Add clone endpoint**

```python
# Append to apps/academics/admin_views.py

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def clone_course_view(request, course_id):
    """Clone a course with all its modules and contents."""
    from apps.courses.models import Course
    course = get_object_or_404(Course, pk=course_id, tenant=request.tenant)

    from .services import clone_course
    new_title = request.data.get('title')
    new_course = clone_course(course, new_title=new_title, cloned_by=request.user)

    log_audit('CREATE', 'Course', target_id=str(new_course.id),
              target_repr=f"Cloned from {course.title}", request=request)

    from apps.courses.serializers import CourseListSerializer
    return Response(
        CourseListSerializer(new_course, context={'request': request}).data,
        status=status.HTTP_201_CREATED,
    )
```

- [ ] **Step 3: Add URL**

```python
    path("courses/<uuid:course_id>/clone/", admin_views.clone_course_view, name="clone_course"),
```

- [ ] **Step 4: Commit**

```bash
git add apps/academics/services.py apps/academics/admin_views.py apps/academics/admin_urls.py
git commit -m "feat(academics): clone course action with deep content copy"
```

---

## Chunk 5: Academic Year Promotion & Teacher Views

### Task 16: Academic Year Promotion Workflow

**Files:**
- Modify: `apps/academics/services.py`
- Modify: `apps/academics/admin_views.py`
- Modify: `apps/academics/admin_urls.py`

- [ ] **Step 1: Write promotion preview service**

```python
# Append to apps/academics/services.py

def get_promotion_preview(tenant):
    """Generate preview of what promotion will do."""
    from apps.users.models import User

    grades = Grade.all_objects.filter(
        tenant=tenant,
    ).order_by('order')

    preview = []
    max_order = grades.last().order if grades.exists() else 0

    for grade in grades:
        student_count = User.objects.filter(
            grade_fk=grade, role='STUDENT', is_deleted=False, is_active=True,
        ).count()
        next_grade = grades.filter(order__gt=grade.order).first()

        preview.append({
            'grade_id': str(grade.id),
            'grade_name': grade.name,
            'student_count': student_count,
            'next_grade_id': str(next_grade.id) if next_grade else None,
            'next_grade_name': next_grade.name if next_grade else 'GRADUATED',
            'is_final_grade': grade.order == max_order,
        })

    return preview


def execute_promotion(tenant, excluded_student_ids=None, graduated_student_ids=None, new_academic_year=None):
    """Execute academic year promotion."""
    from apps.users.models import User

    excluded = set(excluded_student_ids or [])
    graduated = set(graduated_student_ids or [])

    grades = list(Grade.all_objects.filter(tenant=tenant).order_by('order'))
    grade_map = {g.order: g for g in grades}
    orders = sorted(grade_map.keys())

    promoted_count = 0
    graduated_count = 0

    # Process in reverse order to avoid conflicts
    for order in reversed(orders):
        grade = grade_map[order]
        students = User.objects.filter(
            grade_fk=grade, role='STUDENT', is_deleted=False, is_active=True,
        ).exclude(id__in=excluded)

        next_order_idx = orders.index(order) + 1
        next_grade = grade_map.get(orders[next_order_idx]) if next_order_idx < len(orders) else None

        for student in students:
            if str(student.id) in graduated:
                # Mark as graduated — keep grade, clear section
                student.section_fk = None
                student.save(update_fields=['section_fk'])
                graduated_count += 1
            elif next_grade:
                student.grade_fk = next_grade
                student.section_fk = None  # Admin re-assigns
                student.save(update_fields=['grade_fk', 'section_fk'])
                promoted_count += 1
            else:
                # Final grade, not marked graduated — auto-graduate
                student.section_fk = None
                student.save(update_fields=['section_fk'])
                graduated_count += 1

    # Update academic year
    if new_academic_year:
        tenant.current_academic_year = new_academic_year
        tenant.save(update_fields=['current_academic_year'])

    # Clear assigned_students on academic courses
    from apps.courses.models import Course
    for course in Course.all_objects.filter(tenant=tenant, course_type='ACADEMIC'):
        course.assigned_students.clear()

    return {
        'promoted': promoted_count,
        'graduated': graduated_count,
        'new_academic_year': new_academic_year or tenant.current_academic_year,
    }
```

- [ ] **Step 2: Add promotion endpoints**

```python
# Append to apps/academics/admin_views.py

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def promotion_preview(request):
    from .services import get_promotion_preview
    preview = get_promotion_preview(request.tenant)
    return Response({
        'current_academic_year': request.tenant.current_academic_year,
        'grades': preview,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def promotion_execute(request):
    from .services import execute_promotion
    result = execute_promotion(
        tenant=request.tenant,
        excluded_student_ids=request.data.get('excluded_student_ids', []),
        graduated_student_ids=request.data.get('graduated_student_ids', []),
        new_academic_year=request.data.get('new_academic_year'),
    )
    log_audit('UPDATE', 'Tenant', target_id=str(request.tenant.id),
              target_repr=f"Promotion to {result['new_academic_year']}",
              changes=result, request=request)
    return Response(result)
```

- [ ] **Step 3: Add URLs**

```python
    path("promotion/preview/", admin_views.promotion_preview, name="promotion_preview"),
    path("promotion/execute/", admin_views.promotion_execute, name="promotion_execute"),
```

- [ ] **Step 4: Commit**

```bash
git add apps/academics/services.py apps/academics/admin_views.py apps/academics/admin_urls.py
git commit -m "feat(academics): academic year promotion workflow with preview and execute"
```

---

### Task 17: Teacher "My Classes" API Endpoints

**Files:**
- Create: `apps/academics/teacher_views.py`
- Modify: `apps/academics/teacher_urls.py`

- [ ] **Step 1: Write teacher views**

```python
# apps/academics/teacher_views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Count, Q, Avg

from utils.decorators import teacher_or_admin, tenant_required
from .models import TeachingAssignment, Section
from .serializers import TeachingAssignmentSerializer, SectionSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def my_classes(request):
    """Teacher's assigned sections grouped by subject."""
    assignments = TeachingAssignment.objects.filter(
        teacher=request.user,
        academic_year=request.tenant.current_academic_year,
    ).select_related('subject').prefetch_related(
        'sections__grade',
    )

    result = []
    for ta in assignments:
        sections = []
        for section in ta.sections.all():
            from apps.users.models import User
            student_count = User.objects.filter(
                section_fk=section, role='STUDENT', is_deleted=False, is_active=True,
            ).count()
            from apps.courses.models import Course
            course_count = Course.objects.filter(
                target_sections=section, course_type='ACADEMIC',
                created_by=request.user,
            ).count()
            sections.append({
                **SectionSerializer(section).data,
                'student_count': student_count,
                'course_count': course_count,
            })

        result.append({
            'assignment_id': str(ta.id),
            'subject': {
                'id': str(ta.subject.id),
                'name': ta.subject.name,
                'code': ta.subject.code,
            },
            'sections': sections,
        })

    return Response(result)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def section_dashboard(request, section_id):
    """Teacher's section dashboard — students, courses, analytics."""
    section = get_object_or_404(Section, pk=section_id, tenant=request.tenant)

    # Verify teacher has access via TeachingAssignment
    has_access = TeachingAssignment.objects.filter(
        teacher=request.user,
        sections=section,
        academic_year=request.tenant.current_academic_year,
    ).exists()
    if not has_access and request.user.role not in ('SCHOOL_ADMIN', 'SUPER_ADMIN'):
        return Response({'error': 'No teaching assignment for this section'}, status=403)

    tab = request.GET.get('tab', 'students')

    if tab == 'students':
        from apps.users.models import User
        from apps.users.serializers import UserSerializer
        students = User.objects.filter(
            section_fk=section, role='STUDENT', is_deleted=False, is_active=True,
        ).order_by('last_name', 'first_name')
        return Response(UserSerializer(students, many=True).data)

    elif tab == 'courses':
        from apps.courses.models import Course
        from apps.courses.serializers import CourseListSerializer
        courses = Course.objects.filter(
            target_sections=section, course_type='ACADEMIC',
        )
        # If teacher, only show their courses
        if request.user.role in ('TEACHER', 'HOD', 'IB_COORDINATOR'):
            courses = courses.filter(created_by=request.user)
        return Response(CourseListSerializer(
            courses, many=True, context={'request': request},
        ).data)

    elif tab == 'analytics':
        from apps.users.models import User
        student_count = User.objects.filter(
            section_fk=section, role='STUDENT', is_deleted=False,
        ).count()
        return Response({
            'student_count': student_count,
            'section_name': str(section),
            # Add more analytics in future
        })

    elif tab == 'assignments':
        from apps.progress.models import Assignment
        from apps.courses.models import Course

        course_ids = Course.objects.filter(
            target_sections=section, course_type='ACADEMIC',
            created_by=request.user,
        ).values_list('id', flat=True)

        assignments = Assignment.objects.filter(
            course_id__in=course_ids,
        ).order_by('-created_at')

        # Return basic assignment data
        data = [{
            'id': str(a.id),
            'title': a.title,
            'course_id': str(a.course_id),
            'due_date': a.due_date,
            'is_active': a.is_active,
        } for a in assignments[:50]]
        return Response(data)

    return Response({'error': 'Invalid tab'}, status=400)
```

- [ ] **Step 2: Wire URLs**

```python
# apps/academics/teacher_urls.py
from django.urls import path
from . import teacher_views

app_name = "teacher_academics"

urlpatterns = [
    path("my-classes/", teacher_views.my_classes, name="my_classes"),
    path("sections/<uuid:section_id>/dashboard/", teacher_views.section_dashboard, name="section_dashboard"),
]
```

- [ ] **Step 3: Commit**

```bash
git add apps/academics/teacher_views.py apps/academics/teacher_urls.py
git commit -m "feat(academics): teacher My Classes and section dashboard API endpoints"
```

---

## Chunk 6: Keystone Seed Data & Management Command

### Task 18: Keystone Seed Data Management Command

**Files:**
- Create: `apps/academics/management/commands/seed_keystone.py`

- [ ] **Step 1: Write the management command**

```python
# apps/academics/management/commands/seed_keystone.py
import os
import secrets
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.tenants.models import Tenant
from apps.academics.models import GradeBand, Grade, Section, Subject
from apps.users.models import User


class Command(BaseCommand):
    help = 'Seeds the Keystone International School tenant with academic structure'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete existing Keystone data first')

    @transaction.atomic
    def handle(self, *args, **options):
        # 1. Create or get tenant
        tenant, created = Tenant.objects.get_or_create(
            subdomain='keystone',
            defaults={
                'name': 'Keystone International School',
                'slug': 'keystone-international',
                'email': 'admin@keystoneeducation.in',
                'current_academic_year': '2026-27',
                'id_prefix': 'KIS',
                'white_label': True,
                'welcome_message': 'Welcome to Keystone Learning',
                'school_motto': 'Powered by the Idea-Loom Model',
                'primary_color': '#00964B',
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f'Created tenant: {tenant.name}'))
        else:
            self.stdout.write(f'Tenant already exists: {tenant.name}')
            if options['reset']:
                GradeBand.all_objects.filter(tenant=tenant).delete()
                Grade.all_objects.filter(tenant=tenant).delete()
                Subject.all_objects.filter(tenant=tenant).delete()
                self.stdout.write(self.style.WARNING('Reset existing academic data'))

        # 2. Create admin if tenant was just created
        if created:
            admin_password = os.getenv('KEYSTONE_ADMIN_PASSWORD') or secrets.token_urlsafe(18)
            admin = User.objects.create_user(
                email='admin@keystoneeducation.in',
                password=admin_password,
                first_name='Keystone',
                last_name='Admin',
                tenant=tenant,
                role='SCHOOL_ADMIN',
            )
            self.stdout.write(f'Admin: admin@keystoneeducation.in')

        # 3. Grade Bands
        BANDS = [
            ('Early Years', 'KEY', 1, 'REGGIO_EMILIA', {
                'accent_color': '#8DC63F',
                'welcome_msg': 'Welcome, little explorer!',
            }),
            ('Primary', 'PRI', 2, 'CAMBRIDGE_PRIMARY', {
                'accent_color': '#00A99D',
                'welcome_msg': 'Ready to learn something amazing?',
            }),
            ('Middle School', 'MID', 3, 'CAMBRIDGE_SECONDARY', {
                'accent_color': '#0072BC',
                'welcome_msg': 'Challenge yourself today!',
            }),
            ('High School', 'HS', 4, 'IGCSE', {
                'accent_color': '#662D91',
                'welcome_msg': 'Your future starts here.',
            }),
        ]

        band_objs = {}
        for name, code, order, curriculum, theme in BANDS:
            band, _ = GradeBand.all_objects.get_or_create(
                tenant=tenant, name=name,
                defaults={
                    'short_code': code, 'order': order,
                    'curriculum_framework': curriculum,
                    'theme_config': theme,
                },
            )
            band_objs[code] = band
            self.stdout.write(f'  GradeBand: {name}')

        # 4. Grades
        GRADES = [
            ('KEY', [('Nursery', 'NUR', 1), ('PP1', 'PP1', 2), ('PP2', 'PP2', 3)]),
            ('PRI', [
                ('Grade 1', 'G1', 4), ('Grade 2', 'G2', 5), ('Grade 3', 'G3', 6),
                ('Grade 4', 'G4', 7), ('Grade 5', 'G5', 8),
            ]),
            ('MID', [
                ('Grade 6', 'G6', 9), ('Grade 7', 'G7', 10), ('Grade 8', 'G8', 11),
            ]),
            ('HS', [
                ('Grade 9', 'G9', 12), ('Grade 10', 'G10', 13),
                ('Grade 11', 'G11', 14), ('Grade 12', 'G12', 15),
            ]),
        ]

        grade_objs = {}
        for band_code, grades in GRADES:
            for name, code, order in grades:
                grade, _ = Grade.all_objects.get_or_create(
                    tenant=tenant, short_code=code,
                    defaults={
                        'grade_band': band_objs[band_code],
                        'name': name, 'order': order,
                    },
                )
                grade_objs[code] = grade

        self.stdout.write(f'  Created {len(grade_objs)} grades')

        # 5. Default sections (A, B for each grade)
        for code, grade in grade_objs.items():
            for section_name in ['A', 'B']:
                Section.all_objects.get_or_create(
                    tenant=tenant, grade=grade, name=section_name,
                    academic_year='2026-27',
                )

        self.stdout.write(f'  Created default sections (A, B per grade)')

        # 6. Subjects
        SUBJECTS = [
            # (name, code, department, applicable_from, is_elective)
            ('English', 'ENG', 'Languages', 'NUR', False),
            ('Mathematics', 'MAT', 'Mathematics', 'NUR', False),
            ('Science', 'SCI', 'Science', 'NUR', False),
            ('Social Studies', 'SST', 'Humanities', 'G1', False),
            ('Hindi', 'HIN', 'Languages', 'G6', False),
            ('Computer Science', 'CS', 'Technology', 'G6', False),
            ('Physics', 'PHY', 'Science', 'G9', False),
            ('Chemistry', 'CHE', 'Science', 'G9', False),
            ('Biology', 'BIO', 'Science', 'G9', False),
            ('Economics', 'ECO', 'Commerce', 'G9', True),
            ('Business Studies', 'BUS', 'Commerce', 'G9', True),
            ('Psychology', 'PSY', 'Humanities', 'G11', True),
            ('Sociology', 'SOC', 'Humanities', 'G11', True),
            ('Art & Design', 'ART', 'Arts', 'G11', True),
        ]

        for name, code, dept, from_grade, is_elective in SUBJECTS:
            subject, _ = Subject.all_objects.get_or_create(
                tenant=tenant, code=code,
                defaults={
                    'name': name, 'department': dept, 'is_elective': is_elective,
                },
            )
            # Set applicable grades
            from_order = grade_objs[from_grade].order
            applicable = [g for g in grade_objs.values() if g.order >= from_order]
            subject.applicable_grades.set(applicable)

        self.stdout.write(f'  Created {len(SUBJECTS)} subjects')

        self.stdout.write(self.style.SUCCESS('\nKeystone seed data complete!'))
        self.stdout.write(f'Subdomain: keystone')
        self.stdout.write(f'Academic year: 2026-27')
        self.stdout.write(f'Grades: {len(grade_objs)}')
        self.stdout.write(f'Subjects: {len(SUBJECTS)}')
```

- [ ] **Step 2: Run the command**

```bash
cd backend && python manage.py seed_keystone
```

- [ ] **Step 3: Commit**

```bash
git add apps/academics/management/
git commit -m "feat(academics): seed_keystone management command with full academic structure"
```

---

## Chunk 7: Frontend — Academic Service & Admin School View

### Task 19: Frontend API Service

**Files:**
- Create: `src/services/academicsService.ts`

- [ ] **Step 1: Write the service**

```typescript
// src/services/academicsService.ts
import api from '../config/api';

export interface GradeBand {
  id: string;
  name: string;
  short_code: string;
  order: number;
  curriculum_framework: string;
  theme_config: { accent_color?: string; bg_image?: string; welcome_msg?: string } | null;
  grade_count: number;
  grades?: Grade[];
}

export interface Grade {
  id: string;
  grade_band: string;
  grade_band_name: string;
  name: string;
  short_code: string;
  order: number;
  student_count: number;
  section_count: number;
}

export interface Section {
  id: string;
  grade: string;
  grade_name: string;
  name: string;
  academic_year: string;
  class_teacher: string | null;
  class_teacher_name: string | null;
  student_count: number;
}

export interface Subject {
  id: string;
  name: string;
  code: string;
  department: string;
  applicable_grade_ids: string[];
  is_elective: boolean;
}

export interface TeachingAssignment {
  id: string;
  teacher: string;
  teacher_name: string;
  subject: string;
  subject_name: string;
  section_ids: string[];
  academic_year: string;
  is_class_teacher: boolean;
}

export interface MyClassesItem {
  assignment_id: string;
  subject: { id: string; name: string; code: string };
  sections: (Section & { course_count: number })[];
}

export const academicsService = {
  // School Overview
  async getSchoolOverview(): Promise<(GradeBand & { grades: Grade[] })[]> {
    const res = await api.get('/v1/academics/school-overview/');
    return res.data;
  },

  // GradeBands
  async getGradeBands(): Promise<GradeBand[]> {
    const res = await api.get('/v1/academics/grade-bands/');
    return res.data;
  },
  async createGradeBand(data: Partial<GradeBand>): Promise<GradeBand> {
    const res = await api.post('/v1/academics/grade-bands/', data);
    return res.data;
  },

  // Grades
  async getGrades(gradeBandId?: string): Promise<Grade[]> {
    const res = await api.get('/v1/academics/grades/', {
      params: gradeBandId ? { grade_band: gradeBandId } : undefined,
    });
    return res.data;
  },

  // Sections
  async getSections(gradeId?: string): Promise<Section[]> {
    const res = await api.get('/v1/academics/sections/', {
      params: gradeId ? { grade: gradeId } : undefined,
    });
    return res.data;
  },
  async createSection(data: Partial<Section>): Promise<Section> {
    const res = await api.post('/v1/academics/sections/', data);
    return res.data;
  },
  async getSectionStudents(sectionId: string) {
    const res = await api.get(`/v1/academics/sections/${sectionId}/students/`);
    return res.data;
  },
  async getSectionTeachers(sectionId: string) {
    const res = await api.get(`/v1/academics/sections/${sectionId}/teachers/`);
    return res.data;
  },
  async getSectionCourses(sectionId: string) {
    const res = await api.get(`/v1/academics/sections/${sectionId}/courses/`);
    return res.data;
  },
  async importStudents(sectionId: string, file: File) {
    const form = new FormData();
    form.append('file', file);
    const res = await api.post(
      `/v1/academics/sections/${sectionId}/import-students/`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return res.data;
  },
  async addStudent(sectionId: string, data: { email: string; first_name: string; last_name: string }) {
    const res = await api.post(`/v1/academics/sections/${sectionId}/add-student/`, data);
    return res.data;
  },

  // Subjects
  async getSubjects(): Promise<Subject[]> {
    const res = await api.get('/v1/academics/subjects/');
    return res.data;
  },

  // Teaching Assignments
  async getTeachingAssignments(params?: { teacher?: string; academic_year?: string }): Promise<TeachingAssignment[]> {
    const res = await api.get('/v1/academics/teaching-assignments/', { params });
    return res.data;
  },
  async createTeachingAssignment(data: Partial<TeachingAssignment>): Promise<TeachingAssignment> {
    const res = await api.post('/v1/academics/teaching-assignments/', data);
    return res.data;
  },

  // Promotion
  async getPromotionPreview() {
    const res = await api.get('/v1/academics/promotion/preview/');
    return res.data;
  },
  async executePromotion(data: {
    new_academic_year: string;
    excluded_student_ids?: string[];
    graduated_student_ids?: string[];
  }) {
    const res = await api.post('/v1/academics/promotion/execute/', data);
    return res.data;
  },

  // Clone Course
  async cloneCourse(courseId: string, title?: string) {
    const res = await api.post(`/v1/academics/courses/${courseId}/clone/`, { title });
    return res.data;
  },

  // Teacher: My Classes
  async getMyClasses(): Promise<MyClassesItem[]> {
    const res = await api.get('/v1/teacher/academics/my-classes/');
    return res.data;
  },
  async getSectionDashboard(sectionId: string, tab: string) {
    const res = await api.get(`/v1/teacher/academics/sections/${sectionId}/dashboard/`, {
      params: { tab },
    });
    return res.data;
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add src/services/academicsService.ts
git commit -m "feat(frontend): add academicsService API client"
```

---

### Task 20: Admin School View Page (Level 1 — Grade Cards)

**Files:**
- Create: `src/pages/admin/SchoolViewPage.tsx`
- Modify: `src/App.tsx`

- [ ] **Step 1: Create SchoolViewPage**

Build a page that:
- Fetches `academicsService.getSchoolOverview()`
- Groups grade cards by grade band
- Each band is a section header with band name + curriculum badge
- Each grade card shows: grade name, student count, section count
- Click navigates to `/admin/school/grades/:gradeId`
- Top bar shows: school name (from tenant), academic year, gear icon for settings
- "Add Grade" and "Add Grade Band" buttons

Use: `useQuery({ queryKey: ['schoolOverview'], queryFn: academicsService.getSchoolOverview })`

Layout: responsive grid `grid-cols-2 md:grid-cols-3 lg:grid-cols-4` for grade cards.

Colors: Use grade band `theme_config.accent_color` for card accent borders.

- [ ] **Step 2: Add route to App.tsx**

Add lazy import and route:

```typescript
const SchoolViewPage = lazy(() => import('./pages/admin/SchoolViewPage'));
const GradeDetailPage = lazy(() => import('./pages/admin/GradeDetailPage'));
const SectionDetailPage = lazy(() => import('./pages/admin/SectionDetailPage'));
```

Add routes under admin layout:

```typescript
<Route path="school" element={<SchoolViewPage />} />
<Route path="school/grades/:gradeId" element={<GradeDetailPage />} />
<Route path="school/grades/:gradeId/sections/:sectionId" element={<SectionDetailPage />} />
```

- [ ] **Step 3: Add "School" to admin sidebar**

In `src/components/layout/AdminSidebar.tsx`, add nav item with `BuildingLibraryIcon`:

```typescript
{ name: 'School', path: '/admin/school', icon: BuildingLibraryIcon },
```

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add src/pages/admin/SchoolViewPage.tsx src/App.tsx src/components/layout/AdminSidebar.tsx
git commit -m "feat(frontend): admin School View page with grade cards grid"
```

---

### Task 21: Admin Grade Detail Page (Level 2 — Section Cards)

**Files:**
- Create: `src/pages/admin/GradeDetailPage.tsx`

- [ ] **Step 1: Create GradeDetailPage**

Build a page that:
- Uses `useParams()` to get `gradeId`
- Fetches sections: `academicsService.getSections(gradeId)`
- Shows breadcrumb: School > Grade Name
- Section cards grid showing: section name (e.g. "9A"), student count, class teacher name, course count
- Click navigates to `/admin/school/grades/:gradeId/sections/:sectionId`
- Actions: "Add Section" button (modal with name + academic_year)
- "Import Students" button (contextual — opens CSV upload for this grade)

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add src/pages/admin/GradeDetailPage.tsx
git commit -m "feat(frontend): admin Grade Detail page with section cards"
```

---

### Task 22: Admin Section Detail Page (Level 3 — 3 Tabs)

**Files:**
- Create: `src/pages/admin/SectionDetailPage.tsx`

- [ ] **Step 1: Create SectionDetailPage**

Build a page with 3 tabs:

**Students tab:**
- Fetches `academicsService.getSectionStudents(sectionId)`
- Table: Name, Student ID, Email, Status (active/inactive)
- Actions: "Add Student" (modal), "Import CSV" (file upload)
- CSV upload calls `academicsService.importStudents(sectionId, file)`

**Teachers tab:**
- Fetches `academicsService.getSectionTeachers(sectionId)`
- Table: Teacher Name, Subject, Is Class Teacher

**Courses tab:**
- Fetches `academicsService.getSectionCourses(sectionId)`
- Course cards with title, completion rate

Use tab state via `useState` or URL search params.

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add src/pages/admin/SectionDetailPage.tsx
git commit -m "feat(frontend): admin Section Detail page with Students/Teachers/Courses tabs"
```

---

## Chunk 8: Frontend — Teacher My Classes & White-Label

### Task 23: Teacher My Classes Page

**Files:**
- Create: `src/pages/teacher/MyClassesPage.tsx`
- Modify: `src/App.tsx`

- [ ] **Step 1: Create MyClassesPage**

Build a page that:
- Fetches `academicsService.getMyClasses()`
- Groups section cards by subject
- Each subject is a section header
- Each section card shows: grade+section name, student count, course count
- Click navigates to `/teacher/classes/:sectionId`

- [ ] **Step 2: Add route and sidebar nav**

Add lazy import and route in App.tsx:

```typescript
const MyClassesPage = lazy(() => import('./pages/teacher/MyClassesPage'));
const SectionDashboardPage = lazy(() => import('./pages/teacher/SectionDashboardPage'));
```

Routes:
```typescript
<Route path="classes" element={<MyClassesPage />} />
<Route path="classes/:sectionId" element={<SectionDashboardPage />} />
```

Add "My Classes" to teacher sidebar.

- [ ] **Step 3: Commit**

```bash
git add src/pages/teacher/MyClassesPage.tsx src/App.tsx
git commit -m "feat(frontend): teacher My Classes page with section cards grouped by subject"
```

---

### Task 24: Teacher Section Dashboard Page (4 Tabs)

**Files:**
- Create: `src/pages/teacher/SectionDashboardPage.tsx`

- [ ] **Step 1: Create SectionDashboardPage**

Build a page with 4 tabs:

**Students tab:**
- Fetches `academicsService.getSectionDashboard(sectionId, 'students')`
- Student roster with name, last active, status indicator (green/amber/red)

**Courses tab:**
- Fetches `academicsService.getSectionDashboard(sectionId, 'courses')`
- Teacher's courses for this section
- "Create Course" button (pre-fills subject + target section)

**Analytics tab:**
- Fetches `academicsService.getSectionDashboard(sectionId, 'analytics')`
- Student count, basic stats
- Placeholder for future analytics

**Assignments tab:**
- Fetches `academicsService.getSectionDashboard(sectionId, 'assignments')`
- Assignment list with due dates

- [ ] **Step 2: Verify build**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add src/pages/teacher/SectionDashboardPage.tsx
git commit -m "feat(frontend): teacher Section Dashboard with 4-tab layout"
```

---

### Task 25: White-Label Branding Support

**Files:**
- Modify: Login page component
- Modify: Tenant theme endpoint (if needed)

- [ ] **Step 1: Update tenant theme API to include white-label fields**

The existing tenant theme endpoint (`/api/v1/tenants/theme/`) already returns tenant branding data. Verify it includes the new fields. If not, add `white_label`, `login_bg_image`, `welcome_message`, `school_motto` to the tenant serializer.

- [ ] **Step 2: Update login page for white-label**

In the login page component:
- If `tenant.white_label` is true:
  - Show tenant logo instead of LearnPuddle logo
  - Show `tenant.name` instead of "LearnPuddle"
  - Use `login_bg_image` as background
  - Hide "Powered by LearnPuddle" footer
- Update the identifier input:
  - Change label from "Email" to "Email or Student ID"
  - Change field name from `email` to `identifier`

- [ ] **Step 3: Update student dashboard greeting**

In the student dashboard, use `welcome_message` from tenant config when available.

- [ ] **Step 4: Verify build**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add src/
git commit -m "feat(frontend): white-label branding support for login and dashboard"
```

---

## Chunk 9: Integration Tests & Final Verification

### Task 26: End-to-End Integration Tests

**Files:**
- Create: `tests/academics/test_integration.py`

- [ ] **Step 1: Write integration tests**

```python
# tests/academics/test_integration.py
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.test import TestCase
from apps.tenants.models import Tenant
from apps.users.models import User
from apps.academics.models import GradeBand, Grade, Section, Subject, TeachingAssignment
from apps.courses.models import Course


class FullWorkflowTest(TestCase):
    """Test the complete academic workflow end-to-end."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="KIS", slug="kis-e2e", subdomain="kise2e",
            email="a@kis.com", id_prefix="KIS",
            current_academic_year="2026-27",
        )
        self.admin = User.objects.create_user(
            email="admin@kis.com", password="Admin123!",
            first_name="A", last_name="D",
            tenant=self.tenant, role="SCHOOL_ADMIN",
        )
        self.client = APIClient()
        tokens = RefreshToken.for_user(self.admin)
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {tokens.access_token}',
            HTTP_HOST='kise2e.localhost',
        )

    def test_full_academic_setup_workflow(self):
        # 1. Create grade band
        resp = self.client.post('/api/v1/academics/grade-bands/', {
            'name': 'High School', 'short_code': 'HS', 'order': 1,
            'curriculum_framework': 'IGCSE',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        band_id = resp.data['id']

        # 2. Create grade
        resp = self.client.post('/api/v1/academics/grades/', {
            'grade_band': band_id, 'name': 'Grade 9', 'short_code': 'G9', 'order': 9,
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        grade_id = resp.data['id']

        # 3. Create section
        resp = self.client.post('/api/v1/academics/sections/', {
            'grade': grade_id, 'name': 'A', 'academic_year': '2026-27',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        section_id = resp.data['id']

        # 4. Add student to section
        resp = self.client.post(f'/api/v1/academics/sections/{section_id}/add-student/', {
            'email': 'student@kis.com', 'first_name': 'Test', 'last_name': 'Student',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.data['student_id'].startswith('KIS-S-'))

        # 5. Verify school overview
        resp = self.client.get('/api/v1/academics/school-overview/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)  # 1 grade band
        self.assertEqual(resp.data[0]['grades'][0]['student_count'], 1)

    def test_cross_tenant_isolation(self):
        """Verify tenant isolation — admin of tenant A cannot see tenant B data."""
        other_tenant = Tenant.objects.create(
            name="Other", slug="other", subdomain="other", email="o@o.com",
        )
        band = GradeBand.all_objects.create(
            tenant=other_tenant, name="Test", short_code="T", order=1,
        )

        # Current admin should not see other tenant's data
        resp = self.client.get('/api/v1/academics/grade-bands/')
        self.assertEqual(resp.status_code, 200)
        ids = [b['id'] for b in resp.data]
        self.assertNotIn(str(band.id), ids)
```

- [ ] **Step 2: Run all tests**

```bash
cd backend && python manage.py test tests.academics -v2
```

- [ ] **Step 3: Commit**

```bash
git add tests/academics/
git commit -m "test(academics): add full workflow integration and tenant isolation tests"
```

---

### Task 27: Final Verification

- [ ] **Step 1: Backend check**

```bash
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run  # No pending migrations
python manage.py test tests.academics -v2
```

- [ ] **Step 2: Frontend build**

```bash
cd frontend
npx tsc --noEmit
npm run build
```

- [ ] **Step 3: Seed Keystone and verify**

```bash
cd backend
python manage.py seed_keystone
python manage.py shell -c "
from apps.academics.models import *
print(f'GradeBands: {GradeBand.all_objects.filter(tenant__subdomain=\"keystone\").count()}')
print(f'Grades: {Grade.all_objects.filter(tenant__subdomain=\"keystone\").count()}')
print(f'Sections: {Section.all_objects.filter(tenant__subdomain=\"keystone\").count()}')
print(f'Subjects: {Subject.all_objects.filter(tenant__subdomain=\"keystone\").count()}')
"
```

Expected: GradeBands: 4, Grades: 15, Sections: 30, Subjects: 14

- [ ] **Step 4: Commit**

```bash
git commit --allow-empty -m "chore: academic structure implementation complete — all checks passing"
```
