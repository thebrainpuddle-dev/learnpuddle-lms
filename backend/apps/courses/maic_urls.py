from django.conf import settings
from django.urls import path
from . import maic_views

app_name = "maic"

# Phase 4 MAIC-431: gate the legacy v1 generation routes behind
# MAIC_GENERATION_USE_V2. When True (default), the v1 `generate/*`
# endpoints are NOT mounted — clients route to v2's
# `POST /api/maic/v2/generate/` instead. The non-generation v1
# routes (chat, classrooms CRUD, exports, director, etc.) stay
# mounted; they're orchestration around running classrooms, not
# the generation pipeline that v2 replaces.
#
# Flip MAIC_GENERATION_USE_V2=False at the env level to fall back
# to the v1 generation path. Phase 8 owns the final delete of both
# this gate and apps/courses/maic_generation_service.py.
_USE_V2_GENERATION = getattr(settings, "MAIC_GENERATION_USE_V2", True)


# Teacher MAIC URL patterns
teacher_urlpatterns = [
    # Proxy endpoints (SSE/JSON/binary -> OpenMAIC sidecar)
    path("chat/", maic_views.teacher_maic_chat, name="teacher_maic_chat"),
]

# v1 generation routes (DEFERRED: Phase 8 final delete; gated by flag)
if not _USE_V2_GENERATION:
    teacher_urlpatterns += [
        path("generate/outlines/", maic_views.teacher_maic_generate_outlines, name="teacher_maic_generate_outlines"),
        path("generate/scene-content/", maic_views.teacher_maic_generate_scene_content, name="teacher_maic_generate_scene_content"),
        path("generate/scene-actions/", maic_views.teacher_maic_generate_scene_actions, name="teacher_maic_generate_scene_actions"),
        path("generate/classroom/", maic_views.teacher_maic_generate_classroom, name="teacher_maic_generate_classroom"),
    ]

teacher_urlpatterns += [
    path("generate/tts/", maic_views.teacher_maic_generate_tts, name="teacher_maic_generate_tts"),
    path("generate/image/", maic_views.teacher_maic_generate_image, name="teacher_maic_generate_image"),
    # Quiz grading, export, web search
    path("quiz-grade/", maic_views.teacher_maic_quiz_grade, name="teacher_maic_quiz_grade"),
    path("export/pptx/", maic_views.teacher_maic_export_pptx, name="teacher_maic_export_pptx"),
    path("export/html/", maic_views.teacher_maic_export_html, name="teacher_maic_export_html"),
    path("generate/agent-profiles/", maic_views.teacher_maic_generate_agent_profiles, name="teacher_maic_generate_agent_profiles"),
    path("director/turn/", maic_views.teacher_maic_director_turn, name="teacher_maic_director_turn"),
    path("web-search/", maic_views.teacher_maic_web_search, name="teacher_maic_web_search"),

    # Classroom CRUD
    path("classrooms/", maic_views.teacher_maic_classroom_list, name="teacher_maic_classroom_list"),
    path("classrooms/create/", maic_views.teacher_maic_classroom_create, name="teacher_maic_classroom_create"),
    path("classrooms/<uuid:classroom_id>/", maic_views.teacher_maic_classroom_detail, name="teacher_maic_classroom_detail"),
    path("classrooms/<uuid:classroom_id>/update/", maic_views.teacher_maic_classroom_update, name="teacher_maic_classroom_update"),
    path("classrooms/<uuid:classroom_id>/delete/", maic_views.teacher_maic_classroom_delete, name="teacher_maic_classroom_delete"),
    path("classrooms/<uuid:classroom_id>/publish/", maic_views.teacher_maic_classroom_publish, name="teacher_maic_classroom_publish"),
    path("classrooms/<uuid:classroom_id>/progress/", maic_views.teacher_maic_classroom_progress, name="teacher_maic_classroom_progress"),
    # CG-P0-8 — recover an orphaned (GENERATING + partial content) classroom
    # by flipping to READY with whatever scenes were saved by persistPartial.
    path("classrooms/<uuid:classroom_id>/finalize-partial/", maic_views.teacher_maic_classroom_finalize_partial, name="teacher_maic_classroom_finalize_partial"),

    # Agent roster + per-agent regeneration + TTS preview
    path("agents/regenerate-one/", maic_views.teacher_maic_regenerate_one_agent, name="teacher_maic_regenerate_one_agent"),
    path("tts/preview/", maic_views.teacher_maic_tts_preview, name="teacher_maic_tts_preview"),
]

# Student MAIC URL patterns
student_urlpatterns = [
    # Browse (teacher-created public classrooms)
    path("classrooms/", maic_views.student_maic_classroom_list, name="student_maic_classroom_list"),
    path("classrooms/<uuid:classroom_id>/", maic_views.student_maic_classroom_detail, name="student_maic_classroom_detail"),

    # Student's own classrooms (CRUD + generation)
    path("my-classrooms/", maic_views.student_maic_my_classrooms, name="student_maic_my_classrooms"),
    path("classrooms/create/", maic_views.student_maic_classroom_create, name="student_maic_classroom_create"),
    path("classrooms/<uuid:classroom_id>/update/", maic_views.student_maic_classroom_update, name="student_maic_classroom_update"),
    path("classrooms/<uuid:classroom_id>/delete/", maic_views.student_maic_classroom_delete, name="student_maic_classroom_delete"),
    path("validate-topic/", maic_views.student_maic_validate_topic, name="student_maic_validate_topic"),

    # Generation proxies (with guardrails) — gated by MAIC_GENERATION_USE_V2.
    # When True (default), v2's POST /api/maic/v2/generate/ is the canonical
    # generation route; the v1 paths below stay dormant until the flag flips.
    *(
        []
        if _USE_V2_GENERATION
        else [
            path("generate/outlines/", maic_views.student_maic_generate_outlines, name="student_maic_generate_outlines"),
            path("generate/scene-content/", maic_views.student_maic_generate_scene_content, name="student_maic_generate_scene_content"),
            path("generate/scene-actions/", maic_views.student_maic_generate_scene_actions, name="student_maic_generate_scene_actions"),
        ]
    ),

    # Agent roster (student) — mirrors teacher variants with @student_or_admin
    path("generate/agent-profiles/", maic_views.student_maic_generate_agent_profiles, name="student_maic_generate_agent_profiles"),
    path("agents/regenerate-one/", maic_views.student_maic_regenerate_one_agent, name="student_maic_regenerate_one_agent"),

    # Chat, TTS, quiz (existing)
    path("chat/", maic_views.student_maic_chat, name="student_maic_chat"),
    path("generate/tts/", maic_views.student_maic_generate_tts, name="student_maic_generate_tts"),
    path("quiz-grade/", maic_views.student_maic_quiz_grade, name="student_maic_quiz_grade"),

    # Director (multi-agent turn-taking) — Porting P3.1
    path("director/turn/", maic_views.student_maic_director_turn, name="student_maic_director_turn"),
]
