"""Tests for the v1 → v2 generation gate (Phase 4, MAIC-431).

The legacy v1 generation routes in apps/courses/maic_urls.py are
gated behind `settings.MAIC_GENERATION_USE_V2`. When True (the
expected default), the v1 generate/* endpoints are NOT mounted;
clients route to v2's POST /api/maic/v2/generate/ instead.

The non-generation v1 routes (chat, classrooms CRUD, exports,
director, etc.) stay mounted — they're orchestration around running
classrooms, not the generation pipeline that v2 replaces.
"""
from __future__ import annotations

from importlib import reload

import pytest


def _reload_maic_urls():
    """Force a reload so the module-level _USE_V2_GENERATION binding
    re-reads from settings (settings overrides take effect)."""
    from apps.courses import maic_urls

    reload(maic_urls)
    return maic_urls


def test_v1_generation_routes_not_mounted_when_v2_flag_enabled(settings):
    """MAIC_GENERATION_USE_V2=True hides v1 generate/* routes for migrated clients."""
    settings.MAIC_GENERATION_USE_V2 = True
    maic_urls = _reload_maic_urls()

    teacher_paths = [str(p.pattern) for p in maic_urls.teacher_urlpatterns]
    assert not any(
        "generate/outlines" in p for p in teacher_paths
    ), "v1 generate/outlines should not be mounted when v2 is enabled"
    assert not any("generate/scene-content" in p for p in teacher_paths)
    assert not any("generate/scene-actions" in p for p in teacher_paths)
    assert not any("generate/classroom" in p for p in teacher_paths)


def test_v1_generation_routes_mounted_when_flag_disabled(settings):
    """Rollback path: MAIC_GENERATION_USE_V2=False mounts v1 generate
    routes again (so prod can flip back if v2 has a regression)."""
    settings.MAIC_GENERATION_USE_V2 = False
    maic_urls = _reload_maic_urls()

    teacher_paths = [str(p.pattern) for p in maic_urls.teacher_urlpatterns]
    assert any("generate/outlines" in p for p in teacher_paths)
    assert any("generate/scene-content" in p for p in teacher_paths)
    assert any("generate/scene-actions" in p for p in teacher_paths)
    assert any("generate/classroom" in p for p in teacher_paths)

    # Reset to default for other tests
    settings.MAIC_GENERATION_USE_V2 = True
    _reload_maic_urls()


def test_non_generation_v1_routes_always_mounted(settings):
    """Chat / classrooms / exports / director / TTS / quiz-grade /
    web-search / image / agent-profiles ALL stay mounted regardless
    of the flag — they're orchestration around running classrooms,
    not the generation pipeline."""
    settings.MAIC_GENERATION_USE_V2 = True
    maic_urls = _reload_maic_urls()

    teacher_paths = [str(p.pattern) for p in maic_urls.teacher_urlpatterns]
    assert any("chat/" in p for p in teacher_paths)
    assert any("quiz-grade/" in p for p in teacher_paths)
    assert any("export/pptx/" in p for p in teacher_paths)
    assert any("export/html/" in p for p in teacher_paths)
    assert any("director/turn/" in p for p in teacher_paths)
    assert any("generate/tts/" in p for p in teacher_paths)
    assert any("generate/image/" in p for p in teacher_paths)
    assert any("generate/agent-profiles/" in p for p in teacher_paths)
    assert any("classrooms/" in p for p in teacher_paths)


def test_student_v1_generation_routes_gated(settings):
    """Student-side v1 generate routes follow the same flag."""
    settings.MAIC_GENERATION_USE_V2 = True
    maic_urls = _reload_maic_urls()

    student_paths = [str(p.pattern) for p in maic_urls.student_urlpatterns]
    assert not any("generate/outlines" in p for p in student_paths)
    assert not any("generate/scene-content" in p for p in student_paths)
    assert not any("generate/scene-actions" in p for p in student_paths)


def test_default_v2_setting_makes_teacher_wizard_v2_first():
    """Default hides v1 generation now that the teacher wizard is migrated."""
    from django.conf import settings

    assert settings.MAIC_GENERATION_USE_V2 is True


def test_v1_service_module_carries_deprecation_marker():
    """apps/courses/maic_generation_service.py module docstring
    declares the v1 deprecation status. A future contributor seeing
    the module reads the DEFERRED notice + heads to apps/maic/
    generation/ instead."""
    from apps.courses import maic_generation_service

    docstring = maic_generation_service.__doc__ or ""
    assert "DEPRECATED" in docstring
    assert "Phase 4, MAIC-431" in docstring
    assert "Phase 8 final delete" in docstring
    # Pointer to the v2 home
    assert "apps/maic/generation" in docstring
