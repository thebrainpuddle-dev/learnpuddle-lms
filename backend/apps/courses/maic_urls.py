from django.urls import path
from . import maic_views

app_name = "maic"

# Teacher MAIC URL patterns
teacher_urlpatterns = [
    # Proxy endpoints (SSE/JSON/binary -> OpenMAIC sidecar)
    path("chat/", maic_views.teacher_maic_chat, name="teacher_maic_chat"),
    path("generate/outlines/", maic_views.teacher_maic_generate_outlines, name="teacher_maic_generate_outlines"),
    path("generate/scene-content/", maic_views.teacher_maic_generate_scene_content, name="teacher_maic_generate_scene_content"),
    path("generate/tts/", maic_views.teacher_maic_generate_tts, name="teacher_maic_generate_tts"),
    path("generate/classroom/", maic_views.teacher_maic_generate_classroom, name="teacher_maic_generate_classroom"),
    path("generate/image/", maic_views.teacher_maic_generate_image, name="teacher_maic_generate_image"),
    # Quiz grading, export, web search
    path("quiz-grade/", maic_views.teacher_maic_quiz_grade, name="teacher_maic_quiz_grade"),
    path("export/pptx/", maic_views.teacher_maic_export_pptx, name="teacher_maic_export_pptx"),
    path("export/html/", maic_views.teacher_maic_export_html, name="teacher_maic_export_html"),
    path("generate/scene-actions/", maic_views.teacher_maic_generate_scene_actions, name="teacher_maic_generate_scene_actions"),
    path("generate/agent-profiles/", maic_views.teacher_maic_generate_agent_profiles, name="teacher_maic_generate_agent_profiles"),
    path("web-search/", maic_views.teacher_maic_web_search, name="teacher_maic_web_search"),

    # Classroom CRUD
    path("classrooms/", maic_views.teacher_maic_classroom_list, name="teacher_maic_classroom_list"),
    path("classrooms/create/", maic_views.teacher_maic_classroom_create, name="teacher_maic_classroom_create"),
    path("classrooms/<uuid:classroom_id>/", maic_views.teacher_maic_classroom_detail, name="teacher_maic_classroom_detail"),
    path("classrooms/<uuid:classroom_id>/update/", maic_views.teacher_maic_classroom_update, name="teacher_maic_classroom_update"),
    path("classrooms/<uuid:classroom_id>/delete/", maic_views.teacher_maic_classroom_delete, name="teacher_maic_classroom_delete"),
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

    # Generation proxies (with guardrails)
    path("generate/outlines/", maic_views.student_maic_generate_outlines, name="student_maic_generate_outlines"),
    path("generate/scene-content/", maic_views.student_maic_generate_scene_content, name="student_maic_generate_scene_content"),
    path("generate/scene-actions/", maic_views.student_maic_generate_scene_actions, name="student_maic_generate_scene_actions"),

    # Chat, TTS, quiz (existing)
    path("chat/", maic_views.student_maic_chat, name="student_maic_chat"),
    path("generate/tts/", maic_views.student_maic_generate_tts, name="student_maic_generate_tts"),
    path("quiz-grade/", maic_views.student_maic_quiz_grade, name="student_maic_quiz_grade"),
]
