# apps/progress/gamification_urls.py

from django.urls import path

from . import gamification_admin_views
from . import gamification_teacher_views

app_name = "gamification"

urlpatterns = [
    # Admin endpoints
    path("admin/config/", gamification_admin_views.gamification_config_get, name="admin_config_get"),
    path("admin/config/update/", gamification_admin_views.gamification_config_update, name="admin_config_update"),
    path("admin/badges/", gamification_admin_views.badge_list, name="admin_badge_list"),
    path("admin/badges/create/", gamification_admin_views.badge_create, name="admin_badge_create"),
    path("admin/badges/<uuid:badge_id>/update/", gamification_admin_views.badge_update, name="admin_badge_update"),
    path("admin/badges/<uuid:badge_id>/delete/", gamification_admin_views.badge_delete, name="admin_badge_delete"),
    path("admin/leaderboard/", gamification_admin_views.admin_leaderboard, name="admin_leaderboard"),
    path("admin/xp-history/", gamification_admin_views.xp_history, name="admin_xp_history"),
    path("admin/xp-adjust/", gamification_admin_views.xp_adjust, name="admin_xp_adjust"),

    # Teacher endpoints
    path("summary/", gamification_teacher_views.teacher_xp_summary, name="teacher_summary"),
    path("leaderboard/", gamification_teacher_views.teacher_leaderboard, name="teacher_leaderboard"),
    path("badge-definitions/", gamification_teacher_views.teacher_badge_definitions, name="teacher_badge_definitions"),
    path("badges/", gamification_teacher_views.teacher_badges, name="teacher_badges"),
    path("xp-history/", gamification_teacher_views.teacher_xp_history, name="teacher_xp_history"),
    path("opt-out/", gamification_teacher_views.teacher_opt_out, name="teacher_opt_out"),
    path("opt-in/", gamification_teacher_views.teacher_opt_in, name="teacher_opt_in"),
    path("streak-freeze/", gamification_teacher_views.teacher_streak_freeze, name="teacher_streak_freeze"),
]
