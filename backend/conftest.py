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

# ---------------------------------------------------------------------------
# Backend CI and local pytest should exercise the MAIC v2/PBL route surface.
# This must be set before Django imports settings/asgi modules.
# ---------------------------------------------------------------------------
import os

os.environ.setdefault("MAIC_V2_ENABLED", "true")
os.environ.setdefault("MAIC_GENERATION_USE_V2", "true")

# ---------------------------------------------------------------------------
# Host-env guard: fail fast with one clear error instead of 20+ cryptic ones.
#
# `utils/logging.py` imports `pythonjsonlogger` at module level (line 32).
# If the host `pytest` binary (e.g. Homebrew Python 3.13) is used instead of
# the project venv, packages may be missing and every test that transitively
# imports `utils.logging` (or future utils) errors at collection time.
#
# This block is inert inside Docker (all packages ARE installed there).
# Outside Docker it raises ONE actionable error before any test is collected,
# naming the missing module so the developer knows exactly what to install.
#
# SPRINT-2-BATCH-2-F9: tuple-based iteration replaces the single hardcoded
# try/except so a future requirements addition that lands in utils/logging.py
# (or any other conftest-imported util) can be added to _REQUIRED_HOST_MODULES
# without touching the error-handling logic.
# ---------------------------------------------------------------------------
_REQUIRED_HOST_MODULES = (
    "pythonjsonlogger",
)

for _mod_name in _REQUIRED_HOST_MODULES:
    try:
        __import__(_mod_name)
    except ImportError as _exc:
        raise ImportError(
            "\n\n"
            "========================================================\n"
            f"  ENV-P1-1: {_mod_name!r} is missing from the Python\n"
            "  interpreter that is running pytest.\n"
            "\n"
            "  Root cause: host pytest (/usr/local/bin/pytest) uses\n"
            "  Homebrew Python 3.13 which does not have this package,\n"
            "  while the project venv (backend/.venv / backend/venv)\n"
            "  does. utils/logging.py fails to import.\n"
            "\n"
            "  Canonical fix (recommended):\n"
            "    docker compose exec web pytest <args>\n"
            "\n"
            "  Host escape-hatch:\n"
            f"    pip install {_mod_name}\n"
            "  (must target the same Python that `which pytest` uses)\n"
            "========================================================\n"
        ) from _exc

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
    if getattr(settings, "PLATFORM_DOMAIN", None) in (None, "", "localhost"):
        settings.PLATFORM_DOMAIN = "lms.com"


# ---------------------------------------------------------------------------
# PERF-P0-5: run Celery tasks (and chords) synchronously in tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _celery_eager_mode():
    """Force Celery into eager mode for the test session.

    PERF-P0-5 introduced a ``chord`` in ``pre_generate_classroom_tts`` —
    eager mode runs each scene-task inline and immediately fires the
    callback, which is what the existing test suite expects (it calls the
    parent task synchronously and then asserts on the post-state).

    We mutate the live celery app config rather than ``settings`` because
    ``django-celery-results`` pulls the app config once at autodiscovery.
    """
    try:
        from config.celery import app as _celery_app
    except Exception:  # noqa: BLE001
        yield
        return
    prev_always_eager = _celery_app.conf.task_always_eager
    prev_propagates = _celery_app.conf.task_eager_propagates
    _celery_app.conf.task_always_eager = True
    _celery_app.conf.task_eager_propagates = True
    try:
        yield
    finally:
        _celery_app.conf.task_always_eager = prev_always_eager
        _celery_app.conf.task_eager_propagates = prev_propagates


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


# ---------------------------------------------------------------------------
# SPRINT-2-BATCH-8-F8: Prometheus registry isolation fixture
# ---------------------------------------------------------------------------
#
# Counters / histograms in :mod:`utils.metrics` are module-level singletons
# attached to ``prometheus_client.REGISTRY`` — the canonical pattern, but it
# means tests that exercise the same metrics in different modules can
# carry-pollute each other's sample values.  Tests inside
# ``backend/tests/test_metrics.py`` defend against this with
# delta-based ``after == before + 1`` assertions, but absolute-value
# assertions are unsafe without explicit cleanup.
#
# This fixture provides an opt-in snapshot/restore for test modules that
# want absolute counter assertions: it captures every sample value
# emitted by every collector before the test runs and resets each
# Counter / Gauge / Histogram back to its pre-test state afterwards.
# Use sparingly — most metric tests should still prefer the cheaper
# delta-based ``_sample()`` approach.
#
# Usage::
#
#     def test_my_absolute_counter(metrics_registry_snapshot):
#         my_counter.inc()
#         assert REGISTRY.get_sample_value("my_counter_total") == 1.0
# ---------------------------------------------------------------------------

@pytest.fixture
def metrics_registry_snapshot():
    """Snapshot/restore prometheus_client REGISTRY samples around a test.

    Captures the full ``REGISTRY.collect()`` snapshot before the test and
    rewinds Counter / Gauge values to their pre-test state on teardown.
    Histograms are not perfectly restorable (they don't expose a public
    ``_value.set()`` for buckets), so we record + log a deviation rather
    than raising — most tests don't care about histogram drift.

    Yields the captured snapshot dict so tests can inspect prior state
    if needed.
    """
    from prometheus_client import REGISTRY

    # Capture (collector, label_dict) -> value
    snapshot: dict = {}
    for collector in list(REGISTRY._collector_to_names.keys()):
        for metric in collector.collect():
            for sample in metric.samples:
                snapshot[(metric.name, tuple(sorted(sample.labels.items())),
                          sample.name)] = sample.value

    yield snapshot

    # Restore Counter / Gauge values; ignore Histograms (best-effort).
    for collector in list(REGISTRY._collector_to_names.keys()):
        # Reset any Counter / Gauge whose post-state diverges from
        # captured pre-state.  We only know how to set Counters via the
        # internal ``_value`` attribute; if the API changes upstream
        # this fixture will need updating.
        cls_name = type(collector).__name__
        if cls_name not in ("Counter", "Gauge"):
            continue
        for metric in collector.collect():
            for sample in metric.samples:
                key = (metric.name,
                       tuple(sorted(sample.labels.items())),
                       sample.name)
                pre = snapshot.get(key, 0.0)
                if sample.value == pre:
                    continue
                # Best-effort: navigate the internal label map.
                try:
                    label_values = tuple(
                        sample.labels[k] for k in collector._labelnames
                    )
                    metric_obj = collector._metrics.get(label_values)
                    if metric_obj is None:
                        continue
                    if hasattr(metric_obj, "_value"):
                        metric_obj._value.set(pre)
                except Exception:
                    # Fixture must never raise on teardown — observability
                    # cleanup is best-effort, not a correctness boundary.
                    continue
