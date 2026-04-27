"""
Tests for TEST-P1-10 — Prometheus counters at the 4 MAIC choke points.

We assert REGISTRY.get_sample_value() deltas (not absolute values) because
the metrics are global module-level singletons; other tests in the same run
may have already incremented them.

Cross-module isolation
----------------------
For tests that NEED absolute-value assertions, use the
``metrics_registry_snapshot`` fixture (defined in ``backend/conftest.py``,
SPRINT-2-BATCH-8-F8) to snapshot/restore every Counter / Gauge sample
around the test.  Histograms are best-effort (their internal bucket
counters cannot be cleanly reset without re-instantiating the collector).
The fixture is opt-in — none of the tests in this module currently use
it because the delta-based ``_sample()`` approach is cheaper and safer
against future test additions outside this module.

Coverage:
  * generate_scene_content success → outcome="ok" increments
  * generate_scene_content fallback → outcome="fallback" increments
  * generate_scene_actions fallback → outcome="fallback" on scene_actions label
  * fetch_scene_image with all providers cooling → outcome="cooling" on each
    cooling provider AND on the "all" sentinel
  * fetch_scene_image with placeholder fallthrough → outcome="placeholder"
  * /metrics/ endpoint:
      - returns 200 + contains expected metric names when DEBUG is on
      - returns 200 to a staff user
      - returns 403 to an anonymous user when DEBUG=False and no allowlist
      - returns 200 when client IP is in METRICS_ALLOW_IPS
      - XFF spoofing hardening (SPRINT-2-BATCH-8-F7):
          * XFF ignored when REMOTE_ADDR is not in METRICS_TRUSTED_PROXIES
          * XFF honoured when REMOTE_ADDR is a trusted proxy
"""
from __future__ import annotations

import pytest
from prometheus_client import REGISTRY
from rest_framework.test import APIClient


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _sample(metric_name: str, labels: dict) -> float:
    """Return current REGISTRY sample (or 0.0 if absent yet)."""
    val = REGISTRY.get_sample_value(metric_name, labels)
    return float(val) if val is not None else 0.0


# ─── 1. Scene generation counter ─────────────────────────────────────────────

def test_generate_scene_content_ok_increments_counter(monkeypatch):
    """A successful LLM-parsed scene increments outcome=ok."""
    from apps.courses import maic_generation_service as svc

    before = _sample(
        "maic_scene_generation_total",
        {"scene_type": "lecture", "outcome": "ok"},
    )

    # Stub the JSON-retry helper to look like a clean LLM hit.
    fake_parsed = {
        "slides": [
            {
                "id": "slide-1",
                "title": "Intro",
                "elements": [
                    {"id": "e1", "type": "text", "content": "hi",
                     "x": 0, "y": 0, "width": 100, "height": 40},
                ],
                "background": "#fff",
                "duration": 30,
                "speakerScript": "Hello world",
            }
        ]
    }
    monkeypatch.setattr(
        svc, "_call_llm_with_json_retry",
        lambda *a, **kw: (fake_parsed, "raw"),
    )
    # Skip image fetching to keep the test hermetic.
    monkeypatch.setattr(svc, "_fill_image_urls", lambda *a, **kw: None)

    class _Cfg:
        llm_provider = "openrouter"
        llm_model = "test-model"
        llm_base_url = ""
        image_provider = "disabled"

    scene = {"id": "scene-1", "title": "Intro", "type": "lecture",
             "slideCount": 3, "agentIds": []}
    result = svc.generate_scene_content(
        scene, agents=[{"id": "a1", "name": "A", "role": "professor"}],
        language="en", config=_Cfg(),
    )
    assert isinstance(result, dict)

    after = _sample(
        "maic_scene_generation_total",
        {"scene_type": "lecture", "outcome": "ok"},
    )
    assert after == before + 1.0


def test_generate_scene_content_fallback_increments_counter(monkeypatch):
    """Empty LLM response → fallback path increments outcome=fallback."""
    from apps.courses import maic_generation_service as svc

    before = _sample(
        "maic_scene_generation_total",
        {"scene_type": "lecture", "outcome": "fallback"},
    )

    # Simulate the LLM giving up entirely.
    monkeypatch.setattr(
        svc, "_call_llm_with_json_retry", lambda *a, **kw: (None, None),
    )

    class _Cfg:
        llm_provider = "openrouter"
        llm_model = "test-model"
        llm_base_url = ""
        image_provider = "disabled"

    scene = {"id": "scene-1", "title": "Intro", "type": "lecture",
             "slideCount": 3, "agentIds": []}
    svc.generate_scene_content(
        scene, agents=[{"id": "a1", "name": "A", "role": "professor"}],
        language="en", config=_Cfg(),
    )

    after = _sample(
        "maic_scene_generation_total",
        {"scene_type": "lecture", "outcome": "fallback"},
    )
    assert after == before + 1.0


def test_generate_scene_actions_fallback_increments_counter(monkeypatch):
    """generate_scene_actions also wires into the same counter under
    scene_type=scene_actions when the LLM response is unusable.
    """
    from apps.courses import maic_generation_service as svc

    before = _sample(
        "maic_scene_generation_total",
        {"scene_type": "scene_actions", "outcome": "fallback"},
    )

    monkeypatch.setattr(
        svc, "_call_llm_with_json_retry", lambda *a, **kw: (None, None),
    )

    class _Cfg:
        llm_provider = "openrouter"
        llm_model = "test-model"
        llm_base_url = ""
        image_provider = "disabled"

    scene = {
        "id": "scene-1", "title": "T", "type": "lecture",
        "agentIds": ["a1"],
        "content": {"slides": [{"title": "S", "elements": [], "speakerScript": ""}]},
    }
    svc.generate_scene_actions(
        scene,
        agents=[
            {"id": "a1", "name": "A", "role": "professor"},
            {"id": "a2", "name": "B", "role": "student"},
        ],
        language="en", config=_Cfg(),
    )

    after = _sample(
        "maic_scene_generation_total",
        {"scene_type": "scene_actions", "outcome": "fallback"},
    )
    assert after == before + 1.0


# ─── 2. Image fetch counter ──────────────────────────────────────────────────

def test_fetch_scene_image_all_cooling_records_counters(monkeypatch):
    """When every provider is cooling, the all-cooling short-circuit must
    increment one sample per cooling provider plus a sentinel on
    provider="all".
    """
    from apps.courses import image_service as imgsvc

    # Force every provider into the cooling state. _is_provider_cooling is
    # the boundary the entry point checks; freezing it to True makes the
    # short-circuit deterministic.
    monkeypatch.setattr(imgsvc, "_is_provider_cooling", lambda _p: True)
    # Stub keys so availability calc doesn't depend on env.
    monkeypatch.setattr(
        imgsvc, "_get_api_key",
        lambda name: "fake" if name in (
            "GOOGLE_AI_API_KEY", "UNSPLASH_ACCESS_KEY", "PEXELS_API_KEY"
        ) else "",
    )

    before_all = _sample(
        "maic_image_fetch_total", {"provider": "all", "outcome": "cooling"},
    )
    before_imagen = _sample(
        "maic_image_fetch_total", {"provider": "imagen", "outcome": "cooling"},
    )
    before_pollinations = _sample(
        "maic_image_fetch_total", {"provider": "pollinations", "outcome": "cooling"},
    )

    url = imgsvc.fetch_scene_image("photosynthesis")
    # Always returns a usable placeholder, never raises.
    assert "placehold.co" in url

    after_all = _sample(
        "maic_image_fetch_total", {"provider": "all", "outcome": "cooling"},
    )
    after_imagen = _sample(
        "maic_image_fetch_total", {"provider": "imagen", "outcome": "cooling"},
    )
    after_pollinations = _sample(
        "maic_image_fetch_total", {"provider": "pollinations", "outcome": "cooling"},
    )

    assert after_all == before_all + 1.0
    assert after_imagen == before_imagen + 1.0
    assert after_pollinations == before_pollinations + 1.0


def test_fetch_scene_image_empty_keyword_counts_placeholder():
    """Empty keyword → deterministic placeholder; counted on placeholder/placeholder."""
    from apps.courses import image_service as imgsvc

    before = _sample(
        "maic_image_fetch_total",
        {"provider": "placeholder", "outcome": "placeholder"},
    )
    url = imgsvc.fetch_scene_image("")
    assert "placehold.co" in url
    after = _sample(
        "maic_image_fetch_total",
        {"provider": "placeholder", "outcome": "placeholder"},
    )
    assert after == before + 1.0


# ─── 3. /metrics/ endpoint ───────────────────────────────────────────────────

# The /metrics/ view is unit-testable without the DB by calling it
# directly through Django's RequestFactory — it never touches an ORM
# query. This sidesteps a flaky shared `test_lms_db` in the developer
# env (ENV-P1-1 cousin) while still exercising the auth gate.

def _make_request(path: str = "/metrics/", remote_addr: str = "127.0.0.1",
                  user=None):
    from django.test import RequestFactory
    rf = RequestFactory()
    req = rf.get(path, REMOTE_ADDR=remote_addr)
    # Mimic the user attribute that AuthenticationMiddleware would set.
    if user is None:
        from django.contrib.auth.models import AnonymousUser
        req.user = AnonymousUser()
    else:
        req.user = user
    return req


def test_metrics_endpoint_returns_200_and_metric_names(settings):
    """In DEBUG mode the endpoint serves Prometheus exposition text containing
    every metric we registered.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = True
    settings.METRICS_ALLOW_IPS = []

    resp = metrics_view(_make_request())
    assert resp.status_code == 200
    body = resp.content.decode("utf-8")
    assert "maic_scene_generation_total" in body
    assert "maic_llm_call_duration_seconds" in body
    assert "maic_image_fetch_total" in body
    assert "maic_classroom_polls_total" in body
    # Spec compliance — must be Prometheus text exposition.
    assert resp["Content-Type"].startswith("text/plain")


def test_metrics_endpoint_denies_anonymous_when_locked_down(settings):
    """When DEBUG=False and the IP isn't allowlisted, anon → 403."""
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = []

    resp = metrics_view(_make_request(remote_addr="9.9.9.9"))
    assert resp.status_code == 403


def test_metrics_endpoint_allows_allowlisted_ip(settings):
    """A request from an IP in METRICS_ALLOW_IPS is allowed even when
    DEBUG=False and the requester is anonymous (the prod prometheus path).
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["10.0.0.5"]

    resp = metrics_view(_make_request(remote_addr="10.0.0.5"))
    assert resp.status_code == 200
    assert "maic_scene_generation_total" in resp.content.decode("utf-8")


def test_metrics_endpoint_denies_school_admin(settings):
    """AUDIT-2026-04-25-1: a SCHOOL_ADMIN session MUST be denied — even
    from an allowlisted IP.

    Prometheus counters are module-level globals shared across tenants;
    allowing a tenant-scoped role to scrape them leaks platform-wide
    usage to that tenant.  Only SUPER_ADMIN (or anonymous from an
    allowlisted scraper IP) may pass the gate.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["10.0.0.5"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1"

    class _SchoolAdminStub:
        is_authenticated = True
        is_staff = False
        role = "SCHOOL_ADMIN"

    resp = metrics_view(
        _make_request(remote_addr="10.0.0.5", user=_SchoolAdminStub()),
    )
    assert resp.status_code == 403


def test_metrics_endpoint_uses_x_forwarded_for_left_most(settings):
    """When the request comes from a trusted proxy, the leftmost XFF
    entry is used to identify the public client (nginx-friendly).

    SPRINT-2-BATCH-8-F7: XFF is ONLY honoured when REMOTE_ADDR is in
    METRICS_TRUSTED_PROXIES; this test exercises the happy path.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["1.2.3.4"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1,10.0.0.0/8"

    from django.test import RequestFactory
    from django.contrib.auth.models import AnonymousUser
    rf = RequestFactory()
    # 10.0.0.1 IS in the trusted-proxy CIDR → XFF is consulted, leftmost
    # entry "1.2.3.4" is the resolved client IP.
    req = rf.get("/metrics/", REMOTE_ADDR="10.0.0.1",
                 HTTP_X_FORWARDED_FOR="1.2.3.4, 10.0.0.5")
    req.user = AnonymousUser()

    resp = metrics_view(req)
    assert resp.status_code == 200


# ─── SPRINT-2-BATCH-8-F7: XFF spoofing hardening ─────────────────────────────

def test_metrics_xff_ignored_when_remote_addr_untrusted(settings):
    """When REMOTE_ADDR is NOT in the trusted-proxy list, X-Forwarded-For
    must be ignored entirely — even if it claims to be an allowlisted IP.

    Defends against attackers who reach Gunicorn directly (bypassing the
    nginx XFF-strip rules) and inject ``X-Forwarded-For: <allowlisted>``
    to escalate into the metrics endpoint.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["1.2.3.4"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1,10.0.0.0/8"

    from django.test import RequestFactory
    from django.contrib.auth.models import AnonymousUser
    rf = RequestFactory()
    # 9.9.9.9 is NOT in the trusted-proxy list → XFF is ignored even
    # though it claims to be the allowlisted "1.2.3.4".
    req = rf.get("/metrics/", REMOTE_ADDR="9.9.9.9",
                 HTTP_X_FORWARDED_FOR="1.2.3.4")
    req.user = AnonymousUser()

    resp = metrics_view(req)
    assert resp.status_code == 403


def test_metrics_xff_honoured_when_remote_addr_is_trusted_proxy(settings):
    """A request that arrives from a trusted in-cluster nginx (REMOTE_ADDR
    inside 10.0.0.0/8) MUST have its X-Forwarded-For honoured so the
    real public client IP is what the allowlist checks.
    """
    from utils.metrics import metrics_view

    settings.DEBUG = False
    settings.METRICS_ALLOW_IPS = ["8.8.8.8"]
    settings.METRICS_TRUSTED_PROXIES = "127.0.0.1,10.0.0.0/8"

    from django.test import RequestFactory
    from django.contrib.auth.models import AnonymousUser
    rf = RequestFactory()
    req = rf.get("/metrics/", REMOTE_ADDR="10.0.0.7",
                 HTTP_X_FORWARDED_FOR="8.8.8.8, 10.0.0.7")
    req.user = AnonymousUser()

    resp = metrics_view(req)
    assert resp.status_code == 200
