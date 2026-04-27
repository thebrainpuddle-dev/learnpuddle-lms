"""
Prometheus metrics for the MAIC pipeline (TEST-P1-10).

Defines module-level Counter / Histogram / Gauge instruments at the four
highest-traffic choke points so Grafana dashboards can alert on regressions:

    1. Scene generation outcomes (`maic_scene_generation_total`)
    2. LLM call duration distribution (`maic_llm_call_duration_seconds`)
    3. Image fetch outcomes per provider (`maic_image_fetch_total`)
    4. Classroom-detail polling rate by status (`maic_classroom_polls_total`)

Why module-level: prometheus_client metrics are global registry singletons —
constructing them at import time is the canonical pattern and lets us share
one ``REGISTRY`` view across tests + the ``/metrics/`` scrape endpoint.

Why django-prometheus is already a dep: see ``backend/requirements.txt``.
We deliberately depend on the underlying ``prometheus_client`` package
(re-exported via django-prometheus) rather than django-prometheus's
``ExportModelOperationsMixin`` because our hot paths are Celery tasks and
service functions, not Django models.

The ``time_llm_call`` context manager wraps ``_call_llm`` /
``_call_llm_with_json_retry`` so latency is measured even when the LLM call
raises — the sample is recorded in the ``finally`` branch.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator, Literal

from prometheus_client import Counter, Histogram


# SPRINT-2-BATCH-8-F9: pinned values for the ``path`` label on
# ``maic_llm_call_duration_seconds``.  Free-form caller strings (e.g. an
# f-string interpolating scene_type) would risk unbounded Prometheus
# cardinality; this Literal documents the contract that callers MUST
# pass one of these stable constants.  Add a new value here ONLY when
# adding a new top-level LLM call site, and update the dashboards
# accordingly.  See ``apps/courses/maic_generation_service.py`` for the
# canonical call sites.
LLMCallPath = Literal[
    "scene_content_interactive",
    "scene_content_lecture",
    "scene_content_quiz",
    "scene_actions",
]


#: Tuple form of :data:`LLMCallPath` for runtime validation in tests.
LLM_CALL_PATHS: tuple[str, ...] = (
    "scene_content_interactive",
    "scene_content_lecture",
    "scene_content_quiz",
    "scene_actions",
)


# ─── 1. Scene generation outcomes ────────────────────────────────────────────
#
# Labels:
#   scene_type — "lecture", "quiz", "interactive", "scene_actions" (for
#                 generate_scene_actions), "fallback_interactive", etc.
#                 Free-form so callers can pass scene["type"] directly.
#   outcome    — "ok"        : LLM returned, parsed, validator passed
#                "fallback"  : LLM bailed → deterministic fallback used
#                "error"     : unexpected exception bubbled out (rare)
maic_scene_generation_total = Counter(
    "maic_scene_generation_total",
    "MAIC scene-generation calls by scene type and final outcome.",
    ["scene_type", "outcome"],
)


# ─── 2. LLM call duration ────────────────────────────────────────────────────
#
# Histogram buckets tuned for the 0.5s–120s LLM timeout window — most
# provider calls land in the 1s–10s band; the long tail is what we actually
# need to see in dashboards.
maic_llm_call_duration_seconds = Histogram(
    "maic_llm_call_duration_seconds",
    "Duration of MAIC LLM calls in seconds, labelled by provider + caller path.",
    ["provider", "path"],
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0, 120.0),
)


@contextmanager
def time_llm_call(provider: str, path: LLMCallPath) -> Iterator[None]:
    """Context manager that records elapsed wall-clock into the LLM histogram.

    Always records — even when the wrapped call raises — so a flapping
    provider that times out at 120s shows up in the long-tail bucket
    rather than going invisible.

    Usage::

        with time_llm_call(provider="openrouter", path="scene_content_lecture"):
            resp = http_requests.post(...)

    Parameters
    ----------
    provider : str
        One of ``{"openrouter", "ollama", "openai", "deterministic",
        "unknown"}``.  Free-form is accepted but cardinality is on the
        caller.
    path : LLMCallPath
        MUST be one of the values in :data:`LLM_CALL_PATHS`
        (SPRINT-2-BATCH-8-F9).  Passing a dynamic / unbounded string here
        will silently inflate Prometheus label cardinality.  The type
        annotation is enforced at lint time only; callers are expected
        to pass the exact string constant.
    """
    start = time.monotonic()
    try:
        yield
    finally:
        maic_llm_call_duration_seconds.labels(
            provider=provider or "unknown",
            path=path or "unknown",
        ).observe(time.monotonic() - start)


# ─── 3. Image fetch outcomes ─────────────────────────────────────────────────
#
# Labels:
#   provider — "imagen", "nanobanana", "unsplash", "pexels", "pollinations",
#              "placeholder" (the deterministic fallback). The sentinel
#              "all" is reserved for the all-providers-cooling short-circuit
#              recorded once per ``fetch_scene_image`` entry.
#   outcome  — "ok"          : provider returned a usable URL/bytes
#              "cooling"      : circuit breaker open, skipped
#              "error"        : provider raised / returned non-2xx
#              "placeholder"  : fell through to placehold.co
maic_image_fetch_total = Counter(
    "maic_image_fetch_total",
    "MAIC image-fetch attempts by provider and outcome.",
    ["provider", "outcome"],
)


# ─── 4. Classroom-detail polling ─────────────────────────────────────────────
#
# Frontend polls these endpoints every 3s while GENERATING (PERF-P0-2 backoff
# eventually stretches to 30s). High polling volume → easy to spot saturation
# events. The state label is the *effective* state surfaced to the FE, so
# READY+images_pending=true is bucketed separately as
# "ready_pending_images" — that's the polling that the FE actually keeps
# alive after the main GENERATING → READY transition.
maic_classroom_polls_total = Counter(
    "maic_classroom_polls_total",
    "MAIC classroom-detail poll requests by effective state.",
    ["state"],
)


__all__ = [
    "maic_scene_generation_total",
    "maic_llm_call_duration_seconds",
    "time_llm_call",
    "maic_image_fetch_total",
    "maic_classroom_polls_total",
    "metrics_view",
]


# ─── /metrics/ scrape endpoint ───────────────────────────────────────────────

def _parse_trusted_proxies(raw) -> list:
    """Parse a comma-separated list of trusted-proxy IPs / CIDRs.

    Accepts either a list (already-parsed via Django settings) or a
    comma-separated string (typical env var form).  Each entry is fed
    through ``ipaddress.ip_network(strict=False)`` so plain IPs (e.g.
    ``"127.0.0.1"``) are converted to ``/32`` networks.
    """
    import ipaddress

    if not raw:
        return []
    if isinstance(raw, str):
        items = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        items = [str(p).strip() for p in raw if str(p).strip()]
    networks = []
    for item in items:
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            # Skip malformed entries silently; mis-configuration should
            # not prevent the metrics endpoint from booting.
            continue
    return networks


def _client_ip(request) -> str:
    """Extract the originating client IP for the metrics allowlist check.

    SPRINT-2-BATCH-8-F7: hardened against XFF spoofing.  ``X-Forwarded-For``
    is honoured ONLY when ``REMOTE_ADDR`` is a trusted proxy (in-cluster
    nginx or loopback); otherwise the raw ``REMOTE_ADDR`` is used.

    Without this guard, an attacker who reaches Gunicorn directly (e.g.
    via a leaked port mapping) could pass an arbitrary
    ``X-Forwarded-For: <allowlisted_ip>`` and bypass the IP allowlist.

    The trusted-proxy list is configured via
    ``settings.METRICS_TRUSTED_PROXIES`` (or env ``METRICS_TRUSTED_PROXIES``,
    comma-separated CIDRs / IPs).  The default ``127.0.0.1, 10.0.0.0/8``
    covers the typical Docker / k8s in-cluster nginx topology.
    """
    import ipaddress

    from django.conf import settings

    remote_addr = (request.META.get("REMOTE_ADDR") or "").strip()
    raw = getattr(
        settings, "METRICS_TRUSTED_PROXIES", "127.0.0.1,10.0.0.0/8",
    )
    trusted = _parse_trusted_proxies(raw)

    remote_is_trusted = False
    if remote_addr:
        try:
            remote_ip = ipaddress.ip_address(remote_addr)
            remote_is_trusted = any(remote_ip in net for net in trusted)
        except ValueError:
            remote_is_trusted = False

    if remote_is_trusted:
        xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if xff:
            # Use leftmost — the public client per the nginx convention.
            return xff.split(",")[0].strip()
    # Untrusted REMOTE_ADDR (or no XFF) → ignore XFF entirely.
    return remote_addr


def metrics_view(request):
    """Plain-text Prometheus scrape endpoint.

    Access policy (AUDIT-2026-04-25-1 — hardened against cross-tenant
    counter leak).  Prometheus counters in this module are module-level
    globals shared across every tenant in the deployment; allowing any
    tenant-scoped role to scrape them lets that tenant infer
    platform-wide usage / error volume of every other tenant.

    Therefore the gate is:

        IP allowlist is REQUIRED for every non-DEBUG path.  The role
        gate is layered on top — only SUPER_ADMIN sessions may
        accompany the IP check; SCHOOL_ADMIN / HOD / TEACHER and any
        other tenant-scoped role is denied unconditionally.

    Decision matrix (role / IP-allowlisted / DEBUG → status):

        SCHOOL_ADMIN   *           False  → 403   (cross-tenant leak)
        SCHOOL_ADMIN   *           True   → 200   (DEBUG escape hatch)
        SUPER_ADMIN    yes         False  → 200
        SUPER_ADMIN    no          False  → 403   (defense in depth)
        anonymous      yes         False  → 200   (Prometheus scraper)
        anonymous      no          False  → 403
        anonymous      *           True   → 200   (DEBUG escape hatch)

    The ``is_staff`` field is intentionally NOT consulted — a tenant
    admin who's been granted Django-admin access for some other reason
    must not inherit metrics-scrape rights.

    The endpoint always emits ``text/plain; version=0.0.4; charset=utf-8``
    per the Prometheus exposition spec.
    """
    # Local imports — avoid Django app-config errors when this module is
    # imported during settings parsing.
    from django.conf import settings
    from django.http import HttpResponse, HttpResponseForbidden
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        REGISTRY,
        generate_latest,
    )

    # DEBUG escape hatch: local dev convenience.  Must use ``getattr``
    # against the live settings module (NOT a captured value) so the
    # ``settings`` pytest fixture can flip it per-test.
    if bool(getattr(settings, "DEBUG", False)):
        payload = generate_latest(REGISTRY)
        return HttpResponse(payload, content_type=CONTENT_TYPE_LATEST)

    # IP allowlist is the FIRST gate.  Anything not coming from an
    # allowlisted source is denied regardless of session.
    allow_ips = set(getattr(settings, "METRICS_ALLOW_IPS", []) or [])
    if _client_ip(request) not in allow_ips:
        return HttpResponseForbidden("metrics endpoint not authorised")

    # Past the IP gate.  If a session is attached, it MUST be SUPER_ADMIN.
    # SCHOOL_ADMIN / HOD / IB_COORDINATOR / TEACHER — any tenant-scoped
    # role — is denied so a single tenant cannot infer cross-tenant usage
    # via the global Prometheus counters.
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        if getattr(user, "role", "") != "SUPER_ADMIN":
            return HttpResponseForbidden("metrics endpoint not authorised")

    payload = generate_latest(REGISTRY)
    return HttpResponse(payload, content_type=CONTENT_TYPE_LATEST)
