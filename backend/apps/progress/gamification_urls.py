# apps/progress/gamification_urls.py

from django.urls import path

from . import challenge_views
from . import coin_views
from . import gamification_admin_views
from . import gamification_teacher_views
from . import league_views
from . import mastery_views

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
    path(
        "streak-freeze/inventory/",
        gamification_teacher_views.teacher_streak_freeze_inventory,
        name="teacher_streak_freeze_inventory",
    ),
    path(
        "streak-freeze/use/",
        gamification_teacher_views.teacher_streak_freeze_use,
        name="teacher_streak_freeze_use",
    ),
    path(
        "streak-freeze/weekend-mode/",
        gamification_teacher_views.teacher_streak_freeze_weekend_mode,
        name="teacher_streak_freeze_weekend_mode",
    ),
    path(
        "streak-freeze/ledger/",
        gamification_teacher_views.teacher_streak_freeze_ledger,
        name="teacher_streak_freeze_ledger",
    ),

    # --- TASK-016: Leagues ----------------------------------------------
    path("league/", league_views.teacher_current_league, name="teacher_current_league"),
    path("league/history/", league_views.teacher_league_history, name="teacher_league_history"),
    path("admin/leagues/", league_views.admin_leagues_overview, name="admin_leagues_overview"),

    # --- TASK-017: Challenges -------------------------------------------
    # Teacher endpoints
    path(
        "challenges/",
        challenge_views.teacher_active_challenges,
        name="teacher_active_challenges",
    ),
    path(
        "challenges/completed/",
        challenge_views.teacher_completed_challenges,
        name="teacher_completed_challenges",
    ),
    # Admin endpoints
    path(
        "admin/challenges/",
        challenge_views.admin_list_challenges,
        name="admin_list_challenges",
    ),
    path(
        "admin/challenges/create/",
        challenge_views.admin_create_challenge,
        name="admin_create_challenge",
    ),
    path(
        "admin/challenges/<uuid:challenge_id>/",
        challenge_views.admin_update_challenge,
        name="admin_update_challenge",
    ),
    path(
        "admin/challenges/<uuid:challenge_id>/delete/",
        challenge_views.admin_delete_challenge,
        name="admin_delete_challenge",
    ),

    # --- TASK-018: Mastery Points ---------------------------------------
    path(
        "mastery/",
        mastery_views.teacher_mastery_summary,
        name="teacher_mastery_summary",
    ),
    path(
        "mastery/history/",
        mastery_views.teacher_mastery_history,
        name="teacher_mastery_history",
    ),
    path(
        "admin/mastery/leaderboard/",
        mastery_views.admin_mastery_leaderboard,
        name="admin_mastery_leaderboard",
    ),

    # --- TASK-019: Puddle Coins -----------------------------------------
    path(
        "coins/",
        coin_views.teacher_coin_balance,
        name="teacher_coin_balance",
    ),
    path(
        "coins/history/",
        coin_views.teacher_coin_history,
        name="teacher_coin_history",
    ),
    path(
        "coins/purchase/streak-freeze/",
        coin_views.teacher_purchase_streak_freeze,
        name="teacher_purchase_streak_freeze",
    ),
]
