# conftest.py
"""
Shared pytest fixtures for the LearnPuddle LMS backend test suite.

Provides reusable fixtures for:
- Tenant and user creation
- API client setup with correct Host headers
- Common course/module/content hierarchies
- Test data helpers

Usage example:
    def test_my_view(api_client_for, tenant, admin_user):
        client = api_client_for(admin_user, tenant)
        response = client.get('/api/v1/courses/', HTTP_HOST=f'{tenant.subdomain}.lms.com')
        assert response.status_code == 200
"""

import pytest
from rest_framework.test import APIClient

# ---------------------------------------------------------------------------
# Tenant fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tenant(db):
    """A single active tenant with subdomain='test' for use in tests."""
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name="Test School",
        slug="test-school-fixture",
        subdomain="test",
        email="fixture@testschool.com",
        is_active=True,
    )


@pytest.fixture
def tenant_b(db):
    """A second active tenant (for cross-tenant isolation tests)."""
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name="Other School",
        slug="other-school-fixture",
        subdomain="other",
        email="fixture@otherschool.com",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def admin_user(db, tenant):
    """A SCHOOL_ADMIN user belonging to the primary test tenant."""
    from apps.users.models import User
    return User.objects.create_user(
        email="admin@testschool.com",
        password="AdminPass!123",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


@pytest.fixture
def teacher_user(db, tenant):
    """A TEACHER user belonging to the primary test tenant."""
    from apps.users.models import User
    return User.objects.create_user(
        email="teacher@testschool.com",
        password="TeacherPass!123",
        first_name="Teacher",
        last_name="User",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def admin_user_b(db, tenant_b):
    """A SCHOOL_ADMIN user belonging to the secondary test tenant."""
    from apps.users.models import User
    return User.objects.create_user(
        email="admin@otherschool.com",
        password="AdminPass!123",
        first_name="Admin",
        last_name="B",
        tenant=tenant_b,
        role="SCHOOL_ADMIN",
        is_active=True,
    )


@pytest.fixture
def super_admin_user(db, tenant):
    """A SUPER_ADMIN user (platform-wide access)."""
    from apps.users.models import User
    return User.objects.create_user(
        email="superadmin@learnpuddle.com",
        password="SuperAdmin!123",
        first_name="Super",
        last_name="Admin",
        tenant=tenant,
        role="SUPER_ADMIN",
        is_active=True,
    )


# ---------------------------------------------------------------------------
# API client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def api_client():
    """Unauthenticated DRF APIClient."""
    return APIClient()


@pytest.fixture
def admin_client(admin_user, tenant):
    """
    DRF APIClient pre-authenticated as the admin_user.
    Sets the Host header to the tenant's subdomain automatically.
    """
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


@pytest.fixture
def teacher_client(teacher_user, tenant):
    """
    DRF APIClient pre-authenticated as the teacher_user.
    """
    client = APIClient()
    client.force_authenticate(user=teacher_user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


@pytest.fixture
def api_client_for():
    """
    Factory fixture: creates an authenticated APIClient for any user/tenant pair.

    Usage:
        def test_something(api_client_for, user, tenant):
            client = api_client_for(user, tenant)
            response = client.get('/api/v1/courses/')
    """
    def _make(user, tenant):
        client = APIClient()
        client.force_authenticate(user=user)
        client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
        return client
    return _make


# ---------------------------------------------------------------------------
# Course fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def course(db, tenant, admin_user):
    """A published course belonging to the primary tenant."""
    from apps.courses.models import Course
    return Course.objects.create(
        tenant=tenant,
        title="Fixture Course",
        slug="fixture-course",
        description="Created by conftest.py fixture",
        created_by=admin_user,
        is_published=True,
        is_active=True,
    )


@pytest.fixture
def module(db, course):
    """A module inside the fixture course."""
    from apps.courses.models import Module
    return Module.objects.create(
        course=course,
        title="Fixture Module",
        description="Module from fixture",
        order=1,
        is_active=True,
    )


@pytest.fixture
def text_content(db, module):
    """A TEXT content item inside the fixture module."""
    from apps.courses.models import Content
    return Content.objects.create(
        module=module,
        title="Fixture Text Content",
        content_type="TEXT",
        order=1,
        text_content="<p>Hello from fixture</p>",
        is_mandatory=True,
        is_active=True,
    )


@pytest.fixture
def video_content(db, module):
    """A VIDEO content item inside the fixture module (no actual file)."""
    from apps.courses.models import Content
    return Content.objects.create(
        module=module,
        title="Fixture Video Content",
        content_type="VIDEO",
        order=2,
        file_url="",
        file_size=0,
        duration=600,
        text_content="",
        is_mandatory=True,
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Override settings helper
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def override_allowed_hosts(settings):
    """
    Ensure the test suite can use lms.com subdomains without needing
    ALLOWED_HOSTS to be explicitly set per-test.
    """
    settings.ALLOWED_HOSTS = ["*"]
    settings.PLATFORM_DOMAIN = "lms.com"


# ---------------------------------------------------------------------------
# Tenant context cleanup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_tenant_context():
    """
    Ensure the contextvars tenant is cleared before and after every test,
    preventing stale state from leaking between test functions.
    """
    from utils.tenant_middleware import clear_current_tenant
    clear_current_tenant()
    yield
    clear_current_tenant()
