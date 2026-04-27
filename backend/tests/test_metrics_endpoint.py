"""
AUDIT-2026-04-25-1 — /metrics/ cross-tenant counter leak (P0 security).

Trust model under test
----------------------
Prometheus counters in ``utils/metrics.py`` are module-level globals
shared across every tenant in the deployment.  Any tenant-scoped role
that can read them learns platform-wide usage / error rates of every
other tenant in the deployment (a competitive-intel leak).

Therefore the only roles allowed to read ``/metrics/`` are:

    1. SUPER_ADMIN with an IP-allowlisted session (defense-in-depth — a
       compromised SUPER_ADMIN cookie on a hotel WiFi MUST NOT scrape).
    2. Anonymous Prometheus scraper from an IP-allowlisted source.
    3. Local dev (``settings.DEBUG=True``) — the explicit escape hatch.

SCHOOL_ADMIN, HOD, IB_COORDINATOR, TEACHER and any other tenant-scoped
role must be denied 403, regardless of the IP they are coming from and
regardless of ``is_staff``.

Decision matrix (auth gate)
---------------------------
+----------------+--------------+--------+----------+
| role / anon    | IP allow?    | DEBUG? | expected |
+================+==============+========+==========+
| SCHOOL_ADMIN   | yes          | False  | 403      |
| SCHOOL_ADMIN   | no           | False  | 403      |
| SUPER_ADMIN    | yes          | False  | 200      |
| SUPER_ADMIN    | no           | False  | 403      |
| anonymous      | yes          | False  | 200      |
| anonymous      | no           | False  | 403      |
| anonymous      | no           | True   | 200      |
+----------------+--------------+--------+----------+

These tests use Django's RequestFactory directly so we don't need a DB
row — the view only inspects ``request.user.is_authenticated`` /
``role`` / ``is_staff`` and ``request.META``.
"""
from __future__ import annotations


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_request(remote_addr: str = "127.0.0.1", user=None,
                  xff: str | None = None):
    """Build a GET /metrics/ request with optional user + XFF header."""
    from django.test import RequestFactory

    rf = RequestFactory()
    extra = {"REMOTE_ADDR": remote_addr}
    if xff is not None:
        extra["HTTP_X_FORWARDED_FOR"] = xff
    req = rf.get("/metrics/", **extra)
    if user is None:
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
    else:
        req.user = user
    return req


class _RoleStub:
    """Minimal duck-typed user for role-based gate checks."""

    def __init__(self, role: str, is_staff: bool = False,
                 is_authenticated: bool = True):
        self.role = role
        self.is_staff = is_staff
        self.is_authenticated = is_authenticated


# ─── SCHOOL_ADMIN must NEVER pass ────────────────────────────────────────────


def test_school_admin_with_allowlisted_ip_is_forbidden(settings):
    """A SCHOOL_ADMIN coming from an allowlisted IP MUST be 403.

    This is the cross-tenant leak: globals are shared, so even an
    allowlisted SCHOOL_ADMIN session can scrape every tenant's counters.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["10.0.0.5"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    user = _RoleStub(role="SCHOOL_ADMIN")
    resp = metrics_view(_make_request(remote_addr="10.0.0.5", user=user))
    assert resp.status_code == 403


def test_school_admin_with_unlisted_ip_is_forbidden(settings):
    """A SCHOOL_ADMIN from an unlisted IP is 403 (the obvious case)."""
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = []
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    user = _RoleStub(role="SCHOOL_ADMIN")
    resp = metrics_view(_make_request(remote_addr="9.9.9.9", user=user))
    assert resp.status_code == 403


def test_school_admin_with_is_staff_true_is_still_forbidden(settings):
    """A SCHOOL_ADMIN with is_staff=True (Django admin access) is STILL 403.

    The previous staff-bypass branch trusted ``user.is_staff`` blindly,
    which let any tenant-scoped admin who'd been granted Django-admin
    access scrape the global counters.  That bypass must be gone.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["10.0.0.5"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    user = _RoleStub(role="SCHOOL_ADMIN", is_staff=True)
    resp = metrics_view(_make_request(remote_addr="10.0.0.5", user=user))
    assert resp.status_code == 403


# ─── SUPER_ADMIN: needs IP allowlist (defense in depth) ──────────────────────


def test_super_admin_with_unlisted_ip_is_forbidden(settings):
    """A SUPER_ADMIN session from a non-allowlisted IP is 403.

    Defense-in-depth: a stolen SUPER_ADMIN cookie used from a hotel WiFi
    must not be enough to scrape platform-wide usage data.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["10.0.0.5"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    user = _RoleStub(role="SUPER_ADMIN", is_staff=True)
    resp = metrics_view(_make_request(remote_addr="9.9.9.9", user=user))
    assert resp.status_code == 403


def test_super_admin_with_allowlisted_ip_is_allowed(settings):
    """A SUPER_ADMIN session from an allowlisted IP is 200."""
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["10.0.0.5"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    user = _RoleStub(role="SUPER_ADMIN", is_staff=True)
    resp = metrics_view(_make_request(remote_addr="10.0.0.5", user=user))
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "maic_scene_generation_total" in body


# ─── Anonymous (Prometheus scraper) path ─────────────────────────────────────


def test_anonymous_from_allowlisted_ip_is_allowed(settings):
    """The Prometheus scraper path: anonymous, allowlisted IP → 200."""
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["10.0.0.5"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    resp = metrics_view(_make_request(remote_addr="10.0.0.5"))
    assert resp.status_code == 200


def test_anonymous_from_unlisted_ip_is_forbidden(settings):
    """Anonymous + unlisted IP → 403 (the deny-by-default case)."""
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["10.0.0.5"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    resp = metrics_view(_make_request(remote_addr="9.9.9.9"))
    assert resp.status_code == 403


# ─── DEBUG escape hatch ──────────────────────────────────────────────────────


def test_debug_mode_allows_anonymous(settings):
    """When DEBUG=True the endpoint is open for local-dev convenience."""
    from utils.metrics import metrics_view

    settings.DEBUG = True
    settings.METRICS_ALLOW_IPS = []
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    resp = metrics_view(_make_request(remote_addr="9.9.9.9"))
    assert resp.status_code == 200


# ─── XFF spoofing must still be hardened (no regression on BATCH-8-F7) ───────


def test_xff_spoof_from_untrusted_remote_addr_is_ignored(settings):
    """Regression guard for SPRINT-2-BATCH-8-F7: when REMOTE_ADDR is NOT a
    trusted proxy, X-Forwarded-For must not be consulted, even if it
    claims to be an allowlisted IP.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["1.2.3.4"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1,10.0.0.0/8"

    resp = metrics_view(
        _make_request(remote_addr="9.9.9.9", xff="1.2.3.4"),
    )
    assert resp.status_code == 403


# ─── Other tenant-scoped roles also denied ───────────────────────────────────


def test_teacher_role_is_forbidden_even_on_allowlisted_ip(settings):
    """A TEACHER with an allowlisted IP is still 403 — only SUPER_ADMIN
    or anonymous-scraper-from-allowlist may pass.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["10.0.0.5"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    user = _RoleStub(role="TEACHER")
    resp = metrics_view(_make_request(remote_addr="10.0.0.5", user=user))
    assert resp.status_code == 403
