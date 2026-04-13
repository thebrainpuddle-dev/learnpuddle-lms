# apps/courses/chatbot_urls.py
from django.urls import path
from . import chatbot_views

# Teacher chatbot URL patterns
teacher_urlpatterns = [
    path("", chatbot_views.teacher_chatbot_list_create, name="teacher_chatbot_list_create"),
    path("my-sections/", chatbot_views.teacher_my_sections, name="teacher_my_sections"),
    path("<uuid:chatbot_id>/", chatbot_views.teacher_chatbot_detail, name="teacher_chatbot_detail"),
    path("<uuid:chatbot_id>/clone/", chatbot_views.teacher_chatbot_clone, name="teacher_chatbot_clone"),
    path("<uuid:chatbot_id>/knowledge/", chatbot_views.teacher_knowledge_list_create, name="teacher_knowledge_list_create"),
    path("<uuid:chatbot_id>/knowledge/<uuid:knowledge_id>/", chatbot_views.teacher_knowledge_delete, name="teacher_knowledge_delete"),
    path("<uuid:chatbot_id>/refresh-sources/", chatbot_views.teacher_chatbot_refresh_sources, name="teacher_chatbot_refresh_sources"),
    path("<uuid:chatbot_id>/conversations/", chatbot_views.teacher_conversation_list, name="teacher_conversation_list"),
    path("<uuid:chatbot_id>/conversations/<uuid:conversation_id>/", chatbot_views.teacher_conversation_detail, name="teacher_conversation_detail"),
    path("<uuid:chatbot_id>/analytics/", chatbot_views.teacher_chatbot_analytics, name="teacher_chatbot_analytics"),
    path("<uuid:chatbot_id>/chat/", chatbot_views.teacher_chat_preview, name="teacher_chat_preview"),
]

# Student chatbot URL patterns
student_urlpatterns = [
    path("", chatbot_views.student_chatbot_list, name="student_chatbot_list"),
    path("<uuid:chatbot_id>/chat/", chatbot_views.student_chat, name="student_chat"),
    path("<uuid:chatbot_id>/conversations/", chatbot_views.student_conversation_list_create, name="student_conversation_list_create"),
    path("<uuid:chatbot_id>/conversations/<uuid:conversation_id>/", chatbot_views.student_conversation_detail, name="student_conversation_detail"),
]
