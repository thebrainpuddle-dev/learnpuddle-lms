import api from '../config/api';

// ── Admin types ──────────────────────────────────────────────────────

export interface GamificationConfig {
  id: string;
  xp_per_content_completion: number;
  xp_per_course_completion: number;
  xp_per_assignment_submission: number;
  xp_per_quiz_submission: number;
  xp_per_streak_day: number;
  streak_freeze_max: number;
  leaderboard_enabled: boolean;
  leaderboard_anonymize: boolean;
  opt_out_allowed: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BadgeDefinition {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  category: 'milestone' | 'streak' | 'completion' | 'skill' | 'special';
  criteria_type: 'xp_threshold' | 'courses_completed' | 'streak_days' | 'content_completed' | 'manual';
  criteria_value: number;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface BadgeCreateData {
  name: string;
  description?: string;
  icon?: string;
  color?: string;
  category: string;
  criteria_type: string;
  criteria_value: number;
  is_active?: boolean;
  sort_order?: number;
}

export interface XPTransaction {
  id: string;
  teacher: string;
  teacher_name: string;
  teacher_email: string;
  xp_amount: number;
  reason: string;
  description: string;
  reference_id: string | null;
  reference_type: string;
  created_at: string;
}

export interface XPAdjustData {
  teacher_id: string;
  xp_amount: number;
  reason?: string;
}

// ── Leaderboard types ────────────────────────────────────────────────

export interface LeaderboardEntry {
  rank: number;
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  total_xp: number;
  xp_period: number;
  level: number;
  level_name: string;
  badge_count: number;
  current_streak: number;
}

export interface LeaderboardResponse {
  period: string;
  entries: LeaderboardEntry[];
  snapshot_date: string;
}

// ── Teacher types ────────────────────────────────────────────────────

export interface TeacherXPSummary {
  total_xp: number;
  level: number;
  level_name: string;
  xp_this_month: number;
  xp_this_week: number;
  current_streak: number;
  longest_streak: number;
  last_xp_at: string | null;
  opted_out: boolean;
  badges: TeacherBadge[];
  /**
   * The **absolute total-XP threshold** at which the next level begins
   * (not the band width). For example, if Level 2 starts at 500 XP,
   * then a teacher at Level 1 with 300 XP will see `next_level_xp: 500`
   * and `xp_to_next_level: 200`.
   *
   * `null` when the teacher is already at the maximum level.
   *
   * Invariant: `total_xp + xp_to_next_level === next_level_xp` (when non-null).
   *
   * To render overall progress toward the next level, use:
   *   `(total_xp / next_level_xp) * 100`
   */
  next_level_xp: number | null;
  /** Remaining XP needed to reach `next_level_xp`. Zero when at max level. */
  xp_to_next_level: number;
}

export interface TeacherBadge {
  id: string;
  badge: BadgeDefinition;
  awarded_at: string;
  awarded_reason: string;
}

// ── Streak Freeze (TASK-015) ─────────────────────────────────────────

export interface StreakFreezeToken {
  id: string;
  source: string;
  earned_at: string;
  consumed_at: string | null;
  expires_at: string | null;
  reference_type: string;
  reference_id: string | null;
}

export interface StreakFreezeInventory {
  token_count: number;
  max_inventory: number;
  earn_every_n_days: number;
  expires_days: number;
  tokens: StreakFreezeToken[];
  weekend_mode_enabled: boolean;
  weekend_mode_available: boolean;
  grace_period_hours: number;
  in_grace_period: boolean;
  grace_period_ends_at: string | null;
  current_streak: number;
  longest_streak: number;
}

export interface StreakFreezeUseResponse {
  success: boolean;
  tokens_remaining: number;
  token_id?: string;
}

// ── Leagues (TASK-016) ───────────────────────────────────────────────

export interface LeagueMember {
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  weekly_xp: number;
  final_rank: number | null;
}

export interface CurrentLeague {
  tier_code: string | null;
  tier_name: string | null;
  tier_rank: number | null;
  week_start_date: string;
  members: LeagueMember[];
  promote_count: number;
  demote_count: number;
  cohort_size: number;
}

export interface LeagueHistoryEntry {
  week_start_date: string;
  tier_code: string;
  tier_name: string | null;
  tier_rank: number;
  final_rank: number | null;
  weekly_xp: number;
  outcome: 'promote' | 'hold' | 'demote' | '';
}

export interface LeagueHistoryResponse {
  history: LeagueHistoryEntry[];
}

// ── Challenges (TASK-017) ────────────────────────────────────────────

export type ChallengeType = 'daily' | 'weekly';
export type ChallengeGoalType =
  | 'complete_lessons'
  | 'finish_course'
  | 'submit_assignments'
  | 'earn_xp'
  | 'maintain_streak';

export interface TeacherChallenge {
  id: string;
  title: string;
  description: string;
  challenge_type: ChallengeType | string;
  goal_type: ChallengeGoalType | string;
  goal_target: number;
  goal_reference_id: string | null;
  start_at: string;
  end_at: string;
  reward_xp: number;
  reward_badge_id: string | null;
  progress_value: number;
  progress_percent: number;
  completed_at: string | null;
}

export interface ChallengeListResponse {
  results: TeacherChallenge[];
}

// ── API service ──────────────────────────────────────────────────────

export const gamificationService = {
  // ── Admin: Config ──────────────────────────────────────────────────
  admin: {
    async getConfig(): Promise<GamificationConfig> {
      const res = await api.get('/gamification/admin/config/');
      return res.data;
    },
    async updateConfig(data: Partial<GamificationConfig>): Promise<GamificationConfig> {
      const res = await api.patch('/gamification/admin/config/update/', data);
      return res.data;
    },

    // ── Admin: Badges ────────────────────────────────────────────────
    async listBadges(): Promise<BadgeDefinition[]> {
      const res = await api.get('/gamification/admin/badges/');
      return res.data.results ?? res.data;
    },
    async createBadge(data: BadgeCreateData): Promise<BadgeDefinition> {
      const res = await api.post('/gamification/admin/badges/create/', data);
      return res.data;
    },
    async updateBadge(id: string, data: Partial<BadgeCreateData>): Promise<BadgeDefinition> {
      const res = await api.patch(`/gamification/admin/badges/${id}/update/`, data);
      return res.data;
    },
    async deleteBadge(id: string): Promise<void> {
      await api.delete(`/gamification/admin/badges/${id}/delete/`);
    },

    // ── Admin: Leaderboard ───────────────────────────────────────────
    async getLeaderboard(period?: string): Promise<LeaderboardResponse> {
      const res = await api.get('/gamification/admin/leaderboard/', { params: { period: period ?? 'all_time' } });
      return res.data;
    },

    // ── Admin: XP History ────────────────────────────────────────────
    async getXPHistory(params?: { teacher_id?: string; reason?: string }): Promise<XPTransaction[]> {
      const res = await api.get('/gamification/admin/xp-history/', { params });
      return res.data.results ?? res.data;
    },

    // ── Admin: XP Adjust ─────────────────────────────────────────────
    async adjustXP(data: XPAdjustData): Promise<XPTransaction> {
      const res = await api.post('/gamification/admin/xp-adjust/', data);
      return res.data;
    },
  },

  // ── Teacher endpoints ──────────────────────────────────────────────
  async getSummary(): Promise<TeacherXPSummary> {
    const res = await api.get('/gamification/summary/');
    return res.data;
  },

  async getLeaderboard(period?: string): Promise<LeaderboardResponse> {
    const res = await api.get('/gamification/leaderboard/', { params: { period: period ?? 'weekly' } });
    return res.data;
  },

  async getBadgeDefinitions(): Promise<BadgeDefinition[]> {
    const res = await api.get('/gamification/badge-definitions/');
    return res.data.results ?? res.data;
  },

  async getMyBadges(): Promise<TeacherBadge[]> {
    const res = await api.get('/gamification/badges/');
    return res.data.results ?? res.data;
  },

  async getXPHistory(): Promise<XPTransaction[]> {
    const res = await api.get('/gamification/xp-history/');
    return res.data.results ?? res.data;
  },

  async optOut(): Promise<void> {
    await api.post('/gamification/opt-out/');
  },

  async optIn(): Promise<void> {
    await api.post('/gamification/opt-in/');
  },

  async useStreakFreeze(): Promise<{ success: boolean; freezes_remaining: number }> {
    const res = await api.post('/gamification/streak-freeze/');
    return res.data;
  },

  // ── Streak Freeze Inventory (TASK-015) ──────────────────────────────
  async getStreakFreezeInventory(): Promise<StreakFreezeInventory> {
    const res = await api.get('/gamification/streak-freeze/inventory/');
    return res.data;
  },

  async spendStreakFreezeToken(): Promise<StreakFreezeUseResponse> {
    const res = await api.post('/gamification/streak-freeze/use/');
    return res.data;
  },

  // ── Leagues (TASK-016) ──────────────────────────────────────────────
  async getCurrentLeague(): Promise<CurrentLeague> {
    const res = await api.get('/gamification/league/');
    return res.data;
  },

  async getLeagueHistory(): Promise<LeagueHistoryResponse> {
    const res = await api.get('/gamification/league/history/');
    return res.data;
  },

  // Alias used by LeaguesPage — returns the cohort members list.
  async getLeagueStandings(): Promise<CurrentLeague> {
    const res = await api.get('/gamification/league/');
    return res.data;
  },

  // ── Challenges (TASK-017) ───────────────────────────────────────────
  async getActiveChallenges(): Promise<TeacherChallenge[]> {
    const res = await api.get<ChallengeListResponse>('/gamification/challenges/');
    return res.data.results ?? [];
  },

  async getCompletedChallenges(): Promise<TeacherChallenge[]> {
    const res = await api.get<ChallengeListResponse>('/gamification/challenges/completed/');
    return res.data.results ?? [];
  },
};
